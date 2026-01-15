from app.models.database import Database
from app.utils.security import verify_password, hash_password
import datetime


class UserModel:
    def __init__(self):
        self.db = Database()
        self.conn = self.db.get_connection()

    def authenticate(self, username, password):
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, username, password_hash, role, signature_path FROM users WHERE username = ?",
            (username,),
        )
        user = cursor.fetchone()

        if user and verify_password(password, user[2]):
            return {
                "id": user[0],
                "username": user[1],
                "role": user[3],
                "signature_path": user[4],
            }
        return None

    def create_user(self, username, password, role):
        try:
            pwd_hash = hash_password(password)
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, pwd_hash, role),
            )
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error creating user: {e}")
            return False

    def update_signature(self, user_id, signature_path):
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE users SET signature_path = ? WHERE id = ?",
            (signature_path, user_id),
        )
        self.conn.commit()
        self.log_action(user_id, "UPDATE_SIG", "Signature File")

    def log_action(self, user_id, action, filename):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO history (user_id, action, filename) VALUES (?, ?, ?)",
            (user_id, action, filename),
        )
        self.conn.commit()

    def get_all_users(self):
        """Devuelve una lista de tuplas (id, username, role)"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, username, role FROM users")
        return cursor.fetchall()

    def delete_user(self, user_id):
        """Borra un usuario por ID"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error deleting user: {e}")
            return False

    def reset_password(self, user_id, new_password):
        """Actualiza el password de un usuario específico"""
        try:
            pwd_hash = hash_password(new_password)
            cursor = self.conn.cursor()
            cursor.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?", (pwd_hash, user_id)
            )
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error resetting password: {e}")
            return False
