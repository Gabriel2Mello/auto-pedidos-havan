import unittest
from contextlib import ExitStack
from dataclasses import replace
from unittest.mock import MagicMock, patch

from src.config import ATALHOS, CONFIG, usar_configuracao
from src.estado import EstadoError
from src.importar import importar_pedido
from src.erros import SisplanError, NumeroInternoForaSequenciaError
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
        self.stack.enter_context(patch('src.importar.handle_produto_sem_cadastro', return_value=False))
        self.duplicado = self.stack.enter_context(patch('src.importar.handle_aviso_duplicado', return_value=False))
        self.enviar = self.stack.enter_context(patch('src.importar.send_keys_sleep'))
        self.campo = MagicMock()
        self.campo.window_text.return_value = '100'
        self.stack.enter_context(patch('src.importar.aguardar_campo', return_value=self.campo))
        self.args = ('2026-12345', MagicMock(), MagicMock(), MagicMock(), {'numero': self.campo})

    def test_checkpoint_e_salvo_antes_do_comando_de_gravacao(self) -> None:
        eventos = []
        self.enviar.side_effect = lambda tecla, *args: eventos.append(tecla)
        resultado = importar_pedido(*self.args, lambda numero: eventos.append(('checkpoint', numero)), referencia_numero=100)
        self.assertLess(eventos.index(('checkpoint', '100')), eventos.index(ATALHOS['gravar']))
        self.assertEqual(resultado.situacao, 'aguarda_confirmacao')

    def test_falha_de_persistencia_nao_envia_gravar(self) -> None:
        with self.assertRaises(SisplanError):
            importar_pedido(*self.args, MagicMock(side_effect=EstadoError('Disco cheio')), referencia_numero=100)
        self.assertNotIn(ATALHOS['gravar'], [chamada.args[0] for chamada in self.enviar.call_args_list])

    def test_falha_no_aviso_nao_retorna_pedido_como_valido(self) -> None:
        self.duplicado.side_effect = SisplanError('Aviso não tratado')
        with self.assertRaises(SisplanError):
            importar_pedido(*self.args, MagicMock(), referencia_numero=100)

    def simular_numeros(self, numeros: list[str]) -> None:
        self.numero_atual = '11249'
        self.numero_anterior = self.numero_atual
        self.campo.window_text.side_effect = lambda: self.numero_atual
        def enviar(tecla, *args):
            if tecla == ATALHOS['incluir']:
                self.numero_anterior = self.numero_atual
                self.numero_atual = numeros.pop(0)
            elif tecla == ATALHOS['desistir']:
                self.numero_atual = self.numero_anterior
        self.enviar.side_effect = enviar

    def teclas(self) -> list[str]:
        return [chamada.args[0] for chamada in self.enviar.call_args_list]

    def test_numero_um_cancela_e_repete_o_mesmo_pedido_uma_vez(self) -> None:
        self.simular_numeros(['1', '11253'])
        checkpoint = MagicMock()
        resultado = importar_pedido(*self.args, checkpoint, referencia_numero=11250)
        self.assertEqual(resultado.numero, '11253')
        self.assertEqual(self.teclas().count(ATALHOS['incluir']), 2)
        self.assertEqual(self.teclas().count(ATALHOS['desistir']), 1)
        self.assertEqual(self.teclas().count(ATALHOS['gravar']), 1)
        checkpoint.assert_called_once_with('11253')

    def test_duas_anomalias_cancelam_sem_gravar_e_pedem_acao(self) -> None:
        for numeros in (['1', '1'], ['1', '999999'], ['', 'abc'], ['0', '-1']):
            with self.subTest(numeros=numeros):
                self.enviar.reset_mock()
                self.simular_numeros(list(numeros))
                checkpoint = MagicMock()
                with self.assertRaises(NumeroInternoForaSequenciaError) as capturado:
                    importar_pedido(*self.args, checkpoint, referencia_numero=11250)
                self.assertEqual(self.teclas().count(ATALHOS['incluir']), 2)
                self.assertEqual(self.teclas().count(ATALHOS['desistir']), 2)
                self.assertNotIn(ATALHOS['gravar'], self.teclas())
                checkpoint.assert_not_called()
                self.assertIn('duas tentativas', mensagem_erro(capturado.exception))
                self.assertIn('referência 11250', mensagem_erro(capturado.exception))

    def test_saltos_e_zeros_a_esquerda_dentro_da_tolerancia_sao_aceitos(self) -> None:
        for numero in ('11251', '11350', '11150', '0011258'):
            with self.subTest(numero=numero):
                self.enviar.reset_mock()
                self.simular_numeros([numero])
                resultado = importar_pedido(*self.args, MagicMock(), referencia_numero=11250)
                self.assertEqual(resultado.numero, numero)
                self.assertEqual(self.teclas().count(ATALHOS['incluir']), 1)
                self.assertNotIn(ATALHOS['desistir'], self.teclas())

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
        self.assertEqual(self.teclas().count(ATALHOS['gravar']), 1)

    def test_aplica_tolerancia_da_configuracao_da_execucao(self) -> None:
        self.simular_numeros(['11276', '11275'])
        with usar_configuracao(replace(CONFIG, tolerancia_numero_interno=25)):
            resultado = importar_pedido(*self.args, MagicMock(), referencia_numero=11250)
        self.assertEqual(resultado.numero, '11275')
        self.assertEqual(self.teclas().count(ATALHOS['desistir']), 1)

    def test_falha_de_cancelamento_nao_tenta_segunda_inclusao(self) -> None:
        self.simular_numeros(['1', '11251'])
        self.args[1].wait.side_effect = RuntimeError('Tela indisponível')
        checkpoint = MagicMock()
        with self.assertRaisesRegex(SisplanError, 'confirmar o cancelamento'):
            importar_pedido(*self.args, checkpoint, referencia_numero=11250)
        self.assertEqual(self.teclas().count(ATALHOS['incluir']), 1)
        checkpoint.assert_not_called()

    def test_cancelamento_sem_restaurar_numero_nao_repete(self) -> None:
        self.simular_numeros(['1', '11251'])
        with patch('src.importar.wait_until', side_effect=RuntimeError('Número não restaurado')):
            with self.assertRaisesRegex(SisplanError, 'confirmar o cancelamento'):
                importar_pedido(*self.args, MagicMock(), referencia_numero=11250)
        self.assertEqual(self.teclas().count(ATALHOS['incluir']), 1)
