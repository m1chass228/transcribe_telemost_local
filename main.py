# main.py
import time
import logging
import argparse
import queue
import threading
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from utils.config_loader import cfg
from utils.lock import cleanup_locks
from utils.logs import setup_logging

from src.pipeline import start_pipeline

# --- WORKER ---
# Создаем очередь для последовательной обработки файлов
processing_queue = queue.Queue()
def worker():
    """Фоновый поток для обработки очереди"""
    while True:
        file_path = processing_queue.get()
        if file_path is None:
            break
        try:
            start_pipeline(str(file_path))
        except Exception as e:
            logging.error(f"│   [ CRIT ] Ошибка в воркере: {e}", exc_info=True)
        finally:
            processing_queue.task_done()

# --- WATCHDOG ---
class TelemostHandler(FileSystemEventHandler):
    """Обработчик событий создания новых файлов"""
    def on_created(self, event):
        if event.is_directory:
            return
        
        path = Path(event.src_path)
        
        # Пропускаем временные файлы и логи самого процесса
        if path.suffix.lower() in ('.lock', '.wav', '.txt', '.tmp'):
            return

        # Обрабатываем только видео-контейнеры
        if path.suffix.lower() in ('.webm', '.mp4', '.mkv'):
            # Дополнительная проверка: если замок уже существует, значит файл в работе
            lock_file = path.with_suffix(path.suffix + '.lock')
            if lock_file.exists():
                logging.debug(f"│   [ SKIP ] Файл уже обрабатывается: {path.name}")
                return

            logging.info(f"│   [ NEW  ] Обнаружен файл: {path.name}")
            processing_queue.put(path)

def run_watchdog(input_dir):
    """Режим постоянного мониторинга папки"""
    input_path = Path(input_dir)
    logging.info(f"│   [ SRVC ] Мониторинг запущен: {input_path.absolute()}")
    
    # Запускаем воркер-поток
    t = threading.Thread(target=worker, daemon=True)
    t.start()

    # Сначала обрабатываем то, что уже лежит в папке
    # Исключаем файлы, у которых уже есть .lock замок
    valid_suffixes = ('.webm', '.mp4', '.mkv')
    existing = []
    
    for p in input_path.iterdir():
        if p.suffix.lower() in valid_suffixes:
            lock_file = p.with_suffix(p.suffix + '.lock')
            # Берем только те, которые еще не заблокированы
            if not lock_file.exists():
                existing.append(p)
            else:
                logging.info(f"│   [ SKIP ] Файл уже в процессе (найден lock): {p.name}")

    for f_path in existing:
        processing_queue.put(f_path)

    handler = TelemostHandler()
    observer = Observer()
    observer.schedule(handler, str(input_path), recursive=False)
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("│   [ SRVC ] Остановка мониторинга...")
        processing_queue.put(None)
        observer.stop()
    observer.join()
    t.join()

# --- ТОЧКА ВХОДА ---
def main():
    parser = argparse.ArgumentParser(description="AI-секретарь для обработки записей встреч")
    
    # Создаем группу, чтобы нельзя было запустить одновременно файл и папку
    group = parser.add_mutually_exclusive_group()
    
    group.add_argument("-f", "--file", type=str, help="Путь к конкретному файлу для обработки")
    group.add_argument("-w", "--watch", action="store_true", help="Запустить в режиме мониторинга папки (из конфига)")

    parser.add_argument("--debug", action="store_true", help="Включить отладочные логи")
    parser.add_argument("--trace", action="store_true", help="Выводить полные ответы нейросети")
    
    args = parser.parse_args()

    setup_logging(debug_mode=args.debug, trace_ai=args.trace)

    input_dir = cfg.get('PATHS', 'input_folder')
    cleanup_locks(input_dir)

    if args.file:
        file_path = Path(args.file)
        if file_path.exists():
            start_pipeline(str(file_path))
        else:
            logging.error(f"│   [ FAIL ] Файл не найден: {args.file}")
    elif args.watch:
        run_watchdog(input_dir)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()