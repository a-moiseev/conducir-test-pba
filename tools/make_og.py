"""Share preview (og:image) for every page: a green road sign in the site's colors and font.

Usage: .venv/bin/python tools/make_og.py [site_dir]   -> site/og.png (1200x630)
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

GREEN, WHITE, YELLOW = "#00663d", "#ffffff", "#ffc20e"
W, H = 1200, 630


def font(site, size, weight):
    f = ImageFont.truetype(str(site / "fonts" / "overpass-latin.woff2"), size)
    try:
        f.set_variation_by_axes([weight])
    except OSError:  # not a variable font: regular weight only
        pass
    return f


def main():
    site = Path(sys.argv[1] if len(sys.argv) > 1 else "site")
    img = Image.new("RGB", (W, H), GREEN)
    d = ImageDraw.Draw(img)
    # White inset border, like the frame of a guide sign.
    d.rounded_rectangle((28, 28, W - 28, H - 28), radius=36, outline=WHITE, width=8)
    d.text((96, 92), "conducir.ar", font=font(site, 40, 700), fill=YELLOW)
    d.text((96, 170), "Test de manejo", font=font(site, 108, 800), fill=WHITE)
    d.text((96, 290), "Provincia de Buenos Aires", font=font(site, 64, 700), fill=WHITE)
    lines = ["Las preguntas oficiales del examen teórico", "con respuestas y simulacro de 40 preguntas. Gratis."]
    for i, line in enumerate(lines):
        d.text((96, 420 + i * 52), line, font=font(site, 38, 400), fill=WHITE)
    img.save(site / "og.png", optimize=True)
    print(site / "og.png")


if __name__ == "__main__":
    main()
