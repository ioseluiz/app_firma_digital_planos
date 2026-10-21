import multiprocessing
import sys
import traceback

from PyQt6.QtWidgets import QApplication, QMessageBox


def selftest():
    """Comprobación sin interfaz del ejecutable empaquetado: sella un PDF temporal
    (secuencial y con procesos) y verifica el resultado. Código de salida 0 = OK."""
    import io
    import os
    import tempfile

    import pymupdf
    from PIL import Image, ImageDraw

    from app.utils import pdf_stamper, seal_id
    from app.utils.crypto_vault import decrypt, derive_key, encrypt
    from app.workers.signing_worker import SigningWorker

    img = Image.new("RGBA", (440, 230), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle((2, 2, 437, 227), outline=(0, 0, 0, 255), width=4)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    key = derive_key("selftest", b"0" * 16, n=2 ** 10)
    assert decrypt(key, encrypt(key, b"ok")) == b"ok"

    QApplication(sys.argv)
    with tempfile.TemporaryDirectory() as tmp:
        jobs = []
        for i in range(2):
            src = os.path.join(tmp, f"in{i}.pdf")
            doc = pymupdf.open()
            doc.new_page(width=34 * 72, height=22 * 72)
            doc.save(src)
            doc.close()
            jobs.append({"key": src, "args": dict(
                src_path=src, out_path=os.path.join(tmp, f"out{i}.pdf"),
                placements=[(0, 1500, 900, 12.0)], stamp_png=buf.getvalue(), stamp_w_mm=57.0,
                stamp_h_mm=29.2, hmac_key=b"k" * 32, owner_pw=pdf_stamper.generate_owner_password())})
        for workers in (1, 2):
            results = []
            worker = SigningWorker(jobs, max_workers=workers)
            worker.job_finished.connect(results.append)
            worker.run()   # en este mismo hilo
            assert len(results) == 2 and all(r["ok"] for r in results), results
        with pymupdf.open(os.path.join(tmp, "out0.pdf")) as d:
            assert seal_id.parse_keywords(d.metadata["keywords"])[1] == [0]
    return 0


def main():
    if "--version" in sys.argv:
        from app import __version__
        print(__version__)
        sys.exit(0)
    if "--selftest" in sys.argv:
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            sys.exit(selftest())
        except Exception:
            traceback.print_exc()
            sys.exit(1)

    app = QApplication(sys.argv)
    app.setApplicationName("DigitalSealer")
    from app import __version__
    app.setApplicationVersion(__version__)
    # La ventana principal se oculta al bloquear; la app termina solo al cerrarla
    app.setQuitOnLastWindowClosed(False)

    try:
        # Importamos aquí para atrapar errores de dependencias
        from app.controllers.main_controller import MainController

        controller = MainController()
        if not controller.start():
            sys.exit(0)

        sys.exit(app.exec())

    except Exception as e:
        # En modo sin consola, usamos QMessageBox para mostrar el error fatal
        error_msg = str(e)
        trace_info = traceback.format_exc()

        # Mostramos la ventana de error
        QMessageBox.critical(None, "Error Crítico",
                             f"Ocurrió un error inesperado y el programa debe cerrarse:\n\n{error_msg}\n\n{trace_info}")
        sys.exit(1)


if __name__ == "__main__":
    # Necesario para el sellado en paralelo (ProcessPoolExecutor) en el .exe de PyInstaller
    multiprocessing.freeze_support()
    main()
