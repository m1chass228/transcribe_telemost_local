import json
import os
from src.config_loader import cfg

def write_to_excel(raw_results):
    """
    Заглушка: выводит результат анализа в консоль.
    raw_results: список строк от Ollama (результаты по каждому чанку)
    """
    print("\n" + "="*50)
    print("ФИНАЛЬНЫЙ РЕЗУЛЬТАТ АНАЛИЗА (ЗАГЛУШКА)")
    print("="*50)

    # Объединяем результаты всех чанков для вывода
    full_output = "\n".join(raw_results)

    print(full_output)

    print("="*50)

    # Давай сохраним это в лог-файл, чтобы данные не пропали, если консоль очистится
    output_folder = os.path.dirname(cfg.get('PATHS', 'output_excel'))
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    debug_txt = os.path.join(output_folder, "last_analysis_debug.txt")
    with open(debug_txt, "w", encoding="utf-8") as f:
        f.write(full_output)

    print(f"Сырой вывод также сохранен в: {debug_txt}")
    print("="*50 + "\n")
