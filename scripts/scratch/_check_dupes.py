import sqlite3
c = sqlite3.connect(r"am4_data.db")
# Check for rows that would violate a plain unique constraint
dupes = list(c.execute("""
    SELECT iata, COUNT(*) FROM airports
    WHERE iata IS NULL OR TRIM(iata) = ''
    GROUP BY iata HAVING COUNT(*) > 1
"""))
print("NULL/empty iata dupes:", dupes)
print("NULL count:", c.execute("SELECT COUNT(*) FROM airports WHERE iata IS NULL OR TRIM(iata)=''").fetchone()[0])
