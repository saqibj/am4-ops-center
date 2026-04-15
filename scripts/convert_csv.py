#!/usr/bin/env python3
"""
Convert AM4 route CSV export into fleet.csv and my_routes.csv
for import into am4-ops-center.

Usage:
    python scripts/convert_csv.py am4_routes.csv
    python scripts/convert_csv.py am4_routes.csv --on-undercount warn|bump|fail

Outputs:
    fleet.csv       — aircraft you own (type + count)
    my_routes.csv   — active route assignments
    mapping_report.txt — shows which names mapped and which didn't
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

# ─── Aircraft name mapping ───────────────────────────────────────────
# CSV Aircraft_Type  →  am4 shortname
# Verify these against: python -c "from am4.utils.db import init; init(); from am4.utils.aircraft import Aircraft; r=Aircraft.search('a342'); print(r.ac.shortname, r.ac.name)"
AIRCRAFT_MAP = {
    # Airbus narrowbody (shortnames match am4.utils.aircraft.Aircraft.search)
    "A220-100":     "a221",
    "A220-300":     "a220-300",
    "A318-100":     "a3181",
    "A319-200":     "a3192",
    "A319NEO":      "a319neo",
    "A320-200":     "a322",
    "A320-NEO":     "a32neo",
    "A320-VIP":     "a32vip",
    "A321-200":     "a3212",
    "A321-NEO":     "a321neo",
    "A321-XLR":     "a321x1r",

    # Airbus widebody
    "A310-300F":    "a313f",
    "A340-200":     "a342",
    "A350F":        "a350f",
    "A400M":        "a400m",

    # Boeing
    "B737 MAX 9":   "b73max9",
    "B737-700C":    "b737c",

    # Bombardier / Cessna (VIP)
    "Bombardier Challenger 605-VIP": "ch605",
    "Cessna Citation X-VIP":        "ccx",

    # Douglas
    "DC-9-10":      "dc910",

    # Embraer
    "ERJ 135ER":    "erj135er",
    "ERJ 145ER":    "erj145er",
    "ERJ 145XR":    "erj145xr",
    "ERJ 170-200":  "erj172",
    "ERJ 190-200":  "erj192",

    # ATR
    "ATR 42-320":   "atr4232",
}

# Route type mapping
ROUTE_TYPE_MAP = {
    "Passenger": "PAX",
    "Cargo":     "CARGO",
    "VIP":       "VIP",
    "Charter":   "PAX",  # charters are PAX in am4 terms
}


def _shortname_for_type(ac_type: str) -> str:
    return AIRCRAFT_MAP.get(ac_type, f"UNMAPPED:{ac_type}")


def _tty_color(code: str) -> str:
    if sys.stdout.isatty():
        return code
    return ""


def _warn_line(msg: str, *, color: str = "yellow") -> None:
    """Print a warning line (yellow or red when stdout is a TTY)."""
    if color == "red":
        pre = _tty_color("\033[1;31m")
    else:
        pre = _tty_color("\033[1;33m")
    reset = _tty_color("\033[0m")
    print(f"{pre}⚠{reset} {msg}")


def convert(
    input_file: str | Path,
    *,
    on_undercount: str = "bump",
    output_dir: Path | None = None,
) -> None:
    input_path = Path(input_file)
    out = Path(output_dir) if output_dir is not None else Path.cwd()

    rows = []
    with open(input_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Strip whitespace and \r from all values
            row = {k.strip(): v.strip().strip("\r") for k, v in row.items()}
            rows.append(row)

    print(f"Read {len(rows)} routes from {input_path}")

    # ─── Build fleet (unique aircraft by registration → type) ────────
    reg_to_type = {}
    unmapped = set()
    mapped_types = set()

    for row in rows:
        reg = row["Aircraft_Reg"]
        ac_type = row["Aircraft_Type"]
        reg_to_type[reg] = ac_type

        if ac_type in AIRCRAFT_MAP:
            mapped_types.add(ac_type)
        else:
            unmapped.add(ac_type)

    # Count unique registrations per aircraft type
    type_counts = Counter(reg_to_type.values())

    # ─── Routes aggregate (needed before fleet write for consistency checks) ─
    route_key_counts = Counter()
    route_key_notes = {}
    for row in rows:
        hub = row["Hub"]
        dest = row["Destination"]
        ac_type = row["Aircraft_Type"]
        route_type = row.get("Route_Type", "Passenger")
        shortname = _shortname_for_type(ac_type)
        key = (hub, dest, shortname)
        route_key_counts[key] += 1
        route_key_notes[key] = ROUTE_TYPE_MAP.get(route_type, "PAX")

    # ─── Implied minimum fleet per type from route rows ─────────────────
    undercounts: list[tuple[str, int, int]] = []
    for ac_type in type_counts:
        sn = _shortname_for_type(ac_type)
        implied_min = sum(
            count
            for (_h, _d, key_sn), count in route_key_counts.items()
            if key_sn == sn
        )
        if type_counts[ac_type] < implied_min:
            undercounts.append((ac_type, type_counts[ac_type], implied_min))

    # ─── Registration uniqueness per type (OCR garble signal) ───────────
    rows_by_type: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        rows_by_type[row["Aircraft_Type"]].append(row["Aircraft_Reg"])

    reg_uniqueness_warnings: list[tuple[str, int, int]] = []
    for ac_type, regs in sorted(rows_by_type.items()):
        n_rows = len(regs)
        n_unique = len(set(regs))
        if n_rows > n_unique:
            reg_uniqueness_warnings.append((ac_type, n_rows, n_unique))

    # ─── Handle route-implied undercounts ──────────────────────────────
    bump_records: list[tuple[str, int, int]] = []
    warn_only_undercounts: list[tuple[str, int, int]] = []

    if undercounts:
        if on_undercount == "fail":
            _warn_line(
                "Fleet counts are below route-implied minimum (OCR likely garbled Aircraft_Reg):",
                color="red",
            )
            for ac_type, fleet_n, implied in sorted(undercounts):
                sn = _shortname_for_type(ac_type)
                print(f"    {ac_type} ({sn}): fleet {fleet_n} < routes imply {implied}")
            sys.exit(1)

        if on_undercount == "warn":
            for ac_type, fleet_n, implied in sorted(undercounts):
                _warn_line(
                    f"{ac_type}: fleet count {fleet_n} < route-implied minimum {implied} "
                    f"(not adjusted; use --on-undercount bump)",
                )
                warn_only_undercounts.append((ac_type, fleet_n, implied))
        else:
            # bump (default)
            for ac_type, fleet_n, implied in sorted(undercounts):
                _warn_line(
                    f"{ac_type}: raising fleet count {fleet_n} → {implied} "
                    f"(route-implied minimum)",
                )
                bump_records.append((ac_type, fleet_n, implied))
                type_counts[ac_type] = implied

    for ac_type, n_rows, n_unique in reg_uniqueness_warnings:
        _warn_line(
            f"{ac_type}: {n_rows} rows → {n_unique} unique reg "
            f"(OCR likely garbled Aircraft_Reg)",
        )

    # ─── Write fleet.csv ─────────────────────────────────────────────
    with open(out / "fleet.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["shortname", "count", "notes"])
        for ac_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            shortname = _shortname_for_type(ac_type)
            writer.writerow([shortname, count, f"Imported from {ac_type}"])

    print(
        f"Wrote fleet.csv — {len(type_counts)} aircraft types, "
        f"{sum(type_counts.values())} total aircraft"
    )

    # ─── Write my_routes.csv ─────────────────────────────────────────
    with open(out / "my_routes.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["hub", "destination", "aircraft", "num_assigned", "notes"])
        for (hub, dest, shortname), count in sorted(route_key_counts.items()):
            route_type = route_key_notes[(hub, dest, shortname)]
            writer.writerow([hub, dest, shortname, count, route_type])

    print(f"Wrote my_routes.csv — {len(route_key_counts)} unique routes")

    # ─── Write mapping report ────────────────────────────────────────
    with open(out / "mapping_report.txt", "w", encoding="utf-8") as f:
        f.write("AM4 Ops Center — CSV Import Mapping Report\n")
        f.write("=" * 50 + "\n\n")

        f.write("SUCCESSFULLY MAPPED:\n")
        for t in sorted(mapped_types):
            f.write(f"  {t:40s} → {AIRCRAFT_MAP[t]}\n")

        if unmapped:
            f.write(f"\nUNMAPPED ({len(unmapped)} types — fix AIRCRAFT_MAP in this script):\n")
            for t in sorted(unmapped):
                f.write(f"  {t:40s} → ???\n")
        else:
            f.write("\nAll aircraft types mapped successfully!\n")

        f.write("\nDATA QUALITY WARNINGS:\n")
        f.write("-" * 50 + "\n")
        any_dq = False
        if bump_records:
            any_dq = True
            f.write("Undercount repair (fleet tally raised to route-implied minimum):\n")
            for ac_type, before, after in bump_records:
                sn = _shortname_for_type(ac_type)
                f.write(f"  {ac_type} ({sn}): {before} → {after}\n")
        if warn_only_undercounts:
            any_dq = True
            f.write("Undercount detected (warn mode — not repaired):\n")
            for ac_type, fleet_n, implied in warn_only_undercounts:
                sn = _shortname_for_type(ac_type)
                f.write(f"  {ac_type} ({sn}): fleet {fleet_n}, route-implied minimum {implied}\n")
        if reg_uniqueness_warnings:
            any_dq = True
            f.write("Registration uniqueness (rows vs unique Aircraft_Reg):\n")
            for ac_type, n_rows, n_unique in reg_uniqueness_warnings:
                f.write(
                    f"  {ac_type}: {n_rows} rows → {n_unique} unique reg "
                    f"(OCR likely garbled Aircraft_Reg)\n"
                )
        if not any_dq:
            f.write("No OCR inconsistencies detected.\n")

        f.write(f"\nFLEET SUMMARY:\n")
        f.write(f"  Total aircraft types: {len(type_counts)}\n")
        f.write(f"  Total aircraft:       {sum(type_counts.values())}\n")
        for ac_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            sn = _shortname_for_type(ac_type)
            f.write(f"  {count:4d}× {ac_type:40s} ({sn})\n")

        f.write(f"\nROUTES BY HUB:\n")
        hub_counts = Counter(row["Hub"] for row in rows)
        for hub, count in sorted(hub_counts.items(), key=lambda x: -x[1]):
            f.write(f"  {hub}: {count} routes\n")

    print(f"Wrote mapping_report.txt")

    if unmapped:
        print(f"\n⚠️  {len(unmapped)} aircraft types could not be mapped:")
        for t in sorted(unmapped):
            print(f"    {t}")
        print("Edit AIRCRAFT_MAP in this script and re-run.")
    else:
        print("\n✅ All aircraft mapped. Review fleet.csv and my_routes.csv, then import:")
        print("   python main.py fleet import --file fleet.csv")
        print("   python main.py routes import --file my_routes.csv")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert AM4 route CSV export into fleet.csv and my_routes.csv.",
    )
    parser.add_argument("input_file", help="Path to OCR'd routes CSV")
    parser.add_argument(
        "--on-undercount",
        choices=("warn", "bump", "fail"),
        default="bump",
        help="When fleet count from regs is below route-implied minimum (default: bump).",
    )
    args = parser.parse_args()
    convert(args.input_file, on_undercount=args.on_undercount)


if __name__ == "__main__":
    main()
