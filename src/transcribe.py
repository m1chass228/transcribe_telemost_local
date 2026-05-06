import os
import time
import hashlib
import json
import logging
import configparser
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Импортируем наши модули из папки src
from src.config_loader import cfg
from src.audio import extract_audio
from src.transcribe import run_whisper
from src.analyzer import analyze_meeting
from src.excel_gen import write_to_excel

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)

def get_file_hash(file_path):
    """Считает MD5 хеш файла блоками по 64кб (безопасно для ОЗУ)."""
    hasher = hashlib.md5()
    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        logging.error(f"Ошибка при расчете хеша: {e}")
        return None

def is_already_processed(file_hash):
    db_path = cfg.get('PATHS', 'db_path')
    if not os.path.exists(db_path):
        return False
    with open(db_path, 'r', encoding='utf-8') as f:
        try:
            db = json.load(f)
            return file_hash in db
        except:
            return False

def mark_as_processed(file_hash, filename):
    db_path = cfg.get('PATHS', 'db_path')
    db = {}
    if os.path.exists(db_path):
        with open(db_path, 'r', encoding='utf-8') as f:
            try: db = json.load(f)
            except: db = {}

    db[file_hash] = {
        "filename": filename,
        "processed_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    with open(db_path, 'w', encoding='utf-8') as f:
        json.dump(db, f, indent=4, ensure_ascii=False)

def process_file(file_path):
    """Основной пайплайн обработки одного файла."""
    filename = os.path.basename(file_path)

    # 1. Проверка хеша
    f_hash = get_file_hash(file_path)
    if not f_hash or is_already_processed(f_hash):
        logging.info(f"Пропускаю (уже обработан или ошибка): {filename}")
        return

    logging.info(f"Начинаю обработку: {filename}")
    start_time = time.time()

    try:
        # 2. Извлечение аудио
        wav_path = extract_audio(file_path)
        if not wav_path: raise Exception("Ошибка на этапе FFmpeg")

        # 3. Транскрибация
        # Здесь память будет занята Whisper
        txt_path = run_whisper(
            wav_path,
            cfg.get('PATHS', 'bin_path'),
            cfg.get('PATHS', 'model_path')
        )

        # Удаляем временный WAV сразу после транскрибации, чтобы освободить место на SSD
        if os.path.exists(wav_path):
            os.remove(wav_path)

        # 4. Анализ (Ollama / Qwen)
        # Здесь Whisper уже закрыт, память свободна для LLM
        analysis_results = analyze_meeting(txt_path)

        # 5. Сохранение (Заглушка в консоль + лог)
        write_to_excel(analysis_results)

        # 6. Фиксация успеха
        mark_as_processed(f_hash, filename)

        duration = (time.time() - start_time) / 60
        logging.info(f"✅ Успешно завершено за {duration:.2f} мин: {filename}")

    except Exception as e:
        logging.error(f"❌ Критическая ошибка при обработке {filename}: {e}")

class TelemostWatcher(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith(('.webm', '.mp4', '.mkv')):
            logging.info(f"✨ Обнаружен новый файл: {os.path.basename(event.src_path)}")
            # Небольшая пауза, чтобы файл успел дозаписаться/скопироваться
            time.sleep(3)
            process_file(event.src_path)

if __name__ == "__main__":
    input_dir = cfg.get('PATHS', 'input_folder')

    if not os.path.exists(input_dir):
        logging.error(f"Папка ввода не найдена: {input_dir}")
        exit(1)

    logging.info("--- Бот-секретарь запущен и готов к работе ---")
    logging.info(f"Слежу за: {input_dir}")

    # Сначала обрабатываем всё, что уже лежит в папке
    existing_files = [os.path.join(input_dir, f) for f in os.listdir(input_dir)
                      if f.endswith(('.webm', '.mp4', '.mkv'))]

    if existing_files:
        logging.info(f"Найдено {len(existing_files)} существующих файлов. Начинаю проверку...")
        for f_path in existing_files:
            process_file(f_path)

    # Затем переходим в режим ожидания новых файлов
    event_handler = TelemostWatcher()
    observer = Observer()
    observer.schedule(event_handler, input_dir, recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Stopping...")
        observer.stop()
    observer.join()
