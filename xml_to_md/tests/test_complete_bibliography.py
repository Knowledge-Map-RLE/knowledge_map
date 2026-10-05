"""Проверка сохранения библиографии целиком, включая ссылки после пятидесятой."""
import re

from src.converters.pmc import PmcXmlConverter


def test_preserves_all_references_and_does_not_cap_at_fifty():
    references = "".join(f'<ref><label>{i}.</label><mixed-citation>Reference {i} complete text.</mixed-citation></ref>'
                         for i in range(1, 76))
    xml = ('<article><front><article-meta><title-group><article-title>Full study</article-title></title-group>'
           '</article-meta></front><body><sec><title>Results</title><p>Complete results.</p></sec></body>'
           f'<back><ref-list>{references}</ref-list></back></article>')
    markdown = PmcXmlConverter().convert(xml.encode())
    assert [int(v) for v in re.findall(r"(?m)^(\d+)\. Reference", markdown)] == list(range(1, 76))
    assert "75. Reference 75 complete text." in markdown


def test_preserves_direct_body_text_complete_captions_table_footnotes_and_spans():
    xml = b'''<article><body><p>Direct body paragraph.</p><sec><title>Results</title>
      <table-wrap><label>Table 1</label><caption><title>Complete caption title.</title>
      <p>First caption paragraph.</p><p>Second caption paragraph.</p></caption><table>
      <tr><th colspan="2">Two outcomes</th></tr><tbody><tr><td rowspan="2">Group</td>
      <td>p &lt; 0.05</td></tr></tbody><tfoot><tr><td>All participants</td></tr></tfoot></table>
      <table-wrap-foot><fn><p>Adjusted for baseline age and sex.</p></fn></table-wrap-foot></table-wrap>
      <fig><label>Figure 1</label><caption><title>Figure caption title.</title>
      <p>First figure paragraph.</p><p>Second figure paragraph.</p></caption></fig>
      <fn-group><fn><p>Full disclosure paragraph.</p></fn></fn-group>
      </sec></body></article>'''
    markdown = PmcXmlConverter().convert(xml)
    for text in ("Direct body paragraph.", "Complete caption title.", "First caption paragraph.",
                 "Second caption paragraph.", "All participants", "Adjusted for baseline age and sex.",
                 "Figure caption title.", "First figure paragraph.", "Second figure paragraph.",
                 "Full disclosure paragraph.", 'colspan="2"', 'rowspan="2"', "p &lt; 0.05"):
        assert text in markdown


def test_preserves_standalone_formula_and_boxed_text():
    xml = b'''<article><body><disp-formula><tex-math>$$x=1$$</tex-math></disp-formula>
      <boxed-text><title>Protocol</title><p>Independent protocol text.</p></boxed-text></body></article>'''
    markdown = PmcXmlConverter().convert(xml)
    assert "x=1" in markdown and "Independent protocol text." in markdown


def test_preserves_back_matter_without_duplicating_bibliography():
    xml = b'''<article><body><p>Study body.</p></body><back>
      <ack><p>Funding disclosure.</p></ack><app-group><app><title>Supplement</title>
      <p>Additional protocol.</p></app></app-group><ref-list>
      <ref><mixed-citation>Unique bibliographic entry.</mixed-citation></ref>
      </ref-list></back></article>'''
    markdown = PmcXmlConverter().convert(xml)
    assert "Funding disclosure." in markdown and "Additional protocol." in markdown
    assert markdown.count("Unique bibliographic entry.") == 1
    assert markdown.index("Additional protocol.") < markdown.index("## References")
