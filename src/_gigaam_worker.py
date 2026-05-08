import sys
import os
import logging
import torch
import torchaudio
import platform

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger("GigaAM-Worker")

def get_device():
    """Аналог #ifdef для выбора устройства"""
    if torch.cuda.is_available():
        return torch.device("cuda")
    elif torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")

def cleanup_memory(device, model=None):
    """Универсальная очистка памяти (Metal, CUDA, CPU)"""
    logger.info(f"│   [ MEM ] Очистка ресурсов ({device.type})...")
    
    if model is not None:
        del model
    
    if device.type == "mps":
        # Специфично для Mac (твоего M3)
        torch.mps.empty_cache()
        torch.mps.synchronize()
    elif device.type == "cuda":
        # Специфично для NVIDIA
        torch.cuda.empty_cache()
    
    # Общее для всех
    import gc
    gc.collect()

def main():
    if len(sys.argv) < 3:
        print("Usage: _gigaam_worker.py <wav_path> <txt_path>")
        sys.exit(1)

    wav_path = sys.argv[1]
    txt_path = sys.argv[2]

    hf_token = os.environ.get('HF_TOKEN', '')
    revision = os.environ.get('GIGAAM_REVISION', 'e2e_rnnt')

    device = get_device()
    logger.info(f"╒══ GigaAM Worker запущен")
    logger.info(f"│   OS: {platform.system()} {platform.machine()}")
    logger.info(f"│   Device: {device.type.upper()}")

    model = None

    try:
        from transformers import AutoModel

        logger.info(f"│   [ LOAD ] Загрузка ai-sage/GigaAM-v3...")
        
        # 2. Загружаем модель
        model = AutoModel.from_pretrained(
            "ai-sage/GigaAM-v3",
            revision=revision,
            trust_remote_code=True,
            token=hf_token
        ).to(device)
        
        model.eval()

        # 3. Загрузка аудио
        waveform, sr = torchaudio.load(wav_path)
        segment_sec = 15
        segment_samples = int(sr * segment_sec)
        total_segments = (waveform.shape[1] + segment_samples - 1) // segment_samples

        logger.info(f"│   [ PROC ] Сегментов: {total_segments}")

        full_text = []
        output_prefix = wav_path.rsplit('.', 1)[0]

        # 4. Цикл транскрибации
        for i, start in enumerate(range(0, waveform.shape[1], segment_samples)):
            end = min(start + segment_samples, waveform.shape[1])
            segment = waveform[:, start:end]

            temp_path = f"{output_prefix}_seg_{i:04d}.wav"
            torchaudio.save(temp_path, segment, sr)

            with torch.no_grad():
                result = model.transcribe(temp_path)
                text = result if isinstance(result, str) else result.get("text", str(result))
                if text.strip():
                    full_text.append(text.strip())

            if os.path.exists(temp_path):
                os.remove(temp_path)

            # Логируем прогресс каждые 10 сегментов
            if (i + 1) % 10 == 0 or (i + 1) == total_segments:
                logger.info(f"│   ├── {i+1}/{total_segments} выполнено")

        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(full_text) + "\n")

        logger.info(f"│   [ DONE ] Результат: {txt_path}")

    except Exception as e:
        logger.error(f"│   [ FAIL ] Критическая ошибка: {e}")
        sys.exit(1)
    finally:
        cleanup_memory(device, model)
        logger.info(f"┕━━ Процесс завершен")

if __name__ == "__main__":
    main()