#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WISO GOLABEL - Запуск сервера БЕЗ GUI
Для работы в фоновом режиме + автоперезапуск при сбое.
"""

import asyncio
import logging
import time
from server_unified import UnifiedServer

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('server_unified.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def run_with_autorestart():
    """Запуск сервера с автоперезапуском."""
    restart_delay = 3
    max_delay = 60
    short_crashes = 0

    logger.info('=' * 60)
    logger.info('ЗАПУСК СЕРВЕРА БЕЗ GUI (AUTO-RESTART)')
    logger.info('=' * 60)

    while True:
        started_at = time.time()
        server = UnifiedServer()

        try:
            asyncio.run(server.start())
            # Если сервер завершился без исключения, все равно поднимем его снова.
            logger.warning('Сервер завершил работу без исключения. Перезапуск...')
        except KeyboardInterrupt:
            logger.info('Сервер остановлен пользователем (Ctrl+C)')
            break
        except Exception as e:
            logger.critical(f'Критическая ошибка сервера: {e}', exc_info=True)

        uptime_sec = time.time() - started_at
        if uptime_sec > 120:
            restart_delay = 3
            short_crashes = 0
        else:
            short_crashes += 1
            restart_delay = min(max_delay, restart_delay * 2)

        logger.warning(
            f'Перезапуск через {restart_delay} сек. '
            f'(uptime={uptime_sec:.1f}s, short_crashes={short_crashes})'
        )
        time.sleep(restart_delay)


if __name__ == '__main__':
    run_with_autorestart()
