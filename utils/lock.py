import logging
import os
import time
from pathlib import Path

def create_lock(file_path: str) -> str:
    """
    Создает .lock файл для указанного пути.
    """
    lock_path = f"{file_path}.lock"
    try:
        with open(lock_path, "w", encoding="utf-8") as f:
            f.write(str(time.time()))
        logging.debug(f"[ LOCK ] Создан замок: {os.path.basename(lock_path)}")
        return lock_path
    except Exception as e:
        logging.error(f"[ LOCK ] Ошибка создания замка для {file_path}: {e}")
        return ""

def remove_lock(lock_path: str):
    """
    Удаляет конкретный lock-файл.
    """
    try:
        p = Path(lock_path)
        if p.exists():
            p.unlink()
            logging.debug(f"[ LOCK ] Замок снят: {p.name}")
    except Exception as e:
        logging.error(f"[ LOCK ] Не удалось удалить замок {lock_path}: {e}")

def cleanup_locks(target_path: str, max_age_seconds: int = 0):
    """
    Универсальная очистка зависших замков.
    """
    path = Path(target_path)
    
    # Если передан путь к конкретному локу
    if path.is_file() and path.suffix == '.lock':
        remove_lock(str(path))
        return

    # Если передана директория для массовой очистки
    if path.is_dir():
        logging.info(f"[ LOCK ] Проверка зависших замков в: {path}")
        now = time.time()
        count = 0
        
        for f in path.glob("*.lock"):
            try:
                lock_age = now - f.stat().st_mtime
                if lock_age >= max_age_seconds:
                    f.unlink()
                    logging.warning(f"[ LOCK ] Удален старый замок: {f.name} (возраст: {lock_age/60:.1f} мин)")
                    count += 1
            except Exception as e:
                logging.error(f"[ LOCK ] Ошибка при проверке {f.name}: {e}")
        
        if count > 0:
            logging.info(f"[ LOCK ] Очищено замков: {count}")