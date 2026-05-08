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
def run_watchdog(input_dir):
    """Режим постоянного мониторинга папки"""
    input_path = Path(input_dir)
    logging.info(f"│   [ SRVC ] Мониторинг запущен: {input_path.absolute()}")
    
    # Запускаем воркер-поток
    t = threading.Thread(target=worker, daemon=True)
    t.start()

    # Сначала обрабатываем то, что уже лежит в папке
    existing = [p for p in input_path.iterdir() if p.suffix.lower() in ('.webm', '.mp4', '.mkv')]
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
        processing_queue.put(None) # Сигнал воркеру на выход
        observer.stop()
    observer.join()
    t.join()

class TelemostHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        
        path = Path(event.src_path)
        if path.suffix.lower() in ('.webm', '.mp4', '.mkv'):
            logging.info(f"│   [ NEW  ] Обнаружен файл: {path.name}")
            # Добавляем в очередь
            processing_queue.put(path)

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