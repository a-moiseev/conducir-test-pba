"""WebP copies of the question images for the site.

The JPEGs in data/pba/images stay the source of truth: question ids hash their bytes, so
re-encoding them would reset everyone's progress. The site serves these WebP copies instead.
Needs Pillow (in requirements.txt); the site build itself only copies the results.

Usage: .venv/bin/python tools/make_webp.py [data_dir]
"""
import sys
from pathlib import Path

from PIL import Image

QUALITY = 70  # indistinguishable from the JPEG sources at question-image sizes


def main():
    data = Path(sys.argv[1] if len(sys.argv) > 1 else "data/pba")
    src, out = data / "images", data / "webp"
    out.mkdir(exist_ok=True)
    jpgs = sorted(src.glob("*.jpg"))
    for jpg in jpgs:
        with Image.open(jpg) as im:
            im.save(out / f"{jpg.stem}.webp", "WEBP", quality=QUALITY, method=6)
    wanted = {f"{jpg.stem}.webp" for jpg in jpgs}
    for stale in out.glob("*.webp"):
        if stale.name not in wanted:
            stale.unlink()
    before = sum(p.stat().st_size for p in jpgs)
    after = sum((out / name).stat().st_size for name in wanted)
    print(f"webp: {len(jpgs)} images, {before // 1024} KB -> {after // 1024} KB")


if __name__ == "__main__":
    main()
