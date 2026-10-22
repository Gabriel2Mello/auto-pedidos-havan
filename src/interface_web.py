"""Adaptador HTTP local. Estado e executor ficam em src.controlador."""

from __future__ import annotations

from integracao_hub import atender_integracao

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from secrets import compare_digest, token_urlsafe
from threading import Event, Thread
from time import monotonic
from typing import cast
from urllib.parse import urlsplit

from src.config import diretorio_aplicacao
from src.controlador import ConflitoInterface, EstadoInterface as EstadoInterface
from src.logs import get_logger
from src.seguranca import redigir

logger = get_logger(__name__)


class ServidorInterface(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, handler: type[BaseHTTPRequestHandler], estado: EstadoInterface) -> None:
        super().__init__(('127.0.0.1', 0), handler)
        self.estado = estado
        self.paginas: dict[str, Event] = {}
        self.teve_pagina = False
        self.fechamento_solicitado = False
        self.sem_paginas_desde = monotonic()
        self.parar_presenca = Event()
        self.fechando = False

    def service_actions(self) -> None:
        with self.estado.trava:
            limite = 1 if self.fechamento_solicitado else 5 if self.teve_pagina else 120
            if not self.paginas and monotonic() - self.sem_paginas_desde >= limite:
                self.estado.encerrar()
            if self.estado.finalizado.is_set() and self.estado.encerrando and not self.fechando:
                self.fechando = True
                Thread(target=self.shutdown, daemon=True).start()

    def fechar_pagina(self, pagina: str, *, solicitado: bool = False) -> None:
        with self.estado.trava:
            presenca = self.paginas.pop(pagina, None)
            if presenca is not None:
                presenca.set()
                if not self.paginas:
                    self.sem_paginas_desde = monotonic()
            if solicitado and not self.paginas:
                self.fechamento_solicitado = True
                self.sem_paginas_desde = monotonic()

    def shutdown(self) -> None:
        self.parar_presenca.set()
        super().shutdown()

    def server_close(self) -> None:
        self.parar_presenca.set()
        self.estado.encerrar()
        super().server_close()


def criar_servidor(estado: EstadoInterface) -> tuple[ServidorInterface, str]:
    token = token_urlsafe(32)
    raiz = diretorio_aplicacao()

    class Manipulador(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def host_valido(self) -> bool:
            return self.headers.get_all('Host') == [f'127.0.0.1:{servidor.server_port}']

        def autorizado(self) -> bool:
            origem = f'http://127.0.0.1:{servidor.server_port}'
            return (self.host_valido()
                    and compare_digest(self.headers.get('Authorization', ''), f'Bearer {token}')
                    and self.headers.get('Origin') in ((origem,) if self.command == 'POST' else (None, origem)))

        def responder(self, status: int, conteudo: bytes, tipo: str = 'application/json; charset=utf-8',
                      download: bool = False) -> None:
            self.send_response(status)
            self.send_header('Content-Type', tipo)
            self.send_header('Content-Length', str(len(conteudo)))
            self.send_header('Cache-Control', 'no-store')
            if self.close_connection:
                self.send_header('Connection', 'close')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'; form-action 'none'")
            if download:
                self.send_header('Content-Disposition', 'attachment; filename="auto-pedidos.log"')
            self.end_headers()
            self.wfile.write(conteudo)

        def json_resposta(self, status: int, dados: object) -> None:
            self.responder(status, json.dumps(dados, ensure_ascii=False, allow_nan=False).encode('utf-8'))

        def acompanhar(self) -> None:
            pagina = self.headers.get('X-Havan-Pagina', '')
            if not pagina or len(pagina) > 100 or not pagina.isascii():
                self.json_resposta(400, {'erro': 'Identificação da página inválida.'})
                return
            presenca = Event()
            with estado.trava:
                if estado.encerrando:
                    self.json_resposta(503, {'erro': 'O programa está encerrando.'})
                    return
                anterior = servidor.paginas.get(pagina)
                if anterior is not None:
                    anterior.set()
                servidor.paginas[pagina] = presenca
                servidor.teve_pagina = True
                servidor.fechamento_solicitado = False
            try:
                self.connection.settimeout(3)
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                while not servidor.parar_presenca.is_set() and not presenca.is_set():
                    self.wfile.write(b': ativo\n\n')
                    self.wfile.flush()
                    if presenca.wait(1):
                        break
            except (OSError, ValueError):
                pass
            finally:
                with estado.trava:
                    if servidor.paginas.get(pagina) is presenca:
                        servidor.fechar_pagina(pagina)

        def do_GET(self) -> None:
            if atender_integracao(self):
                return
            caminho = urlsplit(self.path).path
            publicos = {
                '/': ('src/pedidos.html', 'text/html; charset=utf-8'),
                '/pedidos.css': ('src/pedidos.css', 'text/css; charset=utf-8'),
                '/pedidos.js': ('src/pedidos.js', 'text/javascript; charset=utf-8'),
                '/nunes-tema.js': ('src/nunes-tema.js', 'text/javascript; charset=utf-8'),
                '/icons/icone.svg': ('icons/icone.svg', 'image/svg+xml'),
                '/favicon.ico': ('icons/icone.ico', 'image/x-icon'),
                '/icons/icone-192.png': ('icons/icone-192.png', 'image/png'),
                '/icons/icone-512.png': ('icons/icone-512.png', 'image/png'),
            }
            try:
                if caminho in publicos and self.host_valido():
                    arquivo, tipo = publicos[caminho]
                    conteudo = (raiz / arquivo).read_bytes()
                    if caminho == '/':
                        with estado.trava:
                            if not servidor.paginas:
                                servidor.sem_paginas_desde = monotonic()
                                servidor.fechamento_solicitado = False
                        conteudo = conteudo.replace(b'__TOKEN__', token.encode('ascii'))
                    self.responder(200, conteudo, tipo)
                elif not self.autorizado():
                    self.json_resposta(403, {'erro': 'Acesso não autorizado.'})
                elif caminho == '/api/estado':
                    self.json_resposta(200, estado.situacao())
                elif caminho == '/api/presenca':
                    self.acompanhar()
                elif caminho == '/api/log':
                    self.responder(200, redigir(estado.arquivo_log.read_bytes().decode('utf-8')).encode('utf-8'), 'text/plain; charset=utf-8', download=True)
                else:
                    self.json_resposta(404, {'erro': 'Recurso não encontrado.'})
            except OSError:
                logger.exception('Não foi possível servir um recurso da interface.')
                self.json_resposta(500, {'erro': 'Não consegui abrir esse recurso. Avise o responsável.'})

        def do_POST(self) -> None:
            if atender_integracao(self):
                return
            if not self.autorizado():
                self.close_connection = True
                self.json_resposta(403, {'erro': 'Acesso não autorizado.'})
                return
            try:
                tamanhos = self.headers.get_all('Content-Length', [])
                if (len(tamanhos) != 1 or not tamanhos[0].isascii() or not tamanhos[0].isdigit()
                        or int(tamanhos[0]) > 16384 or self.headers.get('Transfer-Encoding') is not None
                        or self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json'):
                    self.close_connection = True
                    raise ValueError('Solicitação inválida ou muito grande.')
                self.connection.settimeout(5)
                conteudo = self.rfile.read(int(tamanhos[0]))
                if len(conteudo) != int(tamanhos[0]):
                    raise ValueError('Corpo da solicitação incompleto.')
                objeto: object = json.loads(conteudo)
                if not isinstance(objeto, dict):
                    raise ValueError('Solicitação inválida.')
                dados = cast(dict[str, object], objeto)
                caminho = urlsplit(self.path).path
                if caminho == '/api/iniciar':
                    estado.iniciar(dados)
                elif caminho == '/api/decidir':
                    estado.decidir(dados)
                elif caminho == '/api/parar':
                    estado.parar(dados.get('execucao'))
                elif caminho == '/api/encerrar':
                    estado.encerrar()
                elif caminho == '/api/fechar':
                    servidor.fechar_pagina(self.headers.get('X-Havan-Pagina', ''), solicitado=True)
                else:
                    self.json_resposta(404, {'erro': 'Ação não encontrada.'})
                    return
                self.json_resposta(200, {'ok': True})
            except ConflitoInterface as erro:
                self.json_resposta(409, {'erro': str(erro)})
            except (ValueError, UnicodeError, OSError) as erro:
                self.close_connection = True
                self.json_resposta(400, {'erro': str(erro) if isinstance(erro, ValueError) else 'Não consegui ler a solicitação.'})
            except Exception:
                logger.exception('Falha ao atender uma ação da interface.')
                self.json_resposta(500, {'erro': 'Não foi possível concluir. Envie o log ao responsável.'})

    servidor = ServidorInterface(Manipulador, estado)
    return servidor, token
