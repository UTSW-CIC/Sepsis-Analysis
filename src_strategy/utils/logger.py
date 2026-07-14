import logging
import sys
from pathlib import Path

def setup_root_logger(log_dir: str = "./logs") -> logging.Logger:
    """
    Call this ONCE at application startup in main.py.
    All module-level loggers will inherit this configuration.
    """
    logger = logging.getLogger()

    # avoid adding duplicate handlers if get_logger is called multiple times
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    main_handler = logging.FileHandler(log_path / "pipeline.log")
    main_handler.setFormatter(formatter)
    main_handler.setLevel(logging.INFO)

    error_handler = logging.FileHandler(log_path / "errors.log")
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.ERROR)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    logger.addHandler(main_handler)
    logger.addHandler(error_handler)
    logger.addHandler(console_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Call this at the top of every module.
    Returns a named logger that inherits root configuration.
    """
    return logging.getLogger(name)