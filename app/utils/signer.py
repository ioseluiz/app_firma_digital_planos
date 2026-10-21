"""
Punto de extensión para la firma digital con certificado (PAdES).

Aún no se implementa: no hay certificado. Cuando exista, una implementación
(por ejemplo con pyHanko) recibirá el PDF ya sellado y aplanado por
`pdf_stamper.stamp_document` y le añadirá una firma criptográfica que detecta
cualquier modificación posterior y acredita la identidad del firmante.

Orden previsto: sellar (aplanado + ID) → firmar digitalmente → registrar hash.
La firma debe ir al final, porque cualquier cambio posterior la invalida.
"""


class DigitalSigner:
    """Interfaz. `sign` debe escribir en `out_path` el PDF firmado y devolver su SHA-256."""

    available = False

    def sign(self, pdf_path, out_path):
        raise NotImplementedError("La firma digital con certificado aún no está configurada.")


class NoSigner(DigitalSigner):
    """Implementación por defecto: no firma (sin certificado)."""
