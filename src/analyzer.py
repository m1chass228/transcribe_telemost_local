import ollama
import json
import logging

from utils.config_loader import cfg
from utils.logs import get_preview_limit

logger = logging.getLogger(__name__)

def _deduplicate_tasks(rows):
    """Удаляет почти идентичные задачи, возникшие из-за overlap чанков"""
    unique_tasks = []
    seen = set()
    for row in rows:
        # Создаем ключ из ответственного и нормализованного названия задачи
        key = f"{row['assignee_code']}_{row['task'].lower().strip()}"
        if key not in seen:
            unique_tasks.append(row)
            seen.add(key)
    return unique_tasks

def analyze_meeting(txt_file):
    # Загружаем настройки с приведением типов
    model = cfg.get('OLLAMA', 'model', fallback='llama3.2:3b')
    c_size = cfg.getint('OLLAMA', 'chunk_size', fallback=2000) 
    overlap = cfg.getint('OLLAMA', 'overlap', fallback=300)
    
    # Важно: параметры нейронки должны быть float/int
    temp = cfg.getfloat('OLLAMA', 'temperature', fallback=0.1)
    n_ctx = cfg.getint('OLLAMA', 'num_ctx', fallback=3072)
    t_p = cfg.getfloat('OLLAMA', 'top_p', fallback=0.9)
    t_k = cfg.getint('OLLAMA', 'top_k', fallback=20)
    keep_alive = cfg.get('OLLAMA', 'keep_alive', fallback='0')

    with open(txt_file, 'r', encoding='utf-8') as f:
        text = f.read()

    # Разбиваем на чанки
    chunks = []
    for i in range(0, len(text), c_size - overlap):
        chunks.append(text[i:i + c_size])

    logger.info(f"»»» Подготовка: {len(chunks)} чанков. Модель: {model} (ctx: {n_ctx})")

    all_rows = []
    system_instruction = cfg.get('OLLAMA', 'prompt')
    client = ollama.Client(timeout=180)

    for i, chunk in enumerate(chunks):
        limit = get_preview_limit()
        chunk_bytes = len(chunk.encode('utf-8'))

        p_text = chunk[:limit].replace('\n', ' ') if limit else chunk.replace('\n', ' ')
        chunk_preview = p_text + "..." if limit and len(chunk) > limit else p_text
        
        logger.info(f"╒══ Чанк {i+1}/{len(chunks)}")
        logger.debug(f"│   Размер: {chunk_bytes} bytes")
        logger.debug(f"│   Контекст: {chunk_preview}")

        try:
            response = client.generate(
                model=model,
                prompt=f"{system_instruction}\n\n=== TRANSCRIPT CHUNK ===\n{chunk}\n=== END ===",
                format='json',
                keep_alive = keep_alive,
                options={
                    'temperature': temp,
                    'num_ctx': n_ctx,  
                    'top_p': t_p,
                    'top_k': t_k,
                }
            )

            answer = response.response.strip()
            logger.ai_trace(f"RAW OLLAMA JSON:\n{answer}") # Для глубокой отладки
            
            try:
                data = json.loads(answer)
                raw_list = data.get('rows') or []
                
                found_in_chunk = 0
                for item in raw_list:
                    if isinstance(item, dict):
                        row = {
                            'task': item.get('task') or '???',
                            'assignee': item.get('assignee_name') or 'unknown',
                            'assignee_code': item.get('assignee_code') or 'unknown',
                            'details': item.get('report_text') or '',
                            'deadline': item.get('deadline')
                        }
                        all_rows.append(row)
                        found_in_chunk += 1
                        logger.info(f"│   ├─ ◈ [{row['assignee_code']}] {row['task']}")
                
                if found_in_chunk == 0:
                    logger.info("│   ╰─ [ EMPTY ] Задач в контексте не найдено")
                else:
                    logger.info(f"│   ╰─ [ DONE ] Найдено объектов: {found_in_chunk}")

            except json.JSONDecodeError:
                logger.error(f"│   ╰─ [ FAIL ] Модель выдала битый JSON")

        except Exception as e:
            logger.error(f"│   ╰─ [ CRIT ] Критическая ошибка: {e}")

    logger.info(f"┕━━ Завершено. Всего извлечено: {len(all_rows)}")

    # Дедупликация перед возвратом
    final_rows = _deduplicate_tasks(all_rows)
    logger.info(f"┕━━ Анализ завершен. Найдено всего: {len(all_rows)}, уникальных: {len(final_rows)}")
    
    return {"rows": final_rows}