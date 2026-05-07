import os
import json
from src.config_loader import cfg

def write_to_excel(data):
    # Если пришел словарь {"rows": [...]}, вытаскиваем сам список
    if isinstance(data, dict):
        rows = data.get('rows', [])
    else:
        rows = data

    print("\n" + "="*60)
    print("📋 РЕЗУЛЬТАТЫ АНАЛИЗА")
    print("="*60)

    if not rows:
        print("Задач не найдено.")
        print("="*60 + "\n")
        return

    for idx, row in enumerate(rows, 1):
        # Если вдруг в список попала строка, обрабатываем её безопасно
        if isinstance(row, str):
            task = row
            assignee = "unknown"
            deadline = "—"
            details = "Ошибка: данные получены строкой"
        else:
            task     = row.get('task') or '—'
            assignee = row.get('assignee') or 'unknown'
            deadline = row.get('deadline') or '—'
            details  = row.get('details') or ''

        print(f"{idx:>3}. [{assignee}] {task}")
        if deadline and deadline != '—':
            print(f"       📅 {deadline}")
        if details:
            print(f"       └─ {details}")

    print("-" * 60)
    print(f"Всего задач: {len(rows)}")
    print("="*60)

    # Сохраняем JSON для отладки
    try:
        output_path = cfg.get('PATHS', 'output_excel', fallback='output/tasks.json')
        output_folder = os.path.dirname(output_path)
        
        if output_folder and not os.path.exists(output_folder):
            os.makedirs(output_folder)

        debug_path = os.path.join(output_folder or '.', "last_analysis_debug.json")
        with open(debug_path, 'w', encoding='utf-8') as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        print(f"💾 Данные сохранены в: {debug_path}\n")
    except Exception as e:
        print(f"⚠️ Не удалось сохранить файл: {e}")