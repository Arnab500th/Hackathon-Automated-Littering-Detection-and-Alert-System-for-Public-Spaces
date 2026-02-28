import sqlite3 as SQL

with SQL.connect("main.db") as conn:
    cursor=conn.cursor()

    create_table_querry="""
    CREATE TABLE IF NOT EXISTS vehicle(
    id              INTEGER PRIMARY KEY AUTOINCREMENT, 
    license_plate   VARCHAR(20) UNIQUE NOT NULL , 
    first_seen      DATETIME, 
    last_seen       DATETIME, 
    incident_count  INTEGER DEFAULT 1
    )"""

    cursor.execute(create_table_querry)
    conn.commit()
    print("Table created successfully")



with SQL.connect("main.db") as conn:
    cursor=conn.cursor()

    insert_query = "INSERT INTO vehicle (id,license_plate) VALUES (?, ?)"
    user_data = [
        (1,'TN37M275'),
        (2,'WB37MW75'),
        (3,'WB88M275')
        ]
    cursor.executemany(insert_query, user_data)
    conn.commit()
    print("Data inserted successfully")
