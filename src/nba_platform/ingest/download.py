"""Download raw source files into data/raw/.

Files are written once and never overwritten (CLAUDE.md rule 4). Download goes to a
temporary ``.part`` file first so an interrupted download never leaves a truncated
file that looks complete.

Naming quirks (see CLAUDE.md "Known source quirks"):
- ramirobentes uses the season END year:   pbp_regular_2005.parquet  = 2004-05
                                           pbp_playoffs_2005.parquet = 2004-05 playoffs
- shufinskiy uses the season START year:   shotdetail_2004 / shotdetail_po_2004 = 2004-05

Usage:
    python -m nba_platform.ingest.download --season-end-year 2005
    python -m nba_platform.ingest.download --season-end-year 2005 --season-type playoffs
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import shutil
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
MANIFEST = RAW_DIR / "manifest.csv"
MANIFEST_COLUMNS = ["path", "source", "url", "downloaded_at", "sha256", "bytes", "note"]

RAMIROBENTES_URL = (
    "https://github.com/ramirobentes/nba_data/releases/download/pbp/{name}"
)
SHUFINSKIY_LIST_URL = (
    "https://raw.githubusercontent.com/shufinskiy/nba_data/main/list_data.txt"
)
SHUFINSKIY_DATASETS = ("shotdetail", "pbpstats")

_RB_TYPE = {"regular": "regular", "playoffs": "playoffs"}
_SH_SUFFIX = {"regular": "", "playoffs": "_po"}


def ramirobentes_filename(season_end_year: int, season_type: str) -> str:
    return f"pbp_{_RB_TYPE[season_type]}_{season_end_year}.parquet"


def shufinskiy_key(dataset: str, season_end_year: int, season_type: str) -> str:
    return f"{dataset}{_SH_SUFFIX[season_type]}_{season_end_year - 1}"


def fetch_shufinskiy_index() -> dict[str, str]:
    """Return {dataset_key: url} from shufinskiy's list_data.txt."""
    with urllib.request.urlopen(SHUFINSKIY_LIST_URL, timeout=60) as resp:
        text = resp.read().decode("utf-8")
    index = {}
    for line in text.splitlines():
        line = line.strip()
        if line and "=" in line:
            key, url = line.split("=", 1)
            index[key.strip()] = url.strip()
    return index


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# Purchased files: their listing stays on this machine (data/raw/manifest_local.csv, git-ignored);
# the committed manifest holds only publicly downloadable sources.
PRIVATE_SOURCES = {"bigdataball"}


def local_manifest_path() -> Path:
    return MANIFEST.with_name("manifest_local.csv")


def _read_csv(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {row["path"]: row for row in csv.DictReader(f)}


def read_manifest() -> dict[str, dict]:
    """Both manifests merged: the committed one and the local one for purchased files."""
    return {**_read_csv(MANIFEST), **_read_csv(local_manifest_path())}


def _write_manifest(rows: dict[str, dict]) -> None:
    """Write public sources to manifest.csv and purchased ones to manifest_local.csv."""
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    for path, keep in ((MANIFEST, lambda r: r["source"] not in PRIVATE_SOURCES),
                       (local_manifest_path(), lambda r: r["source"] in PRIVATE_SOURCES)):
        part = sorted((r for r in rows.values() if keep(r)), key=lambda r: r["path"])
        if not part and not path.exists():
            continue
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS)
            w.writeheader()
            w.writerows(part)


def record_in_manifest(dest: Path, url: str, downloaded_at: str, note: str = "") -> None:
    """Add (or keep) one manifest row per raw file: url, download time, SHA-256."""
    rows = read_manifest()
    key = dest.relative_to(RAW_DIR).as_posix()
    if key in rows:
        return
    rows[key] = {
        "path": key, "source": key.split("/")[0], "url": url, "downloaded_at": downloaded_at,
        "sha256": sha256(dest), "bytes": dest.stat().st_size, "note": note,
    }
    _write_manifest(rows)


def record_local_files(folder: Path, origin: str) -> int:
    """Add files that were placed by hand (e.g. purchased BigDataBall CSVs) to the manifest.

    `url` holds the origin description; `downloaded_at` is the file modification time
    (the note says so). Existing rows are kept. Returns the number of rows added.
    """
    rows = read_manifest()
    added = 0
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        key = path.relative_to(RAW_DIR).as_posix()
        if key in rows:
            continue
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
        rows[key] = {"path": key, "source": key.split("/")[0], "url": origin, "downloaded_at": mtime,
                     "sha256": sha256(path), "bytes": path.stat().st_size,
                     "note": "local file placed by owner; downloaded_at = file mtime"}
        added += 1
    if added:
        _write_manifest(rows)
    return added


def download(url: str, dest: Path) -> str:
    """Download url to dest unless dest already exists. Returns 'skipped' or 'downloaded'.

    Every file ends up in data/raw/manifest.csv. A file that predates the manifest is
    backfilled with its file modification time, and the note says so.
    """
    if dest.exists():
        mtime = datetime.fromtimestamp(dest.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
        record_in_manifest(dest, url, mtime, note="downloaded_at backfilled from file mtime")
        return "skipped"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "nba-analytics-platform"})
    with urllib.request.urlopen(req, timeout=600) as resp, open(tmp, "wb") as f:
        shutil.copyfileobj(resp, f, length=1 << 20)
    tmp.rename(dest)
    record_in_manifest(dest, url, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    return "downloaded"


def download_season(
    season_end_year: int,
    season_type: str = "regular",
    shufinskiy_datasets: tuple[str, ...] = SHUFINSKIY_DATASETS,
    shufinskiy_index: dict[str, str] | None = None,
) -> list[tuple[Path, str]]:
    """Download every source file for one season. Missing upstream files raise."""
    results = []

    name = ramirobentes_filename(season_end_year, season_type)
    dest = RAW_DIR / "ramirobentes" / name
    results.append((dest, download(RAMIROBENTES_URL.format(name=name), dest)))

    if shufinskiy_datasets:
        index = shufinskiy_index or fetch_shufinskiy_index()
        for dataset in shufinskiy_datasets:
            key = shufinskiy_key(dataset, season_end_year, season_type)
            if key not in index:
                raise KeyError(f"shufinskiy has no dataset '{key}' in list_data.txt")
            dest = RAW_DIR / "shufinskiy" / f"{key}.tar.xz"
            results.append((dest, download(index[key], dest)))

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--season-end-year", type=int, required=True)
    parser.add_argument("--season-type", choices=sorted(_RB_TYPE), default="regular")
    parser.add_argument(
        "--shufinskiy", nargs="*", default=list(SHUFINSKIY_DATASETS),
        help="shufinskiy datasets to fetch (default: shotdetail pbpstats)",
    )
    args = parser.parse_args()
    for dest, status in download_season(
        args.season_end_year, args.season_type, tuple(args.shufinskiy)
    ):
        print(f"{status:>10}  {dest.relative_to(PROJECT_ROOT)}  ({dest.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
