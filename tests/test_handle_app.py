import unittest
from unittest.mock import MagicMock, patch

import win32con
from pywinauto.findwindows import ElementNotFoundError
from pywinauto.timings import TimeoutError as JanelaTimeoutError

from src.handle_app import handle_aviso_duplicado, importa_arq_integracao, inicia_app, tratar_avisos_importacao
from src.erros import (SisplanError)


class PreparacaoGuiasTests(unittest.TestCase):
    def test_seleciona_1002_e_pedido_no_formulario_correto(self) -> None:
        with patch('src.handle_app.Application') as fabrica, \
             patch('src.handle_app.selecionar_modulo') as modulo, \
             patch('src.handle_app.selecionar_guia') as guia, \
             patch('src.handle_app.mapear_campos'):
            app = fabrica.return_value.connect.return_value
            janela = app.window.return_value
            inicia_app()
            modulo.assert_called_once_with(janela, '1002', 'TfmVenPedidoGrade')
            janela.child_window.assert_any_call(class_name='TfmVenPedidoGrade', visible_only=False)
            guia.assert_called_once()
            self.assertFalse(any('title_re' in c.kwargs for c in app.window.call_args_list))


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
            self.assertIsNone(tratar_avisos_importacao('2026-12345', 123))
            self.assertTrue(self.procurar.call_args.kwargs['visible_only'])

    @patch('src.handle_app.Application')
    def test_falhas_de_busca_nao_sao_interpretadas_como_ausencia(self, application: MagicMock) -> None:
        for erro in (PermissionError('Acesso negado'), JanelaTimeoutError(), RuntimeError('Ambíguo')):
            application.return_value.connect.side_effect = erro
            with self.assertRaises(SisplanError):
                handle_aviso_duplicado(123)
            with self.assertRaises(SisplanError):
                tratar_avisos_importacao('2026-12345', 123)

    @patch('src.handle_app.Application')
    def test_janela_encontrada_que_nao_fica_pronta_e_falha(self, application: MagicMock) -> None:
        application.return_value.connect.return_value.window.return_value.wait.side_effect = JanelaTimeoutError()
        with self.assertRaises(SisplanError):
            handle_aviso_duplicado(123)

    @patch('src.handle_app._clicar_botao')
    @patch('src.handle_app.localizar_aviso')
    def test_so_fecha_bloqueio_com_mensagem_conhecida(self, localizar: MagicMock, clicar: MagicMock) -> None:
        aviso = localizar.return_value
        aviso.window_text.return_value = 'Bloqueio'
        texto = MagicMock()
        texto.is_visible.return_value = True
        texto.window_text.return_value = 'Outro bloqueio.'
        aviso.wrapper_object.return_value.descendants.return_value = [texto]
        with self.assertRaisesRegex(SisplanError, 'tratar'):
            tratar_avisos_importacao('2026-12345', 123)
        clicar.assert_not_called()

    @patch('src.handle_app.salvar_pedido_txt')
    @patch('src.handle_app._clicar_botao')
    @patch('src.handle_app.localizar_aviso')
    def test_fecha_bloqueio_e_relatorio_por_botoes(self, localizar: MagicMock, clicar: MagicMock,
                                                  salvar: MagicMock) -> None:
        aviso, relatorio, texto = MagicMock(), MagicMock(), MagicMock()
        aviso.window_text.return_value = 'Bloqueio'
        aviso.wrapper_object.return_value.descendants.return_value = [texto]
        texto.is_visible.return_value = True
        texto.window_text.return_value = 'Existem itens não encontrados na grade de produtos.'
        localizar.side_effect = [aviso, relatorio]
        eventos = MagicMock()
        eventos.attach_mock(clicar, 'clicar')
        eventos.attach_mock(aviso.wait_not, 'aguardar_aviso')
        eventos.attach_mock(relatorio.wait_not, 'aguardar_relatorio')
        eventos.attach_mock(salvar, 'registrar')

        self.assertEqual(tratar_avisos_importacao('2026-12345', 123), 'sem_cadastro')
        localizar.assert_called_with('Itens não encontrados na grade de produtos', 'TForm', 5, 123)
        aviso.child_window.assert_called_once_with(class_name='Button', title='OK')
        relatorio.child_window.assert_called_once_with(class_name='TBitBtn', title='&Fechar')
        self.assertEqual([chamada[0] for chamada in eventos.mock_calls], [
            'clicar', 'aguardar_aviso', 'clicar', 'aguardar_relatorio', 'registrar',
        ])

        salvar.reset_mock()
        localizar.side_effect = [aviso, None]
        with self.assertRaises(SisplanError):
            tratar_avisos_importacao('2026-12345', 123)
        salvar.assert_not_called()

    @patch('src.handle_app.localizar_aviso')
    def test_so_fecha_informacao_com_o_texto_exato(self, localizar: MagicMock) -> None:
        aviso = localizar.return_value
        aviso.window_text.return_value = 'Informação'
        texto = MagicMock()
        texto.is_visible.return_value = True
        aviso.wrapper_object.return_value.descendants.return_value = [texto]
        texto.window_text.return_value = 'Outra informação.'
        with self.assertRaises(SisplanError):
            tratar_avisos_importacao('2026-12345', 123)
        aviso.child_window.assert_not_called()

        texto.window_text.return_value = 'Nenhum item encontrado no arquivo selecionado.'
        botao = aviso.child_window.return_value
        botao.client_rect.return_value.width.return_value = 40
        botao.client_rect.return_value.height.return_value = 20
        self.assertEqual(tratar_avisos_importacao('2026-12345', 123), 'xml_sem_itens')
        botao.click.assert_called_once_with(coords=(20, 10))
        aviso.wait_not.assert_called_once_with('visible', timeout=5)

        aviso.wait_not.side_effect = TimeoutError('Aviso continua aberto')
        with self.assertRaises(SisplanError):
            tratar_avisos_importacao('2026-12345', 123)

    @patch('src.handle_app.win32gui.PostMessage')
    @patch('src.handle_app.Application')
    def test_dialogo_abrir_e_busca_opcional_ficam_no_processo_do_sisplan(self, application: MagicMock,
                                                                      mensagem: MagicMock) -> None:
        janela = application.return_value.connect.return_value.window.return_value
        campo, abrir = MagicMock(), MagicMock()
        campo.window_text.return_value = 'C:/pedido.xml'
        abrir.wrapper_object.return_value.handle = 789
        janela.child_window.side_effect = [campo, abrir]
        importa_arq_integracao('C:/pedido.xml', 123)
        self.assertEqual(self.procurar.call_args.kwargs['process'], 123)
        application.return_value.connect.assert_called_once_with(handle=456)
        application.return_value.connect.return_value.window.assert_called_once_with(handle=456)
        janela.set_focus.assert_called_once()
        campo.set_edit_text.assert_called_once_with('C:/pedido.xml')
        campo.type_keys.assert_not_called()
        janela.child_window.assert_any_call(class_name='Button', control_id=win32con.IDOK)
        mensagem.assert_called_once_with(789, win32con.BM_CLICK, 0, 0)
        janela.wait_not.assert_called_once_with('visible', timeout=5)

    @patch('src.handle_app.win32gui.PostMessage')
    @patch('src.handle_app.localizar_aviso')
    def test_caminho_divergente_nao_aciona_abrir(self, localizar: MagicMock, mensagem: MagicMock) -> None:
        localizar.return_value.child_window.return_value.window_text.return_value = 'C:/outro.xml'
        with self.assertRaises(SisplanError):
            importa_arq_integracao('C:/pedido.xml', 123)
        mensagem.assert_not_called()

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


class CancelamentoDuplicidadeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.aviso, self.confirmacao = MagicMock(), MagicMock()
        botoes = [MagicMock(), MagicMock()]
        for botao, texto in zip(botoes, ('&Não', '&Sim')):
            botao.window_text.return_value = texto
            botao.is_visible.return_value = True
        self.aviso.wrapper_object.return_value.descendants.return_value = botoes
        self.mensagem = MagicMock()
        self.mensagem.window_text.return_value = 'Deseja Cancelar as Alterações ?'
        self.mensagem.is_visible.return_value = True
        self.confirmacao.wrapper_object.return_value.descendants.return_value = [self.mensagem]
        self.localizar = self.enterContext(patch('src.handle_app.localizar_aviso',
                                                side_effect=[self.aviso, self.confirmacao]))
        self.application = self.enterContext(patch('src.handle_app.Application'))
        self.clicar = self.enterContext(patch('src.handle_app._clicar_botao'))
        self.principal = self.application.return_value.connect.return_value.window.return_value
        self.desistir = self.principal.child_window.return_value.child_window.return_value

    def test_cancela_por_botoes_aguardando_as_duas_janelas(self) -> None:
        eventos = MagicMock()
        eventos.attach_mock(self.clicar, 'clicar')
        eventos.attach_mock(self.aviso.wait_not, 'fechar_aviso')
        eventos.attach_mock(self.confirmacao.wait_not, 'fechar_confirmacao')
        eventos.attach_mock(self.desistir.wait_not, 'confirmar_fim_da_inclusao')
        self.assertTrue(handle_aviso_duplicado(123))
        self.aviso.child_window.assert_called_once_with(class_name='TBitBtn', title='&Não')
        self.confirmacao.child_window.assert_called_once_with(class_name='Button', title='&Sim', control_id=6)
        self.application.return_value.connect.assert_called_once_with(process=123)
        self.assertEqual([c[0] for c in eventos.mock_calls], [
            'clicar', 'fechar_aviso', 'clicar', 'clicar', 'fechar_confirmacao', 'confirmar_fim_da_inclusao',
        ])

    def test_aviso_que_nao_fecha_bloqueia_desistir(self) -> None:
        self.aviso.wait_not.side_effect = TimeoutError('Aviso continua aberto')
        with self.assertRaises(SisplanError):
            handle_aviso_duplicado(123)
        self.application.assert_not_called()
        self.confirmacao.child_window.assert_not_called()

    def test_confirmacao_com_outro_texto_bloqueia_sim(self) -> None:
        self.mensagem.window_text.return_value = 'Deseja confirmar a gravação?'
        with self.assertRaises(SisplanError):
            handle_aviso_duplicado(123)
        self.confirmacao.child_window.assert_not_called()
        self.assertEqual(self.clicar.call_count, 2)

    def test_confirmacao_ausente_bloqueia_sim(self) -> None:
        self.localizar.side_effect = [self.aviso, None]
        with self.assertRaises(SisplanError):
            handle_aviso_duplicado(123)
        self.assertEqual(self.clicar.call_count, 2)

    def test_inclusao_aberta_apos_confirmacao_nao_retorna_sucesso(self) -> None:
        self.desistir.wait_not.side_effect = TimeoutError('Inclusão continua aberta')
        with self.assertRaises(SisplanError):
            handle_aviso_duplicado(123)
