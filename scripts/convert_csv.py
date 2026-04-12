#!/usr/bin/env python3
"""
Convert AM4 route CSV export into fleet.csv and my_routes.csv
for import into am4-ops-center.

Usage:
    python scripts/convert_csv.py am4_routes.csv

Outputs:
    fleet.csv       — aircraft you own (type + count)
    my_routes.csv   — active route assignments
    mapping_report.txt — shows which names mapped and which didn't
"""

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


def convert(input_file: str):
    rows = []
    with open(input_file, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Strip whitespace and \r from all values
            row = {k.strip(): v.strip().strip("\r") for k, v in row.items()}
            rows.append(row)

    print(f"Read {len(rows)} routes from {input_file}")

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

    # ─── Write fleet.csv ─────────────────────────────────────────────
    with open("fleet.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["shortname", "count", "notes"])
        for ac_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            shortname = AIRCRAFT_MAP.get(ac_type, f"UNMAPPED:{ac_type}")
            writer.writerow([shortname, count, f"Imported from {ac_type}"])

    print(f"Wrote fleet.csv — {len(type_counts)} aircraft types, {sum(type_counts.values())} total aircraft")

    # ─── Write my_routes.csv ─────────────────────────────────────────
    # Aggregate: same hub + dest + aircraft type → count assigned
    route_key_counts = Counter()
    route_key_notes = {}
    for row in rows:
        hub = row["Hub"]
        dest = row["Destination"]
        ac_type = row["Aircraft_Type"]
        route_type = row.get("Route_Type", "Passenger")
        shortname = AIRCRAFT_MAP.get(ac_type, f"UNMAPPED:{ac_type}")
        key = (hub, dest, shortname)
        route_key_counts[key] += 1
        route_key_notes[key] = ROUTE_TYPE_MAP.get(route_type, "PAX")

    with open("my_routes.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["hub", "destination", "aircraft", "num_assigned", "notes"])
        for (hub, dest, shortname), count in sorted(route_key_counts.items()):
            route_type = route_key_notes[(hub, dest, shortname)]
            writer.writerow([hub, dest, shortname, count, route_type])

    print(f"Wrote my_routes.csv — {len(route_key_counts)} unique routes")

    # ─── Write mapping report ────────────────────────────────────────
    with open("mapping_report.txt", "w") as f:
        f.write("AM4 RouteMine — CSV Import Mapping Report\n")
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

        f.write(f"\nFLEET SUMMARY:\n")
        f.write(f"  Total aircraft types: {len(type_counts)}\n")
        f.write(f"  Total aircraft:       {sum(type_counts.values())}\n")
        for ac_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            sn = AIRCRAFT_MAP.get(ac_type, "???")
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


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <am4_routes.csv>")
        sys.exit(1)
    convert(sys.argv[1])
