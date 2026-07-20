import os
import sqlite3

DB_PATH = os.getenv("VANDA_DB_PATH", "./database.sqlite")


def get_connection(db_path=None):
	conn = sqlite3.connect(db_path or DB_PATH)
	conn.row_factory = sqlite3.Row
	return conn
