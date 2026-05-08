import os
import json
import logging
import datetime
import time
import pandas as pd
from openpyxl.styles import PatternFill, Font, Alignment
from utils.config_loader import cfg

logger = logging.getLogger(__name__)

def format_excel_sheet(worksheet):
    """Применяет стили к листу Excel (ширина колонок, заголовки)"""
    dims = {'A': 40, 'B': 5, 'C': 20, 'D': 15, 'E': 40, 'F': 15, 'G': 15, 'H': 15, 'I': 15}
    for col, width in dims.items():
        worksheet.column_dimensions[col].width = width
    
    header_fill = PatternFill(start_color="CCE5FF", end_color="CCE5FF", fill_type="solid")
    header_font = Font(bold=True)
    
    for cell in worksheet[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center')
    
    for row in worksheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical='top')

def write_output(data, video_date=None):
    """Основная функция вывода: Консоль + Excel (если включено)"""
    # 1. Подготовка данных
    if isinstance(data, dict):
        rows = data.get('rows', [])
    else:
        rows = data

    # Визуальный отчет в консоли
    logger.info("╒══ РЕЗУЛЬТАТЫ АНАЛИЗА")
    if not rows:
        logger.info("│   [ EMPTY ] Задач не обнаружено.")
    else:
        for idx, item in enumerate(rows, 1):
            assignee = item.get('assignee_code') or item.get('assignee') or '??'
            task = item.get('task') or 'Без названия'
            logger.info(f"│   {idx:>2}. [{assignee.upper()}] {task}")
    logger.info(f"┕━━ Всего задач: {len(rows)}")

    # 2. Сохранение в Excel (если разрешено в конфиге)
    if cfg.getboolean('OUTPUT', 'enable_excel', fallback=True):
        _write_to_excel(rows, video_date)

    # 3. Сохранение JSON для отладки (всегда полезно)
    _save_debug_json(rows)

def _write_to_excel(data_list, video_date):
    excel_path = cfg.get('PATHS', 'output_excel', fallback='output/Report.xlsx')
    os.makedirs(os.path.dirname(excel_path), exist_ok=True)
    
    if not video_date:
        video_date = datetime.datetime.now()
    
    sheet_name = video_date.strftime('%d.%m.%Y')
    default_dl = (datetime.datetime.now() + datetime.timedelta(days=7)).strftime("%d.%m.%Y")
    
    # Формируем строки для таблицы
    all_rows = []
    # Сюда можно добавить DEFAULT_TASKS из конфига, если они нужны
    
    for item in data_list:
        # Фильтр по кодам (если нужно)
        code = str(item.get("assignee_code") or "").upper()
        
        deadline = item.get("deadline")
        if not deadline or str(deadline).lower() in ["нет", "none", "—"]:
            deadline = default_dl
            
        all_rows.append({
            "Задача": item.get("task", ""),
            "В": "",
            "Ответственный": item.get("assignee") or item.get("assignee_name", ""),
            "Срок": deadline,
            "Комментарии": item.get("details") or item.get("report_text", "") or "",
            "Пометка ЕС": "", "Пометка ЕКс": "", "Пометка МН": "", "Пометка НС": ""
        })

    if not all_rows:
        return

    df_new = pd.DataFrame(all_rows)
    columns_order = ["Задача", "В", "Ответственный", "Срок", "Комментарии", "Пометка ЕС", "Пометка ЕКс", "Пометка МН", "Пометка НС"]
    df_new = df_new.reindex(columns=columns_order)

    logger.info(f"│   [ EXCEL ] Запись в {os.path.basename(excel_path)}...")
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            file_exists = os.path.exists(excel_path)
            mode = 'a' if file_exists else 'w'
            kwargs = {'if_sheet_exists': 'replace'} if file_exists else {}
            
            # Используем engine='openpyxl' для поддержки стилей и дозаписи
            with pd.ExcelWriter(excel_path, engine='openpyxl', mode=mode, **kwargs) as writer:
                # Если лист с такой датой уже есть, pandas его заменит благодаря if_sheet_exists='replace'
                df_new.to_excel(writer, sheet_name=sheet_name, index=False)
                format_excel_sheet(writer.book[sheet_name])
            
            logger.info(f"│   ╰─ [ OK ] Лист '{sheet_name}' готов.")
            break
        except PermissionError:
            logger.warning(f"│   ╰─ [ WAIT ] Файл занят, попытка {attempt+1}/{max_retries}...")
            time.sleep(5)
        except Exception as e:
            logger.error(f"│   ╰─ [ FAIL ] Ошибка Excel: {e}")
            break

def _save_debug_json(rows):
    try:
        debug_path = "output/last_run_debug.json"
        os.makedirs("output", exist_ok=True)
        with open(debug_path, 'w', encoding='utf-8') as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
    except:
        pass