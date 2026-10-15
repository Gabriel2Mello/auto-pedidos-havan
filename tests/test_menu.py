import io
import tempfile
import unittest
from datetime import datetime
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

import main
from src.banco import BancoSisplanError
from src.estado import EstadoPedido, EstadoPedidos
from src.menu import escolher_operacao, perguntar_apos_erro
from src.prevalidacao import PedidoRejeitadoError
from src.erros import (SessaoPortalExpiradaError)


class MenuTests(unittest.TestCase):
    def setUp(self) -> None:
        patch_relogio = patch('src.pedidos.datetime', wraps=datetime)
        relogio = patch_relogio.start()
        self.addCleanup(patch_relogio.stop)
        relogio.now.return_value = datetime(2026, 10, 15)
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.caminho = Path(self.pasta.name) / 'estado.sqlite3'

    def test_inserir_salva_lista_antes_de_retornar_para_processamento(self) -> None:
        with EstadoPedidos(self.caminho) as historico, redirect_stdout(io.StringIO()):
            with patch('builtins.input', side_effect=['1', '12345, 67890, 12345']):
                modo, pedidos = escolher_operacao(historico)
            self.assertEqual(modo, 'normal')
            self.assertEqual(pedidos, ['2026-12345', '2026-67890'])
            self.assertEqual(historico.pendentes(), pedidos)

    def test_enter_retoma_quando_existem_pendentes(self) -> None:
        saida = io.StringIO()
        with EstadoPedidos(self.caminho) as historico, redirect_stdout(saida):
            historico.adicionar_pedidos(['2026-12345'])
            with patch('builtins.input', return_value=''):
                self.assertEqual(escolher_operacao(historico), ('retomar', []))
        self.assertIn('Existem 1 pedido(s) pendente(s)', saida.getvalue())

    def test_lista_com_item_invalido_exige_correcao_sem_perder_pedidos(self) -> None:
        saida = io.StringIO()
        with EstadoPedidos(self.caminho) as historico, redirect_stdout(saida):
            with patch('builtins.input', side_effect=['1', '12345, abcde', '12345, 67890']):
                _, pedidos = escolher_operacao(historico)
            self.assertEqual(pedidos, ['2026-12345', '2026-67890'])
            self.assertEqual(historico.pendentes(), pedidos)
        self.assertIn('Não entendi estes números: abcde', saida.getvalue())

    def test_reimprimir_pede_numeros_sem_criar_fila_para_importar(self) -> None:
        with EstadoPedidos(self.caminho) as historico, redirect_stdout(io.StringIO()):
            with patch('builtins.input', side_effect=['3', '2026-109335']):
                self.assertEqual(escolher_operacao(historico), ('reimprimir', ['2026-109335']))
            self.assertEqual(historico.pendentes(), [])

    def test_opcao_invalida_e_retomada_vazia_voltam_ao_menu(self) -> None:
        saida = io.StringIO()
        with EstadoPedidos(self.caminho) as historico, redirect_stdout(saida):
            with patch('builtins.input', side_effect=['9', '2', '0']):
                self.assertIsNone(escolher_operacao(historico))
        self.assertIn('Opção inválida', saida.getvalue())
        self.assertIn('Não existem pedidos pendentes', saida.getvalue())

    def test_erro_so_repete_com_escolha_explicita(self) -> None:
        with redirect_stdout(io.StringIO()), patch('builtins.input', return_value='1'):
            self.assertEqual(perguntar_apos_erro('2026-12345', PedidoRejeitadoError('Produto ausente'), True, True), 'repetir')

    def test_sessao_expirada_oferece_reconectar_ou_parar(self) -> None:
        saida = io.StringIO()
        with redirect_stdout(saida), patch('builtins.input', side_effect=['2', '1']):
            decisao = perguntar_apos_erro('2026-12345', SessaoPortalExpiradaError(), True, False)
        self.assertEqual(decisao, 'repetir')
        self.assertIn('Reconectar ao Portal Havan', saida.getvalue())
        self.assertNotIn('2 - Deixar', saida.getvalue())

    def test_falha_ao_abrir_log_orienta_e_aguarda_sem_iniciar_operacoes(self) -> None:
        saida = io.StringIO()
        with patch('main.setup_logging', side_effect=PermissionError('Acesso negado')), \
             patch('main.EstadoPedidos') as estado, patch('builtins.input', return_value='') as entrada, \
             redirect_stdout(saida):
            main.main()
        estado.assert_not_called()
        entrada.assert_called_once()
        self.assertIn('PermissionError', saida.getvalue())
        self.assertIn('auto-pedidos.log', saida.getvalue())

    def test_erro_incerto_nao_oferece_repetir_nem_aceita_opcao_insegura(self) -> None:
        saida = io.StringIO()
        with redirect_stdout(saida), patch('builtins.input', side_effect=['1', '2', '0']):
            self.assertEqual(perguntar_apos_erro('2026-12345', RuntimeError('Falha'), False, False), 'encerrar')
        self.assertNotIn('1 - Corrigi', saida.getvalue())
        self.assertIn('auto-pedidos.log', saida.getvalue())

    @patch('main.setup_logging')
    @patch('main.set_app_id')
    def test_programa_sem_argumentos_abre_menu_e_preserva_entrada(self, app_id: MagicMock, logs: MagicMock) -> None:
        def executar(pedidos, modo, historico, ao_erro):
            self.assertEqual(historico.pendentes(), pedidos)
            self.assertEqual(modo, 'normal')
        with patch('main.EstadoPedidos', side_effect=lambda: EstadoPedidos(self.caminho)), \
             patch('main.processar_pedidos', side_effect=executar) as processar, \
             patch('sys.argv', ['main.py']), \
             patch('builtins.input', side_effect=['1', '12345, 67890', '0']), \
             redirect_stdout(io.StringIO()):
            main.main()
        processar.assert_called_once()

    @patch('main.setup_logging')
    @patch('main.set_app_id')
    def test_falha_ao_abrir_banco_para_e_aguarda_sem_repetir(self, app_id: MagicMock, logs: MagicMock) -> None:
        with patch('main.EstadoPedidos', side_effect=lambda: EstadoPedidos(self.caminho)), \
             patch('main.processar_pedidos', side_effect=BancoSisplanError('Rede')) as processar, \
             patch('sys.argv', ['main.py']), \
             patch('builtins.input', side_effect=['1', '12345', '0', '0']), \
             redirect_stdout(io.StringIO()):
            main.main()
        processar.assert_called_once()
        with EstadoPedidos(self.caminho) as historico:
            self.assertEqual(historico.pendentes(), ['2026-12345'])
