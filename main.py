# main.py
import os
import time
import logging
import argparse
import datetime
import re

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from src.audio import extract_audio
from src.transcribe import transcribe_audio    
from src.analyzer import analyze_meeting
from src.output import write_output

from utils.database import get_file_hash, is_already_processed, mark_as_processed
from utils.config_loader import cfg
from utils.lock import create_lock, cleanup_locks, remove_lock
from utils.logs import setup_logging
from utils.file import wait_for_file_stability



# --- ЛОГИРОВАНИЕ ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)

# --- ОСНОВНОЙ ПАЙПЛАЙН ---

def start_pipeline(file_path):
    """
    Полный цикл обработки одного файла:
    видео → аудио → транскрипция → анализ → отчёт
    """
    filename = os.path.basename(file_path)

    date_match = re.search(r'(\d{2})\.(\d{2})\.(\d{2})', filename)
    
    if date_match:
        day, month, year = date_match.groups()
        # Превращаем в объект datetime (2000 + год, чтобы было 2026)
        video_date = datetime.datetime(2000 + int(year), int(month), int(day))
    else:
        # Если дата в названии не найдена, берем дату создания файла
        file_mtime = os.path.getmtime(file_path)
        video_date = datetime.datetime.fromtimestamp(file_mtime)
        logging.warning(f"│   [ WARN ] Дата в названии не найдена, использую дату файла: {video_date.date()}")

    lock_path = file_path + ".lock"
    if os.path.exists(lock_path):
        logging.warning(f"│   [ BUSY ] Файл уже обрабатывается: {filename}")
        return

    f_hash = get_file_hash(file_path)
    if not f_hash:
        logging.error(f"│   [ FAIL ] Ошибка хеширования: {filename}")
        return

    if is_already_processed(f_hash):
        logging.info(f"│   [ SKIP ] Уже в базе: {filename}")
        return
    
    # Создаем lock-файл
    create_lock(lock_path)

    logging.info(f"╒══ СТАРТ: {filename}")
    start_time = time.time()
    wav_path = None

    try:
        # ШАГ 1: Извлекаем аудио
        logging.info("│   [ STEP 1/4 ] Извлечение аудио...")
        wav_path = extract_audio(file_path)
        if not wav_path:
            raise RuntimeError("FFmpeg не вернул путь к WAV файлу")

        # ШАГ 2: Транскрибация
        txt_path = os.path.splitext(file_path)[0] + ".txt"
        
        if os.path.exists(txt_path):
            logging.info(f"│   [ CACHE ] Найден готовый транскрипт, пропускаю транскрибацию.")
        else:
            engine_name = cfg.get('TRANSCRIPTION', 'engine', fallback='gigaam').upper()
            logging.info(f"│   [ STEP 2/4 ] Транскрибация ({engine_name})...")
            # Вызываем транскрибатор, который создаст txt_path
            txt_path = transcribe_audio(wav_path, output_path=txt_path)
        # Удаляем временный WAVs
        if os.path.exists(wav_path):
            os.remove(wav_path)

        # ШАГ 3: Анализ
        logging.info("│   [ STEP 3/4 ] AI Анализ (Ollama)...")
        data = analyze_meeting(txt_path)

        # ШАГ 4: Excel
        logging.info("│   [ STEP 4/4 ] Генерация отчета...")
        write_output(data, video_date=video_date)

        mark_as_processed(f_hash, filename)

        elapsed = (time.time() - start_time) / 60
        logging.info(f"┕━━ [ DONE ] Время: {elapsed:.1f} мин.")

    except Exception as e:
        logging.error(f"│   [ CRIT ] Ошибка: {e}")
        if wav_path and os.path.exists(wav_path):
            os.remove(wav_path)
    
    finally:
        remove_lock(lock_path)


# --- WATCHDOG ---
def run_watchdog(input_dir):
    """Режим постоянного мониторинга папки"""
    logging.info(f"│   [ SRVC ] Мониторинг запущен: {input_dir}")
    
    # Сначала обрабатываем то, что уже лежит в папке
    existing = [os.path.join(input_dir, f) for f in os.listdir(input_dir) 
                if f.endswith(('.webm', '.mp4', '.mkv'))]
    for f_path in existing:
        start_pipeline(f_path)

    handler = TelemostHandler()
    observer = Observer()
    observer.schedule(handler, input_dir, recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("│   [ SRVC ] Остановка мониторинга...")
        observer.stop()
    observer.join()

class TelemostHandler(FileSystemEventHandler):
    def on_created(self, event):
        # Проверяем расширение
        if not event.is_directory and event.src_path.lower().endswith(('.webm', '.mp4', '.mkv')):
            # Ждем стабилизации файла перед стартом пайплайна
            if wait_for_file_stability(event.src_path):
                start_pipeline(event.src_path)
            else:
                logging.error(f"│   [ FAIL ] Файл исчез или недоступен: {event.src_path}")

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
        # Режим одного файла
        if os.path.exists(args.file):
            start_pipeline(args.file)
        else:
            logging.error(f"│   [ FAIL ] Файл не найден: {args.file}")
    elif args.watch:
        # Режим мониторинга
        input_dir = cfg.get('PATHS', 'input_folder')
        run_watchdog(input_dir)
    else:
        # Если запустили без аргументов — выводим справку
        parser.print_help()

if __name__ == "__main__":
    main()