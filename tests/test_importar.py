import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from src.config import ATALHOS
from src.estado import EstadoError
from src.importar import importar_pedido
from src.erros import (SisplanError)
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
        resultado = importar_pedido(*self.args, lambda numero: eventos.append(('checkpoint', numero)))
        self.assertLess(eventos.index(('checkpoint', '100')), eventos.index(ATALHOS['gravar']))
        self.assertEqual(resultado.situacao, 'aguarda_confirmacao')

    def test_falha_de_persistencia_nao_envia_gravar(self) -> None:
        with self.assertRaises(SisplanError):
            importar_pedido(*self.args, MagicMock(side_effect=EstadoError('Disco cheio')))
        self.assertNotIn(ATALHOS['gravar'], [chamada.args[0] for chamada in self.enviar.call_args_list])

    def test_falha_no_aviso_nao_retorna_pedido_como_valido(self) -> None:
        self.duplicado.side_effect = SisplanError('Aviso não tratado')
        with self.assertRaises(SisplanError):
            importar_pedido(*self.args, MagicMock())
