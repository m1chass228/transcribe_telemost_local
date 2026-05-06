import ollama
from src.config_loader import cfg

def analyze_meeting(txt_file):
    model = cfg.get('OLLAMA', 'model')
    chunk_size = cfg.getint('OLLAMA', 'chunk_size')
    overlap = cfg.getint('OLLAMA', 'overlap')

    with open(txt_file, 'r', encoding='utf-8') as f:
        text = f.read()

    # Сплиттер с нахлестом (overlap)
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        if end >= len(text): break
        start += (chunk_size - overlap)

    print(f"Нейронка {model} погнала разбирать {len(chunks)} частей...")

    results = []
    for i, chunk in enumerate(chunks):
        # Настраиваем параметры генерации прямо здесь
        response = ollama.generate(
            model=model,
            prompt=f"Вытащи задачи из текста: {chunk}",
            options={'temperature': cfg.getfloat('OLLAMA', 'temperature')}
        )
        results.append(response['response'])
        print(f"[{i+1}/{len(chunks)}] Обработано")

    return results
