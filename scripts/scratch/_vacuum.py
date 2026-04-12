import sqlite3, time, os
p = r"am4_data.db"
print("Before:", os.path.getsize(p)/1e9, "GB")
c = sqlite3.connect(p)
t0 = time.time()
c.execute("VACUUM")
c.close()
print("After:", os.path.getsize(p)/1e9, "GB")
print(f"Elapsed: {time.time()-t0:.1f}s")
