import os
import re
import sys
import subprocess
import logging
import time
from collections import Counter
from utils.config_loader import cfg

logger = logging.getLogger(__name__)

HF_TOKEN = cfg.get('GIGAAM', 'hf_token', fallback="")
os.environ["HF_TOKEN"] = HF_TOKEN

def clean_transcript(txt_path):
    """Очистка текста от галлюцинаций и повторов (спам-фильтр)"""
    if not os.path.exists(txt_path):
        return

    with open(txt_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    original_count = len(lines)

    def extract_text(line):
        # Удаляем временные метки [00:00:00]
        return re.sub(r'\[[\d:.,\s>-]+\]', '', line).strip()

    texts = [extract_text(l) for l in lines]
    text_counts = Counter(t for t in texts if t)
    total_lines = len([t for t in texts if t])

    # Динамический порог спама
    spam_threshold = max(5, int(total_lines * 0.03))
    spam_phrases = {
        phrase for phrase, count in text_counts.items()
        if count > spam_threshold
    }

    if spam_phrases:
        logger.warning(f"│   [ SPAM ] Обнаружено {len(spam_phrases)} аномальных повторов")

    cleaned = []
    prev_text = None
    repeat_count = 0
    MAX_REPEATS = 1

    for line in lines:
        text = extract_text(line)
        if not text:
            cleaned.append(line)
            continue
        if text in spam_phrases:
            continue
        if text == prev_text:
            repeat_count += 1
            if repeat_count > MAX_REPEATS:
                continue
        else:
            repeat_count = 0

        cleaned.append(line)
        prev_text = text

    with open(txt_path, 'w', encoding='utf-8') as f:
        f.writelines(cleaned)

    removed = original_count - len(cleaned)
    logger.info(f"│   [ CLEAN ] Строк: {original_count} -> {len(cleaned)} (removed: {removed})")


def run_gigaam(wav_path: str) -> str:
    output_prefix = wav_path.rsplit('.', 1)[0]
    txt_path = output_prefix + ".txt"
    worker_script = os.path.join(os.path.dirname(__file__), '_gigaam_worker.py')

    if not os.path.exists(worker_script):
        raise FileNotFoundError(f"Worker не найден: {worker_script}")

    model_revision = cfg.get('GIGAAM', 'model', fallback='e2e_rnnt')
    env = {**os.environ, 'HF_TOKEN': HF_TOKEN, 'GIGAAM_REVISION': model_revision}

    logger.info(f"╒══ Запуск GigaAM")
    logger.info(f"│   Режим: Subprocess (изоляция RAM)")

    try:
        # Запускаем воркер и ждем завершения
        subprocess.run(
            [sys.executable, worker_script, wav_path, txt_path],
            check=True, text=True, env=env
        )
        
        # КРИТИЧЕСКИ ВАЖНО для 8GB: пауза перед запуском Ollama
        logger.info("│   [ MEM ] Ожидание выгрузки весов из RAM...")
        time.sleep(3) 

        if not os.path.exists(txt_path) or os.path.getsize(txt_path) == 0:
            raise RuntimeError("Воркер не создал файл или файл пуст")

        clean_transcript(txt_path)
        logger.info(f"┕━━ [ DONE ] Транскрипция завершена")
        return txt_path

    except subprocess.CalledProcessError as e:
        logger.error(f"│   [ FAIL ] GigaAM worker crashed (code: {e.returncode})")
        raise


def run_whisper(wav_path, bin_path, model_path):
    output_prefix = wav_path.rsplit('.', 1)[0]
    txt_path = output_prefix + ".txt"
    language = cfg.get('WHISPER', 'language', fallback='ru')
    
    # Путь к VAD модели (если используешь whisper.cpp)
    vad_model = os.path.join(os.path.dirname(bin_path), "models/ggml-silero-v6.2.0.bin")

    logger.info(f"╒══ Запуск Whisper.cpp")
    logger.info(f"│   Модель: {os.path.basename(model_path)}")

    cmd = [
        bin_path, "-m", model_path, "-f", wav_path,
        "-l", language, "--output-txt", "-of", output_prefix,
        "--threads", "8",
        "--no-fallback"
    ]
    
    # Добавляем VAD если файл модели существует
    if os.path.exists(vad_model):
        cmd.extend(["--vad", "--vad-model", vad_model])

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
        
        if os.path.exists(txt_path):
            clean_transcript(txt_path)
            logger.info(f"┕━━ [ DONE ] Whisper завершен")
            return txt_path
        else:
            raise FileNotFoundError("Whisper.cpp не сгенерировал txt")
            
    except subprocess.CalledProcessError:
        logger.error("│   [ FAIL ] Whisper.cpp вернул ошибку")
        raise


def transcribe_audio(wav_path: str) -> str:
    engine = cfg.get('TRANSCRIPTION', 'engine', fallback='gigaam').strip().lower()
    
    if engine == "gigaam":
        return run_gigaam(wav_path)
    else:
        bin_path = cfg.get('WHISPER', 'bin_path')
        model_path = cfg.get('WHISPER', 'model_path')
        return run_whisper(wav_path, bin_path, model_path)