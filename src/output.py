import json
import logging
import datetime
import time
from pathlib import Path
import pandas as pd
from openpyxl.styles import PatternFill, Font, Alignment
from utils.config_loader import cfg

logger = logging.getLogger(__name__)

# Выносим настройки в константы или конфиг
COLUMNS_ORDER = ["Задача", "В", "Ответственный", "Срок", "Комментарии", 
                 "Пометка ЕС", "Пометка ЕКс", "Пометка МН", "Пометка НС"]

def format_excel_sheet(worksheet):
    """Применяет стили к листу Excel"""
    # Динамическая настройка ширины: заголовки и стандартная ширина
    dims = {'A': 45, 'C': 25, 'D': 15, 'E': 50} # Основные широкие колонки
    for col_letter in [chr(65 + i) for i in range(len(COLUMNS_ORDER))]:
        width = dims.get(col_letter, 12) # По умолчанию 12
        worksheet.column_dimensions[col_letter].width = width
    
    header_fill = PatternFill(start_color="CCE5FF", end_color="CCE5FF", fill_type="solid")
    header_font = Font(bold=True)
    
    # Стили заголовка
    for cell in worksheet[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center')
    
    # Стили ячеек данных
    for row in worksheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical='top')

def write_output(data, video_date=None):
    """Основная функция вывода"""
    rows = data.get('rows', []) if isinstance(data, dict) else data

    # 1. Консольный лог
    logger.info("╒══ РЕЗУЛЬТАТЫ АНАЛИЗА")
    if not rows:
        logger.info("│   [ EMPTY ] Задач не обнаружено.")
    else:
        for idx, item in enumerate(rows, 1):
            assignee = item.get('assignee_code') or item.get('assignee') or '??'
            task = item.get('task') or 'Без названия'
            logger.info(f"│   {idx:>2}. [{assignee.upper()}] {task}")
    logger.info(f"┕━━ Всего задач: {len(rows)}")

    # 2. Excel
    if str(cfg.get('OUTPUT', 'enable_excel', fallback='True')).lower() in ('true', '1', 'yes', 'on'):
        _write_to_excel(rows, video_date)

    # 3. JSON Debug
    _save_debug_json(rows)

def _write_to_excel(data_list, video_date):
    excel_path = Path(cfg.get('PATHS', 'output_excel', fallback='output/Report.xlsx'))
    excel_path.parent.mkdir(parents=True, exist_ok=True)
    
    if not video_date:
        video_date = datetime.datetime.now()
    
    sheet_name = video_date.strftime('%d.%m.%Y')
    # Дедлайн через 7 дней от даты ВИДЕО (или текущей), а не всегда от "сегодня"
    default_deadline = (video_date + datetime.timedelta(days=7)).strftime("%d.%m.%Y")
    
    all_rows = []
    for item in data_list:
        deadline = item.get("deadline")
        if not deadline or str(deadline).lower() in ["нет", "none", "—", "null"]:
            deadline = default_deadline
            
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

    df_new = pd.DataFrame(all_rows).reindex(columns=COLUMNS_ORDER)

    max_retries = 3
    for attempt in range(max_retries):
        try:
            file_exists = excel_path.exists()
            mode = 'a' if file_exists else 'w'
            # Важно: if_sheet_exists работает только в режиме 'a'
            write_params = {'engine': 'openpyxl', 'mode': mode}
            if file_exists:
                write_params['if_sheet_exists'] = 'replace'
            
            with pd.ExcelWriter(excel_path, **write_params) as writer:
                df_new.to_excel(writer, sheet_name=sheet_name, index=False)
                format_excel_sheet(writer.book[sheet_name])
            
            logger.info(f"│   ╰─ [ OK ] Excel: Лист '{sheet_name}' сохранен.")
            break
        except PermissionError:
            if attempt < max_retries - 1:
                logger.warning(f"│   ╰─ [ WAIT ] Закройте файл {excel_path.name}! Попытка {attempt+1}...")
                time.sleep(5)
            else:
                logger.error(f"│   ╰─ [ FAIL ] Не удалось записать Excel. Файл занят другим процессом.")
        except Exception as e:
            logger.error(f"│   ╰─ [ FAIL ] Ошибка записи Excel: {e}")
            break

def _save_debug_json(rows):
    debug_path = Path("output/last_run_debug.json")
    try:
        debug_path.parent.mkdir(exist_ok=True)
        with debug_path.open('w', encoding='utf-8') as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.debug(f"Не удалось сохранить дебаг-json: {e}")