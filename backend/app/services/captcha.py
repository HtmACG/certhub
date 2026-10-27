"""图形验证码
=========================================================
登录失败若干次后要求输入图形验证码，挡住脚本撞库。

实现要点：
- 图片是**服务端现画的 SVG**，不引 Pillow / captcha 之类依赖，离线可用；
- 校验用 **HMAC 签名**，不存会话、不落库 —— 令牌里带过期时间，
  服务端只按「用户提交的字符 + 过期时间」重算签名比对，天然支持多进程 / 重启；
- 令牌一次性由前端在提交后丢弃（后端不记录已用过的，重复提交同一张图不拦，
  反正 5 分钟就过期，且失败次数仍受 loginFailLimit 约束）。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import random
import time

from ..config import settings

#: 去掉了 0/O/1/I/l 这类肉眼易混的字符
_CHARSET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
_CODE_LEN = 4
#: 有效期（秒）
TTL = 300


def _sign(code: str, exp: int) -> str:
    raw = f"{code.upper()}.{exp}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), raw, hashlib.sha256).hexdigest()[:32]


def _svg(code: str) -> str:
    """画一张 108×40 的验证码：随机倾斜的字 + 干扰线 + 噪点。"""
    rnd = random.Random()
    width, height = 108, 40
    # 每个字单独旋转/上下浮动，避免一眼看穿的整齐排列
    glyphs = []
    for i, ch in enumerate(code):
        x = 14 + i * 22
        y = 27 + rnd.randint(-3, 3)
        rot = rnd.randint(-16, 16)
        color = rnd.choice(["#1f2937", "#1d4ed8", "#0f766e", "#7c3aed", "#b45309"])
        glyphs.append(
            f'<text x="{x}" y="{y}" fill="{color}" font-size="22" '
            f'font-family="Consolas,Menlo,monospace" font-weight="700" '
            f'transform="rotate({rot} {x} {y})">{ch}</text>'
        )
    lines = []
    for _ in range(3):
        lines.append(
            f'<path d="M{rnd.randint(0, 20)} {rnd.randint(4, height - 4)}'
            f' Q{rnd.randint(30, 70)} {rnd.randint(0, height)}'
            f' {rnd.randint(88, width)} {rnd.randint(4, height - 4)}"'
            f' stroke="{rnd.choice(["#93c5fd", "#fca5a5", "#86efac", "#c4b5fd"])}"'
            f' stroke-width="1.4" fill="none" opacity="0.85"/>'
        )
    dots = "".join(
        f'<circle cx="{rnd.randint(2, width - 2)}" cy="{rnd.randint(2, height - 2)}"'
        f' r="{rnd.choice([0.8, 1.1, 1.5])}" fill="#94a3b8" opacity="0.6"/>'
        for _ in range(26)
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
        f'<rect width="{width}" height="{height}" rx="8" fill="#f8fafc"/>'
        f"{''.join(lines)}{dots}{''.join(glyphs)}</svg>"
    )


def issue() -> dict:
    """生成一张新验证码，返回 {token, image}；image 是可直接放进 img src 的 data URI。"""
    code = "".join(random.choice(_CHARSET) for _ in range(_CODE_LEN))
    exp = int(time.time()) + TTL
    svg = _svg(code)
    return {
        "token": f"{exp}.{_sign(code, exp)}",
        "image": "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode(),
        "expiresIn": TTL,
    }


def verify(token: str, code: str) -> bool:
    """校验用户填的字符与令牌是否匹配，且令牌没过期。"""
    if not token or not code:
        return False
    try:
        exp_raw, sig = token.split(".", 1)
        exp = int(exp_raw)
    except (ValueError, AttributeError):
        return False
    if exp < time.time():
        return False
    return hmac.compare_digest(_sign(code.strip(), exp), sig)
