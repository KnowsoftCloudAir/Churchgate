"""Minimal PPTX builder — works with or without python-pptx."""
from __future__ import annotations
import io
import zipfile
from xml.sax.saxutils import escape
from typing import Any, List


def build_pptx_bytes(title: str, slides: List[Any]) -> bytes:
    try:
        return _via_python_pptx(slides)
    except Exception:
        return _via_ooxml_zip(slides)


def _via_python_pptx(slides: List[Any]) -> bytes:
    from pptx import Presentation as PP
    from pptx.util import Inches, Pt
    from pptx.dml.color import RgbColor
    from pptx.enum.shapes import MSO_SHAPE

    prs = PP()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]
    for s in slides:
        slide = prs.slides.add_slide(blank)
        shape = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), prs.slide_width, prs.slide_height
        )
        shape.fill.solid()
        shape.fill.fore_color.rgb = RgbColor(0x0F, 0x17, 0x2A)
        shape.line.fill.background()
        title_box = slide.shapes.add_textbox(Inches(0.6), Inches(0.5), Inches(12), Inches(1.2))
        tf = title_box.text_frame
        tf.word_wrap = True
        run = tf.paragraphs[0].add_run()
        run.text = (getattr(s, "title", None) or "Slide")[:200]
        run.font.size = Pt(36)
        run.font.bold = True
        run.font.color.rgb = RgbColor(0x5E, 0xEA, 0xD4)
        body_box = slide.shapes.add_textbox(Inches(0.6), Inches(2.0), Inches(12), Inches(4.5))
        bf = body_box.text_frame
        bf.word_wrap = True
        lines = (getattr(s, "body", None) or "").splitlines() or [""]
        for i, line in enumerate(lines[:20]):
            para = bf.paragraphs[0] if i == 0 else bf.add_paragraph()
            run = para.add_run()
            run.text = line[:300]
            run.font.size = Pt(20)
            run.font.color.rgb = RgbColor(0xE2, 0xE8, 0xF0)
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _slide_xml(i: int, s: Any) -> str:
    title = escape((getattr(s, "title", None) or f"Slide {i}")[:200])
    raw_body = (getattr(s, "body", None) or "")[:2000]
    parts = []
    for line in raw_body.splitlines() or [""]:
        parts.append(
            "<a:p><a:r><a:rPr lang=\"en-US\" sz=\"2000\" dirty=\"0\">"
            "<a:solidFill><a:srgbClr val=\"E2E8F0\"/></a:solidFill></a:rPr>"
            f"<a:t>{escape(line)}</a:t></a:r></a:p>"
        )
    body_ps = "".join(parts)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        "<p:cSld><p:bg><p:bgPr><a:solidFill><a:srgbClr val=\"0F172A\"/></a:solidFill>"
        "<a:effectLst/></p:bgPr></p:bg><p:spTree>"
        "<p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"\"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>"
        "<p:grpSpPr><a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext cx=\"0\" cy=\"0\"/>"
        "<a:chOff x=\"0\" y=\"0\"/><a:chExt cx=\"0\" cy=\"0\"/></a:xfrm></p:grpSpPr>"
        "<p:sp><p:nvSpPr><p:cNvPr id=\"2\" name=\"Title\"/><p:cNvSpPr txBox=\"1\"/><p:nvPr/></p:nvSpPr>"
        "<p:spPr><a:xfrm><a:off x=\"457200\" y=\"365760\"/><a:ext cx=\"11277600\" cy=\"914400\"/></a:xfrm>"
        "<a:prstGeom prst=\"rect\"><a:avLst/></a:prstGeom></p:spPr>"
        "<p:txBody><a:bodyPr wrap=\"square\"/><a:lstStyle/>"
        "<a:p><a:r><a:rPr lang=\"en-US\" sz=\"3600\" b=\"1\" dirty=\"0\">"
        "<a:solidFill><a:srgbClr val=\"5EEAD4\"/></a:solidFill></a:rPr>"
        f"<a:t>{title}</a:t></a:r></a:p></p:txBody></p:sp>"
        "<p:sp><p:nvSpPr><p:cNvPr id=\"3\" name=\"Body\"/><p:cNvSpPr txBox=\"1\"/><p:nvPr/></p:nvSpPr>"
        "<p:spPr><a:xfrm><a:off x=\"457200\" y=\"1463040\"/><a:ext cx=\"11277600\" cy=\"4572000\"/></a:xfrm>"
        "<a:prstGeom prst=\"rect\"><a:avLst/></a:prstGeom></p:spPr>"
        f"<p:txBody><a:bodyPr wrap=\"square\"/><a:lstStyle/>{body_ps}</p:txBody></p:sp>"
        "</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>"
    )


def _via_ooxml_zip(slides: List[Any]) -> bytes:
    if not slides:
        class _S:
            title = "Empty"
            body = ""
        slides = [_S()]
    n = len(slides)
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/ppt/presentation.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
        + "".join(
            f'<Override PartName="/ppt/slides/slide{i}.xml" '
            f'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
            for i in range(1, n + 1)
        )
        + "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="ppt/presentation.xml"/></Relationships>'
    )
    pres_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(
            f'<Relationship Id="rId{i}" '
            f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" '
            f'Target="slides/slide{i}.xml"/>'
            for i in range(1, n + 1)
        )
        + "</Relationships>"
    )
    sld_entries = "".join(f'<p:sldId id="{255 + i}" r:id="rId{i}"/>' for i in range(1, n + 1))
    presentation = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" saveSubsetFonts="1">'
        f"<p:sldMasterIdLst/><p:sldIdLst>{sld_entries}</p:sldIdLst>"
        '<p:sldSz cx="12192000" cy="6858000"/><p:notesSz cx="6858000" cy="9144000"/>'
        "</p:presentation>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("ppt/presentation.xml", presentation)
        z.writestr("ppt/_rels/presentation.xml.rels", pres_rels)
        for i, s in enumerate(slides, 1):
            z.writestr(f"ppt/slides/slide{i}.xml", _slide_xml(i, s))
    return buf.getvalue()
