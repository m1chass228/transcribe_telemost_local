import subprocess
import os
from src.config_loader import cfg

def extract_audio(input_video):
    output_wav = input_video.rsplit('.', 1)[0] + "_temp.wav"
    print(f"Обработка: {os.path.basename(input_video)}")

    cmd = [
        'ffmpeg', '-y', '-i', input_video,
        '-ar', '16000', '-ac', '1', '-c:a', 'pcm_s16le',
        output_wav
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return output_wav
    except Exception as e:
        print(f"Ошибка аудио: {e}")
        return None
