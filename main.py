# main.py
import os
import time
import hashlib
import json
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from src.config_loader import cfg
from src.audio import extract_audio
from src.transcribe import transcribe_audio     # ← ИЗМЕНЕНО
from src.analyzer import analyze_meeting
from src.excel_gen import write_to_excel


# --- ЛОГИРОВАНИЕ ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)


# --- ХЕЛПЕРЫ ДЛЯ БД ОБРАБОТАННЫХ ФАЙЛОВ ---
def get_file_hash(file_path):
    hasher = hashlib.md5()
    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        logging.error(f"Ошибка при расчёте хеша [{file_path}]: {e}")
        return None


def is_already_processed(file_hash):
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


# --- ОСНОВНОЙ ПАЙПЛАЙН ---

def start_pipeline(file_path):
    """
    Полный цикл обработки одного файла:
    видео → аудио → транскрипция → анализ → отчёт
    """
    filename = os.path.basename(file_path)

    f_hash = get_file_hash(file_path)
    if not f_hash:
        logging.error(f"Не удалось получить хеш, пропускаю: {filename}")
        return

    if is_already_processed(f_hash):
        logging.info(f"Уже обработан ранее, пропускаю: {filename}")
        return

    logging.info(f"▶ Старт обработки: {filename}")
    start_time = time.time()

    wav_path = None

    try:
        # ШАГ 1: Извлекаем аудио
        logging.info("Шаг 1/4: Извлечение аудио...")
        wav_path = extract_audio(file_path)
        if not wav_path:
            raise RuntimeError("FFmpeg не вернул путь к WAV файлу")

        # ШАГ 2: Транскрибируем (Whisper ИЛИ GigaAM — по конфигу)
        logging.info(f"Шаг 2/4: Транскрибация через {cfg.get('TRANSCRIPTION', 'engine', fallback='gigaam').upper()}...")
        
        txt_path = transcribe_audio(wav_path)          # ← ИЗМЕНЕНО (унифицированный вызов)

        # Удаляем временный WAV
        if os.path.exists(wav_path):
            os.remove(wav_path)
            logging.info(f"Временный WAV удалён: {os.path.basename(wav_path)}")
            wav_path = None

        # ШАГ 3: Анализ
        logging.info("Шаг 3/4: Анализ через Ollama...")
        analysis_results = analyze_meeting(txt_path)

        # ШАГ 4: Excel
        logging.info("Шаг 4/4: Сохранение результата...")
        write_to_excel(analysis_results)

        mark_as_processed(f_hash, filename)

        elapsed = (time.time() - start_time) / 60
        logging.info(f"✅ Обработка завершена за {elapsed:.1f} мин: {filename}")

    except Exception as e:
        logging.error(f"❌ Ошибка при обработке [{filename}]: {e}")

        if wav_path and os.path.exists(wav_path):
            os.remove(wav_path)
            logging.info(f"Временный WAV удалён после ошибки")


# --- WATCHDOG ---
class TelemostHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        if not event.src_path.endswith(('.webm', '.mp4', '.mkv')):
            return

        file_path = event.src_path
        logging.info(f"✨ Обнаружен новый файл: {os.path.basename(file_path)}")

        # Ждём окончания записи
        logging.info("Жду окончания записи файла...")
        last_size = -1
        while True:
            try:
                current_size = os.path.getsize(file_path)
            except OSError:
                time.sleep(1)
                continue

            if current_size == last_size and current_size > 0:
                logging.info(f"Файл готов к обработке ({current_size / 1024 / 1024:.1f} МБ)")
                break

            last_size = current_size
            time.sleep(2)

        start_pipeline(file_path)


# --- ТОЧКА ВХОДА ---
if __name__ == "__main__":
    input_dir = cfg.get('PATHS', 'input_folder')

    if not os.path.exists(input_dir):
        logging.error(f"Папка для мониторинга не найдена: {input_dir}")
        exit(1)

    logging.info("🤖 AI-секретарь запущен")
    logging.info(f"Движок транскрипции: {cfg.get('TRANSCRIPTION', 'engine', fallback='gigaam').upper()}")
    logging.info(f"Слежу за папкой: {input_dir}")

    # Обработка уже существующих файлов
    existing_files = [
        os.path.join(input_dir, f)
        for f in os.listdir(input_dir)
        if f.endswith(('.webm', '.mp4', '.mkv'))
    ]

    if existing_files:
        logging.info(f"Найдено {len(existing_files)} существующих файлов...")
        for f_path in existing_files:
            start_pipeline(f_path)

    # Запуск мониторинга
    handler = TelemostHandler()
    observer = Observer()
    observer.schedule(handler, input_dir, recursive=False)
    observer.start()

    logging.info("Режим мониторинга активен. Ctrl+C для остановки.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Получен сигнал остановки...")
        observer.stop()

    observer.join()
    logging.info("AI-секретарь остановлен.")