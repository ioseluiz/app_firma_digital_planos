import fitz  # PyMuPDF
import os


class PDFStamper:
    @staticmethod
    def stamp_pdf(
        pdf_path,
        signature_img_path,
        output_path,
        page_num=0,
        x=400,
        y=700,
        width=150,
        height=60,
    ):
        """
        Coloca la imagen de la firma en una posición específica (coordenadas por defecto).
        En una app real, estas coordenadas vendrían de la configuración o input del usuario.
        """
        try:
            doc = fitz.open(pdf_path)
            # Asegurarse que la página existe, si no, usar la última o la primera
            if page_num >= len(doc):
                page_num = len(doc) - 1

            page = doc[page_num]

            # Rectángulo donde irá la firma (x0, y0, x1, y1)
            rect = fitz.Rect(x, y, x + width, y + height)

            # Insertar imagen
            page.insert_image(rect, filename=signature_img_path)

            doc.save(output_path)
            doc.close()
            return True, "Firma aplicada correctamente."
        except Exception as e:
            return False, str(e)
