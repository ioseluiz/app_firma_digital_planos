import sqlite3
import os
from app.utils.paths import get_app_data_path
import bcrypt 

class Database:
    def __init__(self):
        self.db_folder = get_app_data_path()
        self.db_path = os.path.join(self.db_folder, "sealer.db")
        self.init_db()

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    def init_db(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Tabla Usuarios
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash BLOB NOT NULL, 
                role TEXT NOT NULL,
                signature_path TEXT
            )
        ''')
        
        # --- CORRECCIÓN AQUÍ: Cambiamos 'audit_log' por 'history' ---
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT,
                filename TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Admin por defecto
        cursor.execute("SELECT count(*) FROM users")
        if cursor.fetchone()[0] == 0:
            password = b"admin123"
            salt = bcrypt.gensalt()
            hashed = bcrypt.hashpw(password, salt)
            cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)", 
                           ("admin", hashed, "admin"))
            print("Usuario admin creado.")

        conn.commit()
        conn.close()