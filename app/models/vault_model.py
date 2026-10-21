"""
Modelo de un solo usuario: contraseña maestra, secretos cifrados y registro de sellado.

Secretos (cifrados con AES-256-GCM, clave derivada de la contraseña maestra):
  - stamp_png:  imagen del sello+firma
  - hmac_key:   clave para generar los IDs de sellado
  - owner_pw:   contraseñas de propietario de cada PDF emitido (en seal_log)
Configuración en claro (no sensible): tema, nombre, tamaño del sello, proyecto.
"""
import json
import os

from app.models.database import Database
from app.utils import crypto_vault
from app.utils.security import hash_password, verify_password

MIN_PASSWORD_LEN = 8


class VaultModel:
    def __init__(self, db=None):
        self.db = db or Database()
        self.conn = self.db.get_connection()
        self._key = None

    # ------------------------------------------------------------ settings
    def get_setting(self, key, default=None):
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        return json.loads(row[0])

    def set_setting(self, key, value):
        self.conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )
        self.conn.commit()

    # ------------------------------------------------------- master password
    def is_initialized(self):
        return self.get_setting("password_hash") is not None

    @property
    def is_unlocked(self):
        return self._key is not None

    def setup(self, password):
        if self.is_initialized():
            raise crypto_vault.VaultError("La bóveda ya está configurada.")
        if len(password) < MIN_PASSWORD_LEN:
            raise crypto_vault.VaultError(f"La contraseña debe tener al menos {MIN_PASSWORD_LEN} caracteres.")
        salt = crypto_vault.new_salt()
        self.set_setting("password_hash", hash_password(password).decode("ascii"))
        self.set_setting("kdf_salt", salt.hex())
        self._key = crypto_vault.derive_key(password, salt)
        self.set_secret("hmac_key", os.urandom(32))

    def unlock(self, password):
        stored = self.get_setting("password_hash")
        if not stored or not verify_password(password, stored.encode("ascii")):
            return False
        self._key = crypto_vault.derive_key(password, bytes.fromhex(self.get_setting("kdf_salt")))
        return True

    def lock(self):
        self._key = None

    def change_password(self, old_password, new_password):
        if len(new_password) < MIN_PASSWORD_LEN:
            raise crypto_vault.VaultError(f"La contraseña debe tener al menos {MIN_PASSWORD_LEN} caracteres.")
        if not self.unlock(old_password):
            raise crypto_vault.VaultError("La contraseña actual no es correcta.")
        old_key = self._key
        secrets = {name: crypto_vault.decrypt(old_key, blob, name.encode())
                   for name, blob in self.conn.execute("SELECT name, blob FROM secrets")}
        logs = [(rid, crypto_vault.decrypt(old_key, blob, b"owner_pw"))
                for rid, blob in self.conn.execute(
                    "SELECT id, owner_pw_enc FROM seal_log WHERE owner_pw_enc IS NOT NULL")]

        salt = crypto_vault.new_salt()
        new_key = crypto_vault.derive_key(new_password, salt)
        with self.conn:
            for name, data in secrets.items():
                self.conn.execute("UPDATE secrets SET blob = ? WHERE name = ?",
                                  (crypto_vault.encrypt(new_key, data, name.encode()), name))
            for rid, data in logs:
                self.conn.execute("UPDATE seal_log SET owner_pw_enc = ? WHERE id = ?",
                                  (crypto_vault.encrypt(new_key, data, b"owner_pw"), rid))
            self.conn.execute("UPDATE settings SET value = ? WHERE key = 'password_hash'",
                              (json.dumps(hash_password(new_password).decode("ascii")),))
            self.conn.execute("UPDATE settings SET value = ? WHERE key = 'kdf_salt'",
                              (json.dumps(salt.hex()),))
        self._key = new_key

    # --------------------------------------------------------------- secrets
    def _require_key(self):
        if self._key is None:
            raise crypto_vault.VaultError("La bóveda está bloqueada.")
        return self._key

    def set_secret(self, name, data):
        blob = crypto_vault.encrypt(self._require_key(), data, name.encode())
        self.conn.execute(
            "INSERT INTO secrets (name, blob) VALUES (?, ?) "
            "ON CONFLICT(name) DO UPDATE SET blob = excluded.blob",
            (name, blob),
        )
        self.conn.commit()

    def get_secret(self, name):
        row = self.conn.execute("SELECT blob FROM secrets WHERE name = ?", (name,)).fetchone()
        if row is None:
            return None
        return crypto_vault.decrypt(self._require_key(), row[0], name.encode())

    def hmac_key(self):
        return self.get_secret("hmac_key")

    # ----------------------------------------------------------------- stamp
    def save_stamp(self, png_bytes, width_mm, height_mm, confirmed=False):
        self.set_secret("stamp_png", png_bytes)
        self.set_setting("stamp_size_mm", [width_mm, height_mm])
        self.set_setting("stamp_size_confirmed", bool(confirmed))

    def load_stamp(self):
        """(png_bytes, width_mm, height_mm) o None si no hay sello configurado."""
        png = self.get_secret("stamp_png")
        size = self.get_setting("stamp_size_mm")
        if png is None or size is None:
            return None
        return png, size[0], size[1]

    def set_stamp_size(self, width_mm, height_mm, confirmed=True):
        self.set_setting("stamp_size_mm", [width_mm, height_mm])
        self.set_setting("stamp_size_confirmed", bool(confirmed))

    # ------------------------------------------------------------- seal log
    def log_seal(self, result, owner_pw):
        enc_pw = crypto_vault.encrypt(self._require_key(), owner_pw.encode("utf-8"), b"owner_pw")
        with self.conn:
            for page_index, page_id in sorted(result["page_ids"].items()):
                self.conn.execute(
                    "INSERT INTO seal_log (seal_date, src_path, src_sha256, out_path, out_sha256, "
                    "doc_id, page_index, page_id, owner_pw_enc) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (result["date"], result["src"], result["src_sha256"], result["out"],
                     result["out_sha256"], result["doc_id"], page_index, page_id, enc_pw),
                )

    def known_output_hashes(self):
        return {r[0] for r in self.conn.execute("SELECT DISTINCT out_sha256 FROM seal_log")}

    def sealed_pages_by_hash(self, sha256):
        rows = self.conn.execute("SELECT page_index FROM seal_log WHERE out_sha256 = ?", (sha256,))
        return sorted({r[0] for r in rows})

    def find_by_hash(self, sha256):
        return self._rows("WHERE out_sha256 = ?", (sha256,))

    def find_by_doc_id(self, doc_id):
        return self._rows("WHERE doc_id = ?", (doc_id,))

    def _rows(self, where, params):
        cur = self.conn.execute(
            "SELECT seal_date, src_path, out_path, out_sha256, doc_id, page_index, page_id, timestamp "
            f"FROM seal_log {where} ORDER BY page_index", params)
        cols = ["seal_date", "src_path", "out_path", "out_sha256", "doc_id", "page_index", "page_id", "timestamp"]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    # ------------------------------------------------------------- migration
    def legacy_signature_paths(self):
        """Firmas de la versión anterior (copias en claro) que se pueden importar."""
        if not self.db.has_legacy_users():
            return []
        rows = self.conn.execute(
            "SELECT signature_path FROM users WHERE signature_path IS NOT NULL").fetchall()
        return [r[0] for r in rows if r[0] and os.path.exists(r[0])]

    def drop_legacy_users(self):
        if self.db.has_legacy_users():
            with self.conn:
                self.conn.execute("DROP TABLE users")
