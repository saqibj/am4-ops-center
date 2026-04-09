import sqlite3, time
c = sqlite3.connect(r"am4_data.db")
t0 = time.time()
c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_route_aircraft_triple ON route_aircraft(origin_id, dest_id, aircraft_id)")
c.commit()
print(f"Index created in {time.time()-t0:.1f}s")
for r in c.execute("SELECT sql FROM sqlite_master WHERE name='ux_route_aircraft_triple'"):
    print(r[0])
c.close()
