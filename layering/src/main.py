"""
Точка входа для микросервиса укладки графа карты знаний.
"""

import argparse
import logging
import sys
from pathlib import Path
from grpc_service import run_server

# Добавляем путь к src в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent))

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Основная функция запуска сервиса"""
    parser = argparse.ArgumentParser(description='Микросервис укладки графа карты знаний')
    parser.add_argument('--port', type=int, default=50051, help='Порт для gRPC сервера (по умолчанию: 50051)')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='Хост для gRPC сервера (по умолчанию: 0.0.0.0)')
    parser.add_argument('--log-level', type=str, default='INFO', 
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                       help='Уровень логирования (по умолчанию: INFO)')
    
    args = parser.parse_args()
    
    # Устанавливаем уровень логирования
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    logger.info(f"Запуск микросервиса укладки графа")
    logger.info(f"Хост: {args.host}")
    logger.info(f"Порт: {args.port}")
    logger.info(f"Уровень логирования: {args.log_level}")
    
    try:
        # Запускаем gRPC сервер
        run_server(host=args.host, port=args.port)
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске сервиса: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main() 