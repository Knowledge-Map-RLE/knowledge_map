#!/usr/bin/env python3
"""
Правильное решение для преобразования PDF в Markdown с использованием Marker
"""
import os
import sys
import json
import subprocess
import tempfile
from pathlib import Path

def convert_pdf_to_markdown_marker_proper(pdf_path, output_dir="markdown-annotator-marker-proper"):
    """Правильное преобразование PDF в Markdown с использованием Marker"""
    
    if not os.path.exists(pdf_path):
        print(f"❌ Файл не найден: {pdf_path}")
        return None
    
    # Создаем директорию
    Path(output_dir).mkdir(exist_ok=True)
    
    pdf_name = Path(pdf_path).name
    markdown_name = f"{Path(pdf_path).stem}.md"
    markdown_path = f"{output_dir}/{markdown_name}"
    
    try:
        print(f"🔄 Преобразование PDF в Markdown с Marker: {pdf_name}")
        
        # Создаем временную папку для Marker (он ожидает папку, а не файл)
        import shutil
        temp_input_dir = f"{output_dir}/temp_input"
        os.makedirs(temp_input_dir, exist_ok=True)
        
        # Копируем PDF в временную папку
        temp_pdf_path = f"{temp_input_dir}/{pdf_name}"
        shutil.copy2(pdf_path, temp_pdf_path)
        
        # Используем правильный CLI команду для Marker
        # Marker создает выходные файлы в той же папке, что и входные
        result = subprocess.run([
            "marker", temp_input_dir
        ], capture_output=True, text=True, timeout=600)
        
        if result.returncode == 0:
            print("✅ Marker конвертация завершена успешно")
            
            # Ищем созданный markdown файл в папке результатов Marker
            import site
            site_packages = site.getsitepackages()[0]
            conversion_results_dir = Path(site_packages) / "conversion_results"
            
            # Если не найдено, попробуем в .venv
            if not conversion_results_dir.exists():
                venv_path = Path.cwd() / ".venv"
                conversion_results_dir = venv_path / "Lib" / "site-packages" / "conversion_results"
            pdf_name_without_ext = Path(pdf_path).stem
            
            print(f"🔍 Ищем результаты в: {conversion_results_dir}")
            print(f"🔍 Имя файла без расширения: {pdf_name_without_ext}")
            
            # Проверяем, существует ли папка результатов
            if not conversion_results_dir.exists():
                print(f"❌ Папка результатов не существует: {conversion_results_dir}")
                return None
            
            # Ищем папку с результатами (Marker создает папку с полным именем файла)
            result_dirs = list(conversion_results_dir.glob(f"*{pdf_name_without_ext}*"))
            if not result_dirs:
                # Попробуем найти по части имени
                result_dirs = list(conversion_results_dir.glob("*FEBS*"))
            if not result_dirs:
                # Попробуем найти любую папку с результатами
                result_dirs = list(conversion_results_dir.glob("*"))
            if result_dirs:
                result_dir = result_dirs[0]
                markdown_files = list(result_dir.glob("*.md"))
                
                if markdown_files:
                    # Читаем результат
                    with open(markdown_files[0], 'r', encoding='utf-8') as f:
                        full_text = f.read()
                    
                    print(f"✅ Markdown извлечен, размер: {len(full_text)} символов")
                    
                    # Копируем изображения в папку с Markdown
                    image_files = list(result_dir.glob("*.jpeg")) + list(result_dir.glob("*.jpg")) + list(result_dir.glob("*.png"))
                    for image_file in image_files:
                        dest_image_path = Path(output_dir) / image_file.name
                        shutil.copy2(image_file, dest_image_path)
                        print(f"📷 Скопировано изображение: {image_file.name}")
                    
                    # Сохраняем markdown в финальную папку
                    with open(markdown_path, 'w', encoding='utf-8') as f:
                        f.write(full_text)
                    
                    # Создаем HTML аннотатор
                    html_path = create_markdown_annotator(markdown_path, full_text, output_dir, "Marker (Proper)")
                    
                    # Создаем JSON файл для Label Studio
                    json_path = create_label_studio_tasks(html_path, output_dir, markdown_name, "marker_proper")
                    
                    return markdown_path, html_path, json_path
                else:
                    print("❌ Markdown файл не найден в результатах")
                    return None
            else:
                print("❌ Папка с результатами не найдена")
                return None
        else:
            print(f"❌ Marker конвертация не удалась: {result.stderr}")
            return None
            
    except subprocess.TimeoutExpired:
        print("⏰ Таймаут Marker конвертации (10 минут)")
        return None
    except FileNotFoundError:
        print("❌ Marker не найден. Установите: pip install marker-pdf")
        return None
    except Exception as e:
        print(f"❌ Ошибка Marker конвертации: {e}")
        return None
    finally:
        # Удаляем временную папку
        if 'temp_input_dir' in locals() and os.path.exists(temp_input_dir):
            shutil.rmtree(temp_input_dir)

def create_markdown_annotator(markdown_path, markdown_content, output_dir, ai_engine):
    """Создание HTML аннотатора для Markdown"""
    
    markdown_name = Path(markdown_path).name
    html_name = f"{Path(markdown_path).stem}_annotator.html"
    html_path = f"{output_dir}/{html_name}"
    
    # Создаем HTML с интерактивным аннотированием
    html_content = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{ai_engine} Markdown Annotator for Label Studio</title>
    <style>
        body {{
            margin: 0;
            padding: 20px;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 2.5em;
            font-weight: 300;
        }}
        .header p {{
            margin: 10px 0 0 0;
            opacity: 0.9;
            font-size: 1.1em;
        }}
        .ai-badge {{
            display: inline-block;
            background: rgba(255,255,255,0.2);
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.9em;
            margin-top: 10px;
        }}
        .controls {{
            padding: 25px;
            background: #f8f9fa;
            border-bottom: 1px solid #e9ecef;
        }}
        .label-buttons {{
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            margin-bottom: 25px;
        }}
        .label-btn {{
            padding: 10px 18px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.3s ease;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .label-btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }}
        .label-btn.active {{
            transform: scale(1.05);
            box-shadow: 0 4px 16px rgba(0,0,0,0.2);
        }}
        .content {{
            padding: 40px;
            font-size: 16px;
            line-height: 1.8;
            background: white;
        }}
        .content h1, .content h2, .content h3, .content h4, .content h5, .content h6 {{
            color: #2c3e50;
            margin-top: 35px;
            margin-bottom: 20px;
            font-weight: 600;
        }}
        .content h1 {{
            border-bottom: 3px solid #667eea;
            padding-bottom: 15px;
            font-size: 2.2em;
        }}
        .content h2 {{
            border-bottom: 2px solid #e74c3c;
            padding-bottom: 10px;
            font-size: 1.8em;
        }}
        .content h3 {{
            border-bottom: 1px solid #3498db;
            padding-bottom: 8px;
            font-size: 1.4em;
        }}
        .content p {{
            margin-bottom: 18px;
            text-align: justify;
        }}
        .content ul, .content ol {{
            margin-bottom: 20px;
            padding-left: 35px;
        }}
        .content li {{
            margin-bottom: 10px;
        }}
        .content blockquote {{
            border-left: 4px solid #3498db;
            margin: 25px 0;
            padding: 15px 25px;
            background: #f8f9fa;
            font-style: italic;
            border-radius: 0 8px 8px 0;
        }}
        .content code {{
            background: #f1f2f6;
            padding: 3px 8px;
            border-radius: 4px;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
        }}
        .content pre {{
            background: #2c3e50;
            color: #ecf0f1;
            padding: 20px;
            border-radius: 8px;
            overflow-x: auto;
            margin: 25px 0;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        }}
        .content table {{
            width: 100%;
            border-collapse: collapse;
            margin: 25px 0;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            border-radius: 8px;
            overflow: hidden;
        }}
        .content th, .content td {{
            border: 1px solid #ddd;
            padding: 15px;
            text-align: left;
        }}
        .content th {{
            background: #34495e;
            color: white;
            font-weight: 600;
        }}
        .content tr:nth-child(even) {{
            background: #f8f9fa;
        }}
        .content tr:hover {{
            background: #e8f4fd;
        }}
        .content hr {{
            border: none;
            border-top: 2px solid #bdc3c7;
            margin: 35px 0;
        }}
        
        /* Стили для аннотаций */
        .annotation {{
            position: relative;
            display: inline;
            cursor: pointer;
            transition: all 0.3s ease;
        }}
        .annotation:hover {{
            background: rgba(255, 255, 0, 0.3);
            border-radius: 4px;
        }}
        .annotation.highlighted {{
            background: rgba(102, 126, 234, 0.3);
            border-radius: 4px;
            padding: 3px 6px;
        }}
        .annotation-label {{
            position: absolute;
            top: -30px;
            left: 0;
            background: rgba(0,0,0,0.9);
            color: white;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 11px;
            white-space: nowrap;
            z-index: 1000;
            opacity: 0;
            transition: opacity 0.3s;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        }}
        .annotation:hover .annotation-label {{
            opacity: 1;
        }}
        
        /* Стили для выделения */
        .selected-text {{
            background: rgba(102, 126, 234, 0.3);
            border-radius: 4px;
            padding: 3px 6px;
        }}
        
        /* Стили для связей */
        .relations {{
            margin-top: 35px;
            padding: 25px;
            background: #f8f9fa;
            border-radius: 8px;
        }}
        .relation {{
            margin: 15px 0;
            padding: 20px;
            background: white;
            border-radius: 8px;
            border-left: 4px solid #667eea;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        
        /* Кнопки управления */
        .control-buttons {{
            display: flex;
            gap: 12px;
            margin-top: 25px;
        }}
        .btn {{
            padding: 12px 24px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.3s ease;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }}
        .btn-primary {{
            background: #667eea;
            color: white;
        }}
        .btn-primary:hover {{
            background: #5a6fd8;
        }}
        .btn-success {{
            background: #27ae60;
            color: white;
        }}
        .btn-success:hover {{
            background: #229954;
        }}
        .btn-warning {{
            background: #f39c12;
            color: white;
        }}
        .btn-warning:hover {{
            background: #e67e22;
        }}
        .btn-danger {{
            background: #e74c3c;
            color: white;
        }}
        .btn-danger:hover {{
            background: #c0392b;
        }}
        
        /* Инструкции */
        .instructions {{
            background: linear-gradient(135deg, #e8f4fd 0%, #f0f8ff 100%);
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 25px;
            border-left: 4px solid #667eea;
        }}
        .instructions h4 {{
            margin: 0 0 15px 0;
            color: #2c3e50;
            font-size: 1.2em;
        }}
        .instructions ol {{
            margin: 0;
            padding-left: 25px;
            color: #34495e;
        }}
        .instructions li {{
            margin-bottom: 8px;
        }}
        
        /* Статистика */
        .stats {{
            background: linear-gradient(135deg, #2c3e50 0%, #34495e 100%);
            color: white;
            padding: 15px 25px;
            border-radius: 8px;
            margin-bottom: 25px;
            text-align: center;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        }}
        .stats span {{
            margin: 0 20px;
            font-weight: 600;
            font-size: 1.1em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🧠 {ai_engine} Markdown Annotator</h1>
            <p>Высококачественное аннотирование PDF документов через AI</p>
            <div class="ai-badge">Powered by {ai_engine}</div>
        </div>
        
        <div class="controls">
            <div class="instructions">
                <h4>📋 Инструкция по использованию:</h4>
                <ol>
                    <li><strong>Выберите метку</strong> - нажмите на кнопку с нужной меткой</li>
                    <li><strong>Выделите текст</strong> - выделите текст в документе как обычно</li>
                    <li><strong>Создайте аннотацию</strong> - нажмите "Создать аннотацию" или используйте Ctrl+Enter</li>
                    <li><strong>Создайте связи</strong> - нажмите на аннотацию для создания связи</li>
                    <li><strong>Экспортируйте результаты</strong> - нажмите "Экспорт аннотаций"</li>
                </ol>
            </div>
            
            <div class="stats" id="stats">
                <span>Аннотации: <span id="annotation-count">0</span></span>
                <span>Связи: <span id="relation-count">0</span></span>
                <span>Выбранная метка: <span id="selected-label">Нет</span></span>
            </div>
            
            <div class="label-buttons">
                <button class="label-btn" data-label="Organization" style="background: orange; color: white;">🏢 Organization</button>
                <button class="label-btn" data-label="Person" style="background: green; color: white;">👤 Person</button>
                <button class="label-btn" data-label="Disease" style="background: red; color: white;">🦠 Disease</button>
                <button class="label-btn" data-label="Drug" style="background: purple; color: white;">💊 Drug</button>
                <button class="label-btn" data-label="Treatment" style="background: violet; color: white;">🏥 Treatment</button>
                <button class="label-btn" data-label="Datetime" style="background: blue; color: white;">📅 Datetime</button>
                <button class="label-btn" data-label="Gene" style="background: teal; color: white;">🧬 Gene</button>
                <button class="label-btn" data-label="Protein" style="background: navy; color: white;">🔬 Protein</button>
                <button class="label-btn" data-label="Scientific_Term" style="background: gray; color: white;">🔬 Scientific Term</button>
                <button class="label-btn" data-label="Measurement" style="background: silver; color: white;">📏 Measurement</button>
            </div>
            
            <div class="control-buttons">
                <button class="btn btn-primary" onclick="createAnnotationFromSelection()">✨ Создать аннотацию</button>
                <button class="btn btn-success" onclick="exportAnnotations()">📤 Экспорт аннотаций</button>
                <button class="btn btn-warning" onclick="showAnnotations()">👁️ Показать аннотации</button>
                <button class="btn btn-danger" onclick="clearAnnotations()">🗑️ Очистить все</button>
            </div>
        </div>
        
        <div class="content" id="markdown-content">
            {markdown_content}
        </div>
        
        <div class="relations">
            <h3>🔗 Связи между аннотациями</h3>
            <div id="relations-list"></div>
        </div>
    </div>

    <script>
        let annotations = [];
        let relations = [];
        let selectedLabel = null;
        let annotationCounter = 0;
        
        // Инициализация
        document.addEventListener('DOMContentLoaded', function() {{
            initializeAnnotator();
        }});
        
        function initializeAnnotator() {{
            // Обработчики для кнопок меток
            document.querySelectorAll('.label-btn').forEach(btn => {{
                btn.addEventListener('click', function() {{
                    document.querySelectorAll('.label-btn').forEach(b => b.classList.remove('active'));
                    this.classList.add('active');
                    selectedLabel = this.dataset.label;
                    document.getElementById('selected-label').textContent = selectedLabel;
                    console.log('Выбрана метка:', selectedLabel);
                }});
            }});
            
            // Обработчик для клавиатуры
            document.addEventListener('keydown', function(e) {{
                if (e.ctrlKey && e.key === 'Enter') {{
                    createAnnotationFromSelection();
                }}
            }});
            
            // Обработчик для выделения текста
            document.addEventListener('mouseup', function() {{
                const selection = window.getSelection();
                const selectedText = selection.toString().trim();
                
                if (selectedText && selectedLabel) {{
                    // Подсвечиваем выделенный текст
                    highlightSelectedText(selection);
                }}
            }});
        }}
        
        function highlightSelectedText(selection) {{
            const range = selection.getRangeAt(0);
            const selectedText = selection.toString().trim();
            
            if (selectedText) {{
                // Создаем временную подсветку
                const span = document.createElement('span');
                span.className = 'selected-text';
                span.textContent = selectedText;
                
                try {{
                    range.deleteContents();
                    range.insertNode(span);
                }} catch (e) {{
                    console.log('Не удалось подсветить текст:', e);
                }}
            }}
        }}
        
        function createAnnotationFromSelection() {{
            if (!selectedLabel) {{
                alert('Сначала выберите метку для аннотирования');
                return;
            }}
            
            const selection = window.getSelection();
            const selectedText = selection.toString().trim();
            
            if (!selectedText) {{
                alert('Сначала выделите текст в документе');
                return;
            }}
            
            // Создаем аннотацию
            const annotation = {{
                id: ++annotationCounter,
                label: selectedLabel,
                text: selectedText,
                timestamp: new Date().toISOString(),
                type: 'text',
                ai_engine: '{ai_engine}'
            }};
            
            annotations.push(annotation);
            
            // Создаем визуальную аннотацию
            createVisualAnnotation(annotation, selection);
            
            // Очищаем выделение
            selection.removeAllRanges();
            
            // Обновляем статистику
            updateStats();
            
            console.log('Аннотация создана:', annotation);
        }}
        
        function createVisualAnnotation(annotation, selection) {{
            const range = selection.getRangeAt(0);
            const selectedText = selection.toString().trim();
            
            // Создаем элемент аннотации
            const span = document.createElement('span');
            span.className = 'annotation highlighted';
            span.dataset.annotationId = annotation.id;
            span.textContent = selectedText;
            
            // Добавляем метку
            const label = document.createElement('span');
            label.className = 'annotation-label';
            label.textContent = annotation.label;
            span.appendChild(label);
            
            // Обработчик клика для создания связей
            span.addEventListener('click', function() {{
                createRelation(annotation.id);
            }});
            
            try {{
                range.deleteContents();
                range.insertNode(span);
            }} catch (e) {{
                console.log('Не удалось создать визуальную аннотацию:', e);
            }}
        }}
        
        function createRelation(annotationId) {{
            const annotation = annotations.find(a => a.id === annotationId);
            if (annotation) {{
                const relation = {{
                    id: Date.now(),
                    from: annotationId,
                    to: null,
                    type: 'related',
                    timestamp: new Date().toISOString()
                }};
                relations.push(relation);
                updateRelationsList();
                updateStats();
                console.log('Связь создана:', relation);
            }}
        }}
        
        function updateRelationsList() {{
            const relationsList = document.getElementById('relations-list');
            relationsList.innerHTML = '';
            
            relations.forEach(relation => {{
                const relationEl = document.createElement('div');
                relationEl.className = 'relation';
                relationEl.innerHTML = `
                    <strong>Связь ${{relation.id}}</strong><br>
                    <small>Тип: ${{relation.type}} | Создано: ${{new Date(relation.timestamp).toLocaleString()}}</small>
                `;
                relationsList.appendChild(relationEl);
            }});
        }}
        
        function updateStats() {{
            document.getElementById('annotation-count').textContent = annotations.length;
            document.getElementById('relation-count').textContent = relations.length;
        }}
        
        function showAnnotations() {{
            console.log('Все аннотации:', annotations);
            console.log('Все связи:', relations);
            
            // Подсвечиваем все аннотации
            document.querySelectorAll('.annotation').forEach(annotation => {{
                annotation.style.background = 'rgba(102, 126, 234, 0.3)';
            }});
            
            setTimeout(() => {{
                document.querySelectorAll('.annotation').forEach(annotation => {{
                    annotation.style.background = '';
                }});
            }}, 2000);
        }}
        
        function exportAnnotations() {{
            const data = {{
                annotations: annotations,
                relations: relations,
                markdown: '{markdown_name}',
                timestamp: new Date().toISOString(),
                total_annotations: annotations.length,
                total_relations: relations.length,
                ai_engine: '{ai_engine}',
                converter: 'marker_proper'
            }};
            
            const blob = new Blob([JSON.stringify(data, null, 2)], {{ type: 'application/json' }});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'marker_proper_annotations.json';
            a.click();
            URL.revokeObjectURL(url);
            
            console.log('Аннотации экспортированы:', data);
        }}
        
        function clearAnnotations() {{
            if (confirm('Вы уверены, что хотите очистить все аннотации?')) {{
                annotations = [];
                relations = [];
                annotationCounter = 0;
                
                // Удаляем визуальные аннотации
                document.querySelectorAll('.annotation').forEach(annotation => {{
                    const text = annotation.textContent;
                    annotation.replaceWith(text);
                }});
                
                // Очищаем список связей
                document.getElementById('relations-list').innerHTML = '';
                
                // Обновляем статистику
                updateStats();
                
                console.log('Все аннотации очищены');
            }}
        }}
    </script>
</body>
</html>"""
    
    # Сохраняем HTML файл
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"📋 HTML аннотатор создан: {html_path}")
    return html_path

def create_label_studio_tasks(html_path, output_dir, markdown_name, converter_type):
    """Создание JSON файла для Label Studio"""
    
    json_name = f"{Path(markdown_name).stem}_{converter_type}_tasks.json"
    json_path = f"{output_dir}/{json_name}"
    
    tasks = [
        {
            "data": {
                "html": f"http://localhost:9002/html/{Path(html_path).name}"
            }
        }
    ]
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)
    
    print(f"📋 JSON файл создан: {json_path}")
    return json_path

def main():
    """Основная функция"""
    print("🚀 Создание правильного Marker PDF в Markdown аннотатора для Label Studio...")
    
    # Проверяем аргументы командной строки
    if len(sys.argv) < 2:
        print("📋 Использование: python create_pdf_to_markdown_marker_proper.py <путь_к_pdf>")
        print("📋 Пример: python create_pdf_to_markdown_marker_proper.py document.pdf")
        return
    
    pdf_path = sys.argv[1]
    
    # Преобразование PDF в Markdown и создание аннотатора
    result = convert_pdf_to_markdown_marker_proper(pdf_path)
    
    if result:
        markdown_path, html_path, json_path = result
        
        print("\n🎉 Готово!")
        print(f"📄 Markdown файл: {markdown_path}")
        print(f"📁 HTML аннотатор: {html_path}")
        print(f"📋 JSON файл: {json_path}")
        
        print("\n📋 Следующие шаги:")
        print("1. Убедитесь, что PDF сервер запущен на порту 9002")
        print("2. Откройте Label Studio")
        print("3. Создайте новый проект")
        print("4. Импортируйте JSON файл с HTML аннотатором")
        print("5. Начните интерактивное аннотирование Markdown!")
        
        print(f"\n🌐 Откройте аннотатор: http://localhost:9002/html/{Path(html_path).name}")

if __name__ == "__main__":
    main()
