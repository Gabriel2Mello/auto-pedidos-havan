"""Interacao Win32 carregada somente por quem executa o Sisplan."""
import ctypes
from time import sleep
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pywinauto import WindowSpecification

def set_app_id() -> None:
    try:
        my_app_id = 'g2mello.autopedidoshavan.v1'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(my_app_id)
    except Exception:
        pass


def send_keys_sleep(keys: str, sleep_time: float = 0.1) -> None:
    from pywinauto.keyboard import send_keys
    send_keys(keys)
    sleep(sleep_time)


def aguardar_campo(campo: 'WindowSpecification', timeout: int = 5) -> 'WindowSpecification':
    campo.wait('ready', timeout=timeout)
    return campo
