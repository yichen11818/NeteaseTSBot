import sqlite3
import os

DB_PATH = "./tsbot.db"

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"Database {DB_PATH} not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get existing columns for history_items
    cursor.execute("PRAGMA table_info(history_items)")
    columns = [info[1] for info in cursor.fetchall()]

    new_columns = {
        "album": "VARCHAR(255) DEFAULT ''",
        "duration": "INTEGER",
        "cover_url": "TEXT DEFAULT ''"
    }

    print("Migrating history_items table...")
    for col_name, col_type in new_columns.items():
        if col_name not in columns:
            print(f"Adding column {col_name}...")
            try:
                cursor.execute(f"ALTER TABLE history_items ADD COLUMN {col_name} {col_type}")
            except Exception as e:
                print(f"Failed to add column {col_name}: {e}")
        else:
            print(f"Column {col_name} already exists.")

    conn.commit()
    conn.close()
    print("Migration completed.")

if __name__ == "__main__":
    migrate()
