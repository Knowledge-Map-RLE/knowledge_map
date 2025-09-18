import asyncio
import threading
import time
import socket
from .grpc_server import serve
from .user_service import UserService
from .config import settings


def start_grpc_server():
    """Запускает gRPC сервер в отдельном потоке"""
    serve()


def _wait_for_neo4j(timeout_sec: int = 60) -> None:
    """Ждёт доступности Neo4j Bolt порта, чтобы не спамить ошибками при старте."""
    uri = settings.NEO4J_URI.replace("bolt://", "")
    if "/" in uri:
        uri = uri.split("/", 1)[0]
    host, port_str = uri.split(":", 1)
    try:
        port = int(port_str)
    except Exception:
        port = 7687
    if host == "localhost":
        host = "127.0.0.1"

    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        try:
            if s.connect_ex((host, port)) == 0:
                return
        except Exception:
            pass
        finally:
            s.close()
        time.sleep(1)


def cleanup_sessions():
    """Периодически очищает истекшие сессии (с бэкоффом при ошибках подключения Neo4j)."""
    user_service = UserService()
    while True:
        try:
            user_service.cleanup_expired_sessions()
            # успех — спим час
            time.sleep(3600)
        except Exception as e:
            print(f"Ошибка очистки сессий: {e}")
            # ошибка — краткая пауза и повтор
            time.sleep(60)


def main():
    """Основная функция запуска"""
    print("Запуск сервиса авторизации...")

    # Ждём Neo4j, чтобы уменьшить шум ошибок при старте
    _wait_for_neo4j(timeout_sec=30)

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
            time.sleep(1)
    except KeyboardInterrupt:
        print("Завершение работы сервиса авторизации...")


if __name__ == "__main__":
    main() 