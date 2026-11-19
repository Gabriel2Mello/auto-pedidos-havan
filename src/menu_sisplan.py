"""Comando de importação da Havan no menu Win32 da grade de itens."""

from ctypes import byref, create_unicode_buffer, sizeof, windll
from ctypes import wintypes
from typing import cast

import win32con
import win32gui
import win32process
from pywinauto import WindowSpecification, win32defines, win32functions, win32structures
from pywinauto.timings import wait_until, wait_until_passes

from src.erros import SisplanError


_ler_rotulo = windll.user32.GetMenuStringW
_ler_rotulo.argtypes = (wintypes.HMENU, wintypes.UINT, wintypes.LPWSTR, wintypes.INT, wintypes.UINT)
_ler_rotulo.restype = wintypes.INT


class _MenuAindaNaoAberto(RuntimeError):
    pass


def _dono_menu(thread: int) -> int:
    estado = win32structures.GUITHREADINFO()
    estado.cbSize = sizeof(estado)
    if not win32functions.GetGUIThreadInfo(thread, byref(estado)):
        raise SisplanError('Não foi possível consultar o menu do Sisplan.')
    return int(estado.hwndMenuOwner or 0)


def _menu_aberto(thread: int) -> tuple[int, int]:
    dono = _dono_menu(thread)
    if not dono:
        raise _MenuAindaNaoAberto()
    janelas: list[int] = []

    def coletar(hwnd: int, _: object) -> bool:
        if win32gui.GetClassName(hwnd) == '#32768' and win32gui.IsWindowVisible(hwnd):
            janelas.append(hwnd)
        return True

    win32gui.EnumThreadWindows(thread, coletar, None)
    if not janelas:
        raise _MenuAindaNaoAberto()
    if len(janelas) != 1:
        raise SisplanError('Mais de um menu está aberto na grade do Sisplan.')
    return dono, janelas[0]


def _dono_do_sisplan(dono: int, processo: int) -> bool:
    return bool(win32gui.IsWindow(dono) and win32gui.GetClassName(dono) == 'TPUtilWindow'
                and win32process.GetWindowThreadProcessId(dono)[1] == processo)


def _posicao(menu: int, titulo: str) -> int:
    encontrados: list[int] = []
    for indice in range(win32gui.GetMenuItemCount(menu)):
        rotulo = create_unicode_buffer(256)
        _ler_rotulo(menu, indice, rotulo, len(rotulo), win32con.MF_BYPOSITION)
        if rotulo.value.replace('&', '').strip() == titulo:
            encontrados.append(indice)
    if len(encontrados) != 1:
        raise SisplanError(f'Opção {titulo!r} ausente ou ambígua no menu do Sisplan.')
    indice = encontrados[0]
    estado = win32gui.GetMenuState(menu, indice, win32con.MF_BYPOSITION)
    if estado & (win32con.MF_GRAYED | win32con.MF_DISABLED):
        raise SisplanError(f'Opção {titulo!r} indisponível no menu do Sisplan.')
    return indice


def abrir_importacao_havan(grade: WindowSpecification, processo: int) -> None:
    grade.wait('ready', timeout=5)
    controle = grade.wrapper_object()
    hwnd = cast(int, controle.handle)
    thread, pid = win32process.GetWindowThreadProcessId(hwnd)
    if pid != processo or _dono_menu(thread):
        raise SisplanError('A grade ou o menu do Sisplan está em um estado inesperado.')
    area = controle.client_rect()
    if area.width() <= 0 or area.height() <= 0:
        raise SisplanError('A grade de itens do Sisplan está sem área visível.')
    x, y = win32gui.ClientToScreen(hwnd, (area.width() // 2, area.height() // 2))
    coordenadas = (x & 0xFFFF) | ((y & 0xFFFF) << 16)
    win32gui.PostMessage(hwnd, win32con.WM_CONTEXTMENU, hwnd, coordenadas)

    dono = 0
    try:
        dono, popup = wait_until_passes(2, 0.05, _menu_aberto, _MenuAindaNaoAberto, thread)
        if not _dono_do_sisplan(dono, processo):
            raise SisplanError('O menu aberto não pertence ao comando de importação do Sisplan.')
        _, menu = win32gui.SendMessageTimeout(popup, win32defines.MN_GETHMENU, 0, 0,
                                            win32con.SMTO_ABORTIFHUNG, 500)
        if not menu:
            raise SisplanError('Não foi possível ler as opções do menu de importação.')
        submenu = win32gui.GetSubMenu(menu, _posicao(menu, 'Importar Pedido'))
        if not submenu:
            raise SisplanError('O submenu Importar Pedido não apareceu.')
        comando = win32gui.GetMenuItemID(submenu, _posicao(submenu, 'Havan'))
        if not 0 < comando < 0xFFFF:
            raise SisplanError('O comando Havan não tem um identificador válido.')
    finally:
        dono_atual = _dono_menu(thread)
        if dono_atual and (not dono or dono_atual == dono) and _dono_do_sisplan(dono_atual, processo):
            win32gui.PostMessage(dono_atual, win32con.WM_CANCELMODE, 0, 0)
            wait_until(2, 0.05, lambda: not _dono_menu(thread))

    if _dono_menu(thread) or not _dono_do_sisplan(dono, processo) or not controle.is_enabled():
        raise SisplanError('O Sisplan mudou de estado antes de abrir o seletor de XML.')
    win32gui.PostMessage(dono, win32con.WM_COMMAND, comando, 0)
