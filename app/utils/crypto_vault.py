"""
Cifrado de secretos en disco (imagen del sello, clave del ID, contraseñas de propietario).

- Clave de 256 bits derivada de la contraseña maestra con scrypt.
- AES-256-GCM (autenticado): un archivo alterado o una contraseña errónea fallan al descifrar.
"""
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

SALT_BYTES = 16
NONCE_BYTES = 12
# Parámetros scrypt (≈ 64 MB, ~0.2-0.5 s): caro para fuerza bruta, rápido para el usuario
SCRYPT_N = 2 ** 16
SCRYPT_R = 8
SCRYPT_P = 1


class VaultError(Exception):
    pass


def new_salt():
    return os.urandom(SALT_BYTES)


def derive_key(password, salt, n=SCRYPT_N):
    kdf = Scrypt(salt=salt, length=32, n=n, r=SCRYPT_R, p=SCRYPT_P)
    return kdf.derive(password.encode("utf-8"))


def encrypt(key, data, aad=b""):
    nonce = os.urandom(NONCE_BYTES)
    return nonce + AESGCM(key).encrypt(nonce, data, aad)


def decrypt(key, blob, aad=b""):
    if not blob or len(blob) <= NONCE_BYTES:
        raise VaultError("Dato cifrado inválido.")
    try:
        return AESGCM(key).decrypt(blob[:NONCE_BYTES], blob[NONCE_BYTES:], aad)
    except InvalidTag as e:
        raise VaultError("No se pudo descifrar (contraseña incorrecta o dato alterado).") from e
