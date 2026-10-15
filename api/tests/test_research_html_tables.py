"""Проверяем реальные формы объединений без домысливания отсутствующих значений."""
import pytest
from domain.article_maps import ArticleMapError
from infrastructure.research_html_tables import read_html_tables


def test_rowspans_keep_joint_p_origin_and_blanks():
    html='<table><tr><td>Q1</td><td></td><td rowspan="2">0.03</td><td>Reference</td></tr><tr><td>Q2</td><td>0.2</td><td>-1</td></tr></table>'
    rows=read_html_tables(html)[0]['rows']
    assert rows[0][1]['text']==''
    assert rows[1][2]['text']=='0.03' and rows[1][2]['origin_row']==0
    assert rows[1][3]['text']=='-1'


def test_colspan_does_not_create_separate_original_cells():
    rows=read_html_tables('<table><tr><th colspan="3">Group</th></tr><tr><td>a</td><td>b</td><td>c</td></tr></table>')[0]['rows']
    assert len(rows[0])==3
    assert {(c['origin_row'],c['origin_cell']) for c in rows[0]}=={(0,0)}


@pytest.mark.parametrize('html',[
    '<table><tr><td rowspan="0">x</td></tr></table>',
    '<table><tr><td rowspan="2">x</td></tr></table>',
    '<table><tr><td>a</td><td rowspan="2">b</td></tr><tr><td colspan="2">overlap</td></tr></table>',
])
def test_invalid_spans_rejected(html):
    with pytest.raises(ArticleMapError):read_html_tables(html)
