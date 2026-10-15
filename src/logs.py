import io
import logging
import sys
from struct import calcsize
from copy import copy
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import cast
from uuid import uuid4

from src.config import diretorio_aplicacao
from src.seguranca import redigir


# pyright: reportArgumentType=false
class CustomLogger(logging.Logger):
    def info_split(self, msg: object, *args: object, **kwargs: object) -> None:
        print()
        self.info(msg, *args, **kwargs)

    def error_split(self, msg: object, *args: object, **kwargs: object) -> None:
        print()
        self.error(msg, *args, **kwargs)

    def critical_split(self, msg: object, *args: object, **kwargs: object) -> None:
        print()
        self.critical(msg, *args, **kwargs)


logging.setLoggerClass(CustomLogger)


def get_logger(name: str) -> CustomLogger:
    return cast(CustomLogger, logging.getLogger(name))


def _configurar_stdout_utf8() -> None:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding='utf-8')
    elif hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


class FiltroExecucao(logging.Filter):
    def __init__(self, identificador: str) -> None:
        super().__init__()
        self.identificador = identificador

    def filter(self, record: logging.LogRecord) -> bool:
        record.execucao = self.identificador
        return True


class FormatoSeguro(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redigir(super().format(record))


class FormatoConsole(FormatoSeguro):
    def format(self, record: logging.LogRecord) -> str:
        # O arquivo mantém o diagnóstico completo; o operador recebe apenas a mensagem.
        simples = copy(record)
        simples.exc_info = None
        simples.exc_text = None
        simples.stack_info = None
        return super().format(simples)


def setup_logging(diretorio: Path | None = None, *, console: bool = True) -> str:
    _configurar_stdout_utf8()

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    for handler in root_logger.handlers[:]:
        if handler.get_name() in ('auto-pedidos-arquivo', 'auto-pedidos-console'):
            root_logger.removeHandler(handler)
            handler.close()

    arquivo_handler = RotatingFileHandler(
        filename=(diretorio or diretorio_aplicacao()) / 'auto-pedidos.log',
        maxBytes=5 * 1024 * 1024, backupCount=5, encoding='utf-8',
    )
    arquivo_handler.set_name('auto-pedidos-arquivo')
    arquivo_handler.setLevel(logging.DEBUG)
    identificador = uuid4().hex[:12]
    arquivo_handler.addFilter(FiltroExecucao(identificador))
    arquivo_handler.setFormatter(FormatoSeguro(
        fmt='%(asctime)s - [%(execucao)s] - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    ))

    root_logger.addHandler(arquivo_handler)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    if console and sys.stdout is not None:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.set_name('auto-pedidos-console')
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(FormatoConsole('%(message)s'))
        root_logger.addHandler(console_handler)
    get_logger(__name__).info('Execução: %s', identificador)
    get_logger(__name__).debug('Ambiente: Python=%s arquitetura=%s bits executável=%s plataforma=%s',
                               sys.version, calcsize('P') * 8, sys.executable, sys.platform)
    return identificador

