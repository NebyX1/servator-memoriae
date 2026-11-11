"""Exportación de transcripciones editables para Microsoft Word y LibreOffice."""
from docx import Document as WordDocument
from docx.shared import Pt


def _xml_text(value):
    """Sustituye caracteres que XML no permite, sin perder el resto del texto."""
    def valid(char):
        code = ord(char)
        return code in (9, 10, 13) or 0x20 <= code <= 0xD7FF or 0xE000 <= code <= 0xFFFD or 0x10000 <= code <= 0x10FFFF
    return ''.join(char if valid(char) else '\ufffd' for char in (value or ''))


def build_docx(doc_id, out_path, text_source="revised_fallback_auto"):
    """Cada página escaneada comienza en una página nueva del archivo editable."""
    from app.models import Document, Page, Line
    from app.services_ocr import export_page_ocr

    source = Document.query.get(doc_id)
    if source is None:
        raise ValueError("Documento no encontrado.")
    pages = Page.query.filter_by(document_id=doc_id).order_by(Page.order_index).all()
    result = WordDocument()
    result.core_properties.title = _xml_text(source.title)
    result.add_heading(_xml_text(source.title), level=0)
    if source.signature:
        result.add_paragraph(f"Signatura: {_xml_text(source.signature)}")

    pending = 0
    for page_index, page in enumerate(pages):
        if page_index:
            result.add_page_break()
        page_title = f"Página {page.order_index + 1}"
        if page.folio:
            page_title += f" · folio {_xml_text(page.folio)}"
        result.add_heading(page_title, level=1)
        ocr = export_page_ocr(page.id, text_source)
        if ocr:
            text = ocr['selected_transcription']
            if text is None:
                result.add_paragraph('[Doble lectura pendiente de selección y revisión]')
                pending += 1
            else:
                if ocr['review_status'] == 'automatic':
                    result.add_paragraph('[Transcripción automática; pendiente de revisión]')
                    pending += 1
                elif ocr['review_status'] == 'previous_line_review':
                    result.add_paragraph('[Revisión anterior de Kraken; puede contener renglones automáticos]')
                for text_line in text.splitlines() or ['']:
                    paragraph = result.add_paragraph(_xml_text(text_line))
                    paragraph.paragraph_format.space_after = Pt(0)
            continue
        lines = Line.query.filter_by(page_id=page.id).order_by(Line.order_index).all()
        if not lines:
            result.add_paragraph("[Sin transcripción; pendiente de revisión]")
            pending += 1
        for line in lines:
            text = line.revised_text if line.revised_text is not None and text_source.startswith("revised") else line.auto_text
            text = _xml_text(text)
            paragraph = result.add_paragraph()
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.add_run(text)
            if line.state in ("illegible", "bad_cut") or not text.strip():
                paragraph.add_run(" [pendiente de revisión]" if text else "[pendiente de revisión]").italic = True
                pending += 1

    result.save(out_path)
    return {"mode": "docx", "pages": len(pages), "pending": pending}
