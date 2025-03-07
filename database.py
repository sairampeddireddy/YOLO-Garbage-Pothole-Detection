import sqlite3

db_path = r"C:\Users\Sai\Downloads\major\data.sqlite"  # Use raw string (r"...") for Windows paths

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get table names
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
print("Tables in database:", tables)

# View first 10 rows from each table
for table in tables:
    table_name = table[0]
    print(f"\nData from {table_name}:")
    cursor.execute(f"SELECT * FROM {table_name} LIMIT 10;")
    rows = cursor.fetchall()
    for row in rows:
        print(row)

conn.close()
