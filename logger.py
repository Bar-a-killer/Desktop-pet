import logging
import sys
from pathlib import Path

# 創建日誌目錄
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 日誌文件路徑
LOG_FILE = LOG_DIR / "desktop_pet.log"

def setup_logger():
    """設置日誌系統，同時輸出到控制臺和文件"""
    logger = logging.getLogger("desktop_pet")
    logger.setLevel(logging.DEBUG)
    
    # 移除已存在的處理器，避免重複
    logger.handlers.clear()
    
    # 文件處理器
    file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    
    # 控制臺處理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(message)s')
    console_handler.setFormatter(console_formatter)
    
    # 添加處理器
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# 全局日誌對象
logger = setup_logger()

def info(msg):
    logger.info(msg)

def debug(msg):
    logger.debug(msg)

def warning(msg):
    logger.warning(msg)

def error(msg):
    logger.error(msg)

def print_log(msg):
    """既輸出到控制臺，也寫入日誌"""
    print(msg)
    logger.info(msg)
