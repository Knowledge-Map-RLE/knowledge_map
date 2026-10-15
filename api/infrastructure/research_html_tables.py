"""Чтение сохранённых таблиц источника с явным происхождением объединённых ячеек."""
from bs4 import BeautifulSoup
from domain.article_maps import require


def read_html_tables(html):
    tables = []
    for table_index, table in enumerate(BeautifulSoup(html, 'html.parser').find_all('table')):
        occupied = {}
        rows = []
        for ri, row in enumerate(table.find_all('tr')):
            col = 0
            for ci, cell in enumerate(row.find_all(['th', 'td'], recursive=False)):
                while (ri, col) in occupied:
                    col += 1
                rs, cs = int(cell.get('rowspan', 1)), int(cell.get('colspan', 1))
                require(0 < rs <= 100 and 0 < cs <= 100, 'Invalid source table span')
                value = {'text': cell.get_text(' ', strip=True), 'origin_row': ri, 'origin_cell': ci,
                         'rowspan': rs, 'colspan': cs}
                for r in range(ri, ri + rs):
                    for c in range(col, col + cs):
                        require((r, c) not in occupied, 'Overlapping source table cells')
                        occupied[r, c] = value
                col += cs
            width = max((c + 1 for r, c in occupied if r == ri), default=0)
            require(all((ri, c) in occupied for c in range(width)), 'Source table has unexplained internal gap')
            rows.append([dict(occupied[ri, c]) for c in range(width)])
        require(all(r < len(rows) for r, c in occupied), 'Source table rowspan exceeds final row')
        tables.append({'index': table_index + 1, 'rows': rows})
    return tables
