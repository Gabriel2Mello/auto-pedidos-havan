import unittest
from unittest.mock import MagicMock, call, patch

import win32con

from src.erros import SisplanError
from src.menu_sisplan import abrir_importacao_havan


class MenuSisplanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.grade = MagicMock()
        controle = self.grade.wrapper_object.return_value
        controle.handle = 10
        controle.client_rect.return_value.width.return_value = 200
        controle.client_rect.return_value.height.return_value = 100
        self.win32 = self.enterContext(patch('src.menu_sisplan.win32gui'))
        self.win32.ClientToScreen.return_value = (150, 90)
        processo = self.enterContext(patch('src.menu_sisplan.win32process'))
        processo.GetWindowThreadProcessId.return_value = (1, 2)
        self.win32.GetClassName.return_value = 'TPUtilWindow'
        self.enterContext(patch('src.menu_sisplan._menu_aberto', return_value=(20, 30)))
        self.dono = self.enterContext(patch('src.menu_sisplan._dono_menu', side_effect=[0, 20, 0, 0]))
        self.win32.SendMessageTimeout.return_value = (1, 40)
        self.win32.GetSubMenu.return_value = 50
        self.win32.GetMenuState.return_value = 0
        self.win32.GetMenuItemID.return_value = 327
        self.titulos = {40: ['&Importar', 'I&mportar Pedido'], 50: ['Outra opção', 'Havan']}
        self.win32.GetMenuItemCount.side_effect = lambda menu: len(self.titulos[menu])

        def ler(menu, indice, buffer, tamanho, flags):
            buffer.value = self.titulos[menu][indice]

        self.enterContext(patch('src.menu_sisplan._ler_rotulo', side_effect=ler))

    def test_resolve_o_comando_no_submenu_exato_e_fecha_o_menu_antes_de_enviar(self) -> None:
        abrir_importacao_havan(self.grade, 2)
        self.win32.GetSubMenu.assert_called_once_with(40, 1)
        self.win32.GetMenuItemID.assert_called_once_with(50, 1)
        self.assertEqual(self.win32.PostMessage.call_args_list, [
            call(10, win32con.WM_CONTEXTMENU, 10, 150 | (90 << 16)),
            call(20, win32con.WM_CANCELMODE, 0, 0),
            call(20, win32con.WM_COMMAND, 327, 0),
        ])

    def test_havan_ambiguo_fecha_o_menu_sem_disparar_comando(self) -> None:
        self.titulos[50].append('&Havan')
        with self.assertRaisesRegex(SisplanError, 'ausente ou ambígua'):
            abrir_importacao_havan(self.grade, 2)
        self.win32.PostMessage.assert_called_with(20, win32con.WM_CANCELMODE, 0, 0)
        self.assertEqual(self.win32.PostMessage.call_count, 2)
        self.win32.GetMenuItemID.assert_not_called()

    def test_grade_de_outro_processo_nao_recebe_mensagem(self) -> None:
        with self.assertRaises(SisplanError):
            abrir_importacao_havan(self.grade, 3)
        self.win32.PostMessage.assert_not_called()
