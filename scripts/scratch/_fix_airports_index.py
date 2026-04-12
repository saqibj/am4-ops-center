import sqlite3
c = sqlite3.connect(r"am4_data.db")
try:
    c.execute("DROP INDEX IF EXISTS idx_airports_iata_unique")
    c.execute("CREATE UNIQUE INDEX idx_airports_iata_unique ON airports(iata)")
    c.commit()
    print("Migration OK")
    # Verify
    for r in c.execute("SELECT sql FROM sqlite_master WHERE name='idx_airports_iata_unique'"):
        print("New index:", r[0])
except Exception as e:
    print("FAIL:", type(e).__name__, e)
finally:
    c.close()
