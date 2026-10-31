import io
import json
from email.message import Message
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import unittest
from unittest.mock import Mock, patch
import desktop_havan as desktop
import desktop_preferencias
from tests.test_interface_web import BaseInterface
from src.resumo import ResumoExecucao
from src.interface_web import criar_servidor

class TestAtivacao(unittest.TestCase):
    def pedido(self, **extras):
        cabecalhos = Message()
        for nome, valor in {'Host': '127.0.0.1:123', 'X-Nunes-Instancia': 'segredo',
                            'Content-Length': '2', 'Content-Type': 'application/json', **extras}.items():
            cabecalhos[nome] = valor
        registro = dict(protocolo=1, id='pedidos-havan', instancia='sintetica', pid=123, token='segredo')
        handler = Mock(command='POST', headers=cabecalhos, rfile=io.BytesIO(b'{}'))
        handler.host_valido.return_value = True
        handler.server = Mock(fechando=False, integracao_nunes=Mock(registro=registro))
        return handler

    def test_ativacao_usa_token_de_instancia_e_recusa_pagina_web(self):
        for extras in [{'Origin': 'http://127.0.0.1:123'}, {'X-Nunes-Instancia': 'errado'},
                       {'Transfer-Encoding': 'chunked'}, {'Content-Length': '3'}]:
            with self.subTest(extras=extras):
                handler = self.pedido(**extras)
                desktop.atender_ativacao(handler)
                self.assertIn(handler.json_resposta.call_args.args[0], (400, 403))
                handler.server.desktop.ativar.set.assert_not_called()
        handler = self.pedido()
        desktop.atender_ativacao(handler)
        self.assertEqual(handler.json_resposta.call_args.args[0], 200)
        handler.server.desktop.ativar.set.assert_called_once()

    def test_tema_persistido_e_validacao_nao_alteram_preferencias_invalidas(self):
        with TemporaryDirectory() as pasta, patch('desktop_preferencias.arquivo', return_value=Path(pasta) / 'tema.json'):
            self.assertEqual(desktop_preferencias.ler_tema(), 'escuro')
            desktop_preferencias.salvar_tema('claro')
            self.assertEqual(desktop_preferencias.ler_tema(), 'claro')
            with self.assertRaises(ValueError):
                desktop_preferencias.salvar_tema('../invalido')
            self.assertEqual(desktop_preferencias.ler_tema(), 'claro')



class TestCiclo(BaseInterface):
    def test_desktop_nao_encerra_por_perda_de_pagina(self):
        servidor, _ = criar_servidor(self.estado, modo_desktop=True)
        try:
            servidor.sem_paginas_desde = 0
            servidor.service_actions()
            self.assertFalse(self.estado.encerrando)
        finally:
            servidor.server_close()

    def test_janela_espera_worker_antes_de_sair(self):
        entrou = Event()
        def executar(*args, **kwargs):
            entrou.set()
            self.liberar.wait(3)
            return ResumoExecucao()
        self.executor = executar
        self.iniciar()
        self.assertTrue(entrou.wait(2))
        servidor, _ = criar_servidor(self.estado, modo_desktop=True)
        janela = desktop.Janela(servidor)
        def executar_janela():
            servidor.encerrar(confirmado=True)
            try:
                self.assertFalse(janela.pronto_para_fechar.wait(.2))
            finally:
                self.liberar.set()
            self.assertTrue(janela.pronto_para_fechar.wait(3))
            self.assertFalse(self.estado.worker.is_alive())
        janela.executar = executar_janela
        try:
            desktop.executar(servidor, fabrica=lambda _: janela)
        finally:
            servidor.server_close()

    def test_fechar_aguarda_preferencias_e_permite_cancelar(self):
        servidor = Mock(fechando=False)
        janela = desktop.Janela(servidor)
        nativa = Mock()
        nativa.create_confirmation_dialog.return_value = False
        self.assertFalse(janela.fechar(nativa))
        servidor.encerrar.assert_not_called()
        nativa.evaluate_js.side_effect = lambda script, callback: callback(False)
        janela.salvar_e_encerrar(nativa)
        servidor.encerrar.assert_not_called()
        nativa.evaluate_js.side_effect = lambda script, callback: callback(True)
        janela.salvar_e_encerrar(nativa)
        servidor.encerrar.assert_called_once_with(confirmado=True)

    def test_callback_ausente_libera_nova_tentativa_sem_encerrar_e_ignora_retorno_tardio(self):
        servidor = Mock(fechando=False)
        janela = desktop.Janela(servidor)
        nativa = Mock()
        callbacks = []
        nativa.evaluate_js.side_effect = lambda script, callback: callbacks.append(callback)
        janela.salvando = True
        thread = Thread(target=janela.salvar_e_encerrar, args=(nativa,), daemon=True)
        with patch('desktop_havan.TEMPO_CONFIRMAR_PREFERENCIAS', 0), \
             self.assertLogs(level='ERROR') as logs:
            try:
                thread.start()
                thread.join(2)
                self.assertFalse(thread.is_alive(), 'A espera pelo callback não terminou')
            finally:
                if thread.is_alive():
                    janela.fechada.set()
                    thread.join(2)
        self.assertIn('TimeoutError', '\n'.join(logs.output))
        self.assertFalse(janela.salvando)
        servidor.encerrar.assert_not_called()
        self.assertIn('tente encerrar novamente', nativa.set_title.call_args.args[0])
        callbacks[0](True)
        servidor.encerrar.assert_not_called()
        nativa.create_confirmation_dialog.return_value = False
        self.assertFalse(janela.fechar(nativa))
        nativa.create_confirmation_dialog.assert_called_once()
        nativa.evaluate_js.side_effect = lambda script, callback: callback(True)
        janela.salvar_e_encerrar(nativa)
        servidor.encerrar.assert_called_once_with(confirmado=True)

class TestApiDesktop(BaseInterface):
    def test_ativacao_http_e_tema_sao_autenticados(self):
        from http.client import HTTPConnection
        servidor, token = criar_servidor(self.estado, modo_desktop=True)
        servidor.desktop = Mock(ativar=Event())
        registro = dict(protocolo=1, id='pedidos-havan', instancia='teste', pid=123, token='token-instancia')
        servidor.integracao_nunes = Mock(registro=registro)
        thread = Thread(target=servidor.serve_forever, kwargs={'poll_interval': .02})
        thread.start()
        conn = HTTPConnection('127.0.0.1', servidor.server_port, timeout=3)
        try:
            headers = {'X-Nunes-Instancia': 'token-instancia', 'Content-Type': 'application/json'}
            conn.request('POST', '/desktop/ativar', body='{}', headers=headers | {'Origin': 'http://outro.example'})
            resposta = conn.getresponse()
            self.assertEqual(resposta.status, 403); resposta.read()
            self.assertFalse(servidor.desktop.ativar.is_set())
            conn.request('POST', '/desktop/ativar', body='{}', headers=headers)
            resposta = conn.getresponse()
            self.assertEqual(resposta.status, 200)
            self.assertEqual(json.loads(resposta.read())['id'], 'pedidos-havan')
            self.assertTrue(servidor.desktop.ativar.is_set())
            with TemporaryDirectory() as pasta, patch('desktop_preferencias.arquivo', return_value=Path(pasta)/'tema.json'):
                headers = {'Authorization': 'Bearer '+token, 'Content-Type': 'application/json',
                           'Origin': f'http://127.0.0.1:{servidor.server_port}'}
                conn.request('POST', '/api/tema', body=json.dumps({'tema':'claro'}), headers=headers)
                resposta = conn.getresponse()
                self.assertEqual(resposta.status, 200); resposta.read()
                self.assertEqual(desktop_preferencias.ler_tema(), 'claro')
                conn.request('GET', '/')
                resposta = conn.getresponse()
                self.assertIn(b'name="havan-desktop" content="1"', resposta.read())
            self.assertEqual(self.chamadas, [])
        finally:
            conn.close(); servidor.shutdown(); servidor.server_close(); thread.join(3)
