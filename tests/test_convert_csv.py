"""Tests for scripts/convert_csv — OCR-robust fleet counting."""

from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

spec = importlib.util.spec_from_file_location("convert_csv", _SCRIPTS / "convert_csv.py")
assert spec and spec.loader
convert_csv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(convert_csv)
convert = convert_csv.convert
AIRCRAFT_MAP = convert_csv.AIRCRAFT_MAP


def _csv_path(tmp_path: Path, name: str, rows: list[dict]) -> Path:
    p = tmp_path / name
    fieldnames = ["Hub", "Destination", "Aircraft_Type", "Aircraft_Reg", "Route_Type"]
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})
    return p


def test_clean_distinct_regs_one_type(tmp_path) -> None:
    """N distinct regs, N rows, one type → fleet count = N, no data-quality issues."""
    ac = "A320-200"
    rows = [
        {
            "Hub": "DXB",
            "Destination": f"D{i}",
            "Aircraft_Type": ac,
            "Aircraft_Reg": f"REG-{i}",
            "Route_Type": "Passenger",
        }
        for i in range(3)
    ]
    p = _csv_path(tmp_path, "clean.csv", rows)
    convert(p, on_undercount="bump", output_dir=tmp_path)

    fleet = {}
    with open(tmp_path / "fleet.csv", newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            fleet[row["shortname"]] = int(row["count"])

    assert fleet[AIRCRAFT_MAP[ac]] == 3

    report = (tmp_path / "mapping_report.txt").read_text(encoding="utf-8")
    assert "No OCR inconsistencies detected." in report


def test_ocr_duplicate_regs_bump_raises_to_route_implied(tmp_path) -> None:
    """Same reg repeated for 4 VIP rows → fleet was 1; bump sets to 4 (route-implied)."""
    ac = "Cessna Citation X-VIP"
    rows = [
        {
            "Hub": "DXB",
            "Destination": f"D{i}",
            "Aircraft_Type": ac,
            "Aircraft_Reg": "???",
            "Route_Type": "VIP",
        }
        for i in range(4)
    ]
    p = _csv_path(tmp_path, "dup_reg.csv", rows)
    convert(p, on_undercount="bump", output_dir=tmp_path)

    fleet = {}
    with open(tmp_path / "fleet.csv", newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            fleet[row["shortname"]] = int(row["count"])

    assert fleet["ccx"] == 4

    report = (tmp_path / "mapping_report.txt").read_text(encoding="utf-8")
    assert "Undercount repair" in report
    assert "Cessna Citation X-VIP" in report
    assert "1 → 4" in report
    assert "Registration uniqueness" in report


def test_ocr_duplicate_regs_warn_keeps_count(tmp_path, capsys) -> None:
    ac = "Cessna Citation X-VIP"
    rows = [
        {
            "Hub": "DXB",
            "Destination": f"D{i}",
            "Aircraft_Type": ac,
            "Aircraft_Reg": "X",
            "Route_Type": "VIP",
        }
        for i in range(4)
    ]
    p = _csv_path(tmp_path, "warn.csv", rows)
    convert(p, on_undercount="warn", output_dir=tmp_path)

    fleet = {}
    with open(tmp_path / "fleet.csv", newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            fleet[row["shortname"]] = int(row["count"])

    assert fleet["ccx"] == 1
    err = capsys.readouterr().out
    assert "route-implied minimum" in err.lower() or "4" in err

    report = (tmp_path / "mapping_report.txt").read_text(encoding="utf-8")
    assert "warn mode — not repaired" in report


def test_ocr_duplicate_regs_fail_exits(tmp_path) -> None:
    ac = "Cessna Citation X-VIP"
    rows = [
        {
            "Hub": "DXB",
            "Destination": f"D{i}",
            "Aircraft_Type": ac,
            "Aircraft_Reg": "X",
            "Route_Type": "VIP",
        }
        for i in range(4)
    ]
    p = _csv_path(tmp_path, "fail.csv", rows)
    with pytest.raises(SystemExit) as ei:
        convert(p, on_undercount="fail", output_dir=tmp_path)
    assert ei.value.code == 1
    assert not (tmp_path / "fleet.csv").exists()


def test_unmapped_type_with_routes_no_crash(tmp_path) -> None:
    """Types not in AIRCRAFT_MAP still produce UNMAPPED: routes; implied-min logic matches."""
    ac = "Mystery Type 999"
    assert ac not in AIRCRAFT_MAP
    rows = [
        {
            "Hub": "KHI",
            "Destination": "DXB",
            "Aircraft_Type": ac,
            "Aircraft_Reg": "R1",
            "Route_Type": "Passenger",
        },
        {
            "Hub": "KHI",
            "Destination": "JFK",
            "Aircraft_Type": ac,
            "Aircraft_Reg": "R2",
            "Route_Type": "Passenger",
        },
    ]
    p = _csv_path(tmp_path, "unmapped.csv", rows)
    convert(p, on_undercount="bump", output_dir=tmp_path)

    fleet = {}
    with open(tmp_path / "fleet.csv", newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            fleet[row["shortname"]] = int(row["count"])

    assert fleet[f"UNMAPPED:{ac}"] == 2
    report = (tmp_path / "mapping_report.txt").read_text(encoding="utf-8")
    assert "UNMAPPED" in report
