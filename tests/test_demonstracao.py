"""Roteiros sintéticos e ligação real entre demonstração, HTTP e controlador."""
import json
import os
from datetime import datetime
from http.client import HTTPConnection
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import unittest
from unittest.mock import Mock, patch

import demonstracao as demo
from src.erros import BancoSisplanError, SessaoPortalExpiradaError
from src.estado import EstadoPedido, EstadoPedidos
from src.interface_web import criar_servidor
from src.pedidos import analisar_entrada_pedidos
from tests.test_interface_web import BaseInterface


class TestSimulacao(unittest.TestCase):
    def setUp(self):
        self.raiz = Path(self.enterContext(TemporaryDirectory()))
        self.historico = self.enterContext(EstadoPedidos(self.raiz / 'estado.sqlite3'))
        self.enterContext(patch('demonstracao.esperar_etapa'))
        self.etapas = []
        self.parada = Event()
        self.parar_na_etapa = ''

    def pedido(self, codigo):
        return f'2027-{codigo}'

    def executar(self, codigos=(), modo='normal', decisao='encerrar'):
        pedidos = [self.pedido(c) for c in codigos]
        if modo == 'normal':
            self.historico.adicionar_pedidos(pedidos)
        elif modo == 'retomar':
            pedidos = self.historico.pendentes()
        self.decidir = Mock(return_value=decisao)
        return demo.simular(pedidos, modo, historico=self.historico, ao_erro=self.decidir,
                            ao_progresso=self.progresso, parar=self.parada.is_set)

    def progresso(self, pedido, indice, total):
        registro = self.historico.obter(pedido)
        if registro is not None:
            self.etapas.append((pedido, registro.etapa))
            if registro.etapa == self.parar_na_etapa:
                self.parada.set()

    def test_catalogo_oferece_roteiros_sem_efetuar_operacoes(self):
        cenarios = demo.cenarios_interface()
        self.assertEqual(len({c['id'] for c in cenarios}), len(cenarios))
        for c in cenarios:
            with self.subTest(cenario=c['id']):
                self.assertTrue(c['orientacao'])
                self.assertIn(c['modo'], ('normal', 'reimprimir'))
                if c['id'] == 'entrada':
                    with self.assertRaises(ValueError):
                        analisar_entrada_pedidos(c['entrada'], ano=2027)
                else:
                    pedidos = analisar_entrada_pedidos(c['entrada'], ano=2027)
                    self.assertTrue(all(p.startswith('2027-') for p in pedidos))
                    if c['id'] == 'paginacao':
                        self.assertEqual(len(pedidos), 60)
        self.assertEqual(self.historico.listar(), [])

    def test_inclusao_completa_e_segunda_solicitacao_sem_repetir_efeitos(self):
        resumo = self.executar(['999002'])
        pedido = self.pedido('999002')
        self.assertEqual(resumo.importados, {pedido})
        self.assertEqual(resumo.situacoes[pedido], 'impressao_enviada')
        self.etapas.clear()
        resumo = self.executar(['999002'])
        self.assertEqual(resumo.importados, set())
        self.assertEqual(resumo.situacoes[pedido], 'existente')
        self.assertNotIn((pedido, 'impressao_iniciada'), self.etapas)

    def test_existente_e_reimpressao_explicita_seguem_fluxos_distintos(self):
        pedido = self.pedido('999001')
        self.historico.salvar(EstadoPedido(pedido, '8001', 'impressao_enviada'))
        self.assertEqual(self.executar(['999001']).situacoes[pedido], 'existente')
        self.etapas.clear()
        resumo = self.executar(['999001'], modo='reimprimir')
        self.assertEqual(resumo.situacoes[pedido], 'impressao_enviada')
        self.assertEqual(resumo.importados, set())
        self.assertNotIn((pedido, 'baixado'), self.etapas)
        self.assertNotIn((pedido, 'gravacao_pendente'), self.etapas)

    def test_reimpressao_sem_gravacao_e_rejeitada_sem_criar_historico(self):
        resumo = self.executar(['999099'], modo='reimprimir')
        self.assertEqual(resumo.situacoes[self.pedido('999099')], 'rejeitado')
        self.assertEqual(self.historico.listar(), [])

    def test_cadastro_fica_pendente_e_nova_solicitacao_simula_correcao(self):
        pedido = self.pedido('999003')
        resumo = self.executar(['999003', '999015'], decisao='pular')
        self.assertEqual(resumo.situacoes[pedido], 'sem_cadastro')
        self.assertEqual(self.historico.obter(pedido).etapa, 'sem_cadastro')
        self.assertTrue(self.historico.obter(pedido).erro)
        resumo = self.executar(modo='retomar')
        self.assertEqual(resumo.importados, {pedido})
        self.assertEqual(self.historico.pendentes(), [])

    def test_falhas_transitorias_oferecem_decisoes_e_recuperam_sem_duplicar(self):
        for codigo, tipo, pular in [('999004', demo.PedidoRejeitadoError, True),
                                    ('999005', SessaoPortalExpiradaError, False),
                                    ('999006', BancoSisplanError, False)]:
            with self.subTest(codigo=codigo):
                resumo = self.executar([codigo], decisao='repetir')
                self.decidir.assert_called_once()
                self.assertIsInstance(self.decidir.call_args.args[1], tipo)
                self.assertEqual(self.decidir.call_args.args[2:], (True, pular))
                self.assertEqual(resumo.importados, {self.pedido(codigo)})
                self.assertEqual(resumo.situacoes[self.pedido(codigo)], 'impressao_enviada')

    def test_parar_na_pausa_preserva_o_proximo_pedido(self):
        self.executar(['999004', '999015'], decisao='encerrar')
        self.assertEqual(self.historico.obter(self.pedido('999015')).etapa, 'para_baixar')
        self.assertEqual(len(self.historico.pendentes()), 2)
        resumo = self.executar(modo='retomar')
        self.assertEqual(len(resumo.importados), 2)

    def test_retomada_continua_do_download_e_da_importacao_sem_regredir(self):
        self.executar(['999009', '999010'])
        self.assertEqual(self.historico.obter(self.pedido('999009')).etapa, 'baixado')
        self.assertEqual(self.historico.obter(self.pedido('999010')).etapa, 'importado')
        self.etapas.clear()
        resumo = self.executar(modo='retomar')
        self.assertEqual(resumo.importados, {self.pedido('999009')})
        self.assertNotIn((self.pedido('999010'), 'gravacao_pendente'), self.etapas)
        self.assertEqual(self.historico.pendentes(), [])

    def test_gravacao_incerta_bloqueia_lote_e_retomada_so_confirma(self):
        pedido = self.pedido('999007')
        self.executar(['999007', '999015'])
        self.assertEqual(self.decidir.call_args.args[2:], (False, False))
        self.assertEqual(self.historico.obter(pedido).etapa, 'gravacao_pendente')
        self.assertEqual(self.historico.obter(self.pedido('999015')).etapa, 'para_baixar')
        self.etapas.clear()
        resumo = self.executar(modo='retomar')
        self.assertEqual(resumo.importados, {self.pedido('999015')})
        self.assertNotIn((pedido, 'importacao_iniciada'), self.etapas)
        self.assertEqual(resumo.situacoes[pedido], 'impressao_enviada')

    def test_aviso_retomado_vira_existente_sem_incluir_ou_imprimir(self):
        pedido = self.pedido('999008')
        self.executar(['999008'])
        self.assertEqual(self.historico.obter(pedido).etapa, 'aviso_pendente')
        self.etapas.clear()
        resumo = self.executar(modo='retomar')
        self.assertEqual(resumo.situacoes[pedido], 'existente')
        self.assertEqual(resumo.importados, set())
        self.assertNotIn((pedido, 'impressao_iniciada'), self.etapas)
        self.assertEqual(self.executar(['999008'], modo='reimprimir').importados, set())

    def test_cancelamento_incompleto_nao_libera_retomada_nem_outro_pedido(self):
        pedido = self.pedido('999014')
        self.executar(['999014'])
        for codigos, modo in [(['999014'], 'normal'), ([], 'retomar'), (['999015'], 'normal')]:
            with self.subTest(modo=modo, codigos=codigos):
                resumo = self.executar(codigos, modo=modo, decisao='pular')
                self.assertEqual(resumo.importados, set())
                self.assertEqual(self.decidir.call_args.args[2:], (False, False))
                self.assertEqual(self.historico.obter(pedido).etapa, 'importacao_iniciada')

    def test_impressao_pendente_retoma_sem_outra_inclusao(self):
        self.executar(['999012'])
        self.assertEqual(self.historico.obter(self.pedido('999012')).etapa, 'impressao_pendente')
        resumo = self.executar(modo='retomar')
        self.assertEqual(resumo.importados, set())
        self.assertEqual(resumo.situacoes[self.pedido('999012')], 'impressao_enviada')

    def test_impressao_incerta_exige_reimpressao_explicita(self):
        pedido = self.pedido('999011')
        self.executar(['999011'], decisao='pular')
        self.etapas.clear()
        resumo = self.executar(modo='retomar', decisao='repetir')
        self.assertEqual(self.decidir.call_args.args[2:], (False, True))
        self.assertEqual(resumo.situacoes[pedido], 'impressao_incerta')
        self.assertNotIn((pedido, 'impressao_iniciada'), self.etapas)
        resumo = self.executar(['999011'], modo='reimprimir')
        self.assertEqual(resumo.importados, set())
        self.assertEqual(resumo.situacoes[pedido], 'impressao_enviada')

    def test_parada_durante_download_preserva_etapa_baixada(self):
        self.parar_na_etapa = 'baixado'
        self.executar(['999016', '999017'])
        self.assertEqual(self.historico.obter(self.pedido('999016')).etapa, 'baixado')
        self.assertEqual(self.historico.obter(self.pedido('999017')).etapa, 'para_baixar')

    def test_parada_durante_gravacao_aguarda_confirmacao_e_nao_imprime(self):
        self.parar_na_etapa = 'gravacao_pendente'
        self.executar(['999016', '999017'])
        self.assertEqual(self.historico.obter(self.pedido('999016')).etapa, 'importado')
        self.assertEqual(self.historico.obter(self.pedido('999017')).etapa, 'para_baixar')
        self.assertNotIn((self.pedido('999016'), 'impressao_iniciada'), self.etapas)

    def test_parada_durante_impressao_termina_o_envio_atual(self):
        self.parar_na_etapa = 'impressao_iniciada'
        self.executar(['999016', '999017'])
        self.assertEqual(self.historico.obter(self.pedido('999016')).etapa, 'impressao_enviada')
        self.assertEqual(self.historico.obter(self.pedido('999017')).etapa, 'para_baixar')

    def test_lista_longa_gera_historico_consultavel_sem_novas_inclusoes(self):
        resumo = self.executar([str(n) for n in range(999100, 999160)])
        self.assertEqual(set(resumo.situacoes.values()), {'existente'})
        self.assertEqual(resumo.importados, set())
        self.assertEqual(len(self.historico.listar()), 60)
        self.assertEqual(self.historico.pendentes(), [])

    def test_abertura_isola_dados_e_libera_recursos_inclusive_apos_falha(self):
        for falhar in (False, True):
            with self.subTest(falhar=falhar), \
                 patch.dict(os.environ, {'HAVAN_DESKTOP_DADOS': str(self.raiz / 'preferencia-anterior')}), \
                 patch('integracao_hub.IntegracaoLocal') as integracao, \
                 patch('sincronizar_estatisticas.Sincronizador') as sincronizador, \
                 patch('src.servico_pedidos.processar_pedidos') as operacional, \
                 patch('requests.Session.request') as requisicao, \
                 patch('metricas_nunes.registrar_evento') as metrica:
                pastas, estados = [], []
                def executar(servidor):
                    pastas.append(Path(os.environ['HAVAN_DESKTOP_DADOS']))
                    estados.append(servidor.estado)
                    self.assertTrue(servidor.demonstracao)
                    self.assertNotEqual(pastas[0], self.raiz / 'preferencia-anterior')
                    self.assertEqual(servidor.estado.situacao()['pedidos'][0]['pedido'], f'{datetime.now().year}-999001')
                    if falhar:
                        raise RuntimeError('Falha sintética do WebView')
                with patch('desktop_havan.executar', side_effect=executar):
                    if falhar:
                        with self.assertRaisesRegex(RuntimeError, 'Falha sintética'):
                            demo.main()
                    else:
                        self.assertEqual(demo.main(), 0)
                self.assertEqual(os.environ['HAVAN_DESKTOP_DADOS'], str(self.raiz / 'preferencia-anterior'))
                self.assertFalse(pastas[0].exists())
                self.assertFalse(estados[0].worker.is_alive())
                for proibido in (integracao, sincronizador, operacional, requisicao, metrica):
                    proibido.assert_not_called()


class TestApiDemonstracao(BaseInterface):
    def setUp(self):
        super().setUp()
        self.enterContext(patch('demonstracao.esperar_etapa'))
        self.servidor, self.token = criar_servidor(self.estado, modo_desktop=True)
        self.http = Thread(target=self.servidor.serve_forever, kwargs={'poll_interval': .02})
        self.http.start()
        self.addCleanup(self.fechar_http)

    def fechar_http(self):
        self.servidor.shutdown()
        self.servidor.server_close()
        self.http.join(3)

    def catalogo(self, token=True):
        conn = HTTPConnection('127.0.0.1', self.servidor.server_port, timeout=3)
        try:
            conn.request('GET', '/api/demo/cenarios', headers={'Authorization': 'Bearer ' + self.token} if token else {})
            resposta = conn.getresponse()
            return resposta.status, json.loads(resposta.read())
        finally:
            conn.close()

    def test_catalogo_autenticado_exclusivo_da_demo_sem_executar(self):
        self.assertEqual(self.catalogo()[0], 404)
        self.servidor.demonstracao = True
        self.assertEqual(self.catalogo(token=False)[0], 403)
        status, cenarios = self.catalogo()
        self.assertEqual(status, 200)
        self.assertEqual(cenarios, demo.cenarios_interface())
        self.assertEqual(self.chamadas, [])
        self.assertEqual(self.estado.situacao()['pedidos'], [])

    def test_simulador_real_pausa_e_reimporta_pelo_controlador(self):
        self.executor = demo.simular
        self.iniciar(pedidos='2027-999003')
        self.aguardar(lambda: self.estado.fase == 'PAUSADO')
        erro = self.estado.situacao()['erro']
        self.assertTrue(erro['repetir'])
        self.assertTrue(erro['pular'])
        self.estado.decidir({'execucao': self.estado.execucao, 'erro': erro['id'], 'decisao': 'pular'})
        self.aguardar(lambda: self.estado.fase == 'CONCLUIDO')
        self.assertEqual(self.estado.situacao()['pedidos'][0]['etapa'], 'sem_cadastro')
        self.iniciar(pedidos='2027-999003', solicitacao='cadastro-corrigido')
        self.aguardar(lambda: self.estado.fase == 'CONCLUIDO')
        self.assertEqual(self.estado.situacao()['resumo']['importacoes_confirmadas'], 1)
        self.assertEqual(self.estado.situacao()['pedidos'][0]['etapa'], 'impressao_enviada')
