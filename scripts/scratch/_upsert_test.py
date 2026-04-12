import sqlite3
c = sqlite3.connect(r"am4_data.db")
try:
    c.execute("INSERT INTO my_hubs (airport_id, notes, is_active, updated_at) VALUES (-9999, 'test', 1, datetime('now')) ON CONFLICT(airport_id) DO UPDATE SET notes='test2'")
    print("UPSERT OK")
    c.execute("DELETE FROM my_hubs WHERE airport_id = -9999")
    c.commit()
except Exception as e:
    print("FAIL:", type(e).__name__, e)
