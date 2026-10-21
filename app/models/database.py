import os
import sqlite3

from app.utils.paths import get_app_data_path


class Database:
    def __init__(self, db_path=None):
        if db_path is None:
            db_path = os.path.join(get_app_data_path(), "sealer.db")
        self.db_path = db_path
        self.init_db()

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    def init_db(self):
        conn = self.get_connection()
        cursor = conn.cursor()

        # Configuración (valores no sensibles) y secretos (cifrados con la clave maestra)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value BLOB
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS secrets (
                name TEXT PRIMARY KEY,
                blob BLOB NOT NULL
            )
        ''')

        # Registro de auditoría: una fila por hoja sellada
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS seal_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                seal_date TEXT,
                src_path TEXT,
                src_sha256 TEXT,
                out_path TEXT,
                out_sha256 TEXT,
                doc_id TEXT,
                page_index INTEGER,
                page_id TEXT,
                owner_pw_enc BLOB
            )
        ''')
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_seal_out ON seal_log(out_sha256)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_seal_doc ON seal_log(doc_id)")

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT,
                filename TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()
        conn.close()

    def has_legacy_users(self):
        """True si existe la tabla de usuarios de la versión multiusuario anterior."""
        conn = self.get_connection()
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
            ).fetchone()
            return row is not None
        finally:
            conn.close()
