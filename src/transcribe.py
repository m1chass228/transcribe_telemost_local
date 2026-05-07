# src/transcribe.py
import os
import re
import sys
import subprocess
import logging
from collections import Counter
from src.config_loader import cfg

HF_TOKEN = ""
os.environ["HF_TOKEN"] = HF_TOKEN


def clean_transcript(txt_path):
    with open(txt_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    original_count = len(lines)

    def extract_text(line):
        return re.sub(r'\[[\d:.,\s>-]+\]', '', line).strip()

    texts       = [extract_text(l) for l in lines]
    text_counts = Counter(t for t in texts if t)
    total_lines = len([t for t in texts if t])

    spam_threshold = max(5, int(total_lines * 0.03))
    spam_phrases   = {
        phrase for phrase, count in text_counts.items()
        if count > spam_threshold
    }

    if spam_phrases:
        logging.warning(f"Обнаружен спам ({len(spam_phrases)} фраз), удаляю")

    cleaned      = []
    prev_text    = None
    repeat_count = 0
    MAX_REPEATS  = 1

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
    logging.info(f"Очистка: {original_count} → {len(cleaned)} строк (удалено {removed})")


def run_gigaam(wav_path: str) -> str:
    """
    Запускает GigaAM в отдельном subprocess.
    После завершения дочернего процесса вся память (torch) освобождается
    автоматически — Ollama получает чистую RAM.
    """
    if not wav_path or not os.path.exists(wav_path):
        raise FileNotFoundError(f"WAV файл не найден: {wav_path}")

    output_prefix = wav_path.rsplit('.', 1)[0]
    txt_path      = output_prefix + ".txt"

    # Путь к воркеру — рядом с этим файлом
    worker_script = os.path.join(os.path.dirname(__file__), '_gigaam_worker.py')

    if not os.path.exists(worker_script):
        raise FileNotFoundError(f"Worker не найден: {worker_script}")

    model_revision = cfg.get('GIGAAM', 'model', fallback='e2e_rnnt')

    env = {
        **os.environ,
        'HF_TOKEN':        HF_TOKEN,
        'GIGAAM_REVISION': model_revision,
    }

    logging.info(f"Запускаю GigaAM worker (отдельный процесс)...")

    try:
        subprocess.run(
            [sys.executable, worker_script, wav_path, txt_path],
            check=True, text=True, env=env
        )
        logging.info("Ожидание освобождения системной памяти...")
        import time
        time.sleep(3) # Даем ОС время на сборку мусора
        
        # Системная команда очистки (может потребовать время, но эффективна)
        # subprocess.run(["purge"]) # Работает только на macOS, чистит дисковый кэш в RAM
        # --------------------
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"GigaAM worker упал с кодом {e.returncode}")

    if not os.path.exists(txt_path):
        raise FileNotFoundError(f"GigaAM не создал файл: {txt_path}")

    if os.path.getsize(txt_path) == 0:
        raise RuntimeError(f"GigaAM создал пустой файл: {txt_path}")

    clean_transcript(txt_path)
    logging.info(f"✅ GigaAM завершён: {os.path.basename(txt_path)}")
    return txt_path


def run_whisper(wav_path, bin_path, model_path):
    import subprocess as sp
    output_prefix = wav_path.rsplit('.', 1)[0]
    txt_path      = output_prefix + ".txt"
    language      = cfg.get('WHISPER', 'language', fallback='ru')
    vad_model     = "./whisper.cpp/models/ggml-silero-v6.2.0.bin"

    cmd = [
        bin_path, "-m", model_path, "-f", wav_path,
        "-l", language, "--output-txt", "-of", output_prefix,
        "--threads", "8",
        "--vad", "--vad-model", vad_model,
        "--no-speech-thold", "0.6",
        "--no-fallback",
        "--entropy-thold", "2.8",
    ]

    logging.info("Запускаю Whisper.cpp...")
    sp.run(cmd, check=True, text=True)

    if os.path.exists(txt_path):
        clean_transcript(txt_path)
        logging.info(f"Whisper завершён: {os.path.basename(txt_path)}")
        return txt_path
    else:
        raise FileNotFoundError("Whisper не создал txt-файл")


def transcribe_audio(wav_path: str) -> str:
    engine = cfg.get('TRANSCRIPTION', 'engine', fallback='gigaam').strip().lower()
    logging.info(f"Запуск транскрипции через → {engine.upper()}")

    if engine == "gigaam":
        return run_gigaam(wav_path)
    else:
        bin_path   = cfg.get('WHISPER', 'bin_path')
        model_path = cfg.get('WHISPER', 'model_path')
        return run_whisper(wav_path, bin_path, model_path)