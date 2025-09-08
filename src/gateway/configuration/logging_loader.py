""" Python logging configuration with colored output. """

import logging
from colorama import init as colorama_init, Fore, Style # type: ignore

class ColorFormatter(logging.Formatter):
    """ Class to specify colors in log output based on severity level. """
    LEVEL_COLORS = {
        logging.DEBUG: Fore.BLUE,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.MAGENTA,
    }

    def format(self, record: logging.LogRecord) -> str:
        color = self.LEVEL_COLORS.get(record.levelno, "")
        orig_levelname = record.levelname
        record.levelname = f"{color}{record.levelname}{Style.RESET_ALL}"
        try:
            fmt = "[%(levelname)s] %(asctime)s - %(name)s - %(message)s"
            formatter = logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")
            return formatter.format(record)
        finally:
            record.levelname = orig_levelname

def configure_logging(level: int = logging.DEBUG) -> None:
    """Configura el root logger con un único StreamHandler y nuestro formatter."""
    colorama_init(autoreset=False)
    root = logging.getLogger()
    root.setLevel(level)

    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        ch = logging.StreamHandler()
        ch.setLevel(level)
        ch.setFormatter(ColorFormatter())
        root.addHandler(ch)

    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
