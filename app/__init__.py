import sys

# PyMuPDF 2.x importa al iniciar dos extras opcionales con IA que esta app no usa:
# el análisis de maquetación (pymupdf.layout) y la conversión a Markdown (pymupdf4llm),
# que cargan onnxruntime y añaden ~0.9 s al arranque y a cada proceso de sellado.
# Marcarlos como no disponibles hace que PyMuPDF los omita (los importa dentro de
# try/except ImportError) sin afectar a la lectura, render ni escritura de PDFs.
for _optional in ("pymupdf.layout", "pymupdf4llm"):
    sys.modules.setdefault(_optional, None)
