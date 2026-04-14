import xml.etree.ElementTree as ET
import re

NS = {
    'graphml': 'http://graphml.graphdrawing.org/xmlns',
    'y': 'http://www.yworks.com/xml/graphml',
}

tree = ET.parse('Карта Знаний. Текущий план.graphml')
root = tree.getroot()

graph = root.find('graphml:graph', NS)

# Parse nodes
nodes = {}
for node in graph.findall('graphml:node', NS):
    node_id = node.get('id')
    shape_node = node.find('.//y:ShapeNode', NS)
    if shape_node is None:
        continue
    
    # Get geometry for position
    geometry = shape_node.find('y:Geometry', NS)
    x = float(geometry.get('x')) if geometry is not None else 0
    y = float(geometry.get('y')) if geometry is not None else 0
    
    # Get label
    label_node = shape_node.find('y:NodeLabel', NS)
    label = label_node.text.strip() if label_node is not None and label_node.text else ''
    
    # Get fill color (for status circles)
    fill = shape_node.find('y:Fill', NS)
    color = fill.get('color') if fill is not None else None
    
    # Get shape type
    shape_elem = shape_node.find('y:Shape', NS)
    shape_type = shape_elem.get('type') if shape_elem is not None else None
    
    # Width and height
    width = float(geometry.get('width')) if geometry is not None else 0
    height = float(geometry.get('height')) if geometry is not None else 0
    
    # Only store text nodes (roundrectangle), not status circles
    if shape_type == 'roundrectangle' and label:
        nodes[node_id] = {
            'label': label,
            'x': x,
            'y': y,
            'width': width,
            'height': height,
            'status': None,  # will be filled by proximity
        }

# Parse status circles (ellipse, star5)
status_circles = []
for node in graph.findall('graphml:node', NS):
    node_id = node.get('id')
    shape_node = node.find('.//y:ShapeNode', NS)
    if shape_node is None:
        continue
    
    shape_elem = shape_node.find('y:Shape', NS)
    shape_type = shape_elem.get('type') if shape_elem is not None else None
    
    if shape_type in ('ellipse', 'star5'):
        geometry = shape_node.find('y:Geometry', NS)
        cx = float(geometry.get('x')) + float(geometry.get('width')) / 2
        cy = float(geometry.get('y')) + float(geometry.get('height')) / 2
        
        fill = shape_node.find('y:Fill', NS)
        color = fill.get('color') if fill is not None else None
        
        status_circles.append({
            'cx': cx,
            'cy': cy,
            'color': color,
            'shape': shape_type,
        })

# Assign status circles to nearest node
def distance(x1, y1, x2, y2):
    return ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5

COLOR_MAP = {
    '#00FF00': '✅ ГОТОВО',
    '#FFCC99': '🟡 В ПРОЦЕССЕ',
    '#FFCC00': '🟡 В ПРОЦЕССЕ',
    '#FF0000': '❌ НЕ РЕАЛИЗОВАНО',
}

for sc in status_circles:
    # Find nearest node (within reasonable distance)
    best_dist = float('inf')
    best_node = None
    for nid, ninfo in nodes.items():
        # Check if circle is near the top-right corner of the node
        node_right = ninfo['x'] + ninfo['width']
        node_top = ninfo['y']
        # Circle should be near the top-right area
        d = distance(sc['cx'], sc['cy'], node_right - 30, node_top + 15)
        if d < best_dist and d < 100:  # threshold
            best_dist = d
            best_node = nid
    
    if best_node:
        status_text = COLOR_MAP.get(status_circles[status_circles.index(sc)]['color'], f'Неизвестно ({sc["color"]})')
        # Re-lookup color
        color = sc['color']
        status_text = COLOR_MAP.get(color, f'Неизвестно ({color})')
        nodes[best_node]['status'] = status_text

# Also try matching by pure proximity for all circles
for sc in status_circles:
    best_dist = float('inf')
    best_node = None
    for nid, ninfo in nodes.items():
        d = distance(sc['cx'], sc['cy'], ninfo['x'] + ninfo['width'] / 2, ninfo['y'] + ninfo['height'] / 2)
        # Prefer circles that are in the upper-right quadrant of the node
        if sc['cx'] > ninfo['x'] and sc['cy'] < ninfo['y'] + ninfo['height'] / 2:
            if d < best_dist:
                best_dist = d
                best_node = nid
    
    if best_node and nodes[best_node]['status'] is None:
        color = sc['color']
        status_text = COLOR_MAP.get(color, f'Неизвестно ({color})')
        nodes[best_node]['status'] = status_text

# Parse edges
edges = []
for edge in graph.findall('graphml:edge', NS):
    source = edge.get('source')
    target = edge.get('target')
    
    # Get line color
    line_style = edge.find('.//y:LineStyle', NS)
    edge_color = line_style.get('color') if line_style is not None else None
    
    edges.append({
        'source': source,
        'target': target,
        'color': edge_color,
    })

# Sort nodes by position (top-to-bottom, left-to-right)
sorted_nodes = sorted(nodes.items(), key=lambda item: (item[1]['y'], item[1]['x']))

print("=" * 80)
print("ГРАФ ПЛАНА — КАРТА ЗНАНИЙ")
print("=" * 80)
print()

# Group by status
for status in ['✅ ГОТОВО', '🟡 В ПРОЦЕССЕ', '❌ НЕ РЕАЛИЗОВАНО']:
    status_nodes = [(nid, ninfo) for nid, ninfo in sorted_nodes if ninfo['status'] == status]
    if not status_nodes:
        continue
    
    print(f"\n{'='*60}")
    print(f"  {status}")
    print(f"{'='*60}")
    
    for nid, ninfo in status_nodes:
        print(f"\n  [{nid}] {ninfo['label']}")
        # Find outgoing edges
        outgoing = [e for e in edges if e['source'] == nid]
        if outgoing:
            print(f"    → Ведёт к:")
            for e in outgoing:
                target_label = nodes.get(e['target'], {}).get('label', e['target'])
                print(f"      • {target_label}")

print("\n" + "=" * 80)
print("ВСЕ СВЯЗИ:")
print("=" * 80)
for e in edges:
    src_label = nodes.get(e['source'], {}).get('label', e['source'])
    tgt_label = nodes.get(e['target'], {}).get('label', e['target'])
    print(f"  {src_label}  →  {tgt_label}")

print("\n" + "=" * 80)
print("СТАТИСТИКА:")
print("=" * 80)
total = len(nodes)
done = sum(1 for n in nodes.values() if n['status'] == '✅ ГОТОВО')
in_progress = sum(1 for n in nodes.values() if n['status'] == '🟡 В ПРОЦЕССЕ')
not_done = sum(1 for n in nodes.values() if n['status'] == '❌ НЕ РЕАЛИЗОВАНО')
unknown = sum(1 for n in nodes.values() if n['status'] is None)

print(f"  Всего блоков: {total}")
print(f"  ✅ Готово: {done}")
print(f"  🟡 В процессе: {in_progress}")
print(f"  ❌ Не реализовано: {not_done}")
print(f"  ❓ Без статуса: {unknown}")
