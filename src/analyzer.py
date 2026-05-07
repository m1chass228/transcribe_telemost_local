import ollama
import json
import logging
import datetime
from src.config_loader import cfg

def analyze_meeting(txt_file):
    # Загружаем настройки. Для 8GB RAM рекомендую llama3.2:3b или llama3.1:8b-instruct-q4_K_M
    model = cfg.get('OLLAMA', 'model', fallback='llama3.2:3b')
    chunk_size = cfg.getint('OLLAMA', 'chunk_size', fallback=2000) # Уменьшил для стабильности
    overlap = cfg.getint('OLLAMA', 'overlap', fallback=300)

    with open(txt_file, 'r', encoding='utf-8') as f:
        text = f.read()

    # Разбиваем на чанки
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        start += (chunk_size - overlap)

    print(f"🔄 Чанков: {len(chunks)}. Модель: {model}")

    all_rows = []
    today = datetime.datetime.now().strftime("%d.%m.%Y")

    # Английский промпт для лучшей логики и работы с плохим текстом
    system_instruction = f"""
Today is {today}. You are an AI Specialist in noisy transcript analysis for a Veterinary Clinic.
Your goal: Extract actionable tasks from low-quality ASR text.

### RECONSTRUCTION STRATEGY:
1. PHONETIC GUESSING: The text has errors. If a word sounds like a business term or a name but is misspelled (e.g., "priznal na kossii" -> "on commission"), use the most logical veterinary/business replacement.
2. CONTEXTUAL MAPPING: Use the surrounding words to identify entities. 
   - Words near "filial" or "report" are likely branch names or managers.
   - Words near "check-list" or "schedule" are likely staff names.
3. NOISE REDUCTION: Ignore stutters, filler words, and sentences that contain zero actionable verbs.

### ASSIGNEE LOGIC:
Assign tasks to the person reporting or the person being addressed. 
Use these codes:
- ES (Chief Doctor)
- MN (Finance/Deputy)
- EKS (Manager)
- NS (Call Center/Admins)
- unknown (if assignee is unclear)

### OUTPUT FORMAT (Strict JSON):
Return ONLY a JSON object with a "rows" array. 
Values must be in Russian, clear and professional. 
Example: {{ "task": "Проверить отчет по вакцинации", "assignee_code": "NS", ... }}
"""

    client = ollama.Client(timeout=120)

    for i, chunk in enumerate(chunks):
        print(f"\n🧩 [Чанк {i+1}/{len(chunks)}]")
        chunk_preview = (chunk[:100] + '...') if len(chunk) > 100 else chunk
        print(f"📖 Контекст: {chunk_preview.replace('\n', ' ')}")

        try:
            response = client.generate(
                model=model,
                prompt=f"{system_instruction}\n\n=== TRANSCRIPT CHUNK ===\n{chunk}\n=== END ===",
                format='json',
                keep_alive=0, # Выгружаем модель сразу после чанка
                options={
                    'temperature': 0.1,
                    'num_ctx': 3072,  
                    'top_p': 0.9,
                    'top_k': 20,
                }
            )

            answer = response.response.strip()
            
            try:
                data = json.loads(answer)
                raw_list = data.get('rows') or []
                
                found_in_chunk = 0
                for item in raw_list:
                    if isinstance(item, dict):
                        # Сопоставляем ключи из промпта с итоговым словарем
                        row = {
                            'task': item.get('task') or '???',
                            'assignee': item.get('assignee_name') or 'unknown',
                            'assignee_code': item.get('assignee_code') or 'unknown',
                            'details': item.get('report_text') or '',
                            'deadline': item.get('deadline')
                        }
                        all_rows.append(row)
                        found_in_chunk += 1
                        print(f"   📌 [{row['assignee_code']}] {row['task']}")
                
                if found_in_chunk == 0:
                    print("   🔸 Задач не обнаружено")
                else:
                    print(f"   ✅ Чанк обработан, добавлено: {found_in_chunk}")

            except json.JSONDecodeError:
                print(f"   ❌ ОШИБКА JSON. Ответ модели не является валидным JSON.")

        except Exception as e:
            print(f"   💥 Критическая ошибка чанка: {e}")

    print(f"\n📋 Итого извлечено задач: {len(all_rows)}")
    return {"rows": all_rows}