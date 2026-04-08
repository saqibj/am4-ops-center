import sqlite3
c = sqlite3.connect(r"am4_data.db")
for r in c.execute("SELECT sql FROM sqlite_master WHERE tbl_name='airports' AND sql IS NOT NULL"):
    print(r[0]); print("---")
