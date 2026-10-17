#!/usr/bin/env python3
"""Download official CALCE CS2 zips (not committed) and write a compact fade CSV."""

from __future__ import annotations

import argparse
from pathlib import Path
from urllib.request import Request, urlopen

from batteryhealth.calce_fade import CALCE_CELLS, fade_table_from_zips
from batteryhealth.config import REPO_ROOT


def download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 1_000_000:
        return dest
    req = Request(url, headers={"User-Agent": "BatteryHealth/0.2 (research; +https://github.com/717Andy/battery-health)"})
    print(f"Downloading {url} → {dest}")
    with urlopen(req, timeout=120) as resp, open(dest, "wb") as fh:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            fh.write(chunk)
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=REPO_ROOT / "data" / "raw" / "calce")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "artifacts" / "early_cycle" / "calce_fade.csv")
    parser.add_argument("--cells", nargs="*", default=list(CALCE_CELLS))
    args = parser.parse_args(argv)
    for cell in args.cells:
        download(CALCE_CELLS[cell], args.raw / f"{cell}.zip")
    fade = fade_table_from_zips(args.raw, cells=tuple(args.cells))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fade.to_csv(args.out, index=False)
    print("Wrote", args.out, "rows", len(fade))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
