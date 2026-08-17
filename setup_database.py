import sqlite3

conn = sqlite3.connect("eldercare.db")

with open("schema.sql", "r") as file:
    conn.executescript(file.read())

conn.close()

print("SQLite database created successfully!")