import sqlite3
c = sqlite3.connect(r"am4_data.db")
for r in c.execute("""
    SELECT sql FROM sqlite_master
    WHERE tbl_name IN ('route_aircraft','extraction_runs','route_demands')
      AND sql IS NOT NULL
    ORDER BY type, name
"""):
    print(r[0]); print("---")
