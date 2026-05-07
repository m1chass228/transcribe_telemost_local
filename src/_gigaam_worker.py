import sys
import os
import logging
import torch
import torchaudio

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

def main():
    if len(sys.argv) < 3:
        print("Usage: _gigaam_worker.py <wav_path> <txt_path>")
        sys.exit(1)

    wav_path = sys.argv[1]
    txt_path = sys.argv[2]
    hf_token = os.environ.get('HF_TOKEN', '')
    revision = os.environ.get('GIGAAM_REVISION', 'e2e_rnnt')

    from transformers import AutoModel

    # 1. Определяем устройство: MPS (Metal) для M3 — это критично для 8GB RAM
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    logging.info(f"GigaAM worker: Использую устройство -> {device}")

    try:
        logging.info(f"GigaAM worker: Загрузка модели ai-sage/GigaAM-v3 ({revision})...")
        
        # 2. Загружаем модель ОДИН РАЗ и сразу на устройство
        model = AutoModel.from_pretrained(
            "ai-sage/GigaAM-v3",
            revision=revision,
            trust_remote_code=True,
            token=hf_token
        ).to(device)
        
        model.eval()
        logging.info("GigaAM worker: Модель готова.")

        # 3. Загрузка аудио
        waveform, sr = torchaudio.load(wav_path)

        segment_sec     = 15
        segment_samples = int(sr * segment_sec)
        output_prefix   = wav_path.rsplit('.', 1)[0]
        full_text       = []
        total_segments  = (waveform.shape[1] + segment_samples - 1) // segment_samples

        logging.info(f"GigaAM worker: Обработка {total_segments} сегментов...")

        # 4. Цикл транскрибации
        for i, start in enumerate(range(0, waveform.shape[1], segment_samples)):
            end      = min(start + segment_samples, waveform.shape[1])
            segment  = waveform[:, start:end]

            temp_path = f"{output_prefix}_seg_{i:04d}.wav"
            torchaudio.save(temp_path, segment, sr)

            with torch.no_grad():
                # Метод transcribe сам разберется с устройством, если модель уже на mps
                result = model.transcribe(temp_path)
                text   = result if isinstance(result, str) else result.get("text", str(result))
                if text.strip():
                    full_text.append(text.strip())

            if os.path.exists(temp_path):
                os.remove(temp_path)

            if (i + 1) % 20 == 0 or (i + 1) == total_segments:
                logging.info(f"GigaAM worker: {i+1}/{total_segments} сегментов завершено")

        # 5. Сохранение результата
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(full_text) + "\n")

        logging.info(f"GigaAM worker: Успешно сохранено в {txt_path}")

    except Exception as e:
        logging.error(f"GigaAM worker: Критическая ошибка: {e}")
        sys.exit(1)
    finally:
        # 6. ОЧИСТКА ПАМЯТИ: Самый важный блок для Mac 8GB
        logging.info("GigaAM worker: Очистка кэша памяти...")
        if device.type == "mps":
            # Принудительно выгружаем тензоры и чистим кэш Metal
            if 'model' in locals():
                del model
            torch.mps.empty_cache()
            torch.mps.synchronize()
        
        logging.info("GigaAM worker: Процесс завершен.")

if __name__ == "__main__":
    main()