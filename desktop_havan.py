"""Janela Windows da Pedidos Havan; a página usa somente HTTP local autenticado."""
import json
import logging
import os
from pathlib import Path
import secrets
import sys
import time
from threading import Event, Thread
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

import desktop_windows
from integracao_hub import (ConflitoAplicacao, IntegracaoLocal, MedidorAbertura,
                            consultar_instancia, ler_registro, texto, trava_ocupada)
from desktop_preferencias import caminho_preferencia
RECURSOS = Path(__file__).resolve().parent

NOME = 'Pedidos Havan'
APP_ID = 'Nunes.PedidosHavan.Desktop.1'
TEMPO_CONFIRMAR_PREFERENCIAS = 10


class SemRedirecionamento(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def ativar_existente(caminho, espera=15):
    limite = time.monotonic() + espera
    while time.monotonic() < limite:
        if not trava_ocupada(caminho.with_suffix('.lock')):
            return False
        registro = ler_registro(caminho)
        saude = consultar_instancia(registro)
        if saude.get('respondendo') and not saude.get('encerrando'):
            if registro.get('id') != 'pedidos-havan':
                raise RuntimeError('O registro não pertence à Pedidos Havan.')
            desktop_windows.permitir_foco(registro['pid'])
            pedido = Request(texto(registro['url']) + '/desktop/ativar', data=b'{}', method='POST',
                             headers={'X-Nunes-Instancia': texto(registro['token']), 'Content-Type': 'application/json'})
            try:
                with build_opener(ProxyHandler({}), SemRedirecionamento()).open(pedido, timeout=3) as resposta:
                    dados = json.loads(resposta.read(4096))
            except HTTPError as erro:
                erro.close()
                raise RuntimeError('A instância existente não permite ativação desktop. Encerre-a normalmente e reabra.') from erro
            except OSError:
                time.sleep(.1)
                continue
            if (not isinstance(dados, dict) or dados.get('desktop') != 1
                    or any(dados.get(chave) != registro.get(chave) for chave in ('protocolo', 'id', 'instancia', 'pid'))):
                raise RuntimeError('Identidade da instância desktop inválida.')
            return True
        time.sleep(.1)
    raise RuntimeError('A Pedidos Havan está iniciando, encerrando ou sem resposta. Aguarde e tente novamente.')


def atender_ativacao(handler):
    servidor = handler.server
    integracao = getattr(servidor, 'integracao_nunes', None)
    handler.close_connection = True
    if (not handler.host_valido() or integracao is None
            or handler.headers.get_all('Origin') is not None
            or len(handler.headers.get_all('X-Nunes-Instancia') or []) != 1
            or not secrets.compare_digest(handler.headers.get('X-Nunes-Instancia', '').encode(),
                                          texto(integracao.registro['token']).encode())):
        handler.json_resposta(403, {'erro': 'Ativação não autorizada.'})
    elif handler.command != 'POST':
        handler.json_resposta(405, {'erro': 'Método não permitido.'})
    elif (handler.headers.get_all('Content-Length') != ['2']
            or handler.headers.get_all('Transfer-Encoding') is not None
            or handler.headers.get_all('Content-Type') != ['application/json']
            or handler.rfile.read(2) != b'{}'):
        handler.json_resposta(400, {'erro': 'Pedido de ativação inválido.'})
    elif servidor.fechando or servidor.desktop is None:
        handler.json_resposta(409, {'erro': 'Instância encerrando ou sem desktop.'})
    else:
        servidor.desktop.ativar.set()
        handler.json_resposta(200, {chave: integracao.registro[chave] for chave in
                              ('protocolo', 'id', 'instancia', 'pid')} | {'desktop': 1})


class Janela:
    def __init__(self, servidor):
        self.servidor = servidor
        self.nome = NOME + (' · Demonstração' if getattr(servidor, 'demonstracao', False) else '')
        self.app_id = APP_ID + ('.Demo' if getattr(servidor, 'demonstracao', False) else '')
        self.ativar = Event()
        self.fechada = Event()
        self.pronto_para_fechar = Event()
        self.liberar = False
        self.erro = None
        self.salvando = False
        self.janela = None

    def fechar(self, janela):
        if self.liberar:
            desktop_windows.salvar_geometria(janela.native, caminho_preferencia().parent)
            return True
        if self.servidor.fechando or self.salvando:
            return False
        if janela.create_confirmation_dialog(self.nome,
                'Encerrar a Pedidos Havan? A etapa em andamento será preservada antes da parada.'):
            self.solicitar_encerramento()
        return False

    def solicitar_encerramento(self):
        if self.servidor.fechando or self.salvando:
            return
        if self.janela is not None and self.janela.events.loaded.is_set():
            self.salvando = True
            Thread(target=self.salvar_e_encerrar, args=(self.janela,), name='havan-fechamento').start()
        else:
            self.servidor.encerrar(confirmado=True)

    def salvar_e_encerrar(self, janela):
        terminou, respostas = Event(), []

        def salvo(valor):
            respostas.append(valor)
            terminou.set()

        try:
            limite = time.monotonic() + TEMPO_CONFIRMAR_PREFERENCIAS
            janela.evaluate_js('salvamentoTema', callback=salvo)
            while not terminou.wait(.1):
                if self.fechada.is_set():
                    raise RuntimeError('A janela fechou antes de confirmar as preferências.')
                if time.monotonic() >= limite:
                    raise TimeoutError('O WebView não confirmou as preferências no prazo.')
            if respostas != [True]:
                janela.set_title(self.nome + ' · Confira a falha ao salvar o tema')
                return
            self.servidor.encerrar(confirmado=True)
        except Exception:
            logging.exception('Falha ao salvar preferências antes de encerrar')
            janela.set_title(self.nome + ' · Falha ao confirmar preferências; tente encerrar novamente')
        finally:
            self.salvando = False

    def executar(self):
        if os.name != 'nt':
            raise RuntimeError('O desktop da Pedidos Havan requer Windows.')
        from dpi_windows import preparar, validar_janela
        preparar('PedidosHavanDesktop')
        import webview
        desktop_windows.identidade_processo(self.app_id)
        webview.settings['ALLOW_DOWNLOADS'] = False
        webview.settings['ALLOW_FILE_URLS'] = False
        janela = webview.create_window(self.nome, f'http://127.0.0.1:{self.servidor.server_port}',
                                      width=1180, height=820, min_size=(760, 540), text_select=True)
        self.janela = janela

        def restaurar():
            dados = desktop_windows.ler_geometria(caminho_preferencia().parent)
            if dados:
                desktop_windows.restaurar_geometria(janela.native, dados)

        janela.events.before_show += restaurar
        janela.events.closing += lambda: self.fechar(janela)

        def fechou():
            self.fechada.set()
            self.servidor.encerrar(confirmado=True)

        janela.events.closed += fechou

        def acompanhar():
            try:
                limite = time.monotonic() + 30
                while not janela.events.shown.wait(.1):
                    if self.pronto_para_fechar.is_set():
                        self.liberar = True
                        janela.destroy()
                        return
                    if time.monotonic() >= limite:
                        raise RuntimeError('A janela não iniciou no prazo.')
                hwnd = janela.native.Handle.ToInt64()
                validar_janela(hwnd)
                desktop_windows.propriedades_janela(hwnd,
                    desktop_windows.comando_reabrir(['--demo'] if getattr(self.servidor, 'demonstracao', False) else [], Path(__file__).with_name('havan.py')),
                    RECURSOS / 'icons/icone.ico', app_id=self.app_id, nome=self.nome)
                avisou = False
                while not self.fechada.wait(.1):
                    if self.servidor.fechando and not avisou:
                        avisou = True
                        janela.set_title(self.nome + ' · Encerrando após a etapa atual…')
                    if not janela.events.loaded.is_set() and time.monotonic() >= limite:
                        raise RuntimeError('O WebView2 não carregou a interface no prazo.')
                    if self.pronto_para_fechar.is_set():
                        self.liberar = True
                        janela.destroy()
                        return
                    if self.ativar.is_set():
                        self.ativar.clear()
                        desktop_windows.focalizar(hwnd)
            except Exception as erro:
                self.erro = erro
                self.servidor.encerrar(confirmado=True)
                self.pronto_para_fechar.wait()
                self.liberar = True
                janela.destroy()

        webview.start(acompanhar, gui='edgechromium', debug=False, private_mode=True,
                      icon=str(RECURSOS / 'icons/icone.ico'))
        self.fechada.set()
        if self.erro:
            raise RuntimeError('Falha na janela desktop; confira o diagnóstico local.') from self.erro


def executar(servidor, fabrica=Janela):
    janela = fabrica(servidor)
    servidor.desktop = janela
    falhas = []

    def servir():
        try:
            servidor.serve_forever(poll_interval=.1)
        except Exception as erro:
            falhas.append(erro)
            servidor.estado.encerrar()
        finally:
            # A OP e a gravação do diário terminam antes de liberar a janela.
            if servidor.estado.worker is not None:
                servidor.estado.worker.join()
            janela.pronto_para_fechar.set()

    thread = Thread(target=servir, name='havan-http')
    thread.start()
    try:
        janela.executar()
    finally:
        servidor.encerrar(confirmado=True)
        thread.join()
        servidor.desktop = None
    if falhas:
        raise RuntimeError('Falha no servidor desktop da Pedidos Havan.') from falhas[0]


def iniciar():
    from havan import main, informar_falha
    if '--criar-atalho' in sys.argv:
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument('--criar-atalho', type=Path, required=True)
        destino = parser.parse_args().criar_atalho
        from dpi_windows import preparar
        preparar('PedidosHavanAtalho')
        desktop_windows.criar_atalho(destino.resolve(),
            desktop_windows.comando_reabrir([], Path(__file__).with_name('havan.py')),
            RECURSOS / 'icons/icone.ico', app_id=APP_ID, descricao=NOME)
        return 0
    medidor = MedidorAbertura('pedidos-havan')
    limite = time.monotonic() + 15
    while True:
        try:
            with IntegracaoLocal('pedidos-havan', NOME, True, sem_navegador=True) as publicacao:
                try:
                    return main(publicacao, desktop=True)
                except Exception as erro:
                    publicacao.registrar_falha(erro)
                    raise
        except ConflitoAplicacao as erro:
            try:
                if erro.registro.get('id') != 'pedidos-havan':
                    raise RuntimeError(str(erro))
                caminho = Path(os.environ.get('NUNES_HUB_DADOS') or medidor.pasta) / 'pedidos-havan.json'
                if ativar_existente(caminho, max(0, limite - time.monotonic())):
                    return 0
                if time.monotonic() >= limite:
                    raise RuntimeError('A instância anterior ainda está encerrando.')
            except Exception as falha:
                informar_falha(str(falha))
                return 2
        except Exception:
            logging.exception('Falha na abertura desktop da Pedidos Havan')
            informar_falha('Não foi possível abrir a Pedidos Havan. Confira WebView2, o ambiente desktop e o diagnóstico do Hub.')
            return 1
