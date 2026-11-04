"""生成社交分享封面 assets/og-cover.png（1200x630）。

用 Pillow 画：品牌 logo + 标题 + 一句技术栈 + 新版产品截图。
改了产品截图或文案后重跑一次即可：

    python _tools/make-og.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public" / "assets"
W, H = 1200, 630

FONT_REG = "C:/Windows/Fonts/msyh.ttc"
FONT_BOLD = "C:/Windows/Fonts/msyhbd.ttc"
FONT_MONO = "C:/Windows/Fonts/consola.ttf"

BRAND = (26, 115, 232)
TEXT = (17, 24, 39)
TEXT2 = (75, 85, 99)
TEXT3 = (107, 114, 128)
BORDER = (216, 222, 233)


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def rounded(img: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, img.size[0], img.size[1]], radius, fill=255)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


def main() -> None:
    canvas = Image.new("RGB", (W, H), (251, 252, 254))
    draw = ImageDraw.Draw(canvas)

    # 网格背景
    for x in range(0, W, 36):
        draw.line([(x, 0), (x, H)], fill=(238, 242, 247))
    for y in range(0, H, 36):
        draw.line([(0, y), (W, y)], fill=(238, 242, 247))

    # 左侧品牌区
    logo = Image.open(PUBLIC / "logo.png").convert("RGBA")
    logo = logo.resize((96, 96), Image.LANCZOS)
    canvas.paste(logo, (64, 64), logo)

    draw.text((64, 180), "CertHub", font=font(FONT_BOLD, 76), fill=TEXT)
    draw.text((66, 276), "SSL 证书自动化管理系统", font=font(FONT_REG, 32), fill=TEXT2)

    draw.line([(64, 350), (100, 350)], fill=BRAND, width=3)
    draw.text((112, 336), "01 / PRODUCT", font=font(FONT_MONO, 18), fill=BRAND)

    draw.text(
        (64, 452),
        "FastAPI · React 19 · ACME v2 · 75 个部署目标",
        font=font(FONT_REG, 23),
        fill=TEXT2,
    )
    draw.text(
        (64, 496),
        "https://certhub.htmacg.com",
        font=font(FONT_MONO, 20),
        fill=TEXT3,
    )
    draw.text((64, 540), "完全免费 · 无套餐、无数量限制", font=font(FONT_REG, 21), fill=TEXT3)

    # 右侧产品截图卡片
    shot = Image.open(PUBLIC / "shots" / "dashboard.png").convert("RGB")
    card_w = 520
    card_h = int(shot.height * card_w / shot.width)
    shot = shot.resize((card_w, card_h), Image.LANCZOS)
    card = Image.new("RGB", (card_w + 2, card_h + 2), BORDER)
    card.paste(shot, (1, 1))
    card = rounded(card, 12)

    x, y = W - card_w - 72, 104
    shadow = Image.new("RGBA", (card.size[0] + 40, card.size[1] + 40), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [10, 12, card.size[0] + 10, card.size[1] + 12], 16, fill=(17, 24, 39, 22)
    )
    canvas.paste(shadow, (x - 10, y - 10), shadow)
    canvas.paste(card, (x, y), card)

    out = PUBLIC / "og-cover.png"
    canvas.save(out, optimize=True)
    print(f"已生成 {out}（{canvas.size[0]}x{canvas.size[1]}）")


if __name__ == "__main__":
    main()
