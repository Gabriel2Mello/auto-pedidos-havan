import unittest
from unittest.mock import MagicMock, patch

from pywinauto.findwindows import ElementNotFoundError
from pywinauto.timings import TimeoutError as JanelaTimeoutError

from src.handle_app import handle_aviso_duplicado, handle_produto_sem_cadastro, importa_arq_integracao
from src.erros import (SisplanError)


class AvisosTests(unittest.TestCase):
    def setUp(self) -> None:
        procurar = patch('src.handle_app.wait_until_passes')
        self.procurar = procurar.start()
        self.addCleanup(procurar.stop)
        self.procurar.return_value.handle = 456

    @patch('src.handle_app.Application')
    def test_ausencia_esperada_retorna_false(self, application: MagicMock) -> None:
        ausente = JanelaTimeoutError()
        ausente.original_exception = ElementNotFoundError()
        for erro in (ElementNotFoundError(), ausente):
            application.return_value.connect.side_effect = erro
            self.assertFalse(handle_aviso_duplicado(123))
            self.assertFalse(handle_produto_sem_cadastro('2026-12345', 123))
            self.assertTrue(self.procurar.call_args.kwargs['visible_only'])

    @patch('src.handle_app.Application')
    def test_falhas_de_busca_nao_sao_interpretadas_como_ausencia(self, application: MagicMock) -> None:
        for erro in (PermissionError('Acesso negado'), JanelaTimeoutError(), RuntimeError('Ambíguo')):
            application.return_value.connect.side_effect = erro
            with self.assertRaises(SisplanError):
                handle_aviso_duplicado(123)
            with self.assertRaises(SisplanError):
                handle_produto_sem_cadastro('2026-12345', 123)

    @patch('src.handle_app.Application')
    def test_janela_encontrada_que_nao_fica_pronta_e_falha(self, application: MagicMock) -> None:
        application.return_value.connect.return_value.window.return_value.wait.side_effect = JanelaTimeoutError()
        with self.assertRaises(SisplanError):
            handle_aviso_duplicado(123)

    @patch('src.handle_app.send_keys_sleep', side_effect=RuntimeError('Tecla não enviada'))
    @patch('src.handle_app.localizar_aviso', return_value=MagicMock())
    def test_falha_ao_fechar_duplicidade_nao_retorna_false(self, localizar: MagicMock, enviar: MagicMock) -> None:
        with self.assertRaisesRegex(SisplanError, 'tratar'):
            handle_aviso_duplicado(123)

    @patch('src.handle_app.send_keys_sleep')
    @patch('src.handle_app.localizar_aviso', return_value=MagicMock())
    def test_cancelamento_incompleto_nao_confirma_aviso(self, localizar: MagicMock, enviar: MagicMock) -> None:
        localizar.return_value.wait_not.side_effect = TimeoutError('Aviso continua aberto')
        with self.assertRaises(SisplanError):
            handle_aviso_duplicado(123)

    @patch('src.handle_app.localizar_aviso')
    def test_falha_no_botao_de_bloqueio_nao_retorna_false(self, localizar: MagicMock) -> None:
        localizar.return_value.wait.return_value = localizar.return_value
        localizar.return_value.OK.click.side_effect = RuntimeError('Botão indisponível')
        with self.assertRaisesRegex(SisplanError, 'tratar'):
            handle_produto_sem_cadastro('2026-12345', 123)

    @patch('src.handle_app.send_keys_sleep')
    @patch('src.handle_app.localizar_aviso', return_value=MagicMock())
    def test_duplicidade_tratada_retorna_true(self, localizar: MagicMock, enviar: MagicMock) -> None:
        self.assertTrue(handle_aviso_duplicado(123))
        self.assertEqual(enviar.call_count, 3)

    @patch('src.handle_app.Application')
    def test_dialogo_abrir_e_busca_opcional_ficam_no_processo_do_sisplan(self, application: MagicMock) -> None:
        importa_arq_integracao('C:/pedido.xml', 123)
        self.assertEqual(self.procurar.call_args.kwargs['process'], 123)
        application.return_value.connect.assert_called_once_with(handle=456)
        application.return_value.connect.return_value.window.assert_called_once_with(handle=456)
        janela = application.return_value.connect.return_value.window.return_value
        janela.set_focus.assert_called_once()

    @patch('src.handle_app.Application')
    def test_ausencia_em_outro_processo_nao_aciona_dialogo_externo(self, application: MagicMock) -> None:
        erro = JanelaTimeoutError()
        erro.original_exception = ElementNotFoundError()
        self.procurar.side_effect = erro
        self.assertFalse(handle_aviso_duplicado(123))
        application.assert_not_called()

    @patch('src.handle_app.Application')
    def test_processo_invalido_bloqueia_busca_global(self, application: MagicMock) -> None:
        with self.assertRaises(SisplanError):
            handle_aviso_duplicado(0)
        self.procurar.assert_not_called()
        application.assert_not_called()
