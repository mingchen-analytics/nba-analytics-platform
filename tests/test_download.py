from nba_platform.ingest import download as dl
from nba_platform.seasons import season_label


def test_file_naming_end_year_vs_start_year():
    # ramirobentes uses the season END year, shufinskiy the START year (CLAUDE.md quirks)
    assert dl.ramirobentes_filename(2005, "regular") == "pbp_regular_2005.parquet"
    assert dl.ramirobentes_filename(2005, "playoffs") == "pbp_playoffs_2005.parquet"
    assert dl.shufinskiy_key("shotdetail", 2005, "regular") == "shotdetail_2004"
    assert dl.shufinskiy_key("pbpstats", 2005, "playoffs") == "pbpstats_po_2004"


def test_season_label():
    assert season_label(2005) == "2004-05"
    assert season_label(2000) == "1999-00"
    assert season_label(1997) == "1996-97"


def test_manifest_records_sha256(tmp_path, monkeypatch):
    monkeypatch.setattr(dl, "RAW_DIR", tmp_path)
    monkeypatch.setattr(dl, "MANIFEST", tmp_path / "manifest.csv")
    f = tmp_path / "src" / "file.bin"
    f.parent.mkdir()
    f.write_bytes(b"abc")
    dl.record_in_manifest(f, "https://example.invalid/file.bin", "2026-10-16T00:00:00+00:00")
    rows = dl.read_manifest()
    assert rows["src/file.bin"]["sha256"] == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert rows["src/file.bin"]["source"] == "src"
    dl.record_in_manifest(f, "https://other", "later")  # existing row is kept, not overwritten
    assert dl.read_manifest()["src/file.bin"]["url"] == "https://example.invalid/file.bin"


def test_purchased_sources_go_to_the_local_manifest(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    monkeypatch.setattr(dl, "RAW_DIR", raw)
    monkeypatch.setattr(dl, "MANIFEST", raw / "manifest.csv")
    for src in ("bigdataball", "shufinskiy"):
        (raw / src).mkdir(parents=True)
        f = raw / src / "a.csv"
        f.write_text("x")
        dl.record_in_manifest(f, "https://example.invalid/" + src, "2026-10-22T00:00:00+00:00")
    public = (raw / "manifest.csv").read_text(encoding="utf-8")
    assert "shufinskiy/a.csv" in public and "bigdataball" not in public
    assert "bigdataball/a.csv" in (raw / "manifest_local.csv").read_text(encoding="utf-8")
    assert set(dl.read_manifest()) == {"bigdataball/a.csv", "shufinskiy/a.csv"}   # merged for the code
