import os
import time
import hashlib
import json
import logging
import configparser
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from src.audio import extract_audio
from src.transcribe import run_whisper
from src.analyzer import analyze_meeting
from src.excel_gen import write_to_excel

# --- НАСТРОЙКИ ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
CONFIG_PATH = 'config.ini'
DB_PATH = 'processed_files.json'

config = configparser.ConfigParser()
config.read(CONFIG_PATH, encoding='utf-8')

INPUT_FOLDER = config['PATHS']['input_folder']
BIN_PATH = config['PATHS']['bin_path']
MODEL_PATH = config['PATHS']['model_path']
OLLAMA_MODEL = config['MODELS']['ollama_model']

# --- ФУНКЦИИ-ХЕЛПЕРЫ ---

def get_file_hash(file_path):
    # Считаем хеш файла, чтобы не обрабатывать дубли.
    hasher = hashlib.md5()
    # Читаем по 64кб, чтобы не вешать память на 2х часовом видео
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def is_already_processed(file_hash):
    if not os.path.exists(DB_PATH):
        return False
    with open(DB_PATH, 'r') as f:
        try:
            db = json.load(f)
            return file_hash in db
        except:
            return False

def mark_as_processed(file_hash, filename):
    db = {}
    if os.path.exists(DB_PATH):
        with open(DB_PATH, 'r') as f:
            try: db = json.load(f)
            except: db = {}

    db[file_hash] = {
        "filename": filename,
        "processed_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    with open(DB_PATH, 'w') as f:
        json.dump(db, f, indent=4)

# --- ОСНОВНОЙ ПАЙПЛАЙН ---

def start_pipeline(file_path):
    file_hash = get_file_hash(file_path)

    if is_already_processed(file_hash):
        logging.info(f"Файл уже был обработан ранее (hash match). Пропускаю: {file_path}")
        return

    logging.info(f"Начинаю полную обработку: {file_path}")

    try:
        # 1. Извлекаем звук
        wav_path = extract_audio(file_path)

        # 2. Транскрибируем
        txt_path = run_whisper(wav_path, BIN_PATH, MODEL_PATH)

        # 3. Анализируем через Ollama
        raw_json_tasks = analyze_meeting(txt_path, OLLAMA_MODEL)

        # 4. Пишем в Excel
        write_to_excel(raw_json_tasks)

        # 5. Финализируем
        mark_as_processed(file_hash, os.path.basename(file_path))

        # Чистим временный WAV, но оставляем .txt на всякий случай
        if os.path.exists(wav_path):
            os.remove(wav_path)

        logging.info(f"Готово! Результаты добавлены в таблицу.")

    except Exception as e:
        logging.error(f"Ошибка пайплайна: {e}")

# --- WATCHDOG ---

class TelemostHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith(('.webm', '.mp4')):
            # Ждем пару секунд, чтобы файл успел "приземлиться"
            time.sleep(2)
            start_pipeline(event.src_path)

if __name__ == "__main__":
    logging.info("🤖 Локальный AI-секретарь запущен.")
    logging.info(f"Наблюдаю за папкой: {INPUT_FOLDER}")

    # Сначала проверяем существующие файлы
    for f in os.listdir(INPUT_FOLDER):
        if f.endswith(('.webm', '.mp4')):
            full_path = os.path.join(INPUT_FOLDER, f)
            start_pipeline(full_path)

    # Запускаем мониторинг новых
    event_handler = TelemostHandler()
    observer = Observer()
    observer.schedule(event_handler, INPUT_FOLDER, recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
