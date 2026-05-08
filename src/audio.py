import subprocess
import logging
from pathlib import Path
from utils.config_loader import cfg

logger = logging.getLogger(__name__)

def extract_audio(input_video_str: str) -> str:
    """
    Извлекает аудиодорожку из видео с помощью FFmpeg.
    Конвертирует в 16kHz, mono, pcm_s16le.
    """
    input_path = Path(input_video_str)
    # Создаем временный wav рядом с оригиналом
    output_wav = input_path.with_name(f"{input_path.stem}_temp.wav")

    logger.info(f"╒══ Извлечение аудио")
    logger.info(f"│   Source: {input_path.name}")

    # -vn: отключить видео (ускоряет процесс)
    # -sn: отключить субтитры
    # -y: перезапись
    cmd = [
        'ffmpeg', '-y', 
        '-i', str(input_path),
        '-vn',                # Полностью игнорировать видеопоток
        '-sn',                # Игнорировать субтитры
        '-dn',                # Игнорировать потоки данных
        '-ar', '16000', 
        '-ac', '1', 
        '-c:a', 'pcm_s16le',
        str(output_wav)
    ]

    try:
        # Запускаем процесс
        result = subprocess.run(
            cmd, 
            check=True, 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.PIPE
        )

        if not output_wav.exists():
            raise FileNotFoundError("FFmpeg завершился успешно, но выходной файл отсутствует.")

        file_size_mb = output_wav.stat().st_size / (1024 * 1024)
        logger.info(f"│   [ DONE ] WAV готов ({file_size_mb:.2f} MB)")
        logger.info(f"┕━━ Путь: {output_wav.name}")
        
        return str(output_wav)

    except FileNotFoundError:
        logger.error("│   [ FAIL ] FFmpeg не найден в системе. Установите его и добавьте в PATH.")
        return None
    except subprocess.CalledProcessError as e:
        # Берем последние пару строк лога для контекста
        err_out = e.stderr.decode(errors='replace').strip().split('\n')
        last_error = err_out[-1] if err_out else "Unknown error"
        logger.error(f"│   [ FAIL ] FFmpeg: {last_error}")
        return None
    except Exception as e:
        logger.error(f"│   [ FAIL ] Ошибка при извлечении аудио: {e}")
        return None