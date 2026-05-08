import os
import hashlib
import logging
import json
import time

from utils.config_loader import cfg

logger = logging.getLogger(__name__)

def get_file_hash(file_path):
    """
    Генерирует быстрый ID файла (Fingerprint) без полного чтения.
    """
    try:
        if not os.path.exists(file_path):
            return None

        stat = os.stat(file_path)
        size = stat.st_size
        mtime = stat.st_mtime
        
        # Берем только первые 1MB для хеша
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            chunk = f.read(1024 * 1024) 
            hasher.update(chunk)
            
        # Формируем ключ: хеш_размер_время
        # Если время изменения или размер изменятся — файл будет считаться новым
        fast_id = f"{hasher.hexdigest()}_{size}_{int(mtime)}"
        return fast_id
        
    except Exception as e:
        logger.error(f"│   [ FAIL ] Ошибка идентификации [{file_path}]: {e}")
        return None


def is_already_processed(file_hash):
    """Проверяет наличие Fingerprint в базе"""
    if not file_hash:
        return False
        
    db_path = cfg.get('PATHS', 'db_path')
    if not os.path.exists(db_path):
        return False
        
    try:
        with open(db_path, 'r', encoding='utf-8') as f:
            db = json.load(f)
            return file_hash in db
    except Exception:
        return False


def mark_as_processed(file_hash, filename):
    """Записывает новый Fingerprint в JSON"""
    if not file_hash:
        return

    db_path = cfg.get('PATHS', 'db_path')
    db = {}

    if os.path.exists(db_path):
        try:
            with open(db_path, 'r', encoding='utf-8') as f:
                db = json.load(f)
        except Exception:
            db = {}

    db[file_hash] = {
        "filename": filename,
        "processed_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    with open(db_path, 'w', encoding='utf-8') as f:
        json.dump(db, f, indent=4, ensure_ascii=False)