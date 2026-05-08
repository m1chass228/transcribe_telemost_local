
import logging
import os
import time

def create_lock(lock_path):
    with open(lock_path, "w") as f: f.write("lock")

def cleanup_locks(input_dir, max_age_seconds=0): # 10800 сек = 3 часа
    """
    Удаляет файлы .lock, которые старше max_age_seconds.
    Это лечит проблему 'мертвых' замков после краша системы.
    """
    logging.info("🧹 Проверка 'зависших' lock-файлов...")
    if not os.path.exists(input_dir):
        return

    now = time.time()
    count = 0
    
    for f in os.listdir(input_dir):
        if f.endswith(".lock"):
            lock_path = os.path.join(input_dir, f)
            try:
                lock_age = now - os.path.getmtime(lock_path)
                if lock_age > max_age_seconds:
                    logging.warning(f"⚠️ Удален старый замок: {f} (возраст: {lock_age/60:.1f} мин)")
                    os.remove(lock_path)
                    count += 1
            except Exception as e:
                logging.error(f"Не удалось проверить замок {f}: {e}")
    
    if count > 0:
        logging.info(f"✅ Очищено замков: {count}")
    else:
        logging.info("✨ Активных 'мертвых' замков не найдено.")