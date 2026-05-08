import logging
import os
import time
import datetime
import re

from pathlib import Path

logger = logging.getLogger(__name__)


def wait_for_file_stability(file_path, stable_limit=6, interval=5):
    """
    Ждет, пока размер файла перестанет расти.
    По умолчанию: 6 проверок по 5 секунд = 30 секунд стабильности.
    """
    logger.info(f"│   [ WAIT ] Ожидание завершения записи: {os.path.basename(file_path)}")
    last_size = -1
    stable_count = 0
    
    while True:
        try:
            if not os.path.exists(file_path):
                return False
                
            current_size = os.path.getsize(file_path)
            
            if current_size == last_size and current_size > 0:
                stable_count += 1
                # Логируем только каждую вторую проверку, чтобы не засорять экран
                if stable_count % 2 == 0:
                    logger.info(f"│   [ WAIT ] Стабилен {stable_count * interval}с...")
            else:
                last_size = current_size
                stable_count = 0
                size_mb = current_size / (1024 * 1024)
                logger.info(f"│   [ DOWN ] Файл дописывается... ({size_mb:.1f} MB)")
            
            if stable_count >= stable_limit:
                logger.info(f"│   [ READY ] Запись завершена.")
                return True
                
            time.sleep(interval)
            
        except Exception as e:
            logger.error(f"│   [ ERR ] Ошибка при ожидании файла: {e}")
            return False
        
def get_video_date(file_path: Path) -> datetime.datetime:
    """Вынос логики парсинга даты."""
    # Улучшенная регулярка для DD.MM.YY или DD.MM.YYYY
    date_match = re.search(r'(\d{2})\.(\d{2})\.(\d{2,4})', file_path.name)
    if date_match:
        day, month, year = date_match.groups()
        year = int(year) + 2000 if len(year) == 2 else int(year)
        return datetime.datetime(year, int(month), int(day))
    
    return datetime.datetime.fromtimestamp(file_path.stat().st_mtime)