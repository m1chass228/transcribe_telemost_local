import logging
import sys
from utils.config_loader import cfg

# Добавляем свой уровень для полных ответов нейросети
AI_TRACE_LEVEL = 15
logging.addLevelName(AI_TRACE_LEVEL, "AI_TRACE")

def ai_trace(self, message, *args, **kws):
    if self.isEnabledFor(AI_TRACE_LEVEL):
        self._log(AI_TRACE_LEVEL, message, args, **kws)

logging.Logger.ai_trace = ai_trace

class CustomFormatter(logging.Formatter):
    """Класс для раскраски логов в терминале"""
    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    cyan = "\x1b[36;20m"
    reset = "\x1b[0m"
    format_str = "%(asctime)s [%(levelname)s] %(message)s (%(filename)s:%(lineno)d)"

    FORMATS = {
        logging.DEBUG: grey + format_str + reset,
        AI_TRACE_LEVEL: cyan + "[AI] " + format_str + reset,
        logging.INFO: reset + "%(asctime)s [%(levelname)s] %(message)s" + reset,
        logging.WARNING: yellow + format_str + reset,
        logging.ERROR: red + format_str + reset,
        logging.CRITICAL: bold_red + format_str + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt="%H:%M:%S")
        return formatter.format(record)

def setup_logging(debug_mode=False, trace_ai=False):
    """
    debug_mode: включает вывод DEBUG (подробности системы)
    trace_ai: включает вывод полных промптов и ответов Ollama
    """
    logger = logging.getLogger()
    
    # Определяем минимальный уровень
    if trace_ai:
        level = AI_TRACE_LEVEL
    elif debug_mode:
        level = logging.DEBUG
    else:
        level = logging.INFO
        
    logger.setLevel(level)

    # Консольный вывод
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(CustomFormatter())
    
    # Файловый вывод (всегда пишем всё в файл для истории)
    file_handler = logging.FileHandler("app.log", encoding="utf-8")
    file_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    file_handler.setFormatter(file_fmt)

    logger.addHandler(stdout_handler)
    logger.addHandler(file_handler)

    logging.info(f"Логирование настроено (Level: {logging.getLevelName(level)})")

def get_preview_limit():
    logger = logging.getLogger()
    if logger.isEnabledFor(15): # AI_TRACE
        return None
    if logger.isEnabledFor(logging.DEBUG):
        return 500
    return 100