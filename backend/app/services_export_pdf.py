"""Construcción de PDFs: facsímil buscable y transcripción legible."""
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from PIL import Image
import io, os

def _register_font():
    # DejaVu incluye enie, tildes y signos historicos basicos; se incrusta en el PDF
    candidates = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "C:/Windows/Fonts/arial.ttf"]
    for c in candidates:
        if os.path.exists(c):
            try:
                pdfmetrics.registerFont(TTFont("Servator", c))
                return "Servator"
            except Exception:
                pass
    return "Helvetica"

def build_pdf(doc_id, out_path, mode="pdf-facsimil", text_source="revised_fallback_auto", storage=None):
    from app.models import Document, Page, Line
    from app.services_ocr import export_page_ocr
    from xml.sax.saxutils import escape
    d = Document.query.get(doc_id)
    pages = Page.query.filter_by(document_id=doc_id).order_by(Page.order_index).all()
    font = _register_font()
    styles = getSampleStyleSheet()
    if mode == "pdf-lectura":
        doc = SimpleDocTemplate(out_path, pagesize=A4)
        story = [Paragraph(f"{d.title} — transcripción para leer", styles["Title"]),
                 Paragraph(f"Signatura: {d.signature or '—'} · Páginas: {len(pages)}", styles["Normal"]), Spacer(1, 12)]
        pending = 0
        for pg in pages:
            story.append(Paragraph(f"Página {pg.order_index+1} (folio {pg.folio or '—'})", styles["Heading3"]))
            ocr = export_page_ocr(pg.id, text_source)
            if ocr:
                txt = ocr['selected_transcription']
                if txt is None:
                    story.append(Paragraph('[Doble lectura pendiente de selección y revisión]', styles['Normal']))
                    pending += 1
                else:
                    if ocr['review_status'] == 'automatic':
                        story.append(Paragraph('[Transcripción automática; pendiente de revisión]', styles['Normal']))
                        pending += 1
                    elif ocr['review_status'] == 'previous_line_review':
                        story.append(Paragraph('[Revisión anterior de Kraken; puede contener renglones automáticos]', styles['Normal']))
                    for row in txt.splitlines() or ['']:
                        story.append(Paragraph(escape(row) or '&nbsp;', styles['Normal']))
                story.append(Spacer(1, 12))
                continue
            for l in Line.query.filter_by(page_id=pg.id).order_by(Line.order_index).all():
                txt = l.revised_text if (l.revised_text is not None and text_source.startswith("revised")) else l.auto_text
                if l.state in ("illegible", "bad_cut") or not (l.revised_text or l.auto_text):
                    pending += 1
                    txt = (txt or "") + " [pendiente de revisión]"
                story.append(Paragraph(escape(txt or ""), styles["Normal"]))
            story.append(Spacer(1, 12))
        doc.build(story)
        return {"mode": mode, "pages": len(pages), "pending": pending, "mixed": True}
    else:
        # facsimil: imagen original + capa de texto invisible por renglon (misma geometria)
        # Implementado con reportlab (sin inventar nivel palabra; usa poligono de renglon).
        from reportlab.pdfgen import canvas as _canvas
        c = _canvas.Canvas(out_path, pagesize=(595, 842))
        for pg in pages:
            img_path = storage.get_path(pg.image_key) if storage else None
            im = Image.open(img_path).convert("RGB")
            w, h = im.width, im.height
            pw, ph = 595.0, 842.0
            scale = min(pw / w, ph / h)
            dw, dh = w * scale, h * scale
            ox, oy = (pw - dw) / 2, (ph - dh) / 2
            c.drawImage(img_path, ox, oy, dw, dh)
            c.saveState()
            chosen_font = font if font in c.getAvailableFonts() else "Helvetica"
            ocr = export_page_ocr(pg.id, text_source)
            if ocr:
                txt = ocr['selected_transcription']
                if txt:
                    # Sin geometría inferida: una capa invisible a nivel de página,
                    # buscable pero sin pretender alinear palabras con la imagen.
                    obj = c.beginText(2, ph - 10)
                    obj.setTextRenderMode(3)
                    obj.setFont(chosen_font, 2)
                    for row in txt.splitlines():
                        obj.textLine(row)
                    c.drawText(obj)
                c.restoreState()
                labels = {'automatic': 'Transcripción automática: pendiente de revisión',
                          'pending': 'Lecturas pendientes de selección y revisión',
                          'previous_line_review': 'Revisión anterior de Kraken; puede contener texto automático'}
                if ocr['review_status'] in labels:
                    c.saveState()
                    c.setFillColorRGB(1, 1, 1)
                    c.rect(0, 0, pw, 14, fill=1, stroke=0)
                    c.setFillColorRGB(0, 0, 0)
                    c.setFont(chosen_font, 7)
                    c.drawString(8, 4, labels[ocr['review_status']])
                    c.restoreState()
                c.showPage()
                continue
            for l in Line.query.filter_by(page_id=pg.id).order_by(Line.order_index).all():
                txt = l.revised_text if (l.revised_text is not None and text_source.startswith("revised")) else (l.auto_text or "")
                if not txt.strip() or not l.polygon:
                    continue
                try:
                    xs = [p[0] for p in l.polygon]; ys = [p[1] for p in l.polygon]
                    x0, y0 = min(xs) * scale + ox, min(ys) * scale + oy
                    obj = c.beginText(x0, ph - y0)
                    obj.setTextRenderMode(3)
                    obj.setFont(chosen_font, 8)
                    obj.textLine(txt[:500])
                    c.drawText(obj)
                except Exception:
                    continue
            c.restoreState()
            c.showPage()
        c.save()
        return {"mode": mode, "pages": len(pages)}
