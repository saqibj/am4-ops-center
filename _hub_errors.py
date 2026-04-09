import sqlite3
c = sqlite3.connect(r"am4_data.db")
for r in c.execute("""
    SELECT a.iata, mh.last_extract_status, mh.last_extract_error, mh.last_extracted_at
    FROM my_hubs mh JOIN airports a ON mh.airport_id = a.id
    WHERE mh.last_extract_status = 'error'
"""):
    print(r[0], "|", r[1], "|", r[3])
    print("  error:", r[2])
    print()
