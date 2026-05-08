import sys
import os
import logging
import torch
import gc
from pathlib import Path

import io
import soundfile as sf

# Отключаем интерактивные запросы PyTorch Hub
torch.hub.set_dir(str(Path.home() / ".cache" / "torch" / "hub"))

logger = logging.getLogger("GigaAM-Worker")

def get_device():
    if torch.cuda.is_available(): return torch.device("cuda")
    if torch.backends.mps.is_available(): return torch.device("mps")
    return torch.device("cpu")

def main():
    if len(sys.argv) < 3:
        sys.exit(1)

    wav_path = Path(sys.argv[1])
    txt_path = Path(sys.argv[2])
    device = get_device()

    try:
        from transformers import AutoModel
        
        # 1. Загрузка VAD с принудительным доверием (trust_repo=True)
        # Это убирает запрос "Do you trust this repository (y/N)?"
        vad_model, utils = torch.hub.load(
            repo_or_dir='snakers4/silero-vad', 
            model='silero_vad', 
            trust_repo=True
        )
        (get_speech_timestamps, _, _, _, _) = utils

        # 2. Загрузка GigaAM
        model = AutoModel.from_pretrained(
            "ai-sage/GigaAM-v3",
            revision=os.environ.get('GIGAAM_REVISION', 'e2e_rnnt'),
            trust_remote_code=True,
            token=os.environ.get('HF_TOKEN', '')
        ).to(device)
        model.eval()

        # 3. БЕЗОПАСНОЕ ЧТЕНИЕ АУДИО
        # Вместо read_audio из utils используем torchaudio напрямую, 
        # так как оно стабильнее работает с путями на Mac
        import torchaudio
        audio, sr = torchaudio.load(str(wav_path))
        
        # GigaAM и Silero требуют 16kHz
        if sr != 16000:
            resampler = torchaudio.transforms.Resample(sr, 16000)
            audio = resampler(audio)
        
        # Silero VAD ожидает моно-сигнал (1 канал)
        if audio.shape[0] > 1:
            audio = torch.mean(audio, dim=0, keepdim=True)
        
        # Для Silero VAD нужен плоский тензор (S)
        audio_flat = audio.squeeze(0)
        
        # Получаем метки речи
        speech_timestamps = get_speech_timestamps(audio_flat, vad_model, sampling_rate=16000)
        
        logger.info(f"│   [ PROC ] Обнаружено фрагментов речи: {len(speech_timestamps)}")

        full_text = []
        
        # 4. Обработка фрагментов
        with torch.no_grad():
            for i, ts in enumerate(speech_timestamps):
                # Вырезаем фрагмент по меткам времени VAD
                segment = audio[:, ts['start']:ts['end']]
                
                # Путь для временного файла фрагмента
                # Используем i, чтобы файлы не пересекались при записи
                tmp_segment_path = f"seg_part_{i}.wav"
                
                try:
                    # Сохраняем тензор в реальный файл (16кГц, моно)
                    # GigaAM v3 ОЧЕНЬ хочет видеть путь к файлу на диске
                    sf.write(tmp_segment_path, segment.t().numpy(), 16000)

                    # Вызываем транскрибацию, передавая ПУТЬ
                    result = model.transcribe(tmp_segment_path)
                    
                    # Извлекаем текст
                    text = result if isinstance(result, str) else result.get("text", "")
                    
                    if text.strip():
                        full_text.append(text.strip())
                        # Печатаем прогресс, чтобы ты видел, что процесс идет
                        logger.info(f"│   [фрагмент {i+1}] {text.strip()[:50]}...")
                        
                except Exception as e:
                    logger.error(f"Ошибка на фрагменте {i}: {e}")
                finally:
                    # Удаляем временный файл сразу после использования
                    if os.path.exists(tmp_segment_path):
                        os.remove(tmp_segment_path)

                if (i + 1) % 10 == 0:
                    logger.info(f"│   ├── {i+1}/{len(speech_timestamps)} фрагментов готово")

        txt_path.write_text("\n".join(full_text), encoding='utf-8')

    except Exception as e:
        logger.error(f"│   [ FAIL ] {e}", exc_info=True)
        sys.exit(1)
    finally:
        if 'model' in locals(): del model
        if 'audio' in locals(): del audio
        gc.collect()
        if device.type == "cuda": torch.cuda.empty_cache()
        if device.type == "mps": torch.mps.empty_cache()

if __name__ == "__main__":
    main()