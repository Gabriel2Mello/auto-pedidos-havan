import io
import json
import logging
import tempfile
import unittest
import xml.etree.ElementTree as ET
from contextlib import ExitStack, redirect_stderr
from dataclasses import replace
from datetime import datetime
from http.client import HTTPConnection
from pathlib import Path
from threading import Event, Thread
from time import monotonic
from unittest.mock import MagicMock, patch

from pypdf import PdfWriter
from requests.exceptions import ConnectionError
from urllib3.connectionpool import HTTPSConnectionPool
from urllib3.exceptions import MaxRetryError

import main
import src.servico_pedidos as servico
import tests.test_interface_web as testes_interface
from src.arquivos import caminho_xml
from src.banco import PedidoExistente, ProdutoCadastrado
from src.baixar import baixar_pedidos
from src.config import CONFIG, Configuracao, configuracao_atual, usar_configuracao
from src.controlador import EstadoInterface
from src.erros import ConfiguracaoError
from src.estado import EstadoPedido, EstadoPedidos
from src.imprimir import ResultadoImpressao
from src.importar import ResultadoImportacao
from src.interface_web import criar_servidor
from src.logs import setup_logging
from src.notificacoes import enviar_alerta_teams
from src.pedidos import ItemEsperado, analisar_entrada_pedidos
from src.seguranca import registrar_segredos
from decimal import Decimal
from tests.fixtures import xml_pedido


class RegressaoRevisaoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.enterContext(patch('sincronizar_estatisticas.ler_configuracao', return_value=None))

    def test_encerramento_apos_historico_corrompido_ocupado_ou_pasta_ausente(self):
        for caso in ('corrompido', 'ocupado', 'pasta_ausente'):
            with self.subTest(caso=caso), tempfile.TemporaryDirectory() as pasta, ExitStack() as pilha:
                caminho = Path(pasta) / 'estado.sqlite3'
                if caso == 'corrompido':
                    caminho.write_bytes(b'historico ficticio invalido')
                elif caso == 'ocupado':
                    pilha.enter_context(EstadoPedidos(caminho))
                else:
                    caminho = Path(pasta) / 'ausente' / 'estado.sqlite3'
                with patch('src.controlador.TEMPO_LIBERAR_HISTORICO', 0):
                    estado = EstadoInterface(caminho, executor=MagicMock())
                    self.assertTrue(estado.finalizado.wait(3))
                self.assertEqual(estado.fase, 'FALHA')
                servidor, _ = criar_servidor(estado)
                http = Thread(target=servidor.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
                http.start()
                try:
                    estado.encerrar()
                    http.join(3)
                    self.assertFalse(http.is_alive())
                    self.assertTrue(estado.encerrando)
                    estado.executor.assert_not_called()
                finally:
                    if http.is_alive():
                        servidor.shutdown()
                    servidor.server_close()
                    estado.worker.join(3)

    def test_lista_invalida_no_cli_nao_abre_historico_nem_inicia_fluxo(self):
        for flag in ('--reimprimir', '--reiniciar'):
            for entrada in ('2026-12345,INVALIDO', '   '):
                with self.subTest(flag=flag, entrada=entrada), ExitStack() as pilha:
                    pilha.enter_context(patch('main.setup_logging'))
                    pilha.enter_context(patch('sys.argv', ['main.py', flag, entrada]))
                    historico = pilha.enter_context(patch('main.EstadoPedidos'))
                    fluxo = pilha.enter_context(patch('main.processar_pedidos'))
                    pilha.enter_context(redirect_stderr(io.StringIO()))
                    with self.assertRaises(SystemExit) as erro:
                        main.main()
                    self.assertEqual(erro.exception.code, 2)
                    historico.assert_not_called()
                    fluxo.assert_not_called()

    def test_parser_estrito_compartilha_regras_e_preserva_ordem(self):
        self.assertEqual(analisar_entrada_pedidos('12345\n2026-54321,12345', ano=2026),
                         ['2026-12345', '2026-54321'])
        self.assertEqual(analisar_entrada_pedidos('', permitir_vazio=True), [])
        with self.assertRaises(ValueError):
            analisar_entrada_pedidos('2026-12345,errado')

    def test_assercao_no_worker_reprova_o_teste_principal(self):
        # Metateste: a regressao da revisao precisa resultar em falha observavel.
        teste = testes_interface.InterfaceTests('test_lista_e_salva_antes_da_resposta_e_conexao_pertence_ao_executor')
        resultado = unittest.TestResult()
        with patch('src.estado.EstadoPedidos.pendentes', return_value=[]):
            teste.run(resultado)
        self.assertFalse(resultado.wasSuccessful())
        self.assertTrue(any('AssertionError' in texto for _, texto in resultado.failures + resultado.errors))

    def test_interface_independe_do_ano_atual_e_normalizador_usa_2027(self):
        with patch('src.pedidos.datetime', wraps=datetime) as relogio:
            relogio.now.return_value = datetime(2027, 1, 1)
            self.assertEqual(analisar_entrada_pedidos('12345'), ['2027-12345'])
            resultado = unittest.TestResult()
            unittest.defaultTestLoader.loadTestsFromTestCase(testes_interface.InterfaceTests).run(resultado)
        self.assertTrue(resultado.wasSuccessful(), str(resultado.failures + resultado.errors))

    def test_download_propaga_configuracao_para_thread_de_trabalho(self):
        observacoes = []
        config = replace(CONFIG, pasta_pedidos=Path('C:/teste-contexto-ficticio'))
        def processar(scraper, pedido):
            observacoes.append(caminho_xml(pedido))
            return pedido, True, None
        with usar_configuracao(config), patch('src.baixar.processar_unico', side_effect=processar), patch('src.baixar.tqdm'):
            resultado = baixar_pedidos(MagicMock(), ['2026-12345'])
        self.assertEqual(resultado, {'2026-12345': True})
        self.assertEqual(observacoes, [config.pasta_pedidos / '2026-12345' / 'arq_de_integracao 2026-12345.xml'])
        self.assertIs(configuracao_atual(), CONFIG)

    def test_configuracao_corrigida_e_lida_no_proximo_lote(self):
        with tempfile.TemporaryDirectory() as pasta, ExitStack() as pilha:
            raiz = Path(pasta)
            sumatra, banco_config = raiz / 'Sumatra.exe', raiz / 'banco.json'
            sumatra.touch(); banco_config.touch()
            toml = raiz / 'config.toml'
            def gravar(impressora):
                toml.write_text(f"sumatra = '{sumatra}'\npasta_pedidos = '{raiz}'\nbanco_config = '{banco_config}'\nimpressora = '{impressora}'\n", encoding='utf-8')
            carregar = Configuracao.carregar
            pilha.enter_context(patch('src.servico_pedidos.Configuracao.carregar', side_effect=lambda: carregar(toml, {})))
            banco = MagicMock()
            banco.consultar_pedidos.return_value = {'2026-12345': [PedidoExistente('100', 2)]}
            classe = pilha.enter_context(patch('src.servico_pedidos.BancoSisplan'))
            classe.return_value.__enter__.return_value = banco
            portal = pilha.enter_context(patch('src.servico_pedidos.create_scraper'))
            with EstadoPedidos(raiz / 'estado.sqlite3') as historico:
                gravar('')
                with self.assertRaises(ConfiguracaoError):
                    servico.processar_pedidos(['2026-12345'], historico=historico)
                self.assertEqual(historico.pendentes(), ['2026-12345'])
                classe.assert_not_called()
                gravar('Impressora ficticia')
                resumo = servico.processar_pedidos([], 'retomar', historico=historico)
                self.assertEqual(resumo.situacoes, {'2026-12345': 'existente'})
                self.assertEqual(historico.pendentes(), [])
            portal.assert_not_called()
        self.assertEqual(servico.opcoes_seguras(ConfiguracaoError('corrigir'), None), (False, False))

    def test_logs_redigem_segredos_em_http_excecoes_encadeadas_e_teams(self):
        root = logging.getLogger()
        anteriores, nivel = root.handlers[:], root.level
        with tempfile.TemporaryDirectory() as pasta:
            try:
                setup_logging(Path(pasta), console=False)
                assinatura = 'ASSINATURA_FICTICIA_REVISAO'
                senha = 'SENHA_FICTICIA_REVISAO'
                url = 'https://webhook.example/incoming?sig=' + assinatura
                config = replace(CONFIG, teams_webhook_url=url, senha_portal=senha)
                with usar_configuracao(config):
                    for status in (200, 502):
                        resposta = MagicMock(status_code=status, text=url)
                        with patch('src.notificacoes.requests.post', return_value=resposta):
                            enviar_alerta_teams('2026-12345')
                    erro = ConnectionError(MaxRetryError(HTTPSConnectionPool('webhook.example'), '/incoming?sig=' + assinatura))
                    with patch('src.notificacoes.requests.post', side_effect=erro):
                        enviar_alerta_teams('2026-12345')
                    logging.getLogger('urllib3.connectionpool').warning('GET /incoming?sig=%s', assinatura)
                    try:
                        try:
                            raise ValueError(senha)
                        except ValueError as causa:
                            raise RuntimeError(url) from causa
                    except RuntimeError:
                        root.exception('Falha ficticia para suporte')
                texto = (Path(pasta) / 'auto-pedidos.log').read_text(encoding='utf-8')
                for segredo in (assinatura, senha, url):
                    self.assertNotIn(segredo, texto)
                self.assertIn('Traceback', texto)
                self.assertIn('Falha ficticia para suporte', texto)
                self.assertIn('[oculto]', texto)
            finally:
                for handler in root.handlers[:]:
                    if handler not in anteriores:
                        root.removeHandler(handler); handler.close()
                root.handlers = anteriores; root.setLevel(nivel)

    def test_api_log_redige_conteudo_anterior_e_preserva_nome(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            segredo = 'SEGREDO_FICTICIO_DOWNLOAD'
            registrar_segredos(segredo)
            arquivo = raiz / 'log.txt'
            arquivo.write_text('token=' + segredo, encoding='utf-8')
            estado = EstadoInterface(raiz / 'estado.sqlite3', executor=MagicMock(), arquivo_log=arquivo)
            self.assertTrue(estado.pronto.wait(3))
            servidor, token = criar_servidor(estado)
            http = Thread(target=servidor.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
            http.start()
            conn = HTTPConnection('127.0.0.1', servidor.server_port, timeout=3)
            try:
                conn.request('GET', '/api/log', headers={'Authorization': 'Bearer ' + token})
                resposta = conn.getresponse()
                self.assertEqual(resposta.status, 200)
                self.assertNotIn(segredo.encode(), resposta.read())
            finally:
                conn.close(); servidor.shutdown(); servidor.server_close()
                http.join(3); estado.worker.join(3)

    def test_api_controlador_servico_confirmam_importacao_e_impressao_simuladas(self):
        with tempfile.TemporaryDirectory() as pasta, ExitStack() as pilha:
            raiz = Path(pasta)
            pedido, numero = '2026-12345', '100'
            pasta_pedido = raiz / pedido; pasta_pedido.mkdir()
            ET.ElementTree(xml_pedido()).write(pasta_pedido / f'arq_de_integracao {pedido}.xml', encoding='utf-8')
            writer = PdfWriter(); writer.add_blank_page(width=595, height=842)
            with (pasta_pedido / f'ordem_de_compra {pedido}.pdf').open('wb') as arquivo:
                writer.write(arquivo)
            sumatra, banco_config = raiz / 'Sumatra.exe', raiz / 'banco.json'
            sumatra.touch(); banco_config.touch()
            config = replace(CONFIG, erro_leitura='', sumatra=sumatra, banco_config=banco_config,
                             pasta_pedidos=raiz, impressora='Impressora ficticia')
            pilha.enter_context(patch('src.servico_pedidos.Configuracao.carregar', return_value=config))
            banco = MagicMock()
            banco.consultar_pedidos.return_value = {}
            banco.consultar_barras.return_value = {'0123456789012': {ProdutoCadastrado('P1', 'C1', 'T1')}}
            banco.confirmar_gravacao.return_value = PedidoExistente(numero, 2)
            classe = pilha.enter_context(patch('src.servico_pedidos.BancoSisplan'))
            classe.return_value.__enter__.return_value = banco
            portal = pilha.enter_context(patch('src.servico_pedidos.create_scraper'))
            app = pilha.enter_context(patch('src.servico_pedidos.inicia_app', return_value=(MagicMock(), MagicMock(), MagicMock(), {})))
            def importar(*args, **kwargs):
                args[-1](numero)
                return ResultadoImportacao(numero, 'aguarda_confirmacao')
            inclusao = pilha.enter_context(patch('src.servico_pedidos.importar_pedido', side_effect=importar))
            pilha.enter_context(patch('src.servico_pedidos.notificar_operacao_confirmada'))
            impressao = pilha.enter_context(patch('src.imprimir.imprimir_pdf', return_value=ResultadoImpressao('enviada')))
            caminho = raiz / 'estado.sqlite3'
            with EstadoPedidos(caminho) as historico:
                historico.salvar(EstadoPedido(pedido, '', 'baixado'))
            estado = EstadoInterface(caminho)
            self.assertTrue(estado.pronto.wait(3))
            servidor, token = criar_servidor(estado)
            http = Thread(target=servidor.serve_forever, kwargs={'poll_interval': .02}, daemon=True); http.start()
            conn = HTTPConnection('127.0.0.1', servidor.server_port, timeout=3)
            try:
                origem = f'http://127.0.0.1:{servidor.server_port}'
                conn.request('POST', '/api/iniciar', body=json.dumps({'modo':'normal','pedidos':pedido,'solicitacao':'integracao-ficticia'}),
                             headers={'Authorization':'Bearer '+token,'Origin':origem,'Content-Type':'application/json'})
                self.assertEqual(conn.getresponse().status, 200)
                limite = monotonic() + 3
                while estado.fase == 'EXECUTANDO' and monotonic() < limite:
                    Event().wait(.01)
                situacao = estado.situacao()
                self.assertEqual(situacao['fase'], 'CONCLUIDO', str(situacao['erro']))
                self.assertEqual(situacao['pedidos'][0]['etapa'], 'impressao_enviada')
                self.assertEqual(situacao['pedidos'][0]['fila'], 'enviados')
                self.assertFalse(situacao['pedidos'][0]['pendente'])
                self.assertEqual(situacao['pedidos'][0]['numero'], numero)
                self.assertEqual(banco.confirmar_gravacao.call_args.kwargs['itens_esperados'],
                                 [ItemEsperado('P1', 'C1', 'T1', Decimal(1))])
                portal.assert_not_called(); app.assert_called_once(); inclusao.assert_called_once(); impressao.assert_called_once()
            finally:
                conn.close(); servidor.shutdown(); servidor.server_close()
                http.join(3); estado.worker.join(3)
            with EstadoPedidos(caminho) as historico:
                self.assertEqual(historico.pendentes(), [])
                self.assertEqual(historico.obter(pedido).etapa, 'impressao_enviada')
