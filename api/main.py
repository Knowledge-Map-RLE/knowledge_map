"""
Точка входа приложения.

Layer: Frameworks & Drivers
Запускает uvicorn с приложением из web/app.py.
Старый src/app.py сохранён как TRANSITIONAL redirect.
"""
import uvicorn
from web.app import app  # Новое расположение

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
