#!/usr/bin/env python3
"""Capture README media from a running Cairn demo workspace.

Run the dashboard against deterministic demo data first::

    cairn demo --reset
    cairn ui --workspace ~/.cairn-demo --no-open
    uv run python scripts/gen_readme_assets.py
"""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
UI_ROOT = ROOT / "ui"
ASSETS = ROOT / "docs" / "assets"
VIEWPORT = "1440,900"
OUTPUT_SIZE = (960, 600)
TAIL_TRACE_ID = "ebfa4275-bf56-58ab-a4d6-6a4424197a58"


def _capture(base_url: str, route: str, destination: Path) -> None:
    url = f"{base_url.rstrip('/')}{route}"
    subprocess.run(
        [
            "npx",
            "playwright",
            "screenshot",
            f"--viewport-size={VIEWPORT}",
            "--wait-for-timeout=1500",
            url,
            str(destination),
        ],
        cwd=UI_ROOT,
        check=True,
    )


def _resize(source: Path, destination: Path) -> Image.Image:
    with Image.open(source) as image:
        frame = image.convert("RGB").resize(OUTPUT_SIZE, Image.Resampling.LANCZOS)
    frame.save(destination, format="PNG", optimize=True)
    return frame


def generate(base_url: str) -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    screenshots = {
        "overview.png": "/",
        "session-detail.png": f"/sessions/{TAIL_TRACE_ID}?seq=3",
        "optimize-verdict.png": "/optimize",
    }
    hero_routes = [
        "/",
        "/sessions?sort=waste",
        f"/sessions/{TAIL_TRACE_ID}",
        f"/sessions/{TAIL_TRACE_ID}?seq=1",
        f"/sessions/{TAIL_TRACE_ID}?seq=2",
        f"/sessions/{TAIL_TRACE_ID}?seq=3",
        f"/sessions/{TAIL_TRACE_ID}?seq=3&mode=time",
    ]
    durations = [1400, 1100, 1000, 650, 650, 900, 1400]

    with tempfile.TemporaryDirectory(prefix="cairn-readme-") as temp:
        temp_dir = Path(temp)
        for name, route in screenshots.items():
            raw = temp_dir / f"raw-{name}"
            _capture(base_url, route, raw)
            _resize(raw, ASSETS / name)
            print(f"Wrote {ASSETS / name}")

        frames: list[Image.Image] = []
        for index, route in enumerate(hero_routes):
            raw = temp_dir / f"hero-{index}.png"
            _capture(base_url, route, raw)
            with Image.open(raw) as image:
                frame = image.convert("RGB").resize(OUTPUT_SIZE, Image.Resampling.LANCZOS)
            frames.append(frame.quantize(colors=128, method=Image.Quantize.MEDIANCUT))

        hero = ASSETS / "hero.gif"
        frames[0].save(
            hero,
            save_all=True,
            append_images=frames[1:],
            duration=durations,
            loop=0,
            optimize=True,
            disposal=2,
        )
        print(f"Wrote {hero}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    args = parser.parse_args()
    generate(args.base_url)


if __name__ == "__main__":
    main()
