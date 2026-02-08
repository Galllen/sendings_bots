import sqlite3
from threading import Lock

db="data.db"
db_lock = Lock()

def get_con():
    conn = sqlite3.connect(db,check_same_thread=False)