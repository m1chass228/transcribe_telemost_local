import os
import re
import sys
import subprocess
import logging
import time
from pathlib import Path
from collections import Counter
from utils.config_loader import cfg

logger = logging.getLogger(__name__)

def clean_transcript(txt_path: Path):
    """Очистка текста от галлюцинаций и серийных повторов"""
    if not txt_path.exists():
        return

    lines = txt_path.read_text(encoding='utf-8').splitlines()
    if not lines:
        return

    original_count = len(lines)

    def get_pure_text(line):
        # Убираем таймстампы [00:00:00] и лишние пробелы
        return re.sub(r'\[[\d:.,\s>-]+\]', '', line).strip().lower()

    # 1. Фильтр глобального спама (галлюцинации модели)
    text_counts = Counter(get_pure_text(l) for l in lines if get_pure_text(l))
    # Если фраза повторяется аномально часто для всей встречи
    spam_threshold = max(10, int(len(lines) * 0.05)) 
    spam_phrases = {ph for ph, count in text_counts.items() if count > spam_threshold}

    cleaned = []
    prev_text = None
    repeat_in_row = 0

    for line in lines:
        pure = get_pure_text(line)
        if not pure:
            continue
            
        # Удаляем если это глобальный спам
        if pure in spam_phrases:
            continue
            
        # Удаляем если это локальный повтор (подряд)
        if pure == prev_text:
            repeat_in_row += 1
            if repeat_in_row >= 1: # Больше 1 повтора подряд — удаляем
                continue
        else:
            repeat_in_row = 0
            
        cleaned.append(line)
        prev_text = pure

    txt_path.write_text('\n'.join(cleaned), encoding='utf-8')
    
    removed = original_count - len(cleaned)
    if removed > 0:
        logger.info(f"│   [ CLEAN ] Строк: {original_count} -> {len(cleaned)} (удалено: {removed})")

def run_gigaam(wav_path: Path) -> Path:
    txt_path = wav_path.with_suffix(".txt")
    worker_script = Path(__file__).parent / '_gigaam_worker.py'

    if not worker_script.exists():
        raise FileNotFoundError(f"Worker не найден: {worker_script}")

    hf_token = cfg.get('GIGAAM', 'hf_token', fallback="")
    model_revision = cfg.get('GIGAAM', 'model', fallback='e2e_rnnt')
    
    env = os.environ.copy()
    env.update({'HF_TOKEN': hf_token, 'GIGAAM_REVISION': model_revision})

    logger.info(f"╒══ Запуск GigaAM (Subprocess)")
    
    try:
        # 1. Запуск процесса
        result = subprocess.run(
            [sys.executable, str(worker_script), str(wav_path), str(txt_path)],
            check=True, 
            env=env, 
            capture_output=True, 
            text=True
        )
        
        logger.info("│   [ OK ] GigaAM завершил работу")
        if result.stdout:
            logger.debug(f"GigaAM Output: {result.stdout}")

    except subprocess.CalledProcessError as e:
        # Сюда попадаем, если GigaAM вернул ошибку (код не 0)
        logger.error(f"│   [ FAIL ] GigaAM рухнул с кодом {e.returncode}")
        logger.error(f"│   [ STDERR ]: {e.stderr}")
        raise # Пробрасываем ошибку выше в pipeline.py
        
    except Exception as e:
        # Сюда попадаем при любых других проблемах (нехватка памяти, нет прав и т.д.)
        logger.error(f"│   [ CRIT ] Общая ошибка выполнения: {e}")
        raise

    # --- ВСЁ, ЧТО НИЖЕ, ВЫПОЛНИТСЯ ТОЛЬКО ЕСЛИ НЕТ ОШИБОК ---
    
    # Даем системе "выдохнуть" после тяжелой модели
    time.sleep(2) 

    # Проверка результата
    if not txt_path.exists() or txt_path.stat().st_size == 0:
        logger.error(f"│   [ FAIL ] Файл транскрипции не найден или пуст: {txt_path}")
        raise RuntimeError("Файл транскрипции пуст или не создан")

    # Чистка текста
    clean_transcript(txt_path)
    
    return txt_path

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

def transcribe_audio(wav_path_str: str) -> str:
    """Точка входа для транскрибации"""
    wav_path = Path(wav_path_str)
    engine = cfg.get('TRANSCRIPTION', 'engine', fallback='gigaam').strip().lower()
    
    logger.info(f"│   [ STEP 2/4 ] Транскрибация: {engine}")
    
    if engine == "gigaam":
        result_path = run_gigaam(wav_path)
    else:
        #result_path = run_whisper(wav_path, ...)
        pass
        
    return str(result_path)

# def transcribe_audio(wav_path: str) -> str:
#     engine = cfg.get('TRANSCRIPTION', 'engine', fallback='gigaam').strip().lower()
    
#     if engine == "gigaam":
#         return run_gigaam(wav_path)
#     else:
#         bin_path = cfg.get('WHISPER', 'bin_path')
#         model_path = cfg.get('WHISPER', 'model_path')
#         return run_whisper(wav_path, bin_path, model_path)