import sqlite3, time
c = sqlite3.connect(r"am4_data.db")
c.execute("PRAGMA foreign_keys = OFF")
t0 = time.time()
print("Before:", c.execute("SELECT COUNT(*) FROM route_aircraft").fetchone()[0])
c.execute("""
    DELETE FROM route_aircraft
    WHERE id NOT IN (
        SELECT MAX(id) FROM route_aircraft
        GROUP BY origin_id, dest_id, aircraft_id
    )
""")
c.commit()
print("After:", c.execute("SELECT COUNT(*) FROM route_aircraft").fetchone()[0])
print(f"Elapsed: {time.time()-t0:.1f}s")
