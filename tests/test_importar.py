import unittest
from contextlib import ExitStack
from dataclasses import replace
from typing import cast
from unittest.mock import MagicMock, patch

from src.config import CONFIG, usar_configuracao
from src.estado import EstadoError
from src.importar import CamposSisplan, importar_pedido, selecionar_empresa
from src.erros import AbaPedidoIndisponivelError, SisplanError, NumeroInternoForaSequenciaError, XmlSemItensSisplanError
from src.mensagens import mensagem_erro
from tests.fixtures import xml_pedido


class ImportacaoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for nome in ('preencher_dados_fixos', 'preencher_datas', 'processar_operacao_comercial',
                     'importa_arq_integracao', 'salvar_pedido_txt', 'enviar_alerta_teams'):
            self.stack.enter_context(patch(f'src.importar.{nome}'))
        self.stack.enter_context(patch('src.importar.carregar_xml', return_value=xml_pedido()))
        self.aviso_importacao = self.stack.enter_context(patch('src.importar.tratar_avisos_importacao', return_value=None))
        self.cancelar = self.stack.enter_context(patch('src.importar.cancelar_inclusao'))
        self.abrir_menu = self.stack.enter_context(patch('src.importar.abrir_importacao_havan'))
        self.duplicado = self.stack.enter_context(patch('src.importar.handle_aviso_duplicado', return_value=False))
        self.acionar = self.stack.enter_context(patch('src.importar.acionar_botao_pedido'))
        self.selecionar = self.stack.enter_context(patch('src.importar.selecionar_guia'))
        self.campo = MagicMock()
        self.campo.window_text.return_value = '100'
        self.stack.enter_context(patch('src.importar.aguardar_campo', return_value=self.campo))
        self.combo_empresa = MagicMock()
        self.combo_empresa.item_texts.return_value = ['', '001-NUNES ENXOVAIS', '002-NUNES ENXOVAIS']
        self.combo_empresa.selected_index.return_value = 2
        self.combo_empresa.selected_text.return_value = '002-NUNES ENXOVAIS'
        self.args = ('2026-12345', MagicMock(), MagicMock(), MagicMock(),
                     {'numero': self.campo, 'empresa': self.combo_empresa})

    def test_checkpoint_e_salvo_antes_do_comando_de_gravacao(self) -> None:
        eventos = []
        self.acionar.side_effect = lambda _, comando: eventos.append(comando)
        resultado = importar_pedido(*self.args, lambda numero: eventos.append(('checkpoint', numero)), referencia_numero=100)
        self.assertLess(eventos.index(('checkpoint', '100')), eventos.index('Gravar'))
        self.assertEqual(resultado.situacao, 'aguarda_confirmacao')

    def test_seleciona_aba_pedido_antes_de_ler_numero_e_incluir(self) -> None:
        interacoes = MagicMock()
        interacoes.attach_mock(self.args[1], 'tela')
        interacoes.attach_mock(self.args[2], 'aba')
        interacoes.attach_mock(self.campo, 'numero')
        interacoes.attach_mock(self.acionar, 'acionar')
        interacoes.attach_mock(self.selecionar, 'selecionar')
        importar_pedido(*self.args, MagicMock(), referencia_numero=100)
        self.assertEqual([chamada[0] for chamada in interacoes.mock_calls[:5]],
                         ['selecionar', 'selecionar', 'aba.wait', 'numero.window_text', 'tela.process_id'])
        self.assertEqual(self.selecionar.call_args_list[0].args, (self.args[1],))
        self.assertEqual(self.selecionar.call_args_list[1].args, (self.args[2],))
        self.selecionar.assert_any_call(self.args[2], 'Itens Pedido')
        self.args[1].click_input.assert_not_called()
        self.args[2].click_input.assert_not_called()
        self.args[3].click_input.assert_not_called()
        self.abrir_menu.assert_called_once_with(self.args[3], self.args[1].process_id.return_value)
        self.acionar.assert_any_call(self.args[1].process_id.return_value, 'Incluir')

    def test_falha_na_selecao_da_guia_bloqueia_inclusao(self) -> None:
        self.selecionar.side_effect = RuntimeError('Guia ausente')
        with self.assertRaises(AbaPedidoIndisponivelError):
            importar_pedido(*self.args[:4], cast(CamposSisplan, self.args[4]),
                            MagicMock(), referencia_numero=100)
        self.campo.window_text.assert_not_called()
        self.acionar.assert_not_called()

    def test_se_aba_nao_abre_nenhum_botao_e_acionado(self) -> None:
        self.args[2].wait.side_effect = TimeoutError('Aba invisível')
        checkpoint = MagicMock()
        with self.assertRaisesRegex(AbaPedidoIndisponivelError, 'aba Pedido'):
            importar_pedido(*self.args, checkpoint, referencia_numero=100)
        self.campo.window_text.assert_not_called()
        self.acionar.assert_not_called()
        checkpoint.assert_not_called()

    def test_falha_de_persistencia_nao_envia_gravar(self) -> None:
        with self.assertRaises(SisplanError):
            importar_pedido(*self.args, MagicMock(side_effect=EstadoError('Disco cheio')), referencia_numero=100)
        self.assertNotIn('Gravar', self.comandos())

    def test_empresa_alterada_durante_o_xml_nao_grava(self) -> None:
        checkpoint = MagicMock()
        def importar_xml(*_):
            self.combo_empresa.selected_text.return_value = '001-NUNES ENXOVAIS'
        with patch('src.importar.importa_arq_integracao', side_effect=importar_xml):
            with self.assertRaises(SisplanError) as erro:
                importar_pedido(*self.args, checkpoint, referencia_numero=100)
        self.assertIn('empresa de faturamento mudou', str(erro.exception.__cause__))
        self.assertNotIn('Gravar', self.comandos())
        checkpoint.assert_not_called()

    def test_falha_no_aviso_nao_retorna_pedido_como_valido(self) -> None:
        self.duplicado.side_effect = SisplanError('Aviso não tratado')
        with self.assertRaises(SisplanError):
            importar_pedido(*self.args, MagicMock(), referencia_numero=100)

    def test_aviso_exige_restauracao_do_pedido_anterior(self) -> None:
        self.duplicado.return_value = True
        self.simular_numeros(['101'])
        with patch('src.importar.wait_until', side_effect=TimeoutError('Tela não restaurou')):
            with self.assertRaisesRegex(SisplanError, 'confirmar o cancelamento'):
                importar_pedido(*self.args, MagicMock(), referencia_numero=100)
        self.assertEqual(self.comandos().count('Incluir'), 1)

    def simular_numeros(self, numeros: list[str]) -> None:
        self.numero_atual = '11249'
        self.numero_anterior = self.numero_atual
        self.campo.window_text.side_effect = lambda: self.numero_atual
        def acionar(_, comando):
            if comando == 'Incluir':
                self.numero_anterior = self.numero_atual
                self.numero_atual = numeros.pop(0)
        self.acionar.side_effect = acionar
        self.cancelar.side_effect = lambda _: setattr(self, 'numero_atual', self.numero_anterior)

    def test_sem_cadastro_so_retorna_e_notifica_apos_confirmar_cancelamento(self) -> None:
        self.simular_numeros(['11250'])
        checkpoint = MagicMock()
        eventos = []
        def conferir(timeout, intervalo, condicao):
            self.assertTrue(condicao())
            eventos.append('cancelamento_confirmado')
        with patch('src.importar.tratar_avisos_importacao', return_value='sem_cadastro'), \
             patch('src.importar.wait_until', side_effect=conferir), \
             patch('src.importar.enviar_alerta_teams', side_effect=lambda *args: eventos.append('alerta')):
            resultado = importar_pedido(*self.args, checkpoint, referencia_numero=11250)
        self.assertEqual(resultado.situacao, 'sem_cadastro')
        self.assertEqual(self.numero_atual, self.numero_anterior)
        self.cancelar.assert_called_once_with(self.args[1].process_id.return_value)
        self.args[1].wait.assert_called_once_with('ready', timeout=5)
        self.assertEqual(eventos, ['cancelamento_confirmado', 'alerta'])
        self.assertEqual(self.comandos(), ['Incluir'])
        checkpoint.assert_not_called()

    def test_sem_cadastro_nao_libera_cancelamento_sem_janela_pronta_ou_numero_restaurado(self) -> None:
        for falha in ('janela', 'numero'):
            with self.subTest(falha=falha):
                self.acionar.reset_mock()
                self.simular_numeros(['11250'])
                self.cancelar.side_effect = None
                condicoes = []
                def conferir(timeout, intervalo, condicao):
                    condicoes.append(condicao())
                    raise TimeoutError('Número anterior não restaurado')
                checkpoint = MagicMock()
                with patch('src.importar.tratar_avisos_importacao', return_value='sem_cadastro'), \
                     patch.object(self.args[1], 'wait', side_effect=RuntimeError('Indisponível') if falha == 'janela' else None), \
                     patch('src.importar.wait_until', side_effect=conferir), \
                     patch('src.importar.enviar_alerta_teams') as alerta:
                    with self.assertRaisesRegex(SisplanError, 'confirmar o cancelamento.*produto sem cadastro'):
                        importar_pedido(*self.args, checkpoint, referencia_numero=11250)
                self.assertEqual(self.comandos(), ['Incluir'])
                self.assertEqual(condicoes, [] if falha == 'janela' else [False])
                checkpoint.assert_not_called()
                alerta.assert_not_called()

    def test_xml_sem_itens_cancela_sem_gravar_e_so_rejeita_se_confirmar(self) -> None:
        self.aviso_importacao.return_value = 'xml_sem_itens'
        for confirmado in (True, False):
            with self.subTest(confirmado=confirmado):
                self.acionar.reset_mock()
                self.cancelar.reset_mock()
                self.simular_numeros(['11250'])
                checkpoint = MagicMock()
                with patch('src.importar.wait_until', side_effect=None if confirmado else TimeoutError()):
                    if confirmado:
                        with self.assertRaises(XmlSemItensSisplanError) as erro:
                            importar_pedido(*self.args, checkpoint, referencia_numero=11250)
                        self.assertIn('Confira o arquivo de integração', str(erro.exception))
                    else:
                        with self.assertRaisesRegex(SisplanError, 'confirmar o cancelamento.*XML sem itens'):
                            importar_pedido(*self.args, checkpoint, referencia_numero=11250)
                self.cancelar.assert_called_once()
                self.assertEqual(self.comandos(), ['Incluir'])
                checkpoint.assert_not_called()

    def comandos(self) -> list[str]:
        return [chamada.args[1] for chamada in self.acionar.call_args_list]

    def test_numero_um_cancela_e_repete_o_mesmo_pedido_uma_vez(self) -> None:
        self.simular_numeros(['1', '11253'])
        checkpoint = MagicMock()
        resultado = importar_pedido(*self.args, checkpoint, referencia_numero=11250)
        self.assertEqual(resultado.numero, '11253')
        self.assertEqual(self.comandos(), ['Incluir', 'Incluir', 'Gravar'])
        self.cancelar.assert_called_once()
        checkpoint.assert_called_once_with('11253')

    def test_duas_anomalias_cancelam_sem_gravar_e_pedem_acao(self) -> None:
        for numeros in (['1', '1'], ['1', '999999'], ['', 'abc'], ['0', '-1']):
            with self.subTest(numeros=numeros):
                self.acionar.reset_mock()
                self.cancelar.reset_mock()
                self.simular_numeros(list(numeros))
                checkpoint = MagicMock()
                with self.assertRaises(NumeroInternoForaSequenciaError) as capturado:
                    importar_pedido(*self.args, checkpoint, referencia_numero=11250)
                self.assertEqual(self.comandos(), ['Incluir', 'Incluir'])
                self.assertEqual(self.cancelar.call_count, 2)
                checkpoint.assert_not_called()
                self.assertIn('duas tentativas', mensagem_erro(capturado.exception))
                self.assertIn('referência 11250', mensagem_erro(capturado.exception))

    def test_saltos_e_zeros_a_esquerda_dentro_da_tolerancia_sao_aceitos(self) -> None:
        for numero in ('11251', '11350', '11150', '0011258'):
            with self.subTest(numero=numero):
                self.acionar.reset_mock()
                self.cancelar.reset_mock()
                self.simular_numeros([numero])
                resultado = importar_pedido(*self.args, MagicMock(), referencia_numero=11250)
                self.assertEqual(resultado.numero, numero)
                self.assertEqual(self.comandos().count('Incluir'), 1)
                self.cancelar.assert_not_called()

    def test_mudanca_para_um_durante_xml_tambem_cancela_antes_de_gravar(self) -> None:
        self.simular_numeros(['11251', '11252'])
        def importar_xml(*args):
            if self.numero_atual == '11251':
                self.numero_atual = '1'
        with patch('src.importar.importa_arq_integracao', side_effect=importar_xml):
            checkpoint = MagicMock()
            resultado = importar_pedido(*self.args, checkpoint, referencia_numero=11250)
        self.assertEqual(resultado.numero, '11252')
        checkpoint.assert_called_once_with('11252')
        self.assertEqual(self.comandos().count('Gravar'), 1)

    def test_aplica_tolerancia_da_configuracao_da_execucao(self) -> None:
        self.simular_numeros(['11276', '11275'])
        with usar_configuracao(replace(CONFIG, tolerancia_numero_interno=25)):
            resultado = importar_pedido(*self.args, MagicMock(), referencia_numero=11250)
        self.assertEqual(resultado.numero, '11275')
        self.cancelar.assert_called_once()

    def test_falha_de_cancelamento_nao_tenta_segunda_inclusao(self) -> None:
        self.simular_numeros(['1', '11251'])
        self.cancelar.side_effect = RuntimeError('Confirmação indisponível')
        checkpoint = MagicMock()
        with self.assertRaisesRegex(SisplanError, 'confirmar o cancelamento'):
            importar_pedido(*self.args, checkpoint, referencia_numero=11250)
        self.assertEqual(self.comandos(), ['Incluir'])
        checkpoint.assert_not_called()

    def test_cancelamento_sem_restaurar_numero_nao_repete(self) -> None:
        self.simular_numeros(['1', '11251'])
        with patch('src.importar.wait_until', side_effect=RuntimeError('Número não restaurado')):
            with self.assertRaisesRegex(SisplanError, 'confirmar o cancelamento'):
                importar_pedido(*self.args, MagicMock(), referencia_numero=11250)
        self.assertEqual(self.comandos(), ['Incluir'])


class SelecionarEmpresaTests(unittest.TestCase):
    def test_seleciona_001_e_002_pelo_codigo_independente_da_ordem(self) -> None:
        combo = MagicMock()
        combo.item_texts.return_value = ['002-NUNES ENXOVAIS', '', '001-NUNES ENXOVAIS']
        combo.selected_index.return_value = 0
        combo.selected_text.side_effect = lambda: combo.item_texts.return_value[combo.selected_index.return_value]
        combo.select.side_effect = lambda indice: setattr(combo.selected_index, 'return_value', indice)

        selecionar_empresa(combo, '001')
        combo.select.assert_called_once_with(2)
        combo.select.reset_mock()
        selecionar_empresa(combo, '002')
        combo.select.assert_called_once_with(0)
        combo.type_keys.assert_not_called()

    def test_empresa_ausente_ou_ambigua_interrompe_antes_de_selecionar(self) -> None:
        combo = MagicMock()
        for rotulos in (['002-NUNES ENXOVAIS'], ['001-MATRIZ', '001-OUTRA']):
            combo.item_texts.return_value = rotulos
            with self.assertRaises(SisplanError):
                selecionar_empresa(combo, '001')
        combo.select.assert_not_called()
