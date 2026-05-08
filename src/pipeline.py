import os
import time
import logging
import datetime
import re
from pathlib import Path

from src.audio import extract_audio
from src.transcribe import transcribe_audio    
from src.analyzer import analyze_meeting
from src.output import write_output

from utils.database import get_file_hash, is_already_processed, mark_as_processed
from utils.config_loader import cfg
from utils.lock import create_lock, cleanup_locks

def _parse_date(file_path: Path) -> datetime.datetime:
    """Вспомогательная функция для определения даты встречи."""
    # Регулярка для DD.MM.YY или DD.MM.YYYY
    date_match = re.search(r'(\d{2})\.(\d{2})\.(\d{2,4})', file_path.name)
    
    if date_match:
        day, month, year_str = date_match.groups()
        # Если год 2 цифры (26), делаем 2026. Если 4 (2026) — оставляем.
        year = int(year_str)
        if year < 100:
            year += 2000
        return datetime.datetime(year, int(month), int(day))
    
    # Резервный вариант: дата изменения файла
    file_mtime = file_path.stat().st_mtime
    video_date = datetime.datetime.fromtimestamp(file_mtime)
    logging.warning(f"│   [ WARN ] Дата в названии не найдена, использую системную: {video_date.date()}")
    return video_date

def start_pipeline(file_path_str: str):
    """
    Полный цикл обработки одного файла:
    видео → аудио → транскрипция → анализ → отчёт
    """
    file_path = Path(file_path_str)
    filename = file_path.name
    lock_path = file_path.with_suffix(file_path.suffix + ".lock")
    
    # 1. Проверка на занятость (Lock)
    if lock_path.exists():
        logging.warning(f"│   [ BUSY ] Файл уже обрабатывается: {filename}")
        return

    # 2. Проверка базы данных (Hash)
    try:
        f_hash = get_file_hash(str(file_path))
        if not f_hash:
            logging.error(f"│   [ FAIL ] Ошибка хеширования: {filename}")
            return

        if is_already_processed(f_hash):
            logging.info(f"│   [ SKIP ] Уже в базе: {filename}")
            return
    except Exception as e:
        logging.error(f"│   [ FAIL ] Ошибка при обращении к БД: {e}")
        return

    # 3. Подготовка
    video_date = _parse_date(file_path)
    create_lock(str(lock_path))
    
    logging.info(f"╒══ СТАРТ: {filename}")
    start_time = time.time()
    wav_path = None

    try:
        # ШАГ 1: Извлечение аудио
        logging.info("│   [ STEP 1/4 ] Извлечение аудио...")
        extracted = extract_audio(str(file_path))
        if not extracted:
            raise RuntimeError("FFmpeg не вернул путь к WAV файлу")
        wav_path = Path(extracted)

        # ШАГ 2: Транскрибация
        txt_path = file_path.with_suffix(".txt")
        
        if txt_path.exists():
            logging.info(f"│   [ CACHE ] Найден готовый текст, шаг пропущен.")
        else:
            engine_name = cfg.get('TRANSCRIPTION', 'engine', fallback='gigaam').upper()
            logging.info(f"│   [ STEP 2/4 ] Транскрибация ({engine_name})...")
            # Обновляем txt_path, если функция возвращает новый путь
            txt_path = Path(transcribe_audio(str(wav_path)))

        # Очистка аудио сразу после транскрибации (экономим место)
        if wav_path and wav_path.exists():
            wav_path.unlink()
            wav_path = None
        
        logging.info(f"│   [ INFO ] Текст сохранен в: {txt_path.absolute()}")

        # ШАГ 3: Анализ
        logging.info("│   [ STEP 3/4 ] AI Анализ (Ollama)...")
        data = analyze_meeting(str(txt_path))

        # ШАГ 4: Генерация отчета
        logging.info("│   [ STEP 4/4 ] Запись в Excel...")
        write_output(data, video_date=video_date)

        # Финализация в БД
        mark_as_processed(f_hash, filename)

        elapsed = (time.time() - start_time) / 60
        logging.info(f"┕━━ [ DONE ] Время: {elapsed:.1f} мин.")

    except Exception as e:
        logging.error(f"│   [ CRIT ] Ошибка пайплайна: {e}", exc_info=True)
    
    finally:
        # ГАРАНТИРОВАННАЯ ОЧИСТКА
        if wav_path and wav_path.exists():
            wav_path.unlink()
            logging.info(f"│   [ CLEAN ] Удален временный WAV")
        
        if lock_path.exists():
            cleanup_locks(str(lock_path))