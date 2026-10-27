"""授权（凭据）管理接口"""
from __future__ import annotations

import json

import httpx
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import audit, fail, get_current_user, ok, page_no
from ..models import Access, User
from ..plugins import ACCESS_CATEGORIES, ACCESS_TYPES
from ..services import dns as dns_service
from ..services import net
from ..security import MASK, decrypt_json, encrypt_json, merge_secret

router = APIRouter(prefix="/api/access", tags=["access"])


def _fmt(dt) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""


_CATEGORY_KEYS = {c["key"] for c in ACCESS_CATEGORIES}


def _filter_category(query, category: str):
    """按 category 过滤授权。

    传进来的可能是存库的分类（cloud / host / panel / cert），也可能是「能力」
    （dns）：阿里云这类账号既能部署 CDN 又能改 DNS，库里分类只有一个，
    所以按能力过滤时改成按类型集合过滤，否则域名页的 DNS 授权下拉永远是空的。
    """
    if not category:
        return query
    if category in _CATEGORY_KEYS:
        return query.filter(Access.category == category)
    types = [k for k, v in ACCESS_TYPES.items() if category in (v.get("capabilities") or [])]
    if not types:
        return query.filter(Access.category == category)
    return query.filter(Access.type.in_(types))


def _filter_types(query, types: str):
    """按「授权类型」精确过滤（逗号分隔）。

    只按分类过滤会把同分类的其它厂商塞进来：宝塔 / 1Panel / 群晖 / 威联通 / PVE / NPM /
    雷池 全是 panel 分类，前端下拉必须靠类型过滤，否则「部署到群晖」能看到宝塔授权。
    """
    wanted = [item.strip() for item in (types or "").split(",") if item.strip()]
    if not wanted:
        return query
    return query.filter(Access.type.in_(wanted))


def _meta(atype: str) -> dict:
    return ACCESS_TYPES.get(atype) or {}


def _secret_keys(atype: str) -> list[str]:
    """敏感字段由插件元数据声明：component == "password" 的就是密钥。

    以前是按字段名猜测（含 secret/key/token 就打码），结果腾讯云的 secretId、
    阿里云的 accessKeyId 也被打码，用户打开编辑框只看到一片 ******，
    分不清「没保存」还是「被隐藏」。
    """
    return [item["key"] for item in _meta(atype).get("inputs") or []
            if item.get("component") == "password"]


def _clean_config(config: dict) -> dict:
    """去掉字符串首尾空白：粘贴密钥时最常见的错误就是多带了空格或换行。"""
    return {k: (v.strip() if isinstance(v, str) else v) for k, v in (config or {}).items()}


def _match_show_when(show_when, config: dict) -> bool:
    """字段的 showWhen 条件是否成立；不成立的字段不该校验必填。"""
    if not show_when:
        return True
    current = (config or {}).get(show_when.get("key"))
    values = show_when.get("values")
    if isinstance(values, list):
        return current in values
    if "value" in show_when:
        return current == show_when.get("value")
    return True


def _missing_required(atype: str, config: dict) -> str:
    """返回第一个未填的必填字段标题（没有缺失返回空串）。

    校验的是「最终要写库的配置」：新增时是提交值，编辑时是合并过旧值的结果，
    所以这里一律严格校验——密钥留空且库里也没有旧值，就该报错而不是存个空授权。
    只校验当前可见的字段：被 showWhen 隐藏的项（如「私钥认证」才需要的私钥）
    不该拦住另一种认证方式。
    """
    for item in _meta(atype).get("inputs") or []:
        if not item.get("required"):
            continue
        if not _match_show_when(item.get("showWhen"), config):
            continue
        value = config.get(item["key"])
        if value in (None, "") or (isinstance(value, list) and not value):
            return item.get("title") or item["key"]
    return ""


def _serialize(row: Access) -> dict:
    """授权信息一律返回明文。

    早期版本对密码类字段打码成 ******，结果编辑框里看不到真实值，
    用户以为「信息没保存」，改一下再保存还会把密钥写坏。
    现在明文下发给前端，由密码框的「小眼睛」决定显示还是隐藏。
    """
    cfg = decrypt_json(row.config)
    return {
        "id": row.id, "category": row.category, "type": row.type, "name": row.name,
        "remark": row.remark or "",
        "typeName": _meta(row.type).get("name", row.type),
        "config": cfg,
        "secretKeys": _secret_keys(row.type),
        "createTime": _fmt(row.create_time),
    }


@router.get("/list")
def list_access(page: int = Depends(page_no), size: int = Query(20), category: str = "",
                keyword: str = "", type: str = "", types: str = "",
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(Access).filter(Access.user_id == user.id)
    query = _filter_category(query, category)
    query = _filter_types(query, types)
    if type:
        query = query.filter(Access.type == type)
    keyword = (keyword or "").strip()
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(or_(Access.name.like(like), Access.remark.like(like)))
    total = query.count()
    rows = query.order_by(Access.id.desc()).offset((page - 1) * size).limit(size).all()
    return ok({"records": [_serialize(r) for r in rows], "total": total,
               "current": page, "size": size})


@router.get("/options")
def options(category: str = "", type: str = "", types: str = "",
            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(Access).filter(Access.user_id == user.id)
    query = _filter_category(query, category)
    query = _filter_types(query, types)
    if type:
        query = query.filter(Access.type == type)
    rows = query.order_by(Access.id.desc()).all()
    return ok([{
        "id": r.id, "name": r.name, "type": r.type, "category": r.category,
        "typeName": ACCESS_TYPES.get(r.type, {}).get("name", r.type),
        # 一个授权可能有多个用途（例如阿里云账号既能部署 CDN 也能改 DNS），
        # 前端据此把同一条记录放进多个下拉
        "capabilities": ACCESS_TYPES.get(r.type, {}).get("capabilities") or [r.category],
    } for r in rows])


class AccessParams(BaseModel):
    category: str = "dns"
    type: str
    name: str
    config: dict = {}
    remark: str = ""


@router.post("")
def create_access(params: AccessParams, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    if params.type not in ACCESS_TYPES:
        return fail("不支持的授权类型")
    name = (params.name or "").strip()
    if not name:
        return fail("请填写授权名称")
    config = _clean_config(params.config)
    missing = _missing_required(params.type, config)
    if missing:
        return fail(f"请填写「{missing}」")
    row = Access(user_id=user.id, category=params.category, type=params.type,
                 name=name, config=encrypt_json(config), remark=params.remark)
    db.add(row)
    db.commit()
    db.refresh(row)
    audit(db, user, "新增授权", f"{params.name}({params.type})")
    return ok({"id": row.id})


@router.put("/{access_id}")
def update_access(access_id: int, params: AccessParams,
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(Access, access_id)
    if not row or row.user_id != user.id:
        return fail("授权不存在")
    name = (params.name or "").strip()
    if not name:
        return fail("请填写授权名称")
    if params.type not in ACCESS_TYPES:
        return fail("不支持的授权类型")

    old = decrypt_json(row.config)
    # 编辑时密码框通常留空或显示打码占位符，两者都表示「不改」，先合并再校验
    merged = merge_secret(old, _clean_config(params.config), _secret_keys(params.type))
    missing = _missing_required(params.type, merged)
    if missing:
        return fail(f"请填写「{missing}」")

    row.name = name
    row.type = params.type
    row.category = params.category
    row.remark = params.remark
    row.config = encrypt_json(merged)
    db.commit()
    audit(db, user, "修改授权", name)
    return ok(True)


@router.delete("/{access_id}")
def delete_access(access_id: int, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    row = db.get(Access, access_id)
    if not row or row.user_id != user.id:
        return fail("授权不存在")
    db.delete(row)
    db.commit()
    audit(db, user, "删除授权", row.name)
    return ok(True)


@router.get("/{access_id}/domains")
def access_domains(access_id: int, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """嗅探该 DNS 授权下的主域名，供「申请证书」自动带入。"""
    row = db.get(Access, access_id)
    if not row or row.user_id != user.id:
        return fail("授权不存在")
    cfg = decrypt_json(row.config)
    if row.type not in dns_service.PROVIDERS:
        return fail(f"{_meta(row.type).get('name', row.type)} 不是 DNS 服务商授权，"
                    "无法嗅探域名（请选择 DNS 解析类授权）")
    try:
        domains = dns_service.list_domains(row.type, cfg)
    except Exception as exc:  # noqa: BLE001
        return fail(str(exc))
    # 泛域名也一起给出来：多数用户要的就是 *.example.com
    expanded = []
    for domain in domains:
        expanded.append(domain)
        expanded.append(f"*.{domain}")
    return ok({"type": row.type, "domains": domains, "patterns": expanded})


class SynologyDeviceIdParams(BaseModel):
    """获取群晖设备ID 的入参。

    config 收前端表单里的当前值（地址 / 账号 / 密码 / 设备名 / 忽略证书校验），
    这样「还没保存的新授权」也能先取设备ID；accessId 非空时用库里的配置兜底
    （编辑已有授权时密码框是空的，那次从库里补），成功后写回该授权。
    """

    config: dict = {}
    otpCode: str = ""
    accessId: int = 0


@router.post("/synology/device-id")
def synology_device_id(params: SynologyDeviceIdParams,
                       user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    """群晖「获取设备ID」：输一次 6 位双重认证验证码，换一个长期免验证码的受信设备令牌。

    对应 certd 授权里的 deviceId；前置条件是 DSM 勾选了
    「允许网页浏览器的用户通过信任设备来跳过双重验证」。
    """
    from ..services import deploy as deploy_service

    cfg = _clean_config(params.config)
    if params.accessId:
        row = db.get(Access, int(params.accessId))
        if row and row.user_id == user.id and row.type == "synology":
            stored = decrypt_json(row.config) or {}
            # 表单里留空 / 打码的项（尤其是密码）用库里的值兜底
            for key, value in stored.items():
                if cfg.get(key) in (None, "", MASK):
                    cfg[key] = value

    if not str(cfg.get("url") or "").strip():
        return fail("请先填写 DSM 地址（例如 https://192.168.1.10:5001）")
    if not str(cfg.get("username") or "").strip():
        return fail("请先填写群晖账号")

    try:
        result = deploy_service.synology_fetch_device_id(cfg, params.otpCode)
    except Exception as exc:  # noqa: BLE001 - 业务异常统一转成一句中文
        return fail(str(exc))

    device_id = str(result.get("deviceId") or "").strip()
    if params.accessId:
        # 顺手写回授权，免得用户还要手动粘贴一遍
        deploy_service._persist_access_field(params.accessId, "deviceId", device_id)
        deploy_service._persist_access_field(params.accessId, "deviceName",
                                             result.get("deviceName") or "")
    audit(db, user, "获取群晖设备ID", f"授权 {params.accessId or '-'}")
    return ok({"deviceId": device_id, "deviceName": result.get("deviceName") or ""})


@router.post("/{access_id}/test")
def test_access(access_id: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    row = db.get(Access, access_id)
    if not row or row.user_id != user.id:
        return fail("授权不存在")
    cfg = decrypt_json(row.config)
    try:
        # 带上 accessId：群晖这类会在登录成功后把「设备令牌 / 识别到的版本」写回授权配置，
        # 没有它就只在跑流水线时才回填，点「测试」等于白测。
        cfg = dict(cfg or {})
        cfg["accessId"] = row.id
        # 传当前账号的邮箱：EAB 校验要在 CA 侧注册账户，部分 CA 要求有联系人
        if row.type == "eab":
            # EAB（尤其 FreeSSL / LiteSSL 的一次性 EAB）：把注册出来的账户写回授权，
            # 之后流水线与再次「测试」都复用，不再消耗 EAB
            account = _test_eab(cfg, (user.email or "").strip())
            if account.get("accountKeyPem"):
                merged = dict(cfg)
                merged["acmeAccountKey"] = account["accountKeyPem"]
                merged["accountUrl"] = account.get("accountUrl") or ""
                row.config = encrypt_json(merged)
                db.commit()
            return ok({"success": True, "message": account.get("message") or "EAB 凭据可用"})
        message = _do_test(row.type, cfg, (user.email or "").strip())
        return ok({"success": True, "message": message})
    except Exception as exc:
        return ok({"success": False, "message": str(exc)})


def _test_aliyun(cfg: dict) -> str:
    """阿里云授权连通性测试。

    先用云解析的 DescribeDomains 探活（顺带报出账号下的域名数量）；
    如果这个 AK 没有 DNS 读权限，退一步用 STS 只校验身份，
    避免「AK 完全正常、只是没开 DNS 权限」被误判成鉴权失败。
    """
    from ..services.aliyun import AliyunError, call

    try:
        data = call(cfg, "https://alidns.aliyuncs.com/", "DescribeDomains", "2015-01-09",
                    {"PageSize": 1})
    except AliyunError as exc:
        message = str(exc)
        if not any(k in message.lower() for k in ("forbidden", "nopermission",
                                                 "notauthorized", "no permission")):
            raise RuntimeError(message) from exc
        from ..services.aliyun import test_identity

        who = test_identity(cfg)
        return f"阿里云 {who}，但当前 AK 没有云解析 DNS 的读权限：{message}"
    return f"阿里云连接成功，域名数量 {data.get('TotalCount', 0)}"


def _test_tencent(cfg: dict) -> str:
    from ..services.tencent_ssl import test_connection

    return test_connection(cfg)


def _test_k8s(cfg: dict) -> str:
    """K8s：拉一个命名空间的 Secret 列表，能通说明地址、Token、CA 都对。"""
    import ssl

    base = (cfg.get("apiServer") or cfg.get("apiUrl") or "").rstrip("/")
    if not base:
        raise RuntimeError("未配置 API Server 地址")
    verify = False if cfg.get("insecure", True) else True
    if not cfg.get("insecure", True) and cfg.get("caCert"):
        verify = ssl.create_default_context(cadata=str(cfg["caCert"]))
    namespace = cfg.get("namespace") or "default"
    resp = net.get(f"{base}/api/v1/namespaces/{namespace}/secrets",
                   params={"limit": 1}, timeout=15, verify=verify, trust_env=False,
                   headers={"Authorization": f"Bearer {cfg.get('token') or ''}"})
    if resp.status_code >= 400:
        try:
            data = resp.json() or {}
        except ValueError:
            data = {}
        raise RuntimeError(f"Kubernetes 返回 {resp.status_code}："
                           f"{data.get('message') or resp.text[:150]}")
    total = len((resp.json() or {}).get("items") or [])
    return f"Kubernetes 连接成功（命名空间 {namespace} 可读，示例返回 {total} 条 Secret）"


def _test_cdn_provider(atype: str, cfg: dict) -> str:
    """国内 CDN 服务商：能列出域名 / 站点就说明授权可用。"""
    from ..services import deploy_cn

    if atype == "ctyun":
        domains = deploy_cn.ctyun_domains(cfg, cfg.get("productCode") or "008")
        return f"天翼云连接成功，账号下共 {len(domains)} 个加速域名"
    if atype == "dogecloud":
        domains = deploy_cn.doge_domains(cfg)
        return f"多吉云连接成功，账号下共 {len(domains)} 个 CDN 域名"
    if atype == "kuocaicdn":
        deploy_cn.kuocai_login(cfg)
        domains = deploy_cn.kuocai_domains(cfg)
        return f"括彩云连接成功，账号下共 {len(domains)} 个站点域名"
    if atype == "yidun":
        sites = deploy_cn.yidun_sites(cfg)
        return f"易盾连接成功，账号下共 {len(sites)} 个站点"
    if atype == "jdcloud":
        domains = deploy_cn.jdcloud_cdn_domains(cfg)
        return f"京东云连接成功，账号下共 {len(domains)} 个加速域名"
    if atype == "woai":
        deploy_cn.woai_login(cfg)
        return "我爱云登录成功"
    raise RuntimeError("该类型暂不支持在线校验")


#: EAB 测试用的 ACME 目录：只支持真正需要 EAB 且能自助拿凭据的 CA
_EAB_DIRECTORIES = {
    "google": "https://dv.acme-v02.api.pki.goog/directory",
    "sslcom": "https://acme.ssl.com/sslcom-dv-rsa",
    # FreeSSL.cn 的 ACME v2（LiteSSL，TrustAsia 签发），目录地址是 acme.litessl.com
    "litessl": "https://acme.litessl.com/acme/v2/directory",
}


def _test_eab(cfg: dict, email: str = "") -> dict:
    """EAB 凭据：去 CA 真注册（或复用）一个账户，能过说明 Key 还没过期。

    Google 的 EAB key 创建后 7 天失效，这是「申请失败」最常见的原因，
    所以这里不做本地格式校验，直接问 CA。

    **FreeSSL / LiteSSL 的 EAB 是一次性的**：注册成功一次就作废，所以：
      · 授权里已经存了账户私钥 → 只确认账户还在，不再提交 EAB；
      · 首次注册成功后，把账户私钥 / 账户 URL 返回给调用方，由它写回授权，
        之后流水线与「测试」都复用这个账户。
    """
    from ..services.acme import register_eab_account

    provider = str(cfg.get("provider") or "google").strip()
    directory = _EAB_DIRECTORIES.get(provider, "")
    if not directory:
        raise RuntimeError(
            "请先把「所属 CA」选成 Google Trust Services / SSL.com / FreeSSL（LiteSSL）再测试："
            "只有这几家能在线校验 EAB 凭据")
    return register_eab_account(cfg.get("kid"), cfg.get("hmacKey"), directory,
                                email=email,
                                account_key_pem=str(cfg.get("acmeAccountKey") or "").strip())


def _do_test(atype: str, cfg: dict, email: str = "") -> str:
    if atype == "eab":
        return _test_eab(cfg, email)

    if atype == "ssh":
        from ..services.deploy import _ssh_client

        client = _ssh_client(cfg)
        try:
            _in, out, _err = client.exec_command("echo ok")
            out.read()
            return "SSH 连接成功"
        finally:
            client.close()

    if atype == "aliyun":
        return _test_aliyun(cfg)

    if atype == "tencentcloud":
        return _test_tencent(cfg)

    if atype == "k8s":
        return _test_k8s(cfg)

    if atype == "safeline":
        from ..services import deploy_more

        nodes = deploy_more.safeline_certs(cfg)
        return f"雷池连接成功，账号下共 {len(nodes)} 张证书"

    if atype == "upyun":
        from ..services import deploy_more

        domains = deploy_more.upyun_domains(cfg)
        return f"又拍云连接成功，账号下共 {len(domains)} 个加速域名"

    if atype in ("ctyun", "dogecloud", "kuocaicdn", "yidun", "jdcloud", "woai"):
        return _test_cdn_provider(atype, cfg)

    if atype == "cloudflare":
        resp = net.get("https://api.cloudflare.com/client/v4/zones",
                         headers={"Authorization": f"Bearer {cfg.get('apiToken','')}"},
                         params={"per_page": 1}, timeout=15)
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(f"Cloudflare 校验失败：{data.get('errors')}")
        return "Cloudflare 连接成功"

    if atype == "volcengine":
        from ..services import volcengine

        return volcengine.test_connection(cfg)

    if atype == "baiducloud":
        from ..services import baiducloud

        return baiducloud.test_connection(cfg)

    if atype == "trustasia":
        from ..services import trustasia

        return trustasia.test_connection(cfg)

    if atype in ("baota", "1panel"):
        url = (cfg.get("url") or "").rstrip("/")
        resp = net.get(url, timeout=10, verify=False)
        return f"面板可访问（HTTP {resp.status_code}）"

    if atype == "synology":
        from ..services.deploy import synology_probe

        return synology_probe(cfg)

    if atype in ("qnap", "proxmox"):
        url = (cfg.get("url") or "").rstrip("/")
        if not url:
            raise RuntimeError("未配置面板地址")
        try:
            resp = net.get(url, timeout=10, verify=not cfg.get("insecure", True))
            return f"面板可访问（HTTP {resp.status_code}），凭据将在部署时校验"
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"无法连接 {url}：{exc}")

    required = [k for k, v in cfg.items() if v]
    if not required:
        raise RuntimeError("配置为空")
    return "配置已保存（该类型暂不支持在线校验）"