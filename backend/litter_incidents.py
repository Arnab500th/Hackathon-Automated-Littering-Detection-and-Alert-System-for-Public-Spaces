import sqlite3 as SQL

with SQL.connect("main.db") as conn:
    
    cursor=conn.cursor()

    create_table_query="""
    CREATE TABLE IF NOT EXISTS users(
    
    id                  INTEGER PRIMARY KEY AUTOINCREMENT, 
    timestamp           DATETIME DEFAULT CURRENT_TIMESTAMP, 
    camera_id           VARCHAR(50) NOT NULL, 
    trash_type          VARCHAR NOT NULL, 
    trash_confidence    FLOAT, 
    offender_type       VARCHAR(20) NOT NULL, 
    license_plate       VARCHAR(20), 
    person_image_path   TEXT, 
    vehicle_image_path  TEXT, 
    full_frame_path     TEXT, 
    alert_sent          BOOLEAN DEFAULT FALSE 
    )"""

    cursor.execute(create_table_query)
    conn.commit()
    print("Table created successfully")

