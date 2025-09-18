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
                    
                    # Создаем JSON файл для Label Studio
                    json_path = create_label_studio_tasks(output_dir, markdown_name, "marker_proper")
                    
                    return markdown_path, json_path
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

def create_label_studio_tasks(output_dir, markdown_name, converter_type):
    """Создание JSON файла для Label Studio"""
    
    json_name = f"{Path(markdown_name).stem}_{converter_type}_tasks.json"
    json_path = f"{output_dir}/{json_name}"
    
    tasks = [
        {
            "data": {
                "markdown": f"http://localhost:9002/markdown/{markdown_name}"
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
        markdown_path, json_path = result
        
        print("\n🎉 Готово!")
        print(f"📄 Markdown файл: {markdown_path}")
        print(f"📋 JSON файл: {json_path}")
        
        print("\n📋 Следующие шаги:")
        print("1. Убедитесь, что PDF сервер запущен на порту 9002")
        print("2. Откройте Label Studio")
        print("3. Создайте новый проект")
        print("4. Импортируйте JSON файл с Markdown")
        print("5. Начните интерактивное аннотирование Markdown!")
        
        print(f"\n🌐 Откройте Markdown: http://localhost:9002/markdown/{markdown_name}")

if __name__ == "__main__":
    main()
