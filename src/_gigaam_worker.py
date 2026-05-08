import sys
import os
import logging
import torch
import torchaudio
import gc
from pathlib import Path

logger = logging.getLogger("GigaAM-Worker")

def get_device():
    if torch.cuda.is_available(): return torch.device("cuda")
    if torch.backends.mps.is_available(): return torch.device("mps")
    return torch.device("cpu")

def main():
    wav_path = Path(sys.argv[1])
    txt_path = Path(sys.argv[2])
    device = get_device()

    try:
        from transformers import AutoModel
        
        # 1. Загрузка VAD (чтобы резать по паузам, а не по живому)
        # Silero VAD весит копейки и очень точный
        vad_model, utils = torch.hub.load(repo_or_dir='snakers4/silero-vad', model='silero_vad')
        (get_speech_timestamps, _, read_audio, _, _) = utils

        # 2. Загрузка GigaAM
        model = AutoModel.from_pretrained(
            "ai-sage/GigaAM-v3",
            revision=os.environ.get('GIGAAM_REVISION', 'e2e_rnnt'),
            trust_remote_code=True,
            token=os.environ.get('HF_TOKEN', '')
        ).to(device)
        model.eval()

        # 3. Читаем аудио
        audio = read_audio(str(wav_path), sampling_rate=16000)
        
        # Получаем метки речи (минимум 0.5 сек тишины для разреза)
        speech_timestamps = get_speech_timestamps(audio, vad_model, sampling_rate=16000)
        
        logger.info(f"│   [ PROC ] Обнаружено фрагментов речи: {len(speech_timestamps)}")

        full_text = []
        
        # 4. Обработка фрагментов
        with torch.no_grad():
            for i, ts in enumerate(speech_timestamps):
                # Вырезаем кусок
                segment = audio[ts['start']:ts['end']].unsqueeze(0).to(device)
                
                # Транскрибируем (GigaAM v3 умеет работать с тензорами)
                # Если твоя ревизия требует путь к файлу, используй io.BytesIO
                # Но обычно в v3 работает model.transcribe(segment)
                result = model.transcribe(segment) 
                
                text = result if isinstance(result, str) else result.get("text", "")
                if text.strip():
                    full_text.append(text.strip())

                if (i + 1) % 50 == 0:
                    logger.info(f"│   ├── {i+1}/{len(speech_timestamps)} фрагментов обработано")

        txt_path.write_text("\n".join(full_text), encoding='utf-8')

    except Exception as e:
        logger.error(f"│   [ FAIL ] {e}")
        sys.exit(1)
    finally:
        # Максимально жесткая очистка
        if 'model' in locals(): del model
        if 'audio' in locals(): del audio
        gc.collect()
        if device.type == "cuda": torch.cuda.empty_cache()
        if device.type == "mps": torch.mps.empty_cache()

if __name__ == "__main__":
    main()