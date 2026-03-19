"""Конвертер PMC NLM DTD XML → Markdown.

Извлечено из api/services/pubmed_service.py.
"""
import logging
import re
from typing import Dict, List, Optional
from xml.etree import ElementTree as ET

from .base import BaseXmlConverter, ImageUrls

logger = logging.getLogger(__name__)

_TEX_PREAMBLE_RE = re.compile(
    r'\\documentclass.*?\\begin\{document\}(.*?)\\end\{document\}',
    re.DOTALL,
)

_IMG_QUALITY_ORDER = {".jpg": 0, ".jpeg": 0, ".png": 1, ".tif": 2, ".tiff": 2, ".svg": 3, ".gif": 4}


def extract_tex(el: ET.Element) -> Optional[str]:
    """Извлекает LaTeX из <tex-math>, убирая documentclass-преамбулу и внешние $ / $$."""
    tex_el = el.find(".//tex-math")
    if tex_el is None or not tex_el.text:
        return None
    raw = tex_el.text.strip()
    m = _TEX_PREAMBLE_RE.search(raw)
    if m:
        raw = m.group(1).strip()
    if raw.startswith("$$") and raw.endswith("$$"):
        raw = raw[2:-2].strip()
    elif raw.startswith("$") and raw.endswith("$"):
        raw = raw[1:-1].strip()
    return raw if raw else None


def element_to_text(el: ET.Element) -> str:
    """Конвертирует элемент XML в текст, заменяя формулы на LaTeX-нотацию.

    <inline-formula> → $...$
    <disp-formula>   → $$...$$
    Всё остальное    → itertext()
    """
    parts: List[str] = []
    if el.text:
        parts.append(el.text)
    for child in el:
        if child.tag == "inline-formula":
            tex = extract_tex(child)
            if tex:
                parts.append(f"${tex}$")
            else:
                parts.append("".join(child.itertext()))
        elif child.tag == "disp-formula":
            tex = extract_tex(child)
            if tex:
                parts.append(f"\n\n$$\n{tex}\n$$\n\n")
            else:
                parts.append("".join(child.itertext()))
        else:
            parts.append(element_to_text(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def element_to_text_skip(el: ET.Element, skip_tags: set) -> str:
    """Как element_to_text, но пропускает дочерние элементы с тегами из skip_tags."""
    parts: List[str] = []
    if el.text:
        parts.append(el.text)
    for child in el:
        if child.tag in skip_tags:
            if child.tail:
                parts.append(child.tail)
            continue
        if child.tag == "inline-formula":
            tex = extract_tex(child)
            if tex:
                parts.append(f"${tex}$")
            else:
                parts.append("".join(child.itertext()))
        elif child.tag == "disp-formula":
            tex = extract_tex(child)
            if tex:
                parts.append(f"\n\n$$\n{tex}\n$$\n\n")
            else:
                parts.append("".join(child.itertext()))
        else:
            parts.append(element_to_text_skip(child, skip_tags))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def resolve_fig_image(fig_el: ET.Element, image_urls: ImageUrls) -> Optional[str]:
    """Находит URL изображения для элемента <fig>.

    Ищет атрибут xlink:href у <graphic> внутри фигуры и ищет совпадение в image_urls.
    Среди нескольких совпадений выбирает лучший формат: jpg > png > tif > svg > gif.
    """
    graphic = fig_el.find(".//graphic")
    if graphic is None:
        return None

    href = graphic.get("{http://www.w3.org/1999/xlink}href") or graphic.get("href") or ""
    if not href:
        return None

    base = href.rsplit(".", 1)[0] if "." in href else href
    basename = base.rsplit("/", 1)[-1]

    candidates: List[tuple] = []
    for key, url in image_urls.items():
        key_base = key.rsplit(".", 1)[0] if "." in key else key
        key_base_short = key_base.rsplit("/", 1)[-1]
        if key == href or key_base == base or key_base_short == basename:
            ext = ("." + key.rsplit(".", 1)[1].lower()) if "." in key else ""
            quality = _IMG_QUALITY_ORDER.get(ext, 3)
            candidates.append((quality, url))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def render_fig(fig: ET.Element, lines: List[str], image_urls: ImageUrls) -> None:
    """Рендерит одну фигуру в HTML: изображение + подпись."""
    fig_id = fig.get("id", "")
    label_el = fig.find("label")
    label = "".join(label_el.itertext()).strip() if label_el is not None else ""
    caption_el = fig.find(".//caption/p")
    cap = "".join(caption_el.itertext()).strip() if caption_el is not None else ""

    img_url = resolve_fig_image(fig, image_urls)
    alt = label or fig_id or "Figure"

    html_parts = ['<figure>']
    if img_url:
        html_parts.append(f'  <img src="{img_url}" alt="{alt}">')
    if label or cap:
        caption_text = f"<strong>{label}</strong> {cap}".strip() if label else cap
        html_parts.append(f'  <figcaption>{caption_text}</figcaption>')
    html_parts.append('</figure>')
    lines.append("\n" + "\n".join(html_parts) + "\n")


def render_table(table_el: ET.Element, lines: List[str]) -> None:
    """Конвертирует NLM <table> (thead/tbody/tr/th/td) в HTML-таблицу."""
    rows: List[str] = []
    rows.append("<table>")

    for thead in table_el.findall("thead"):
        rows.append("  <thead>")
        for tr in thead.findall("tr"):
            rows.append("    <tr>")
            for c in tr:
                if c.tag in ("th", "td"):
                    cell = element_to_text(c).strip().replace("\n", " ")
                    rows.append(f"      <th>{cell}</th>")
            rows.append("    </tr>")
        rows.append("  </thead>")

    for tbody in table_el.findall("tbody"):
        rows.append("  <tbody>")
        for tr in tbody.findall("tr"):
            rows.append("    <tr>")
            for c in tr:
                if c.tag in ("th", "td"):
                    cell = element_to_text(c).strip().replace("\n", " ")
                    rows.append(f"      <td>{cell}</td>")
            rows.append("    </tr>")
        rows.append("  </tbody>")

    rows.append("</table>")
    lines.append("\n" + "\n".join(rows) + "\n")


def render_table_wrap(tw: ET.Element, lines: List[str]) -> None:
    """Рендерит <table-wrap>: подпись + HTML-таблица."""
    label_el = tw.find("label")
    caption_el = tw.find(".//caption/p")
    label = element_to_text(label_el).strip() if label_el is not None else ""
    cap = element_to_text(caption_el).strip() if caption_el is not None else ""
    full_cap = f"**{label}**" if label else ""
    if cap:
        full_cap = f"{full_cap} {cap}".strip()
    if full_cap:
        lines.append(f"\n{full_cap}\n")
    table_el = tw.find(".//table")
    if table_el is not None:
        render_table(table_el, lines)


def render_section(
    sec: ET.Element,
    lines: List[str],
    level: int = 2,
    image_urls: Optional[ImageUrls] = None,
    figs_by_id: Optional[Dict[str, ET.Element]] = None,
    rendered_figs: Optional[set] = None,
) -> None:
    """Рекурсивно рендерит раздел статьи в Markdown.

    При наличии figs_by_id вставляет фигуру из <floats-group>
    сразу после первого параграфа, где на неё ссылаются через <xref ref-type="fig">.
    """
    if image_urls is None:
        image_urls = {}
    if figs_by_id is None:
        figs_by_id = {}
    if rendered_figs is None:
        rendered_figs = set()

    title_el = sec.find("title")
    if title_el is not None:
        sec_title = "".join(title_el.itertext()).strip()
        if sec_title:
            lines.append(f"{'#' * level} {sec_title}\n")

    for child in sec:
        tag = child.tag
        if tag == "title":
            continue
        elif tag == "p":
            inner_tables = child.findall("table-wrap")
            if inner_tables:
                text = element_to_text_skip(child, skip_tags={"table-wrap"}).strip()
                if text:
                    lines.append(f"{text}\n")
                for tw in inner_tables:
                    render_table_wrap(tw, lines)
            else:
                text = element_to_text(child).strip()
                if text:
                    lines.append(f"{text}\n")
            if figs_by_id:
                for xref in child.findall('.//xref[@ref-type="fig"]'):
                    rid = xref.get("rid", "")
                    if rid and rid in figs_by_id and rid not in rendered_figs:
                        rendered_figs.add(rid)
                        render_fig(figs_by_id[rid], lines, image_urls)
        elif tag == "sec":
            render_section(child, lines, level + 1, image_urls=image_urls,
                           figs_by_id=figs_by_id, rendered_figs=rendered_figs)
        elif tag == "fig":
            fig_id = child.get("id", "")
            if fig_id and rendered_figs is not None:
                rendered_figs.add(fig_id)
            render_fig(child, lines, image_urls)
        elif tag == "table-wrap":
            render_table_wrap(child, lines)
        elif tag == "list":
            for item in child.findall("list-item"):
                item_text = element_to_text(item).strip()
                if item_text:
                    lines.append(f"- {item_text}\n")

    lines.append("")


class PmcXmlConverter(BaseXmlConverter):
    """Конвертер PMC NLM DTD XML → Markdown."""

    def convert(self, xml_bytes: bytes, **kwargs) -> str:
        """Конвертирует PMC XML в Markdown.

        Args:
            xml_bytes: XML байты статьи
            image_urls: словарь {basename_без_расширения: url} для подстановки в <fig>
        """
        image_urls: ImageUrls = kwargs.get("image_urls") or {}
        return _pmc_xml_to_markdown(xml_bytes, image_urls)


def _pmc_xml_to_markdown(
    xml_bytes: bytes,
    image_urls: Optional[ImageUrls] = None,
) -> str:
    """Конвертирует PMC XML (NLM DTD) в Markdown."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        logger.error(f"[pmc_xml_to_md] Ошибка парсинга XML: {e}")
        return ""

    if image_urls is None:
        image_urls = {}

    lines = []

    # Заголовок
    title_el = root.find(".//article-title")
    if title_el is not None:
        title_text = "".join(title_el.itertext()).strip()
        lines.append(f"# {title_text}\n")

    # Авторы
    authors = []
    for contrib in root.findall(".//contrib[@contrib-type='author']"):
        surname = contrib.findtext(".//surname", "")
        given = contrib.findtext(".//given-names", "")
        if surname:
            authors.append(f"{surname} {given}".strip())
    if authors:
        lines.append(f"**Авторы:** {', '.join(authors)}\n")

    # Журнал и дата
    journal = root.findtext(".//journal-title", "")
    year = root.findtext(".//pub-date/year", "")
    if journal:
        lines.append(f"**Журнал:** {journal}" + (f" ({year})" if year else "") + "\n")

    # DOI
    for article_id in root.findall(".//article-id"):
        if article_id.get("pub-id-type") == "doi":
            lines.append(f"**DOI:** {article_id.text}\n")
            break

    lines.append("")

    # Абстракт
    abstract_el = root.find(".//abstract")
    if abstract_el is not None:
        lines.append("## Abstract\n")
        for p in abstract_el.findall(".//p"):
            text = element_to_text(p).strip()
            if text:
                title_tag = p.get("content-type") or ""
                if title_tag:
                    lines.append(f"**{title_tag}:** {text}\n")
                else:
                    lines.append(f"{text}\n")
        lines.append("")

    # Собираем фигуры из <floats-group>
    figs_by_id: Dict[str, ET.Element] = {}
    floats = root.find(".//floats-group")
    if floats is not None:
        for fig in floats.findall("fig"):
            fig_id = fig.get("id", "")
            if fig_id:
                figs_by_id[fig_id] = fig

    # Также фигуры из body/sec (inline layout)
    for fig in root.findall(".//body//fig"):
        fig_id = fig.get("id", "")
        if fig_id and fig_id not in figs_by_id:
            figs_by_id[fig_id] = fig

    rendered_figs: set = set()

    # Основные секции
    for sec in root.findall(".//body/sec"):
        render_section(sec, lines, level=2, image_urls=image_urls,
                       figs_by_id=figs_by_id, rendered_figs=rendered_figs)

    # Фигуры, не встретившиеся в тексте — добавляем в конец
    remaining = [figs_by_id[fid] for fid in figs_by_id if fid not in rendered_figs]
    if remaining:
        lines.append("## Figures\n")
        for fig in remaining:
            render_fig(fig, lines, image_urls)

    # Список литературы (первые 50)
    refs = root.findall(".//ref-list/ref")
    if refs:
        lines.append("## References\n")
        for i, ref in enumerate(refs[:50], 1):
            mixed_citation = ref.find(".//mixed-citation")
            element_citation = ref.find(".//element-citation")
            if mixed_citation is not None:
                ref_text = "".join(mixed_citation.itertext()).strip()
            elif element_citation is not None:
                ref_text = "".join(element_citation.itertext()).strip()
            else:
                ref_text = "".join(ref.itertext()).strip()
            if ref_text:
                lines.append(f"{i}. {ref_text}\n")

    return "\n".join(lines)
