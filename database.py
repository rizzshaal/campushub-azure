import os
import mysql.connector


def get_db_connection():
    return mysql.connector.connect(
        host=os.environ["rizz-campushub.mysql.database.azure.com"],
        port=int(os.getenv("3306", "3306")),
        user=os.environ["rizzshaal"],
        password=os.environ["rishal@03"],
        database=os.environ["Azure_campus"],
        connection_timeout=15,
    )