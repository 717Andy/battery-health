"""Download NASA Ames PCoE battery .mat files and convert them to canonical JSON."""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from urllib.request import urlopen

from batteryhealth.config import (
    DEFAULT_PROCESSED_DIR,
    DEFAULT_RAW_DIR,
    NASA_BATTERIES,
    NASA_CITATION,
    NASA_DOWNLOAD_URL,
    NASA_INNER_ZIP,
)
from batteryhealth.parsers.canonical import dict_to_summary
from batteryhealth.parsers.nasa import parse_nasa_mat


def download_zip(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 1_000_000:
        return dest
    print(f"Downloading {url} → {dest}")
    with urlopen(url) as resp, open(dest, "wb") as fh:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            fh.write(chunk)
    return dest


def extract_nasa_batteries(zip_path: Path, raw_dir: Path, batteries: tuple[str, ...] = NASA_BATTERIES) -> list[Path]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    wanted = {f"{name}.mat" for name in batteries}
    extracted: list[Path] = []

    def _take(zf: zipfile.ZipFile) -> None:
        for name in zf.namelist():
            base = Path(name).name
            if base in wanted:
                target = raw_dir / base
                with zf.open(name) as src, open(target, "wb") as dst:
                    dst.write(src.read())
                extracted.append(target)

    with zipfile.ZipFile(zip_path) as outer:
        names = outer.namelist()
        if any(Path(n).name in wanted for n in names):
            _take(outer)
            return extracted
        inner = NASA_INNER_ZIP
        if inner not in names:
            # Fall back to the first nested zip that looks like FY08Q4.
            candidates = [n for n in names if n.lower().endswith(".zip") and "fy08" in n.lower()]
            if not candidates:
                candidates = [n for n in names if n.lower().endswith(".zip")]
            if not candidates:
                raise FileNotFoundError(f"Could not find a nested battery zip in {zip_path}")
            inner = candidates[0]
        with outer.open(inner) as src:
            inner_bytes = src.read()
        inner_path = zip_path.with_suffix(".inner.zip")
        inner_path.write_bytes(inner_bytes)
        with zipfile.ZipFile(inner_path) as zf:
            _take(zf)
        inner_path.unlink(missing_ok=True)
    missing = wanted - {p.name for p in extracted}
    if missing:
        raise FileNotFoundError(f"Missing {sorted(missing)} after extract")
    return extracted


def process_raw_dir(raw_dir: Path, processed_dir: Path) -> list[Path]:
    processed_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for path in sorted(raw_dir.glob("B*.mat")):
        record = parse_nasa_mat(path)
        out = processed_dir / f"{record['batteryId']}.json"
        out.write_text(json.dumps(record))
        summary = processed_dir / f"{record['batteryId']}.summary.json"
        summary.write_text(json.dumps(dict_to_summary(record), indent=2))
        written.append(out)
        print(f"Wrote {out} ({dict_to_summary(record)})")
    if not written:
        raise FileNotFoundError(f"No B*.mat files in {raw_dir}")
    (processed_dir / "CITATION.txt").write_text(NASA_CITATION + "\n")
    return written


def run(
    *,
    raw_dir: Path = DEFAULT_RAW_DIR,
    processed_dir: Path = DEFAULT_PROCESSED_DIR,
    cache_zip: Path | None = None,
    skip_download: bool = False,
) -> None:
    have = list(raw_dir.glob("B*.mat")) if raw_dir.exists() else []
    if not have and not skip_download:
        cache_zip = cache_zip or raw_dir.parent / "nasa_battery.zip"
        download_zip(NASA_DOWNLOAD_URL, cache_zip)
        extract_nasa_batteries(cache_zip, raw_dir)
    process_raw_dir(raw_dir, processed_dir)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Download and process NASA PCoE battery files")
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--processed", type=Path, default=DEFAULT_PROCESSED_DIR)
    parser.add_argument("--zip", type=Path, default=None)
    parser.add_argument("--skip-download", action="store_true")
    args = parser.parse_args(argv)
    run(raw_dir=args.raw, processed_dir=args.processed, cache_zip=args.zip, skip_download=args.skip_download)


if __name__ == "__main__":
    main()
