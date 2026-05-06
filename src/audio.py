import subprocess
import os
from src.config_loader import cfg

def extract_audio(input_video):
    output_wav = input_video.rsplit('.', 1)[0] + "_temp.wav"

    threshold = cfg.get('AUDIO', 'silence_threshold')
    duration = cfg.get('AUDIO', 'silence_duration')

    # Собираем фильтр динамически
    silence_filter = f"silenceremove=stop_periods=-1:stop_duration={duration}:stop_threshold={threshold}"

    print(f"Обработка: {os.path.basename(input_video)} (тишина: {threshold}, мин_длительность: {duration}с)")

    cmd = [
        'ffmpeg', '-y', '-i', input_video,
        '-af', silence_filter,
        '-ar', '16000', '-ac', '1', '-c:a', 'pcm_s16le',
        output_wav
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return output_wav
    except Exception as e:
        print(f"Ошибка аудио: {e}")
        return None
