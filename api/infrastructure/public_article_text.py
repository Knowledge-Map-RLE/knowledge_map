"""Полный публичный JATS-текст: таблицы, подписи и отдельная библиография."""
from xml.etree import ElementTree as ET
from dataclasses import dataclass, field
from html.parser import HTMLParser
from domain.article_maps import require

HTML_VERSION = "pmc-public-html-1"


@dataclass
class _Element:
    tag: str
    attributes: dict
    children: list = field(default_factory=list)

    def descendants(self):
        yield self
        for child in self.children:
            if isinstance(child, _Element): yield from child.descendants()

    def text(self):
        return "".join(c.text() if isinstance(c, _Element) else c for c in self.children)


class _PublicHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Element("root", {})
        self.stack = [self.root]

    def handle_starttag(self, tag, attributes):
        element = _Element(tag, dict(attributes))
        self.stack[-1].children.append(element)
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append(element)

    def handle_startendtag(self, tag, attributes):
        self.handle_starttag(tag, attributes)
        if self.stack[-1].tag == tag: self.stack.pop()

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def convert_pmc_html(markup):
    """Публичная страница PMC, явно выбранная вместо отсутствующего лицензированного JATS."""
    parser = _PublicHTML()
    parser.feed(markup)
    articles = [e for e in parser.root.descendants() if e.tag == "article"]
    require(len(articles) == 1, "Expected one complete public PMC article; challenge pages are not sources")
    article = articles[0]
    titles = [e for e in article.descendants() if e.tag == "h1"]
    bodies = [e for e in article.descendants() if {"body", "main-article-body"} <= set(e.attributes.get("class", "").split())]
    require(len(titles) == 1 and len(bodies) == 1, "PMC article title or full body missing")
    body = bodies[0]
    clean = lambda e: " ".join(e.text().split())
    headings = [clean(e).casefold() for e in body.descendants() if e.tag in {"h2", "h3", "h4"}]
    require(any("method" in h for h in headings) and any("result" in h for h in headings), "Primary methods and results sections required")
    output, references = ["# " + clean(titles[0])], []

    def walk(e):
        classes = set(e.attributes.get("class", "").split())
        if "ref-list" in classes:
            for ref in (r for r in e.descendants() if r.tag == "li"):
                citations = [c for c in ref.descendants() if c.tag == "cite"]
                labels = [c for c in ref.descendants() if "label" in c.attributes.get("class", "").split()]
                if citations: references.append((clean(labels[0]) + " " if labels else "") + clean(citations[0]))
            return
        if e.tag in {"script", "style", "button", "nav"}:
            return
        if e.tag in {"h2", "h3", "h4", "h5", "h6"}:
            output.append("#" * int(e.tag[1]) + " " + clean(e)); return
        if e.tag == "table":
            rows = []
            for row in (r for r in e.descendants() if r.tag == "tr"):
                cells = [clean(c) for c in row.children if isinstance(c, _Element) and c.tag in {"td", "th"}]
                if cells: rows.append(" | ".join(cells))
            output.append("\n".join(rows)); return
        if e.tag in {"p", "li", "blockquote", "figcaption"}:
            value = clean(e)
            if value and value.casefold() != "open in a new tab": output.append(value)
            return
        for child in e.children:
            if isinstance(child, _Element): walk(child)
    walk(body)
    require(bool(references), "Full public bibliography required")
    output.extend(["## References", *references])
    return "\n\n".join(output) + "\n"


def convert_xml(xml):
    root = ET.fromstring(xml)
    text = lambda e: " ".join("".join(e.itertext()).split())
    title = text(root.find(".//article-title"))
    output = ["# " + title]
    for abstract in root.findall(".//article-meta/abstract"):
        output.extend(["## Abstract", text(abstract)])
    body = root.find("body")
    require(body is not None, "No complete article body")
    def walk(parent, level=2):
        for e in parent:
            if e.tag == "sec":
                heading = e.find("title")
                if heading is None or text(heading).casefold() != "references": walk(e, min(6, level + 1))
            elif e.tag == "title": output.append("#" * level + " " + text(e))
            elif e.tag == "table-wrap":
                label = e.find("label"); caption = e.find("caption")
                output.append("\n" + (text(label) if label is not None else "Table") + " " + (text(caption) if caption is not None else ""))
                for row in e.findall(".//tr"):
                    output.append(" | ".join(text(c) for c in row if c.tag in {"th", "td"}))
                if not e.findall(".//tr") and e.find(".//graphic") is not None:
                    output.append("[Table values are supplied as an image in the original XML; no numerical transcription is claimed.]")
                foot = e.find("table-wrap-foot")
                if foot is not None: output.append(text(foot))
            elif e.tag == "fig": output.append(text(e))
            elif e.tag in {"p", "boxed-text", "list", "disp-quote", "statement", "supplementary-material", "disp-formula"}: output.append(text(e))
    walk(body)
    for section in root.findall(".//back/sec"):
        heading = section.find("title")
        if heading is not None and text(heading).casefold() == "references": continue
        output.extend(["## " + text(section.find("title")) if section.find("title") is not None else "## Additional material", text(section)])
    references = root.findall(".//ref-list")
    if references:
        output.append("## References")
        for group in references: output.extend(text(ref) for ref in group.findall("ref"))
    return "\n\n".join(output) + "\n"
