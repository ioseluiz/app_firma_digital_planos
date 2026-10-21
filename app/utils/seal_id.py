"""
Identificadores de sellado y marca en metadatos.

El ID de cada hoja es HMAC-SHA256(clave local secreta, hash del PDF original +
hoja + fecha), así nadie sin la clave puede fabricar un ID válido, y el mismo
sello/firma extraído queda ligado al documento y hoja donde se emitió.
"""
import base64
import hashlib
import hmac
import re

MARKER = "DigitalSealer"
_KEYWORDS_RE = re.compile(r"DigitalSealer;doc=([A-Z0-9-]+);pages=([0-9,]*)")


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _code(key, message, length=10):
    digest = hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()
    code = base64.b32encode(digest).decode("ascii").rstrip("=")[:length]
    return f"{code[:length // 2]}-{code[length // 2:]}"


def page_seal_id(key, source_sha256, page_index, date_iso):
    return _code(key, f"page|{source_sha256}|{page_index}|{date_iso}")


def document_seal_id(key, source_sha256, date_iso):
    return _code(key, f"doc|{source_sha256}|{date_iso}")


def build_keywords(doc_id, page_indices):
    pages = ",".join(str(i) for i in sorted(page_indices))
    return f"{MARKER};doc={doc_id};pages={pages}"


def parse_keywords(keywords):
    """Devuelve (doc_id, [páginas selladas]) si el PDF fue sellado por DigitalSealer, si no None."""
    if not keywords:
        return None
    m = _KEYWORDS_RE.search(keywords)
    if not m:
        return None
    pages = [int(p) for p in m.group(2).split(",") if p != ""]
    return m.group(1), pages
