import sqlite3
c = sqlite3.connect(r"am4_data.db")
cur = c.execute("""
    UPDATE my_hubs
    SET last_extract_status = NULL,
        last_extract_error = NULL
    WHERE last_extract_status = 'error'
""")
c.commit()
print("Cleared error state on", cur.rowcount, "hubs")
c.close()
