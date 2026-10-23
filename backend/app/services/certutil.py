"""证书工具：密钥生成、CSR、解析、格式转换"""
import datetime as dt
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.serialization import pkcs12, pkcs7
from cryptography.x509.oid import NameOID

from ..config import settings

try:
    from zoneinfo import ZoneInfo

    LOCAL_TZ = ZoneInfo(settings.TIMEZONE)
except Exception:  # pragma: no cover
    LOCAL_TZ = None


def to_local(value):
    """UTC 时间 -> 本地时间（naive）"""
    if value is None:
        return None
    if LOCAL_TZ is not None:
        return value.astimezone(LOCAL_TZ).replace(tzinfo=None)
    return value.astimezone().replace(tzinfo=None)


# ---------------------------------------------------------------- 密钥

def generate_key(key_type: str = "ec256"):
    if key_type == "rsa2048":
        return rsa.generate_private_key(public_exponent=65537, key_size=2048)
    if key_type == "rsa3072":
        return rsa.generate_private_key(public_exponent=65537, key_size=3072)
    if key_type == "rsa4096":
        return rsa.generate_private_key(public_exponent=65537, key_size=4096)
    if key_type == "ec384":
        return ec.generate_private_key(ec.SECP384R1())
    return ec.generate_private_key(ec.SECP256R1())


def key_to_pem(key) -> str:
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


def load_key(pem: str):
    return serialization.load_pem_private_key(pem.encode(), password=None)


# ---------------------------------------------------------------- CSR

def build_csr(key, domains: list[str]) -> bytes:
    """生成 DER 格式 CSR，主域名作为 CN，其余放入 SAN"""
    domains = [d.strip() for d in domains if d.strip()]
    cn = domains[0]
    builder = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    )
    san = x509.SubjectAlternativeName([x509.DNSName(d) for d in domains])
    builder = builder.add_extension(san, critical=False)
    csr = builder.sign(key, hashes.SHA256())
    return csr.public_bytes(serialization.Encoding.DER)


def csr_to_pem(der: bytes) -> str:
    return x509.load_der_x509_csr(der).public_bytes(serialization.Encoding.PEM).decode()


# ---------------------------------------------------------------- 自签证书

def self_signed(domains: list[str], days: int = 365, key_type: str = "ec256"):
    key = generate_key(key_type)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domains[0])])
    now = dt.datetime.now(dt.timezone.utc)
    san = x509.SubjectAlternativeName([x509.DNSName(d) for d in domains])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=days))
        .add_extension(san, critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    return cert, key


# ---------------------------------------------------------------- 解析

@dataclass
class CertInfo:
    domains: list[str] = field(default_factory=list)
    issuer: str = ""
    not_before: dt.datetime | None = None
    not_after: dt.datetime | None = None


def parse_cert(pem: str) -> CertInfo:
    cert = x509.load_pem_x509_certificate(pem.encode())
    info = CertInfo()
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        info.domains = san.value.get_values_for_type(x509.DNSName)
    except Exception:
        pass
    if not info.domains:
        try:
            info.domains = [cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value]
        except Exception:
            info.domains = []
    try:
        info.issuer = cert.issuer.get_attributes_for_oid(NameOID.ORGANIZATION_NAME)[0].value
    except Exception:
        try:
            info.issuer = cert.issuer.rfc4514_string()
        except Exception:
            info.issuer = ""
    info.not_before = to_local(cert.not_valid_before_utc)
    info.not_after = to_local(cert.not_valid_after_utc)
    return info


def _chain_blocks(pem: str) -> list[str]:
    """把 PEM 拆成单张证书（处理一张文件里带整条链的情况）"""
    import re

    return re.findall(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
                      pem or "", re.S)


def describe_chain(pem: str) -> list[dict]:
    """逐张解析证书链：站点证书在前，后面是中间证书（可能还有根）。

    证书库里存的是站点证书 + 中间证书，展示时必须分开列出来——
    用户排查「链不全」时要能看到到底带了哪几张。
    """
    items: list[dict] = []
    for index, block in enumerate(_chain_blocks(pem)):
        try:
            cert = x509.load_pem_x509_certificate(block.encode())
        except Exception:  # noqa: BLE001
            continue
        try:
            is_ca = cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
        except Exception:  # noqa: BLE001
            is_ca = False
        pub = cert.public_key()
        try:
            key_size = pub.key_size
        except Exception:  # noqa: BLE001
            key_size = 0
        if index == 0:
            kind = "站点证书"
        elif cert.subject == cert.issuer:
            kind = "根证书"
        else:
            kind = "中间证书"
        items.append({
            "index": index + 1,
            "kind": kind,
            "isCA": bool(is_ca),
            "subject": cert.subject.rfc4514_string(),
            "issuer": cert.issuer.rfc4514_string(),
            "notBefore": to_local(cert.not_valid_before_utc).strftime("%Y-%m-%d %H:%M:%S"),
            "notAfter": to_local(cert.not_valid_after_utc).strftime("%Y-%m-%d %H:%M:%S"),
            "signatureAlgorithm": cert.signature_algorithm_oid._name.replace("_", " "),
            "publicKey": f"{type(pub).__name__.replace('PublicKey', '').upper()} {key_size}".strip(),
            "pem": block.strip(),
        })
    return items


def describe_cert(pem: str) -> dict:
    """解析证书详情，供「证书库 → 在线查看」用。

    只做展示：主题/签发者/SAN/序列号指纹/签名算法/公钥、证书链层数。
    单个证书文件里可以带多段 PEM（站点证书 + 中间证书），这里一并数出来。
    """
    blocks = [block.strip() for block in pem.split("-----END CERTIFICATE-----") if "BEGIN CERTIFICATE" in block]
    cert = x509.load_pem_x509_certificate(pem.encode())

    def _name(name) -> str:
        try:
            return name.rfc4514_string()
        except Exception:  # noqa: BLE001
            return ""

    def _text(oid, default: str = "") -> str:
        try:
            return cert.subject.get_attributes_for_oid(oid)[0].value
        except Exception:  # noqa: BLE001
            return default

    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        san_list = san.value.get_values_for_type(x509.DNSName)
    except Exception:  # noqa: BLE001
        san_list = []

    pub = cert.public_key()
    try:
        key_type = f"{type(pub).__name__.replace('PublicKey', '').upper()} {pub.key_size}"
    except Exception:  # noqa: BLE001
        key_type = type(pub).__name__

    fingerprint = cert.fingerprint(hashes.SHA256()).hex()
    fingerprint = ":".join(fingerprint[i:i + 2] for i in range(0, len(fingerprint), 2))

    return {
        "subject": _name(cert.subject),
        "subjectCommonName": _text(NameOID.COMMON_NAME),
        "organization": _text(NameOID.ORGANIZATION_NAME),
        "issuer": _name(cert.issuer),
        "issuerOrganization": (
            cert.issuer.get_attributes_for_oid(NameOID.ORGANIZATION_NAME)[0].value
            if cert.issuer.get_attributes_for_oid(NameOID.ORGANIZATION_NAME) else ""),
        "san": san_list,
        "serialNumber": format(cert.serial_number, "X"),
        "fingerprintSha256": fingerprint,
        "signatureAlgorithm": cert.signature_algorithm_oid._name.replace("_", " "),
        "publicKey": key_type,
        "notBefore": to_local(cert.not_valid_before_utc).strftime("%Y-%m-%d %H:%M:%S"),
        "notAfter": to_local(cert.not_valid_after_utc).strftime("%Y-%m-%d %H:%M:%S"),
        "chainCount": max(1, len(blocks)),
        "isSelfSigned": cert.subject == cert.issuer,
        # 站点证书 + 中间证书逐张列出（证书库要能看链）
        "chain": describe_chain(pem),
    }


def cert_pem_to_der(pem: str) -> bytes:
    return x509.load_pem_x509_certificate(pem.encode()).public_bytes(serialization.Encoding.DER)


_OPENSSL: str | None = None
_OPENSSL_PROBED = False


def find_openssl() -> str | None:
    """找 openssl 可执行文件（PATH 里没有就试常见安装位置）。

    PFX 的「Windows Server 2008 / 2016 兼容档」需要指定 -macalg / -keypbe / -certpbe，
    cryptography 库不支持这些老算法，只能走命令行。
    """
    global _OPENSSL, _OPENSSL_PROBED
    if _OPENSSL_PROBED:
        return _OPENSSL
    _OPENSSL_PROBED = True
    candidates = ["openssl"]
    if os.name == "nt":
        candidates += [
            r"C:\Program Files\Git\usr\bin\openssl.exe",
            r"C:\Program Files\Git\mingw64\bin\openssl.exe",
            r"C:\Program Files\OpenSSL-Win64\bin\openssl.exe",
            r"C:\Program Files (x86)\OpenSSL-Win32\bin\openssl.exe",
            r"C:\ProgramData\chocolatey\bin\openssl.exe",
        ]
    for item in candidates:
        try:
            result = subprocess.run([item, "version"], capture_output=True, timeout=10)
            if result.returncode == 0:
                _OPENSSL = item
                return _OPENSSL
        except (OSError, subprocess.SubprocessError):
            continue
    _OPENSSL = None
    return None


def cert_pem_to_pfx(pem: str, key_pem: str, password: str = "", pfx_args: str = "") -> bytes:
    """将证书 + 私钥打包为 PFX（PKCS#12），用于 IIS / Java 等场景。

    pfx_args：Windows 老版本兼容档（对应 openssl 的 -macalg / -keypbe / -certpbe）。
    填了就优先走 openssl 命令行；没有 openssl 或参数为空时用 cryptography 的默认实现。
    """
    if pfx_args and find_openssl():
        try:
            return _pfx_via_openssl(pem, key_pem, password, pfx_args)
        except Exception as exc:  # noqa: BLE001 - 命令行失败不影响主流程，退回默认实现
            print(f"openssl 生成 PFX 失败，改用默认参数：{exc}", file=sys.stderr)
    certs = x509.load_pem_x509_certificates(pem.encode())
    cert, chain = certs[0], certs[1:]
    key = load_key(key_pem)
    enc = (
        serialization.BestAvailableEncryption(password.encode())
        if password
        else serialization.NoEncryption()
    )
    return pkcs12.serialize_key_and_certificates(
        name=(cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value.encode()
              if cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME) else b"cert"),
        key=key,
        cert=cert,
        cas=chain or None,
        encryption_algorithm=enc,
    )


def _pfx_via_openssl(pem: str, key_pem: str, password: str, pfx_args: str) -> bytes:
    """用 openssl 命令行导出 PFX（支持老版本 Windows 的兼容参数）。"""
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        cert_file = folder / "cert.pem"
        key_file = folder / "key.pem"
        out_file = folder / "out.pfx"
        cert_file.write_text(pem, encoding="utf-8")
        key_file.write_text(key_pem, encoding="utf-8")
        cmd = [
            find_openssl() or "openssl", "pkcs12", "-export",
            "-in", str(cert_file), "-inkey", str(key_file),
            "-out", str(out_file), "-passout", f"pass:{password}",
        ]
        cmd += [item for item in str(pfx_args).split() if item]
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        if result.returncode != 0 or not out_file.exists():
            message = (result.stderr or b"").decode("utf-8", "replace")[:300]
            raise RuntimeError(message or "openssl pkcs12 失败")
        return out_file.read_bytes()


def cert_pem_to_p7b(pem: str) -> bytes:
    """导出 PKCS#7（P7B）证书链"""
    certs = x509.load_pem_x509_certificates(pem.encode())
    return pkcs7.serialize_certificates(certs, serialization.Encoding.DER)


# ---------------------------------------------------------------- JKS

_KEYTOOL: str | None = None
_KEYTOOL_PROBED = False


def find_keytool() -> str | None:
    """定位 keytool。

    Windows 的 javapath 目录里只有 java.exe / javac.exe，没有 keytool，
    所以不能只依赖 PATH，需要用 java.home 反推 JDK 安装目录。
    """
    global _KEYTOOL, _KEYTOOL_PROBED
    if _KEYTOOL_PROBED:
        return _KEYTOOL
    _KEYTOOL_PROBED = True

    import glob
    import shutil
    import subprocess

    exe = "keytool.exe" if os.name == "nt" else "keytool"

    found = shutil.which("keytool")
    if found:
        _KEYTOOL = found
        return _KEYTOOL

    candidates: list[str] = []
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        candidates.append(os.path.join(java_home, "bin", exe))

    # 用 java -XshowSettings 拿到真实 JDK 目录
    java = shutil.which("java")
    if java:
        try:
            out = subprocess.run([java, "-XshowSettings:properties", "-version"],
                                 capture_output=True, text=True, timeout=15)
            for line in (out.stdout + out.stderr).splitlines():
                if "java.home" in line and "=" in line:
                    home = line.split("=", 1)[1].strip()
                    candidates.append(os.path.join(home, "bin", exe))
                    break
        except Exception:
            pass

    for pattern in (
        r"C:\Program Files\Java\*\bin\keytool.exe",
        r"C:\Program Files\Eclipse Adoptium\*\bin\keytool.exe",
        r"C:\Program Files\Amazon Corretto\*\bin\keytool.exe",
        r"C:\Program Files\Zulu\*\bin\keytool.exe",
        "/usr/lib/jvm/*/bin/keytool",
        "/opt/java/*/bin/keytool",
    ):
        candidates.extend(glob.glob(pattern))

    for path in candidates:
        if path and os.path.isfile(path):
            _KEYTOOL = path
            return _KEYTOOL
    return None


def cert_pem_to_jks(pem: str, key_pem: str, password: str = "",
                    alias: str = "") -> bytes:
    """导出 JKS（Java KeyStore），供 Tomcat / WebLogic / 旧版 Java 应用使用。

    先由 cryptography 生成 PKCS#12，再调用 JDK 的 keytool 转成 JKS。
    JKS 是 Sun 私有格式，无纯 Python 写入实现，因此依赖本机 JDK。
    """
    import subprocess
    import tempfile

    keytool = find_keytool()
    if not keytool:
        raise RuntimeError(
            "未检测到 JDK（keytool）。JKS 是 Java 私有格式，需要安装 JDK 后重试；"
            "若目标环境支持，可改用 PFX(PKCS#12) 格式，Java 同样可以直接加载。"
        )

    pwd = password or "changeit"
    if len(pwd) < 6:
        # JKS 格式硬性要求 storepass / keypass 至少 6 位，短密码 keytool 会直接拒绝
        raise RuntimeError("JKS 密钥库密码至少需要 6 位字符（Java KeyStore 的格式限制）")
    with tempfile.TemporaryDirectory(prefix="certd-jks-") as td:
        src = os.path.join(td, "src.p12")
        dest = os.path.join(td, "out.jks")
        with open(src, "wb") as fh:
            fh.write(cert_pem_to_pfx(pem, key_pem, pwd))

        cmd = [
            keytool, "-importkeystore",
            "-srckeystore", src, "-srcstoretype", "PKCS12",
            "-srcstorepass", pwd,
            "-destkeystore", dest, "-deststoretype", "JKS",
            "-deststorepass", pwd, "-destkeypass", pwd,
            "-noprompt",
        ]
        if alias:
            # PKCS#12 里的别名就是证书 CN，指定源别名后才能改名为域名
            cmd += ["-srcalias", _pfx_alias(pem), "-destalias", alias]

        proc = subprocess.run(cmd, capture_output=True, timeout=60)
        if proc.returncode != 0 or not os.path.exists(dest):
            # keytool 在中文 Windows 控制台按 GBK 输出，直接按 UTF-8 解码会变成乱码
            raw_bytes = proc.stderr or proc.stdout or b""
            for enc in ("utf-8", "gbk"):
                try:
                    raw = raw_bytes.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raw = raw_bytes.decode("utf-8", "replace")
            detail = [ln.strip() for ln in raw.strip().splitlines() if ln.strip()]
            raise RuntimeError("keytool 转换失败：" + (" / ".join(detail[-2:]) or "未知错误"))
        with open(dest, "rb") as fh:
            return fh.read()


def _pfx_alias(pem: str) -> str:
    """取证书 CN，作为 PKCS#12 内的别名（与 cert_pem_to_pfx 保持一致）"""
    cert = x509.load_pem_x509_certificates(pem.encode())[0]
    attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    return attrs[0].value if attrs else "cert"


# ---------------------------------------------------------------- 域名

def split_domains(text: str | list) -> list[str]:
    if isinstance(text, list):
        raw = text
    else:
        raw = re.split(r"[,\s;，、]+", text or "")
    result, seen = [], set()
    for d in raw:
        d = (d or "").strip().lower()
        if d and d not in seen:
            seen.add(d)
            result.append(d)
    return result


def root_domain(domain: str) -> str:
    """获取用于 DNS 解析的主域名（不依赖公共后缀列表，覆盖常见两级后缀）"""
    domain = domain.lstrip("*.").strip(".")
    parts = domain.split(".")
    if len(parts) <= 2:
        return domain
    two_level = {"com.cn", "net.cn", "org.cn", "gov.cn", "edu.cn", "co.uk", "org.uk",
                 "com.hk", "com.tw", "co.jp", "com.au", "com.sg"}
    if ".".join(parts[-2:]) in two_level:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def acme_record_name(domain: str, root: str | None = None) -> str:
    """_acme-challenge 记录的主机记录（相对主域名）"""
    return txt_record_name(domain, root=root)


def txt_record_name(domain: str, prefix: str = "_acme-challenge",
                    root: str | None = None) -> str:
    """任意前缀的 TXT 主机记录（相对主域名）。

    火山引擎等云厂商的 DCV 记录前缀不是 _acme-challenge，
    需要能替换前缀，所以把这段逻辑抽出来复用。

    root 用于「子域名托管」：托管域名本身就是独立 zone，
    不能再按 root_domain() 截到上一级。
    """
    domain = domain.lstrip("*.")
    root = (root or root_domain(domain)).strip(".")
    if domain == root:
        return prefix
    sub = domain[: -(len(root) + 1)]
    return f"{prefix}.{sub}"
