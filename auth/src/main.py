import asyncio
import threading
from .grpc_server import serve
from .user_service import UserService


def start_grpc_server():
    """Запускает gRPC сервер в отдельном потоке"""
    serve()


def cleanup_sessions():
    """Периодически очищает истекшие сессии"""
    user_service = UserService()
    while True:
        try:
            user_service.cleanup_expired_sessions()
            asyncio.sleep(3600)  # Каждый час
        except Exception as e:
            print(f"Ошибка очистки сессий: {e}")


def main():
    """Основная функция запуска"""
    print("Запуск сервиса авторизации...")
    
    # Запускаем gRPC сервер в отдельном потоке
    grpc_thread = threading.Thread(target=start_grpc_server, daemon=True)
    grpc_thread.start()
    
    # Запускаем очистку сессий в отдельном потоке
    cleanup_thread = threading.Thread(target=cleanup_sessions, daemon=True)
    cleanup_thread.start()
    
    print("Сервис авторизации запущен")
    
    # Держим основной поток живым
    try:
        while True:
            asyncio.sleep(1)
    except KeyboardInterrupt:
        print("Завершение работы сервиса авторизации...")


if __name__ == "__main__":
    main() 