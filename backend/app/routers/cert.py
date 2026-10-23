"""证书库接口"""
from __future__ import annotations

import datetime as dt
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import audit, fail, get_current_user, ok, page_no
from ..models import Certificate, User
from ..security import decrypt_json, encrypt_json
from ..services import certutil

router = APIRouter(prefix="/api/cert", tags=["cert"])


def _fmt(dt) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""


def _serialize(r: Certificate) -> dict:
    days = (r.not_after - dt.datetime.now()).days if r.not_after else 0
    return {
        "id": r.id, "domains": r.domains.split(",") if r.domains else [],
        "domain": (r.domains or "").split(",")[0],
        "issuer": r.issuer or "", "status": r.status,
        "notBefore": _fmt(r.not_before), "notAfter": _fmt(r.not_after),
        "daysLeft": days,
        "createTime": _fmt(r.create_time),
        "pipelineId": r.pipeline_id,
    }


@router.get("/list")
def list_certs(page: int = Depends(page_no), size: int = Query(10), keyword: str = "",
               expiring: str = Query(""),
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(Certificate).filter(Certificate.user_id == user.id)
    if keyword:
        query = query.filter(or_(Certificate.domains.like(f"%{keyword}%"),
                                 Certificate.issuer.like(f"%{keyword}%")))
    if expiring not in ("", None):
        try:
            days = int(expiring)
        except (TypeError, ValueError):
            days = 0
        if days:
            deadline = dt.datetime.now() + dt.timedelta(days=days)
            query = query.filter(Certificate.not_after <= deadline)
    total = query.count()
    rows = query.order_by(Certificate.id.desc()).offset((page - 1) * size).limit(size).all()
    return ok({"records": [_serialize(r) for r in rows], "total": total,
               "current": page, "size": size})


class ImportParams(BaseModel):
    cert: str
    key: str
    remark: str = ""


@router.post("/import")
def import_cert(params: ImportParams,
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """把外部渠道拿到的证书导入证书库。

    只接受 PEM（证书 + 私钥），其余格式请先在本地转换 —— 转格式是纯客户端的事，
    传上来再解析反而更容易出错。导入后的证书和流水线签发的完全等价：
    能部署、能监控到期、能导出 pfx/jks。
    """
    crt = (params.cert or "").strip()
    key_pem = (params.key or "").strip()
    if "BEGIN CERTIFICATE" not in crt:
        return fail("证书内容不是 PEM 格式（缺少 -----BEGIN CERTIFICATE-----）")
    if "PRIVATE KEY" not in key_pem:
        return fail("私钥内容不是 PEM 格式（缺少 -----BEGIN ... PRIVATE KEY-----）")

    try:
        info = certutil.parse_cert(crt)
    except Exception as exc:  # noqa: BLE001
        return fail(f"证书解析失败：{exc}")

    # 证书与私钥必须是一对，否则要到部署/导出时才报错，不如入库前就拦下
    from cryptography.hazmat.primitives import serialization
    from cryptography import x509

    try:
        cert_pub = x509.load_pem_x509_certificate(crt.encode()).public_key()
        key_pub = certutil.load_key(key_pem).public_key()
    except Exception as exc:  # noqa: BLE001
        return fail(f"私钥解析失败：{exc}")

    def spki(pub) -> bytes:
        return pub.public_bytes(serialization.Encoding.DER,
                                serialization.PublicFormat.SubjectPublicKeyInfo)

    if spki(cert_pub) != spki(key_pub):
        return fail("证书与私钥不匹配，请确认粘贴的是同一份证书对应的私钥")

    row = Certificate(
        user_id=user.id, pipeline_id=0,
        domains=",".join(info.domains),
        cert_pem=crt, key_pem=encrypt_json(key_pem),
        issuer=info.issuer, not_before=info.not_before, not_after=info.not_after,
        status="valid",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    audit(db, user, "导入证书", f"{','.join(info.domains) or '未知域名'}"
                          f"{('（' + params.remark + '）') if params.remark else ''}")
    return ok({"id": row.id, "domains": info.domains,
               "notAfter": _fmt(info.not_after)})


@router.get("/{cert_id}")
def get_cert(cert_id: int, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    row = db.get(Certificate, cert_id)
    if not row or row.user_id != user.id:
        return fail("证书不存在")
    info = certutil.parse_cert(row.cert_pem)
    data = _serialize(row)
    data.update({
        "certPem": row.cert_pem,
        # 私钥同样明文下发，前端默认遮挡、点「显示」才展开
        "keyPem": decrypt_json(row.key_pem) if row.key_pem else "",
        "subject": info.domains,
        # 在线查看用的结构化详情（主题/签发者/SAN/序列号/指纹/公钥/链层数）
        "details": certutil.describe_cert(row.cert_pem),
    })
    return ok(data)


@router.get("/{cert_id}/download")
def download(cert_id: int, format: str = Query("pem"), password: str = "",
             args: str = Query("", description="PFX 兼容参数（Windows 老版本）"),
             type: str = Query("cert"), user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    row = db.get(Certificate, cert_id)
    if not row or row.user_id != user.id:
        return fail("证书不存在")
    key_pem = decrypt_json(row.key_pem) if row.key_pem else ""
    base = (row.domains or "cert").split(",")[0].replace("*", "wildcard")

    if type == "key":
        if format == "pem":
            return _file(key_pem.encode(), f"{base}.key", "application/x-pem-file")
        return fail("私钥仅支持 pem 格式")

    try:
        if format == "pem":
            content = row.cert_pem.encode()
            filename = f"{base}.crt"
            media = "application/x-pem-file"
        elif format == "der":
            content = certutil.cert_pem_to_der(row.cert_pem)
            filename = f"{base}.der"
            media = "application/pkix-cert"
        elif format == "pfx":
            content = certutil.cert_pem_to_pfx(row.cert_pem, key_pem, password, pfx_args=args)
            filename = f"{base}.pfx"
            media = "application/x-pkcs12"
        elif format == "p7b":
            content = certutil.cert_pem_to_p7b(row.cert_pem)
            filename = f"{base}.p7b"
            media = "application/x-pkcs7-certificates"
        elif format == "jks":
            content = certutil.cert_pem_to_jks(row.cert_pem, key_pem, password, alias=base)
            filename = f"{base}.jks"
            media = "application/octet-stream"
        elif format == "nginx":
            content = f"{row.cert_pem}\n{key_pem}".encode()
            filename = f"{base}-nginx.pem"
            media = "application/x-pem-file"
        else:
            return fail("不支持的格式，可选 pem/der/pfx/p7b/jks/nginx")
    except Exception as exc:
        return fail(f"导出失败：{exc}")
    return _file(content, filename, media)


def _file(content: bytes, filename: str, media: str):
    return StreamingResponse(io.BytesIO(content), media_type=media,
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.delete("/{cert_id}")
def delete_cert(cert_id: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    row = db.get(Certificate, cert_id)
    if not row or row.user_id != user.id:
        return fail("证书不存在")
    db.delete(row)
    db.commit()
    return ok(True)
