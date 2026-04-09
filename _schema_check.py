import sqlite3
c = sqlite3.connect(r"am4_data.db")
for r in c.execute("SELECT sql FROM sqlite_master WHERE type IN ('table','index') AND (name='my_hubs' OR tbl_name='my_hubs')"):
    print(r[0])
    print("---")
