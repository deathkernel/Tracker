from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import powerbi_export as exporter


def test_empty_power_bi_tables_keep_importable_headers(tmp_path, monkeypatch):
    monkeypatch.setattr(exporter, "OUT", tmp_path)
    exporter.write_csv("StudyLogs", [])
    with (tmp_path / "StudyLogs.csv").open(encoding="utf-8-sig", newline="") as file:
        assert next(csv.reader(file)) == ["Date", "StudyHours", "MCQs", "CSAT", "Notes"]


def test_power_bi_date_validation_rejects_invalid_dates():
    assert exporter.valid_iso_date("2026-11-18")
    assert not exporter.valid_iso_date("2026-02-30")
    assert not exporter.valid_iso_date("18-11-2026")
    assert not exporter.valid_iso_date(None)


def test_power_bi_numeric_conversion_handles_malformed_values():
    assert exporter.safe_number("4.5") == 4.5
    assert exporter.safe_number("50", integer=True) == 50
    assert exporter.safe_number("2.5", integer=True) == ""
    assert exporter.safe_number("not-a-number") == ""
    assert exporter.safe_number(float("nan")) == ""
    assert exporter.safe_number(-1) == ""
