import fitz  # PyMuPDF
import os

class PDFStamper:
    @staticmethod
    def stamp_pdf(pdf_path, signature_img_path, output_path, page_num=0, x=400, y=700, width=150, height=60):
        try:
            doc = fitz.open(pdf_path)
            
            if page_num >= len(doc):
                page_num = len(doc) - 1
            
            page = doc[page_num]
            
            # Detectamos la rotación de la página
            page_rot = page.rotation
            
            # El rectángulo de destino
            rect = fitz.Rect(x, y, x + width, y + height)
            
            # Insertamos la imagen.
            # CORRECCIÓN: Usamos rotación positiva para alinear con la vista del usuario
            page.insert_image(
                rect, 
                filename=signature_img_path, 
                keep_proportion=True, 
                overlay=True,
                rotate=page_rot  # <--- CAMBIO: Quitamos el signo negativo
            )
            
            doc.save(output_path, garbage=4, deflate=True, clean=True)
            doc.close()
            return True, "Firma aplicada correctamente."
        except Exception as e:
            return False, str(e)