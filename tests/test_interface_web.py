import json
import sqlite3
import tempfile
import unittest
from http.client import HTTPConnection
from pathlib import Path
from queue import SimpleQueue
from threading import Event, Thread, get_ident
from time import monotonic
from unittest.mock import patch

from src.banco import BancoSisplanError
from src.estado import EstadoError, EstadoPedido, EstadoPedidos
from src.interface_web import ConflitoInterface, EstadoInterface, criar_servidor
from src.resumo import ResumoExecucao
from src.erros import (SessaoPortalExpiradaError)


class BaseInterface(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.raiz = Path(self.pasta.name)
        self.caminho = self.raiz / 'estado.sqlite3'
        self.log = self.raiz / 'auto-pedidos.log'
        self.log.write_text('diagnostico sintetico\n', encoding='utf-8')
        self.executado = Event()
        self.liberar = Event()
        self.chamadas = []
        self.falhas_executor = SimpleQueue()
        self.executor = self.executar
        self.estado = EstadoInterface(self.caminho, executor=self.despachar,
                                      codigo_execucao='execucao-teste', arquivo_log=self.log)
        self.addCleanup(self.fechar)
        self.addCleanup(self.liberar.set)
        self.assertTrue(self.estado.pronto.wait(3))
        self.assertEqual(self.estado.fase, 'PRONTO')

    def despachar(self, *args, **kwargs):
        self.chamadas.append((args, kwargs))
        try:
            return self.executor(*args, **kwargs)
        except AssertionError as erro:
            self.falhas_executor.put(erro)
            raise

    def executar(self, pedidos, modo, *, historico, ao_erro, ao_progresso, parar):
        self.executado.set()
        return ResumoExecucao(dict.fromkeys(pedidos, 'existente'))

    def fechar(self) -> None:
        self.estado.encerrar()
        self.estado.worker.join(3)
        self.assertFalse(self.estado.worker.is_alive(), 'Executor não encerrou com segurança')
        if not self.falhas_executor.empty():
            raise self.falhas_executor.get_nowait()

    def aguardar(self, condicao) -> None:
        limite = monotonic() + 3
        while not condicao() and monotonic() < limite:
            Event().wait(.01)
        self.assertTrue(condicao())

    def iniciar(self, **extras) -> None:
        dados = {'modo': 'normal', 'pedidos': '2026-12345, 2026-67890', 'solicitacao': 'pedido-1'}
        dados.update(extras)
        self.estado.iniciar(dados)


class InterfaceTests(BaseInterface):
    def test_reabrir_aguarda_execucao_anterior_liberar_historico(self) -> None:
        nova = EstadoInterface(self.caminho, executor=self.despachar)
        try:
            self.aguardar(lambda: nova.mensagem.startswith('Aguardando a execução anterior'))
            self.assertFalse(nova.pronto.is_set())
            self.estado.encerrar()
            self.assertTrue(nova.pronto.wait(3))
            self.assertEqual(nova.fase, 'PRONTO')
            self.assertFalse(nova.bloqueado)
            self.assertEqual(self.chamadas, [])
        finally:
            nova.encerrar()
            nova.worker.join(3)
            self.assertFalse(nova.worker.is_alive())

    def test_pode_encerrar_enquanto_aguarda_historico(self) -> None:
        nova = EstadoInterface(self.caminho, executor=self.despachar)
        try:
            self.aguardar(lambda: nova.mensagem.startswith('Aguardando a execução anterior'))
            nova.encerrar()
            self.assertTrue(nova.finalizado.wait(3))
            self.assertEqual(nova.fase, 'ENCERRADO')
            self.assertEqual(self.estado.fase, 'PRONTO')
            self.assertEqual(self.chamadas, [])
        finally:
            nova.encerrar()
            nova.worker.join(3)

    def test_historico_ainda_ocupado_tem_mensagem_especifica(self) -> None:
        with patch('src.controlador.TEMPO_LIBERAR_HISTORICO', 0):
            nova = EstadoInterface(self.caminho, executor=self.despachar)
            try:
                self.assertTrue(nova.finalizado.wait(3))
                self.assertEqual(nova.fase, 'FALHA')
                self.assertIn('Outra execução ainda está aberta', nova.mensagem)
                self.assertNotIn('Não consegui salvar ou ler', nova.mensagem)
                self.assertTrue(nova.bloqueado)
                self.assertEqual(self.chamadas, [])
            finally:
                nova.encerrar()
                nova.worker.join(3)

    def test_lista_e_salva_antes_da_resposta_e_conexao_pertence_ao_executor(self) -> None:
        def executar(pedidos, modo, *, historico, **kwargs):
            self.assertNotEqual(get_ident(), principal)
            self.assertEqual(historico.pendentes(), ['2026-12345', '2026-67890'])
            self.liberar.wait(3)
            return ResumoExecucao()
        principal = get_ident()
        self.executor = executar
        self.iniciar()
        conn = sqlite3.connect(self.caminho)
        try:
            self.assertEqual(conn.execute('SELECT count(*) FROM pedidos').fetchone()[0], 2)
        finally:
            conn.close()
        self.assertEqual(len(self.estado.situacao()['pedidos']), 2)
        self.liberar.set()
        self.aguardar(lambda: self.estado.fase == 'CONCLUIDO')

    def test_lista_invalida_nao_perde_parte_nem_inicia_executor(self) -> None:
        with self.assertRaises(ValueError):
            self.iniciar(pedidos='12345, errado, 67890')
        self.assertEqual(self.chamadas, [])
        self.assertEqual(self.estado.situacao()['pendentes'], 0)

    def test_reimpressao_exige_confirmacao_e_nao_cria_fila_de_importacao(self) -> None:
        with self.assertRaises(ValueError):
            self.iniciar(modo='reimprimir')
        self.iniciar(modo='reimprimir', confirmado=True)
        self.assertTrue(self.executado.wait(2))
        self.assertEqual(self.chamadas[0][0][1], 'reimprimir')
        self.assertEqual(self.estado.situacao()['pendentes'], 0)

    def test_clique_repetido_nao_repete_operacao_mesmo_apos_concluir(self) -> None:
        self.iniciar()
        self.aguardar(lambda: self.estado.fase == 'CONCLUIDO')
        with self.assertRaises(ConflitoInterface):
            self.iniciar()
        self.assertEqual(len(self.chamadas), 1)

    def test_outra_aba_nao_inicia_segundo_lote(self) -> None:
        def executar(*args, **kwargs):
            self.liberar.wait(3)
            return ResumoExecucao()
        self.executor = executar
        self.iniciar()
        with self.assertRaises(ConflitoInterface):
            self.iniciar(solicitacao='outra-aba')

    def test_erro_aguarda_decisao_e_recusa_opcao_insegura_e_aviso_antigo(self) -> None:
        def executar(pedidos, modo, *, ao_erro, **kwargs):
            self.assertEqual(ao_erro(pedidos[0], RuntimeError('detalhe_sigilo'), False, False), 'encerrar')
            return ResumoExecucao()
        self.executor = executar
        self.iniciar()
        self.aguardar(lambda: self.estado.fase == 'PAUSADO')
        aviso = self.estado.situacao()['erro']
        self.assertNotIn('detalhe_sigilo', aviso['mensagem'])
        dados = {'execucao': self.estado.execucao, 'erro': aviso['id'], 'decisao': 'repetir'}
        with self.assertRaises(ValueError):
            self.estado.decidir(dados)
        dados['decisao'] = 'encerrar'
        dados['erro'] = 'aviso-antigo'
        with self.assertRaises(ConflitoInterface):
            self.estado.decidir(dados)
        dados['erro'] = aviso['id']
        self.estado.decidir(dados)
        self.aguardar(lambda: self.estado.fase == 'INTERROMPIDO')

    def test_sessao_expirada_nao_repete_ate_usuario_reconectar(self) -> None:
        def executar(pedidos, modo, *, ao_erro, **kwargs):
            self.assertEqual(ao_erro(pedidos[0], SessaoPortalExpiradaError(), True, False), 'repetir')
            return ResumoExecucao()
        self.executor = executar
        self.iniciar()
        self.aguardar(lambda: self.estado.fase == 'PAUSADO')
        aviso = self.estado.situacao()['erro']
        self.assertTrue(aviso['reconectar'])
        self.estado.decidir({'execucao': self.estado.execucao, 'erro': aviso['id'], 'decisao': 'repetir'})
        self.aguardar(lambda: self.estado.fase == 'CONCLUIDO')

    def test_falha_de_conexao_inicial_aguarda_sem_perder_lista(self) -> None:
        tentativas = []
        def executar(*args, **kwargs):
            tentativas.append(1)
            if len(tentativas) == 1:
                raise BancoSisplanError('Rede')
            return ResumoExecucao()
        self.executor = executar
        self.iniciar()
        self.aguardar(lambda: self.estado.fase == 'PAUSADO')
        self.assertEqual(len(tentativas), 1)
        aviso = self.estado.situacao()['erro']
        self.estado.decidir({'execucao': self.estado.execucao, 'erro': aviso['id'], 'decisao': 'repetir'})
        self.aguardar(lambda: self.estado.fase == 'CONCLUIDO')
        self.assertEqual(len(tentativas), 2)

    def test_encerrar_nao_abandona_acao_e_preserva_checkpoint(self) -> None:
        def executar(pedidos, modo, *, historico, parar, **kwargs):
            historico.salvar(EstadoPedido(pedidos[0], '100', 'gravacao_pendente'))
            self.executado.set()
            self.liberar.wait(3)
            self.assertTrue(parar())
            return ResumoExecucao()
        self.executor = executar
        self.iniciar()
        self.assertTrue(self.executado.wait(2))
        self.estado.encerrar()
        self.assertFalse(self.estado.finalizado.is_set())
        self.liberar.set()
        self.assertTrue(self.estado.finalizado.wait(3))
        with EstadoPedidos(self.caminho) as historico:
            self.assertEqual(historico.obter('2026-12345').etapa, 'gravacao_pendente')
            self.assertEqual(len(historico.pendentes()), 2)

    def test_trava_impede_console_simultaneo(self) -> None:
        with self.assertRaises(EstadoError):
            with EstadoPedidos(self.caminho):
                self.fail('Não deveria conseguir abrir outra execução')


class ApiTests(BaseInterface):
    def setUp(self) -> None:
        super().setUp()
        self.servidor, self.token = criar_servidor(self.estado)
        self.http = Thread(target=self.servidor.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
        self.http.start()
        self.addCleanup(self.fechar_http)

    def fechar_http(self) -> None:
        self.servidor.shutdown()
        self.servidor.server_close()
        self.http.join(3)

    def requisitar(self, caminho, dados=None, *, token=True, origem=None, host=None, corpo=None,
                   pagina='pagina-teste'):
        conn = HTTPConnection('127.0.0.1', self.servidor.server_port, timeout=4)
        headers = {'Host': host or f'127.0.0.1:{self.servidor.server_port}'}
        headers['X-Havan-Pagina'] = pagina
        if token:
            headers['Authorization'] = 'Bearer ' + self.token
        if dados is not None or corpo is not None:
            headers['Content-Type'] = 'application/json'
            headers['Origin'] = origem or f'http://127.0.0.1:{self.servidor.server_port}'
        try:
            conn.request('POST' if dados is not None or corpo is not None else 'GET', caminho,
                         body=corpo if corpo is not None else json.dumps(dados) if dados is not None else None,
                         headers=headers)
            r = conn.getresponse()
            return r.status, dict(r.getheaders()), r.read()
        finally:
            conn.close()

    def test_api_exige_token_host_e_origem(self) -> None:
        self.assertEqual(self.requisitar('/api/estado', token=False)[0], 403)
        self.assertEqual(self.requisitar('/api/estado', host='outro.example')[0], 403)
        dados = {'modo':'normal','pedidos':'12345','solicitacao':'api-1'}
        self.assertEqual(self.requisitar('/api/iniciar', dados, origem='https://outro.example')[0], 403)
        self.assertEqual(self.requisitar('/api/iniciar', dados)[0], 200)
        self.assertTrue(self.executado.wait(2))

    def test_recursos_e_assinatura_sao_locais_e_nao_expoe_arquivos_livres(self) -> None:
        status, headers, html = self.requisitar('/', token=False)
        self.assertEqual(status, 200)
        self.assertIn(self.token.encode(), html)
        self.assertIn(b'Gabriel2Mello', html)
        self.assertIn(b'assinatura-ll', html)
        self.assertIn("script-src 'self'", headers['Content-Security-Policy'])
        for caminho in ('/pedidos.js', '/pedidos.css', '/icons/icone.svg', '/favicon.ico', '/icons/icone-192.png'):
            self.assertEqual(self.requisitar(caminho, token=False)[0], 200)
        self.assertEqual(self.requisitar('/../config.toml')[0], 404)
        self.assertEqual(self.requisitar('/icons/../../config.toml')[0], 404)

    def test_json_malformado_tipo_invalido_e_corpo_grande_nao_iniciam_fluxo(self) -> None:
        for corpo in ('{quebrado', '[]', '"texto"', 'x'*16385):
            self.assertEqual(self.requisitar('/api/iniciar', corpo=corpo)[0], 400)
        self.assertEqual(self.chamadas, [])

    def test_log_tem_acesso_protegido_e_nome_fixo(self) -> None:
        self.assertEqual(self.requisitar('/api/log', token=False)[0], 403)
        status, headers, corpo = self.requisitar('/api/log')
        self.assertEqual(status, 200)
        self.assertEqual(corpo, self.log.read_bytes())
        self.assertIn('auto-pedidos.log', headers['Content-Disposition'])

    def test_presenca_da_pagina_impede_encerramento_e_tolerancia_preserva_reload(self) -> None:
        with self.estado.trava:
            self.servidor.teve_pagina = True
            self.servidor.sem_paginas_desde = 100
        with patch('src.interface_web.monotonic', return_value=104):
            self.servidor.service_actions()
        self.assertFalse(self.estado.encerrando)
        with self.estado.trava:
            self.servidor.paginas['pagina-teste'] = Event()
        with patch('src.interface_web.monotonic', return_value=110):
            self.servidor.service_actions()
        self.assertFalse(self.estado.encerrando)
        with self.estado.trava:
            self.servidor.paginas.clear()
        with patch('src.interface_web.monotonic', return_value=110):
            self.servidor.service_actions()
        self.assertTrue(self.estado.encerrando)

    def abrir_presenca(self, pagina):
        conn = HTTPConnection('127.0.0.1', self.servidor.server_port, timeout=3)
        self.addCleanup(conn.close)
        conn.request('GET', '/api/presenca', headers={
            'Authorization': 'Bearer ' + self.token, 'X-Havan-Pagina': pagina,
        })
        resposta = conn.getresponse()
        self.assertEqual(resposta.status, 200)
        self.assertEqual(resposta.readline(), b': ativo\n')
        return conn

    def test_fechar_ultima_pagina_encerra_sem_botao_e_libera_historico(self) -> None:
        self.abrir_presenca('principal')
        self.assertEqual(self.requisitar('/api/fechar', {}, pagina='principal')[0], 200)
        self.assertTrue(self.estado.finalizado.wait(3))
        self.assertEqual(self.estado.fase, 'ENCERRADO')
        self.assertEqual(self.chamadas, [])
        with EstadoPedidos(self.caminho) as historico:
            self.assertEqual(historico.pendentes(), [])

    def test_fechar_uma_pagina_preserva_outra_e_ignora_fechamento_repetido(self) -> None:
        self.abrir_presenca('principal')
        self.abrir_presenca('segunda')
        for _ in range(2):
            self.assertEqual(self.requisitar('/api/fechar', {}, pagina='principal')[0], 200)
        with self.estado.trava, patch('src.interface_web.monotonic', return_value=monotonic()+10):
            self.servidor.service_actions()
            self.assertEqual(set(self.servidor.paginas), {'segunda'})
        self.assertFalse(self.estado.encerrando)

    def test_recarregar_reconecta_antes_de_encerrar(self) -> None:
        self.abrir_presenca('antes')
        self.assertEqual(self.requisitar('/api/fechar', {}, pagina='antes')[0], 200)
        self.abrir_presenca('depois')
        with self.estado.trava, patch('src.interface_web.monotonic', return_value=monotonic()+10):
            self.servidor.service_actions()
        self.assertFalse(self.estado.encerrando)
        self.assertEqual(self.estado.fase, 'PRONTO')

    def test_aviso_de_fechamento_chega_apos_desconexao_e_ainda_encerra(self) -> None:
        self.abrir_presenca('principal')
        self.servidor.fechar_pagina('principal')
        self.assertFalse(self.servidor.fechamento_solicitado)
        self.assertEqual(self.requisitar('/api/fechar', {}, pagina='principal')[0], 200)
        self.assertTrue(self.servidor.fechamento_solicitado)
        self.assertTrue(self.estado.finalizado.wait(3))

    def test_reconectar_presenca_substituida_nao_remove_a_nova(self) -> None:
        self.abrir_presenca('principal')
        anterior = self.servidor.paginas['principal']
        self.abrir_presenca('principal')
        self.assertTrue(anterior.is_set())
        self.assertFalse(self.servidor.paginas['principal'].is_set())
        self.assertFalse(self.estado.encerrando)

    def test_fechar_pagina_nao_abandona_etapa_e_preserva_pendencias(self) -> None:
        def executar(pedidos, modo, *, historico, parar, **kwargs):
            historico.salvar(EstadoPedido(pedidos[0], '100', 'gravacao_pendente'))
            self.executado.set()
            self.liberar.wait(3)
            self.assertTrue(parar())
            return ResumoExecucao()
        self.executor = executar
        self.abrir_presenca('principal')
        self.iniciar()
        self.assertTrue(self.executado.wait(2))
        self.assertEqual(self.requisitar('/api/fechar', {}, pagina='principal')[0], 200)
        self.aguardar(lambda: self.estado.encerrando)
        self.assertFalse(self.estado.finalizado.is_set())
        self.liberar.set()
        self.assertTrue(self.estado.finalizado.wait(3))
        with EstadoPedidos(self.caminho) as historico:
            self.assertEqual(historico.obter('2026-12345').etapa, 'gravacao_pendente')
