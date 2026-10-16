"""Painel local: HTTP recebe ações; um executor possui o histórico e o Sisplan."""

from __future__ import annotations

import logging
from collections import Counter, deque
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from queue import Queue
from threading import Event, RLock, Thread, get_ident
from time import monotonic
from typing import Callable, Protocol
from uuid import uuid4

from src.erros import BancoSisplanError, ConfiguracaoError, EstadoEmUsoError
from src.config import diretorio_aplicacao
from src.estado import EstadoError, EstadoPedidos
from src.logs import get_logger
from src.seguranca import redigir
from src.contratos import AoErro, AoProgresso, DecisaoErro, Modo, ModoWeb
from src.mensagens import mensagem_erro
from src.pedidos import analisar_entrada_pedidos
from src.resumo import ResumoExecucao
from src.etapas import ETAPAS_FINAIS, ROTULOS, fila_da_etapa
from src.erros import (SessaoPortalExpiradaError)

logger = get_logger(__name__)
TEMPO_LIBERAR_HISTORICO = 10


class Executor(Protocol):
    def __call__(self, pedidos: list[str], modo: Modo, *, historico: EstadoPedidos,
                 ao_erro: AoErro, ao_progresso: AoProgresso,
                 parar: Callable[[], bool]) -> ResumoExecucao: ...


def executar_fluxo(pedidos: list[str], modo: Modo, *, historico: EstadoPedidos,
                   ao_erro: AoErro, ao_progresso: AoProgresso,
                   parar: Callable[[], bool]) -> ResumoExecucao:
    # O fluxo de automação é chamado na thread que possui o histórico.
    from src.servico_pedidos import processar_pedidos
    return processar_pedidos(pedidos, modo, historico=historico, ao_erro=ao_erro,
                             ao_progresso=ao_progresso, parar=parar)


class ConflitoInterface(ValueError):
    pass


@dataclass
class Trabalho:
    modo: ModoWeb
    pedidos: list[str]
    recebido: Event = field(default_factory=Event)
    erro: Exception | None = None


class MensagensInterface(logging.Handler):
    def __init__(self, estado: EstadoInterface) -> None:
        super().__init__(logging.INFO)
        self.estado = estado

    def emit(self, record: logging.LogRecord) -> None:
        if (record.thread == self.estado.worker.ident and record.levelno == logging.INFO
                and (record.name.startswith('src.'))):
            self.estado.registrar_mensagem(record.getMessage()[:1000])


class EstadoInterface:
    def __init__(self, caminho: Path | None = None, *, executor: Executor = executar_fluxo,
                 codigo_execucao: str = '', arquivo_log: Path | None = None) -> None:
        self.caminho = caminho
        self.executor = executor
        self.codigo_execucao = codigo_execucao
        self.arquivo_log = arquivo_log or diretorio_aplicacao() / 'auto-pedidos.log'
        self.trava = RLock()
        self.comandos: Queue[Trabalho | None] = Queue()
        self.pronto, self.finalizado, self.parada, self.resposta = Event(), Event(), Event(), Event()
        self.fase = 'INICIANDO'
        self.mensagem = 'Carregando os pedidos salvos…'
        self.execucao = ''
        self.pedido = ''
        self.indice = self.total = 0
        self.filas: dict[str, int] = dict.fromkeys(('para_baixar', 'baixados', 'importados', 'enviados'), 0)
        self.pedidos: list[dict[str, object]] = []
        self.resumo: dict[str, int] = {}
        self.erro: dict[str, object] | None = None
        self.decisao: DecisaoErro | None = None
        self.encerrando = self.bloqueado = False
        self.solicitacoes: deque[str] = deque(maxlen=100)
        self.mensagens: deque[str] = deque(maxlen=30)
        self._historico: EstadoPedidos | None = None
        self.worker = Thread(target=self._executar, name='havan-executor', daemon=False)
        self.worker.start()

    @property
    def ocupada(self) -> bool:
        return self.fase in ('INICIANDO', 'EXECUTANDO', 'PAUSADO', 'PARANDO', 'ENCERRANDO')

    def registrar_mensagem(self, mensagem: str) -> None:
        with self.trava:
            self.mensagens.append(redigir(mensagem))

    def situacao(self) -> dict[str, object]:
        with self.trava:
            return deepcopy({
                'fase': self.fase, 'mensagem': self.mensagem, 'ocupada': self.ocupada,
                'encerrando': self.encerrando, 'bloqueado': self.bloqueado,
                'execucao': self.execucao, 'pedido': self.pedido, 'indice': self.indice,
                'total': self.total, 'filas': self.filas, 'pedidos': self.pedidos,
                'pendentes': sum(p['etapa'] not in ETAPAS_FINAIS for p in self.pedidos),
                'erro': self.erro, 'resumo': self.resumo, 'mensagens': list(self.mensagens),
                'codigo_execucao': self.codigo_execucao,
            })

    def _atualizar(self) -> None:
        assert get_ident() == self.worker.ident
        assert self._historico is not None
        filas = self._historico.filas()
        pedidos: list[dict[str, object]] = [{'pedido': p.pedido, 'numero': p.numero, 'etapa': p.etapa, 'fila': fila_da_etapa(p.etapa),
                    'rotulo': ROTULOS[p.etapa], 'pendente': p.etapa not in ETAPAS_FINAIS,
                    'erro': redigir(p.erro)[:1000]}
                   for p in self._historico.listar()]
        with self.trava:
            self.filas, self.pedidos = filas, pedidos

    def iniciar(self, dados: dict[str, object]) -> None:
        modo = dados.get('modo')
        entrada, solicitacao = dados.get('pedidos', ''), dados.get('solicitacao', '')
        if modo not in ('normal', 'retomar', 'reimprimir'):
            raise ValueError('Escolha Inserir, Retomar ou Reimprimir.')
        if not isinstance(entrada, str) or not isinstance(solicitacao, str) or not 1 <= len(solicitacao) <= 100:
            raise ValueError('Solicitação inválida. Atualize a página e tente novamente.')
        pedidos = analisar_entrada_pedidos(entrada, permitir_vazio=modo == 'retomar')
        if modo == 'reimprimir' and dados.get('confirmado') is not True:
            raise ValueError('Confirme o envio de outra cópia antes de reimprimir.')
        trabalho = Trabalho(modo, pedidos)
        with self.trava:
            if self.ocupada or self.encerrando or self.bloqueado or self.finalizado.is_set():
                raise ConflitoInterface('Já existe uma operação em andamento ou o programa precisa ser reaberto.')
            if solicitacao in self.solicitacoes:
                raise ConflitoInterface('Esta solicitação já foi recebida. Confira o andamento na tela.')
            self.solicitacoes.append(solicitacao)
            self.execucao = uuid4().hex
            self.parada.clear()
            self.erro = None
            self.resumo = {}
            self.pedido, self.indice, self.total = '', 0, len(pedidos)
            self.fase = 'EXECUTANDO'
            self.mensagem = 'Preservando a lista de pedidos…'
            self.comandos.put(trabalho)
        # A resposta HTTP só confirma a entrada depois da persistência pelo executor.
        if not trabalho.recebido.wait(5):
            raise ConflitoInterface('Solicitação recebida. Aguarde o andamento antes de enviá-la novamente.')
        if trabalho.erro is not None:
            raise ValueError(mensagem_erro(trabalho.erro))

    def progresso(self, pedido: str, indice: int, total: int) -> None:
        self._atualizar()
        with self.trava:
            self.pedido, self.indice, self.total = pedido, indice, total
            self.mensagem = f'Processando pedido {indice} de {total}: {pedido}.'

    def aguardar_decisao(self, pedido: str, erro: Exception, repetir: bool, pular: bool) -> DecisaoErro:
        self._atualizar()
        with self.trava:
            if self.parada.is_set() or self.encerrando:
                return 'encerrar'
            self.resposta.clear()
            self.decisao = None
            self.erro = {'id': uuid4().hex, 'pedido': pedido, 'mensagem': mensagem_erro(erro),
                         'repetir': repetir, 'pular': pular,
                         'configuracao': isinstance(erro, ConfiguracaoError),
                         'reconectar': isinstance(erro, SessaoPortalExpiradaError)}
            self.fase = 'PAUSADO'
            self.mensagem = 'O processamento parou e aguarda sua escolha.'
        self.resposta.wait()  # Nenhuma trava é mantida enquanto o usuário decide.
        with self.trava:
            decisao = self.decisao or 'encerrar'
            self.erro = None
            if not self.encerrando:
                self.fase = 'PARANDO' if decisao == 'encerrar' else 'EXECUTANDO'
            return decisao

    def decidir(self, dados: dict[str, object]) -> None:
        with self.trava:
            if (self.fase != 'PAUSADO' or self.erro is None or self.decisao is not None
                    or dados.get('execucao') != self.execucao or dados.get('erro') != self.erro['id']):
                raise ConflitoInterface('Esse aviso já foi resolvido. Confira a situação atual.')
            decisao = dados.get('decisao')
            if (decisao not in ('repetir', 'pular', 'encerrar')
                    or decisao == 'repetir' and not self.erro['repetir']
                    or decisao == 'pular' and not self.erro['pular']):
                raise ValueError('Essa opção não é segura para a etapa atual.')
            self.decisao = decisao
            if decisao == 'encerrar':
                self.parada.set()
            self.resposta.set()

    def parar(self, execucao: object) -> None:
        with self.trava:
            if execucao != self.execucao or not self.ocupada:
                raise ConflitoInterface('Não há esse processamento em andamento.')
            self.parada.set()
            self.decisao = 'encerrar'
            self.resposta.set()
            self.fase = 'PARANDO'
            self.mensagem = 'Parando no próximo ponto seguro. Aguarde a confirmação da etapa atual.'

    def encerrar(self) -> None:
        with self.trava:
            if self.encerrando:
                return
            self.encerrando = True
            if self.finalizado.is_set():
                self.fase = 'ENCERRADO'
                self.mensagem = 'Aplicação encerrada. Você pode fechar esta aba.'
                return
            self.parada.set()
            self.decisao = 'encerrar'
            self.resposta.set()
            self.fase = 'ENCERRANDO'
            self.mensagem = 'Finalizando com segurança e preservando os pedidos…'
            self.comandos.put(None)

    def _falha(self, erro: Exception) -> None:
        logger.exception('Interface Havan: falha na operação %s, pedido %s.', self.execucao, self.pedido)
        with self.trava:
            self.fase = 'FALHA'
            self.mensagem = mensagem_erro(erro)
            self.bloqueado = isinstance(erro, EstadoError)

    def _processar(self, trabalho: Trabalho) -> None:
        assert self._historico is not None
        try:
            if trabalho.modo == 'normal':
                self._historico.adicionar_pedidos(trabalho.pedidos)
            if trabalho.modo == 'retomar':
                trabalho.pedidos = self._historico.pendentes()
            self._atualizar()
            with self.trava:
                self.total = len(trabalho.pedidos)
            trabalho.recebido.set()
            logger.info('Interface: operação=%s modo=%s pedidos=%s', self.execucao, trabalho.modo, trabalho.pedidos)
            while not self.parada.is_set():
                try:
                    resumo = self.executor(trabalho.pedidos, trabalho.modo, historico=self._historico,
                                           ao_erro=self.aguardar_decisao, ao_progresso=self.progresso,
                                           parar=self.parada.is_set)
                    self._atualizar()
                    with self.trava:
                        self.resumo = dict(Counter(resumo.situacoes.values()))
                        self.resumo['importacoes_confirmadas'] = len(resumo.importados)
                        if not self.encerrando:
                            self.fase = 'INTERROMPIDO' if self.parada.is_set() else 'CONCLUIDO'
                            self.mensagem = ('Processamento parado. As pendências foram preservadas.' if self.parada.is_set()
                                             else 'Processamento finalizado. Confira o resultado de cada pedido.')
                    break
                except EstadoError:
                    raise
                except Exception as erro:
                    logger.exception('Falha antes de iniciar o fluxo da operação %s.', self.execucao)
                    decisao = self.aguardar_decisao('início do processamento', erro,
                                                  isinstance(erro, BancoSisplanError), False)
                    if decisao != 'repetir':
                        break
        except Exception as erro:
            trabalho.erro = erro
            self._falha(erro)
        finally:
            trabalho.recebido.set()
            with self.trava:
                if self.fase == 'PARANDO':
                    self.fase = 'INTERROMPIDO'
                    self.mensagem = 'Processamento parado. As pendências foram preservadas.'

    def _executar(self) -> None:
        handler = MensagensInterface(self)
        try:
            limite = monotonic() + TEMPO_LIBERAR_HISTORICO
            while not self.parada.is_set():
                try:
                    with EstadoPedidos(self.caminho) as historico:
                        self._historico = historico
                        self._atualizar()
                        with self.trava:
                            if self.encerrando:
                                break
                            self.fase = 'PRONTO'
                            self.mensagem = 'Tudo pronto. Insira pedidos ou retome as pendências.'
                        logging.getLogger().addHandler(handler)
                        self.pronto.set()
                        while (trabalho := self.comandos.get()) is not None:
                            self._processar(trabalho)
                    break
                except EstadoEmUsoError:
                    if monotonic() >= limite:
                        raise
                    with self.trava:
                        if not self.encerrando:
                            self.mensagem = 'Aguardando a execução anterior liberar o histórico…'
                    if self.parada.wait(.1):
                        break
        except Exception as erro:
            self._falha(erro)
        finally:
            logging.getLogger().removeHandler(handler)
            handler.close()
            self._historico = None
            with self.trava:
                if self.encerrando:
                    self.fase = 'ENCERRADO'
                    self.mensagem = 'Aplicação encerrada. Você pode fechar esta aba.'
            self.pronto.set()
            self.finalizado.set()
