import pytest

from app.models.database import Database
from app.models.vault_model import VaultModel
from app.utils.crypto_vault import VaultError


@pytest.fixture
def vault(tmp_path, monkeypatch):
    # scrypt más barato en tests
    import app.utils.crypto_vault as cv
    monkeypatch.setattr(cv, "derive_key", lambda pw, salt, n=2 ** 10, _orig=cv.derive_key: _orig(pw, salt, n))
    return VaultModel(Database(str(tmp_path / "t.db")))


def test_setup_unlock_and_wrong_password(vault):
    assert not vault.is_initialized()
    with pytest.raises(VaultError):
        vault.setup("corta")
    vault.setup("contraseña-segura")
    vault.save_stamp(b"PNGDATA", 57.0, 29.2)
    vault.lock()
    assert not vault.unlock("incorrecta")
    with pytest.raises(VaultError):
        vault.load_stamp()
    assert vault.unlock("contraseña-segura")
    assert vault.load_stamp() == (b"PNGDATA", 57.0, 29.2)


def test_stamp_is_not_stored_in_clear(vault, tmp_path):
    vault.setup("contraseña-segura")
    marker = b"MI-SELLO-SECRETO-1234567890"
    vault.save_stamp(marker, 57.0, 29.2)
    vault.conn.commit()
    assert marker not in (tmp_path / "t.db").read_bytes()


def test_change_password_keeps_secrets_and_logs(vault):
    vault.setup("contraseña-vieja")
    vault.save_stamp(b"PNG", 50, 25)
    result = {"page_ids": {0: "AAAAA-BBBBB"}, "date": "2026-10-20", "src": "a.pdf",
              "src_sha256": "s", "out": "SELLADO_a.pdf", "out_sha256": "o", "doc_id": "DDDDD-EEEEE"}
    vault.log_seal(result, "owner")
    vault.change_password("contraseña-vieja", "contraseña-nueva")
    vault.lock()
    assert not vault.unlock("contraseña-vieja")
    assert vault.unlock("contraseña-nueva")
    assert vault.load_stamp()[0] == b"PNG"
    assert vault.find_by_hash("o")[0]["page_id"] == "AAAAA-BBBBB"
    assert vault.sealed_pages_by_hash("o") == [0]
