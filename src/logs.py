import logging
import sys
import io
from typing import cast


class CustomLogger(logging.Logger):
    def info_split(self, msg: object, *args: object, **kwargs: object) -> None:
        print()
        self.info(msg, *args, **kwargs) # pyright: ignore[reportArgumentType]

    def error_split(self, msg: object, *args: object, **kwargs: object) -> None:
        print()
        self.error(msg, *args, **kwargs) # pyright: ignore[reportArgumentType]

    def critical_split(self, msg: object, *args: object, **kwargs: object) -> None:
        print()
        self.critical(msg, *args, **kwargs) # pyright: ignore[reportArgumentType]


logging.setLoggerClass(CustomLogger)


def get_logger(name: str) -> CustomLogger:
    return cast(CustomLogger, logging.getLogger(name))

def setup_logging():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    if not root_logger.handlers:
        # --- HANDLER PARA ARQUIVO ---
        arquivo_handler = logging.FileHandler(
            filename='auto-pedidos.log',
            mode='w',
            encoding='utf-8'
        )
        arquivo_handler.setLevel(logging.DEBUG)
        arquivo_format = logging.Formatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        arquivo_handler.setFormatter(arquivo_format)

        # --- HANDLER PARA CONSOLE ---
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_format = logging.Formatter('%(message)s')
        console_handler.setFormatter(console_format)

        root_logger.addHandler(arquivo_handler)
        root_logger.addHandler(console_handler)

