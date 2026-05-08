import subprocess
import os
import logging
from utils.config_loader import cfg

logger = logging.getLogger(__name__)

def extract_audio(input_video):
    """
    Извлекает аудиодорожку из видео с помощью FFmpeg.
    Конвертирует в 16kHz, mono, pcm_s16le (стандарт для GigaAM/Whisper).
    """
    video_filename = os.path.basename(input_video)
    output_wav = input_video.rsplit('.', 1)[0] + "_temp.wav"

    logger.info(f"╒══ Извлечение аудио")
    logger.info(f"│   Source: {video_filename}")

    # Команда FFmpeg:
    # -y: перезаписывать файл если существует
    # -ar 16000: частота дискретизации 16кГц
    # -ac 1: моно
    # -c:a pcm_s16le: кодек
    cmd = [
        'ffmpeg', '-y', '-i', input_video,
        '-ar', '16000', '-ac', '1', '-c:a', 'pcm_s16le',
        output_wav
    ]

    try:
        # Запускаем процесс, скрывая лишний вывод FFmpeg
        subprocess.run(
            cmd, 
            check=True, 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.PIPE # Захватываем ошибки для логов
        )

        if not os.path.exists(output_wav):
            raise FileNotFoundError("FFmpeg завершился без ошибок, но выходной файл не создан")

        file_size_mb = os.path.getsize(output_wav) / (1024 * 1024)
        logger.info(f"│   [ DONE ] WAV готов ({file_size_mb:.2f} MB)")
        logger.info(f"┕━━ Путь: {os.path.basename(output_wav)}")
        
        return output_wav

    except subprocess.CalledProcessError as e:
        # Если FFmpeg вернул ошибку, вытаскиваем детали
        err_msg = e.stderr.decode().split('\n')[-2] if e.stderr else "Unknown FFmpeg error"
        logger.error(f"│   [ FAIL ] FFmpeg: {err_msg}")
        return None
    except Exception as e:
        logger.error(f"│   [ FAIL ] Критическая ошибка: {e}")
        return None