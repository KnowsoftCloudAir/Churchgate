"""PPTX builder — python-pptx preferred; robust OOXML fallback."""
from __future__ import annotations
import io
import zipfile
from xml.sax.saxutils import escape
from typing import Any, List


def build_pptx_bytes(title: str, slides: List[Any]) -> bytes:
    try:
        return _via_python_pptx(slides)
    except Exception as e:
        print("python-pptx path failed:", e)
        return _via_ooxml_zip(title, slides)


def _via_python_pptx(slides: List[Any]) -> bytes:
    from pptx import Presentation as PP
    from pptx.util import Inches, Pt, Emu
    from pptx.dml.color import RGBColor as RgbColor
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.oxml.ns import nsmap
    from pptx.oxml import parse_xml

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
        try:
            shape.line.fill.background()
        except Exception:
            pass
        title_box = slide.shapes.add_textbox(Inches(0.6), Inches(0.5), Inches(12), Inches(1.3))
        tf = title_box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        run = p.add_run()
        run.text = (getattr(s, "title", None) or "Slide")[:200]
        run.font.size = Pt(32)
        run.font.bold = True
        run.font.color.rgb = RgbColor(0x5E, 0xEA, 0xD4)
        body_box = slide.shapes.add_textbox(Inches(0.6), Inches(2.0), Inches(12), Inches(4.8))
        bf = body_box.text_frame
        bf.word_wrap = True
        lines = (getattr(s, "body", None) or "").splitlines() or [""]
        for i, line in enumerate(lines[:24]):
            para = bf.paragraphs[0] if i == 0 else bf.add_paragraph()
            run = para.add_run()
            run.text = line[:400]
            run.font.size = Pt(18)
            run.font.color.rgb = RgbColor(0xE2, 0xE8, 0xF0)
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _via_ooxml_zip(deck_title: str, slides: List[Any]) -> bytes:
    if not slides:
        class _S:
            title = deck_title or "Presentation"
            body = ""
        slides = [_S()]
    n = len(slides)

    def slide_xml(i, s):
        title = escape((getattr(s, "title", None) or f"Slide {i}")[:200])
        lines = (getattr(s, "body", None) or "")[:2500].splitlines() or [""]
        body_ps = []
        for line in lines[:25]:
            body_ps.append(
                "<a:p><a:r><a:rPr lang=\"en-US\" sz=\"1800\">"
                "<a:solidFill><a:srgbClr val=\"E2E8F0\"/></a:solidFill></a:rPr>"
                f"<a:t>{escape(line)}</a:t></a:r></a:p>"
            )
        body = "".join(body_ps)
        return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:bg><p:bgPr><a:solidFill><a:srgbClr val="0F172A"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="Title"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="457200" y="274320"/><a:ext cx="11277600" cy="1005840"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
        <p:txBody><a:bodyPr wrap="square"/><a:lstStyle/>
          <a:p><a:r><a:rPr lang="en-US" sz="3200" b="1"><a:solidFill><a:srgbClr val="5EEAD4"/></a:solidFill></a:rPr>
          <a:t>{title}</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="3" name="Body"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="457200" y="1463040"/><a:ext cx="11277600" cy="4800600"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
        <p:txBody><a:bodyPr wrap="square"/><a:lstStyle/>{body}</p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>'''

    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
''' + "\n".join(
        f'  <Override PartName="/ppt/slides/slide{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        for i in range(1, n + 1)
    ) + "\n</Types>"

    root_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
</Relationships>'''

    pres_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
''' + "\n".join(
        f'  <Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{i}.xml"/>'
        for i in range(1, n + 1)
    ) + "\n</Relationships>"

    sld_ids = "".join(f'<p:sldId id="{256+i}" r:id="rId{i}"/>' for i in range(1, n + 1))
    presentation = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldIdLst>{sld_ids}</p:sldIdLst>
  <p:sldSz cx="12192000" cy="6858000" type="screen16x9"/>
  <p:notesSz cx="6858000" cy="9144000"/>
</p:presentation>'''

    app_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
  <Application>Eleon</Application><Slides>''' + str(n) + '''</Slides>
</Properties>'''
    core_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:title>{escape(deck_title or "Eleon")}</dc:title>
  <dc:creator>Eleon Knowsoft</dc:creator>
</cp:coreProperties>'''

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("ppt/presentation.xml", presentation)
        z.writestr("ppt/_rels/presentation.xml.rels", pres_rels)
        z.writestr("docProps/app.xml", app_xml)
        z.writestr("docProps/core.xml", core_xml)
        for i, s in enumerate(slides, 1):
            z.writestr(f"ppt/slides/slide{i}.xml", slide_xml(i, s))
            z.writestr(
                f"ppt/slides/_rels/slide{i}.xml.rels",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>',
            )
    return buf.getvalue()
