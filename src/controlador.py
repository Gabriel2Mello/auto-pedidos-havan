"""Painel local: HTTP recebe ações; um executor possui o histórico e o Sisplan."""

from __future__ import annotations

import logging
from collections import Counter, deque
from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from queue import Queue
from threading import Event, RLock, Thread, get_ident
from time import monotonic
from typing import Callable, Protocol
from uuid import uuid4
from integracao_hub import MedidorAbertura

from src.erros import BancoSisplanError, ConfiguracaoError, EstadoEmUsoError
from src.config import CONFIG, Configuracao, configuracao_atual, diretorio_aplicacao, usar_configuracao
from src.impressoras import listar_impressoras_windows, salvar_impressora
from src.estado import EstadoError, EstadoPedidos
from src.logs import get_logger
from src.seguranca import redigir
from src.contratos import AoErro, AoProgresso, DecisaoErro, Modo, ModoWeb
from src.mensagens import mensagem_erro, mensagem_observacao
from src.pedidos import analisar_entrada_pedidos
from src.resumo import ResumoExecucao
from src.etapas import ETAPAS_FINAIS, ETAPAS_INICIAIS, ROTULOS, fila_da_etapa
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
    from src.servico_pedidos import ContextoExecucao, processar_pedidos
    return processar_pedidos(pedidos, modo, historico=historico, ao_erro=ao_erro,
                             ao_progresso=ao_progresso, parar=parar,
                             contexto=ContextoExecucao(configuracao_atual()))


class ConflitoInterface(ValueError):
    pass


@dataclass
class Trabalho:
    modo: ModoWeb
    pedidos: list[str]
    impressora: str = ''
    configuracao: Configuracao | None = None
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
                 codigo_execucao: str = '', arquivo_log: Path | None = None,
                 medidor_abertura: MedidorAbertura | None = None,
                 listar_filas: Callable[[], list[str]] | None = None,
                 salvar_fila: Callable[[str], None] | None = None,
                 impressora: str | None = None) -> None:
        self.medidor_abertura = medidor_abertura
        self.caminho = caminho
        self.executor = executor
        self.impressora = CONFIG.impressora if impressora is None else impressora
        self.listar_filas = listar_filas or listar_impressoras_windows
        self.salvar_fila = salvar_fila or salvar_impressora
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
        self.lote: list[str] = []
        self.lote_preparacao: list[str] = []
        self.modo: ModoWeb = 'preparar'
        self.resultados_lote: dict[str, str] = {}
        self.pendentes_ordenados: list[str] = []
        self.revisao = 0
        self.conferencias: deque[tuple[str, str, list[str], int]] = deque(maxlen=20)
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

    def listar_impressoras(self) -> dict[str, object]:
        try:
            nomes = self.listar_filas()
            aviso = (f'A impressora “{self.impressora}” não está instalada ou foi renomeada.'
                     if self.impressora and self.impressora not in nomes else
                     '' if nomes else 'Nenhuma impressora instalada foi encontrada. Instale uma impressora no Windows e atualize a lista.')
        except RuntimeError as erro:
            nomes, aviso = [], str(erro)
        with self.trava:
            return {'impressoras': nomes, 'impressora': self.impressora,
                    'aviso_impressora': aviso}

    def selecionar_impressora(self, nome: object) -> None:
        with self.trava:
            if self.ocupada or self.encerrando or self.finalizado.is_set():
                raise ConflitoInterface('Aguarde o término do lote para alterar a impressora.')
            try:
                nomes = self.listar_filas()
            except RuntimeError as erro:
                raise ValueError(str(erro)) from erro
            if not isinstance(nome, str) or nome not in nomes:
                raise ValueError('Selecione uma impressora instalada neste computador.')
            self.salvar_fila(nome)
            self.impressora = nome
            self.conferencias.clear()

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
                'lote': self.lote, 'lote_preparacao': self.lote_preparacao, 'modo': self.modo, 'resultados_lote': self.resultados_lote,
                'revisao': self.revisao, 'ano': datetime.now().year,
                'impressora': self.impressora,
            })

    def _atualizar(self) -> None:
        assert get_ident() == self.worker.ident
        assert self._historico is not None
        filas = self._historico.filas()
        pedidos: list[dict[str, object]] = [{'pedido': p.pedido, 'numero': p.numero, 'etapa': p.etapa, 'fila': fila_da_etapa(p.etapa),
                    'rotulo': ROTULOS[p.etapa], 'pendente': p.etapa not in ETAPAS_FINAIS,
                    'erro': redigir(mensagem_observacao(p.erro, p.pedido))[:1000]}
                   for p in self._historico.listar()]
        with self.trava:
            if pedidos != self.pedidos:
                self.revisao += 1
            self.pendentes_ordenados = self._historico.pendentes()
            self.filas, self.pedidos = filas, pedidos

    def _pendentes_preparacao(self) -> list[str]:
        iniciais = {str(p['pedido']) for p in self.pedidos if p['etapa'] in ETAPAS_INICIAIS}
        return [p for p in self.pendentes_ordenados if p in iniciais]

    def _validar_selecao(self, modo: str, pedidos: list[str]) -> None:
        historico = {str(p['pedido']): p for p in self.pedidos}
        if modo == 'importar':
            if any(p['etapa'] in ('importacao_iniciada', 'gravacao_pendente', 'aviso_pendente') for p in self.pedidos):
                raise ConflitoInterface('Confira a inclusão anterior incerta antes de importar outros pedidos.')
            if any(p not in historico or historico[p]['etapa'] != 'pronto_importar' or historico[p]['erro'] for p in pedidos):
                raise ConflitoInterface('Somente pedidos prontos e sem pendências podem ser importados. Confira novamente.')
        elif modo == 'revalidar':
            if any(p not in historico or historico[p]['etapa'] not in ETAPAS_INICIAIS for p in pedidos):
                raise ConflitoInterface('Selecione pedidos ainda não importados para conferir os cadastros.')
        elif modo == 'recuperar':
            if any(p not in historico or historico[p]['etapa'] in (*ETAPAS_INICIAIS, *ETAPAS_FINAIS) for p in pedidos):
                raise ConflitoInterface('Selecione apenas inclusões incertas ou impressões pendentes para recuperar.')

    def conferir(self, dados: dict[str, object]) -> dict[str, object]:
        """Revisa somente entrada e snapshot local, sem consultar integrações."""
        modo, entrada = dados.get('modo'), dados.get('pedidos', '')
        if modo not in ('normal', 'retomar', 'preparar', 'revalidar', 'importar', 'recuperar') or not isinstance(entrada, str):
            raise ValueError('Informe o modo e a lista de pedidos.')
        pedidos = analisar_entrada_pedidos(entrada, permitir_vazio=modo == 'retomar')
        with self.trava:
            if self.ocupada or self.bloqueado or self.encerrando or self.finalizado.is_set():
                raise ConflitoInterface('Aguarde a liberação do processamento para conferir o lote.')
            if modo == 'retomar':
                pedidos = self._pendentes_preparacao()
            if not pedidos:
                raise ValueError('Não há pedidos pendentes para retomar.')
            self._validar_selecao(str(modo), pedidos)
            identificador = uuid4().hex
            self.conferencias.append((identificador, str(modo), pedidos, self.revisao))
            historico = {str(p['pedido']): p for p in self.pedidos}
            return deepcopy({'id': identificador, 'revisao': self.revisao, 'modo': modo,
                             'pedidos': [{'pedido': p, 'salvo': historico.get(p)} for p in pedidos]})

    def iniciar(self, dados: dict[str, object]) -> None:
        modo = dados.get('modo')
        entrada, solicitacao = dados.get('pedidos', ''), dados.get('solicitacao', '')
        if modo not in ('normal', 'retomar', 'preparar', 'revalidar', 'importar', 'recuperar'):
            raise ValueError('Escolha Baixar e conferir, Importar, Conferir cadastro, ou Recuperar.')
        if not isinstance(entrada, str) or not isinstance(solicitacao, str) or not 1 <= len(solicitacao) <= 100:
            raise ValueError('Solicitação inválida. Atualize a página e tente novamente.')
        pedidos = analisar_entrada_pedidos(entrada, permitir_vazio=modo == 'retomar')
        # Clientes antigos também ficam limitados à preparação; nunca importam implicitamente.
        modo_executor = 'preparar' if modo in ('normal', 'retomar') else modo
        trabalho = Trabalho(modo_executor, pedidos)
        with self.trava:
            if self.ocupada or self.encerrando or self.bloqueado or self.finalizado.is_set():
                raise ConflitoInterface('Já existe uma operação em andamento ou o programa precisa ser reaberto.')
            if solicitacao in self.solicitacoes:
                raise ConflitoInterface('Esta solicitação já foi recebida. Confira o andamento na tela.')
            lista = self._pendentes_preparacao() if modo == 'retomar' else pedidos
            self._validar_selecao(str(modo), lista)
            conferido = (dados.get('conferencia'), modo, lista, self.revisao)
            if conferido not in self.conferencias:
                raise ConflitoInterface('Confira novamente o lote antes de iniciar. A lista ou o histórico pode ter mudado.')
            if self.executor is executar_fluxo:
                # Relê TOML/preferência ao aceitar o lote e preserva o snapshot.
                trabalho.configuracao = Configuracao.carregar()
                self.impressora = trabalho.configuracao.impressora
            if 'impressora' in dados and modo_executor in ('importar', 'recuperar'):
                if dados['impressora'] != self.impressora:
                    raise ConflitoInterface('A impressora mudou. Confira a seleção e prepare o lote novamente.')
                if modo_executor != 'recuperar' and (not self.impressora or self.impressora not in self.listar_filas()):
                    raise ValueError('Selecione uma impressora instalada nas configurações antes de imprimir.')
            trabalho.impressora = self.impressora
            trabalho.pedidos = list(lista)
            self.conferencias.clear()
            self.solicitacoes.append(solicitacao)
            self.execucao = uuid4().hex
            self.parada.clear()
            self.erro = None
            self.resumo = {}
            self.lote = list(lista)
            self.modo = trabalho.modo
            if modo in ('normal', 'preparar', 'retomar'):
                # Repetir o preparo de uma linha conserva os outros pedidos em conferência.
                if not self.lote_preparacao or not set(lista).issubset(self.lote_preparacao):
                    self.lote_preparacao = list(lista)
            self.resultados_lote = dict.fromkeys(lista, 'aguardando')
            self.mensagens.clear()
            self.pedido, self.indice, self.total = '', 0, len(lista)
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
            if trabalho.modo in ('normal', 'preparar'):
                self._historico.adicionar_pedidos(trabalho.pedidos)
            if trabalho.modo == 'retomar':
                trabalho.pedidos = self._pendentes_preparacao()
            self._atualizar()
            with self.trava:
                self.total = len(trabalho.pedidos)
            trabalho.recebido.set()
            logger.info('Interface: operação=%s modo=%s pedidos=%s', self.execucao, trabalho.modo, trabalho.pedidos)
            while not self.parada.is_set():
                try:
                    config = replace(trabalho.configuracao or CONFIG, impressora=trabalho.impressora)
                    with usar_configuracao(config):
                        resumo = self.executor(trabalho.pedidos, trabalho.modo, historico=self._historico,
                                               ao_erro=self.aguardar_decisao, ao_progresso=self.progresso,
                                               parar=self.parada.is_set)
                    self._atualizar()
                    with self.trava:
                        self.resumo = dict(Counter(resumo.situacoes.values()))
                        self.resultados_lote.update(resumo.situacoes)
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
            if self.medidor_abertura is not None:
                self.medidor_abertura.marcar('historico_iniciado')
            limite = monotonic() + TEMPO_LIBERAR_HISTORICO
            while not self.parada.is_set():
                try:
                    with EstadoPedidos(self.caminho, ao_alterar=self._atualizar) as historico:
                        self._historico = historico
                        self._atualizar()
                        with self.trava:
                            if self.encerrando:
                                break
                            self.fase = 'PRONTO'
                            self.mensagem = 'Informe os pedidos para baixar e conferir, ou revise os estados salvos abaixo.'
                        logging.getLogger().addHandler(handler)
                        if self.medidor_abertura is not None:
                            self.medidor_abertura.marcar('historico_pronto')
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
