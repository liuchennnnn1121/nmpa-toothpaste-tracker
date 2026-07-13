from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
SITE_DIR = ROOT / "site"
PACKAGE_IMAGES_DIR = OUTPUT_DIR / "package_images"


def reset_site_dir() -> None:
    if SITE_DIR.exists():
        shutil.rmtree(SITE_DIR)
    SITE_DIR.mkdir(parents=True, exist_ok=True)


def copy_if_exists(source: Path, target: Path) -> None:
    if not source.exists():
        return
    if source.is_dir():
        shutil.copytree(source, target, dirs_exist_ok=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def main() -> int:
    reset_site_dir()
    copy_if_exists(OUTPUT_DIR / "brand_dashboard.html", SITE_DIR / "index.html")
    copy_if_exists(OUTPUT_DIR / "brand_dashboard.html", SITE_DIR / "brand_dashboard.html")
    for panel in OUTPUT_DIR.glob("*_brand_panel.html"):
        copy_if_exists(panel, SITE_DIR / panel.name)
    copy_if_exists(PACKAGE_IMAGES_DIR, SITE_DIR / "package_images")
    (SITE_DIR / ".nojekyll").write_text("", encoding="utf-8")
    print(SITE_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
