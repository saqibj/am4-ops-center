import sqlite3, os
p = r"am4_ops.db"
print("size:", os.path.getsize(p))
c = sqlite3.connect(p)
rows = list(c.execute("SELECT name, sql FROM sqlite_master WHERE type='table'"))
print("tables:", len(rows))
for name, sql in rows:
    print("---", name)
    print(sql)
# specifically my_hubs
print("=== my_hubs indexes ===")
for r in c.execute("SELECT sql FROM sqlite_master WHERE tbl_name='my_hubs'"):
    print(r[0])
