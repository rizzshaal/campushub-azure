from database import get_db_connection

try:
    db = get_db_connection()

    if db.is_connected():
        print("CampusHub Database Connected Successfully!")

    db.close()

except Exception as e:
    print("Database Error:", e)