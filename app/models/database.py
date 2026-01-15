import sqlite3
import os


class Database:
    def __init__(self, db_name="db/sealer.db"):
        os.makedirs(os.path.dirname(db_name), exist_ok=True)
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        # Tabla de Usuarios
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash BLOB NOT NULL,
                role TEXT NOT NULL, -- 'admin' o 'ingeniero'
                signature_path TEXT
            )
        """)

        # Tabla de Historial
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT,
                filename TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)

        # Crear admin por defecto si no existe (pass: admin123)
        # Nota: En prod esto se hace con un script de seed seguro
        self.cursor.execute("SELECT count(*) FROM users")
        if self.cursor.fetchone()[0] == 0:
            from app.utils.security import hash_password

            pwd = hash_password("admin123")
            self.cursor.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                ("admin", pwd, "admin"),
            )

        self.conn.commit()

    def get_connection(self):
        return self.conn
