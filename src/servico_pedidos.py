from __future__ import annotations

from contextlib import ExitStack, nullcontext
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Callable
from pathlib import Path
from uuid import uuid4

from metricas_nunes import registrar_evento

from cloudscraper import create_scraper
from pywinauto import WindowSpecification

from src.baixar import baixar_pedidos
from src.banco import BancoSisplan, BancoSisplanError, GravacaoNaoConfirmadaError, PedidoExistente
from src.config import Configuracao, usar_configuracao, validar_configuracao
from src.estado import EstadoError, EstadoPedido, EstadoPedidos
from src.filas import conferir_arquivos_baixados
from src.gravacao_download import DownloadPendenteError
from src.handle_app import inicia_app
from src.importar import ResultadoImportacao, importar_pedido, notificar_operacao_confirmada
from src.imprimir import processar_impressao
from src.logs import get_logger
from src.login import realizar_login
from src.contratos import AoErro, AoProgresso, Modo
from src.prevalidacao import PedidoRejeitadoError, validar_pedido_baixado
from src.resumo import ResumoExecucao
from src.erros import ConfiguracaoError, SessaoPortalExpiradaError, NumeroInternoForaSequenciaError, ProdutoSemCadastroError

if TYPE_CHECKING:
    from cloudscraper import ScraperMock

from src.etapas import INCLUSOES_INCERTAS, ETAPAS_INICIAIS

logger = get_logger(__name__)


Campos = tuple[WindowSpecification, WindowSpecification, WindowSpecification, dict[str, WindowSpecification]]


@dataclass(frozen=True)
class Integracoes:
    banco: Callable[[Path, str], BancoSisplan] = field(default_factory=lambda: BancoSisplan)
    portal: Callable[..., ScraperMock] = field(default_factory=lambda: create_scraper)
    login: Callable[[ScraperMock], None] = field(default_factory=lambda: realizar_login)
    baixar: Callable[..., dict[str, bool]] = field(default_factory=lambda: baixar_pedidos)
    sisplan: Callable[[], Campos] = field(default_factory=lambda: inicia_app)
    importar: Callable[..., ResultadoImportacao] = field(default_factory=lambda: importar_pedido)
    imprimir: Callable[..., str] = field(default_factory=lambda: processar_impressao)
    notificar: Callable[[str, str, str], None] = field(default_factory=lambda: notificar_operacao_confirmada)


@dataclass(frozen=True)
class ContextoExecucao:
    configuracao: Configuracao
    integracoes: Integracoes = field(default_factory=Integracoes)


@dataclass
class RecursosExecucao:
    pilha: ExitStack
    contexto: ContextoExecucao
    scraper: ScraperMock | None = None
    sisplan: tuple[
        WindowSpecification, WindowSpecification, WindowSpecification,
        dict[str, WindowSpecification],
    ] | None = None
    parar: Callable[[], bool] | None = None

    def parada_solicitada(self) -> bool:
        return self.parar is not None and self.parar()


def registrar_falha(
    pedido: str, erro: BaseException, historico: EstadoPedidos, resumo: ResumoExecucao,
) -> None:
    try:
        registro = historico.obter(pedido)
        if registro is None:
            resumo.situacoes[pedido] = 'falhou'
            return
        if isinstance(erro, ProdutoSemCadastroError) and registro.etapa in ETAPAS_INICIAIS:
            registro = replace(registro, etapa='sem_cadastro')
            resumo.situacoes[pedido] = 'sem_cadastro'
        elif registro.etapa in ('impressao_iniciada', 'impressao_incerta'):
            resumo.situacoes[pedido] = 'impressao_incerta'
        elif registro.etapa in INCLUSOES_INCERTAS:
            resumo.situacoes[pedido] = 'gravacao_pendente'
        elif registro.etapa in ETAPAS_INICIAIS:
            resumo.situacoes[pedido] = 'rejeitado' if isinstance(erro, PedidoRejeitadoError) else 'falhou'
        else:
            resumo.situacoes[pedido] = 'impressao_pendente'
        historico.salvar(replace(registro, erro=str(erro) or 'Execução interrompida.'))
    except EstadoError:
        logger.error('Não foi possível atualizar o histórico após a falha do pedido %s.', pedido)


def opcoes_seguras(erro: Exception, registro: EstadoPedido | None) -> tuple[bool, bool]:
    if isinstance(erro, NumeroInternoForaSequenciaError):
        return registro is not None and registro.etapa == 'baixado', False
    if isinstance(erro, (EstadoError, ConfiguracaoError)):
        return False, False
    if registro is not None and registro.etapa in INCLUSOES_INCERTAS:
        return False, False
    if isinstance(erro, DownloadPendenteError):
        return False, True
    if isinstance(erro, BancoSisplanError):
        return True, False
    if isinstance(erro, SessaoPortalExpiradaError):
        return True, False
    if registro is not None and registro.etapa in ('impressao_iniciada', 'impressao_incerta'):
        return False, True
    return True, True


def processar_pedidos(
    numero_pedidos: list[str], modo: Modo = 'normal', *,
    historico: EstadoPedidos | None = None, ao_erro: AoErro | None = None,
    ao_progresso: AoProgresso | None = None, parar: Callable[[], bool] | None = None,
    contexto: ContextoExecucao | None = None,
) -> ResumoExecucao:
    contexto = contexto or ContextoExecucao(Configuracao.carregar())
    resumo = ResumoExecucao(dict.fromkeys(numero_pedidos, 'aguardando'))
    execucao_metricas = uuid4().hex
    try:
        with usar_configuracao(contexto.configuracao), (nullcontext(historico) if historico is not None else EstadoPedidos()) as estado:
            if modo in ('normal', 'reiniciar'):
                estado.adicionar_pedidos(numero_pedidos)
            elif modo == 'retomar':
                numero_pedidos = estado.pendentes()
                resumo.situacoes = dict.fromkeys(numero_pedidos, 'aguardando')
            if not numero_pedidos:
                logger.info('Nenhum pedido pendente para processar.')
                return resumo
            logger.debug('Lista de trabalho: modo=%s pedidos=%s', modo, ', '.join(numero_pedidos))
            validar_configuracao(apenas_impressao=True)
            with contexto.integracoes.banco(contexto.configuracao.banco_config, contexto.configuracao.banco_perfil) as banco, ExitStack() as pilha:
                recursos = RecursosExecucao(pilha, contexto, parar=parar)
                existentes_iniciais: dict[str, list[PedidoExistente]] | None = None
                reconectar_banco = False
                for indice, pedido in enumerate(dict.fromkeys(numero_pedidos), start=1):
                    primeira_tentativa = True
                    while True:
                        if recursos.parada_solicitada():
                            logger.info('Parada solicitada. Os pedidos pendentes estão preservados.')
                            return resumo
                        try:
                            if ao_progresso is not None:
                                ao_progresso(pedido, indice, len(resumo.situacoes))
                            logger.info_split('Pedido %s de %s: %s', indice, len(resumo.situacoes), pedido)
                            if reconectar_banco:
                                banco.reconectar()
                                reconectar_banco = False
                                existentes_iniciais = None
                            if existentes_iniciais is None:
                                existentes_iniciais = banco.consultar_pedidos(numero_pedidos)
                            encontrados = existentes_iniciais.get(pedido, []) if primeira_tentativa else None
                            processar_um_pedido(pedido, modo, banco, estado, resumo, recursos, encontrados)
                            if resumo.situacoes.get(pedido) == 'existente':
                                registrar_evento('pedido_existente', f'{execucao_metricas}:{pedido}', pedido,
                                                 execucao=execucao_metricas)
                            if ao_progresso is not None:
                                ao_progresso(pedido, indice, len(resumo.situacoes))
                            break
                        except BaseException as error:
                            if isinstance(error, Exception):
                                registrar_evento('pedido_falhou', f'{execucao_metricas}:{pedido}', pedido,
                                                 execucao=execucao_metricas)
                            registrar_falha(pedido, error, estado, resumo)
                            logger.exception('O processamento do pedido %s foi pausado.', pedido)
                            recursos.sisplan = None
                            if isinstance(error, SessaoPortalExpiradaError):
                                recursos.scraper = None
                            if not isinstance(error, Exception) or ao_erro is None:
                                raise
                            pode_repetir, pode_continuar = opcoes_seguras(error, estado.obter(pedido))
                            decisao = ao_erro(pedido, error, pode_repetir, pode_continuar)
                            if decisao == 'repetir' and pode_repetir:
                                reconectar_banco = isinstance(error, BancoSisplanError)
                                primeira_tentativa = False  # Reconferir mudanças ocorridas durante a pausa.
                                continue
                            if decisao == 'pular' and pode_continuar:
                                break
                            return resumo
        return resumo
    finally:
        resumo.exibir()


def informar_existente(
    pedido: str, encontrados: list[PedidoExistente], historico: EstadoPedidos, resumo: ResumoExecucao,
) -> None:
    if len(encontrados) != 1:
        raise GravacaoNaoConfirmadaError(
            f'Pedido {pedido}: não há uma correspondência única confirmada no banco. '
            'A pendência foi preservada; confira com o responsável antes de prosseguir.'
        )
    unico = encontrados[0]
    historico.salvar(EstadoPedido(
        pedido, unico.numero, 'existente', unico.empresa,
    ))
    resumo.situacoes[pedido] = 'existente'
    logger.info('Pedido %s já consta no Sisplan%s. Nenhuma nova inclusão ou impressão.',
                pedido, f'; número interno {unico.numero}')


def processar_um_pedido(
    pedido: str, modo: Modo, banco: BancoSisplan, historico: EstadoPedidos,
    resumo: ResumoExecucao, recursos: RecursosExecucao,
    encontrados: list[PedidoExistente] | None = None,
) -> None:
    registro = historico.obter(pedido)
    if encontrados is None:
        encontrados = banco.consultar_pedidos([pedido]).get(pedido, [])
    if modo == 'reimprimir':
        if len(encontrados) != 1:
            raise PedidoRejeitadoError('Não encontrei uma gravação única desse pedido no Sisplan para reimprimir.')
        retomar_impressao(pedido, encontrados[0].numero, banco, historico, resumo, forcar=True, parar=recursos.parar, integracoes=recursos.contexto.integracoes)
        return
    if registro is None:
        raise EstadoError('Pedido não está na fila salva. Volte ao menu e escolha Inserir.')
    if registro.etapa == 'aviso_pendente':
        informar_existente(pedido, encontrados, historico, resumo)
        return
    if modo == 'reiniciar' and registro.etapa in INCLUSOES_INCERTAS and not encontrados:
        historico.liberar_importacao(pedido)
        registro = historico.obter(pedido)
        assert registro is not None
    if registro.etapa in ETAPAS_INICIAIS:
        if encontrados:
            informar_existente(pedido, encontrados, historico, resumo)
        else:
            importar_novo(pedido, banco, historico, resumo, recursos)
        return
    if registro.etapa in ('impressao_enviada', 'existente'):
        if encontrados and (not registro.numero or any(p.numero == registro.numero for p in encontrados)):
            resumo.situacoes[pedido] = 'existente'
            logger.info('Pedido %s já processado; consulte Reimprimir se precisar de outra cópia.', pedido)
            return
        raise GravacaoNaoConfirmadaError('O histórico e o Sisplan não correspondem. Avise o responsável.')
    if not encontrados:
        raise GravacaoNaoConfirmadaError(
            f'Pedido {pedido}: a inclusão anterior não foi confirmada. '
            'Confira e cancele a inclusão anterior com o responsável antes de tentar novamente.'
        )
    numero = registro.numero
    if not numero and len(encontrados) == 1:
        numero = encontrados[0].numero
    retomar_impressao(pedido, numero, banco, historico, resumo, parar=recursos.parar, integracoes=recursos.contexto.integracoes)


def retomar_impressao(
    pedido: str, numero: str, banco: BancoSisplan, historico: EstadoPedidos,
    resumo: ResumoExecucao, forcar: bool = False,
    parar: Callable[[], bool] | None = None,
    integracoes: Integracoes | None = None,
) -> None:
    registro = historico.obter(pedido)
    if registro is not None and registro.numero and registro.numero != numero:
        raise EstadoError('O número interno diverge do histórico. Avise o responsável.')
    # Aviso pendente vem de uma inclusão cancelada: confirmar a existência para
    # reimprimir não comprova uma nova inclusão feita por esta automação.
    inclusao_incerta = registro is not None and registro.etapa in ('importacao_iniciada', 'gravacao_pendente')
    if inclusao_incerta:
        itens = historico.obter_itens_esperados(pedido)
        if not itens:
            # Migração de uma inclusão pendente criada antes desta versão.
            itens = validar_pedido_baixado(banco, pedido)
            historico.salvar_itens_esperados(pedido, itens)
        confirmado = banco.confirmar_gravacao(pedido, numero, itens_esperados=itens)
    else:
        confirmado = banco.confirmar_gravacao(pedido, numero)
    if registro is None or registro.etapa in (*ETAPAS_INICIAIS, *INCLUSOES_INCERTAS, 'existente'):
        historico.salvar(EstadoPedido(pedido, confirmado.numero, 'importado', confirmado.empresa))
    if inclusao_incerta:
        registrar_inclusao(pedido, confirmado)
    resumo.retomados.add(pedido)
    if parar is not None and parar():
        resumo.situacoes[pedido] = 'impressao_pendente'
        return
    enviar_impressao(pedido, numero, historico, resumo, forcar=forcar, integracoes=integracoes)


def enviar_impressao(
    pedido: str, numero: str, historico: EstadoPedidos, resumo: ResumoExecucao, forcar: bool = False,
    integracoes: Integracoes | None = None,
) -> None:
    resumo.situacoes[pedido] = (integracoes or Integracoes()).imprimir(pedido, numero, historico, forcar=forcar)
    if resumo.situacoes[pedido] != 'impressao_enviada':
        raise PedidoRejeitadoError(
            f'A impressão do pedido {pedido} não foi concluída com segurança. '
            'Confira a impressora. O pedido está salvo para retomar ou reimprimir.'
        )


def registrar_inclusao(pedido: str, confirmado: PedidoExistente) -> None:
    empresa = 'MATRIZ' if confirmado.empresa == 1 else 'FILIAL'
    registrar_evento('pedido_inserido', f'{confirmado.empresa}:{confirmado.numero}:{pedido}',
                     pedido, empresa=empresa)


def importar_novo(
    pedido: str, banco: BancoSisplan, historico: EstadoPedidos,
    resumo: ResumoExecucao, recursos: RecursosExecucao,
) -> None:
    registro = historico.obter(pedido)
    assert registro is not None
    outras_inclusoes = [p for p in historico.inclusoes_incertas() if p != pedido]
    if outras_inclusoes:
        raise EstadoError('Existe uma inclusão anterior que precisa ser conferida pelo responsável: '
                          + ', '.join(outras_inclusoes))
    logger.debug('Pedido %s: etapa salva=%s.', pedido, registro.etapa)
    logger.info('Conferindo arquivos e produtos do pedido %s.', pedido)
    arquivos_validos = conferir_arquivos_baixados(pedido)
    if registro.etapa in ('baixado', 'sem_cadastro') and not arquivos_validos:
        registro = replace(registro, etapa='para_baixar', erro='Arquivos locais precisam ser baixados novamente.')
        historico.salvar(registro)
        raise PedidoRejeitadoError(
            f'Os arquivos salvos do pedido {pedido} estão ausentes ou inválidos. '
            'Escolha tentar novamente para baixá-los de novo.'
        )
    if registro.etapa == 'para_baixar':
        validar_configuracao()
        if recursos.scraper is None:
            scraper = recursos.pilha.enter_context(recursos.contexto.integracoes.portal(
                browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True},
            ))
            recursos.contexto.integracoes.login(scraper)
            recursos.scraper = scraper
        if recursos.parada_solicitada():
            return
        def registrar_download(numero: str) -> None:
            historico.salvar(EstadoPedido(numero, '', 'baixado'))

        resultados = recursos.contexto.integracoes.baixar(
            recursos.scraper, [pedido],
            ao_baixar=registrar_download,
        )
        if not resultados.get(pedido):
            raise PedidoRejeitadoError(f'Não consegui baixar os arquivos do pedido {pedido}. Verifique o portal ou a conexão.')
        historico.salvar(EstadoPedido(pedido, '', 'baixado'))
    if not conferir_arquivos_baixados(pedido):
        historico.salvar(EstadoPedido(pedido, '', 'para_baixar', erro='Arquivos baixados incompletos ou inválidos.'))
        raise PedidoRejeitadoError(f'Os arquivos do pedido {pedido} estão incompletos ou inválidos. Avise o responsável.')
    itens_esperados = validar_pedido_baixado(banco, pedido)
    encontrados = banco.consultar_pedidos([pedido]).get(pedido, [])
    if encontrados:
        informar_existente(pedido, encontrados, historico, resumo)
        return
    if recursos.parada_solicitada():
        logger.info('Pedido %s preservado antes de iniciar a inclusão.', pedido)
        return
    historico.salvar_itens_esperados(pedido, itens_esperados)
    referencia_numero = banco.consultar_referencia_numero()
    if recursos.sisplan is None:
        recursos.sisplan = recursos.contexto.integracoes.sisplan()
    historico.salvar(EstadoPedido(pedido, '', 'importacao_iniciada'))
    def registrar_gravacao(numero: str) -> None:
        historico.salvar(EstadoPedido(pedido, numero, 'gravacao_pendente'))

    try:
        resultado = recursos.contexto.integracoes.importar(
            pedido, *recursos.sisplan, registrar_gravacao,
            referencia_numero=referencia_numero,
        )
    except NumeroInternoForaSequenciaError:
        # As duas inclusões foram canceladas e nenhum comando de gravação foi enviado.
        historico.salvar(EstadoPedido(pedido, '', 'baixado'))
        raise
    if resultado.situacao == 'duplicado':
        # Persistir antes da consulta: queda de rede ou reinício não apagam o aviso.
        historico.salvar(EstadoPedido(pedido, '', 'aviso_pendente'))
        encontrados = banco.consultar_pedidos([pedido]).get(pedido, [])
        informar_existente(pedido, encontrados, historico, resumo)
        return
    if resultado.situacao == 'sem_cadastro':
        historico.salvar(EstadoPedido(pedido, '', 'sem_cadastro'))
        raise ProdutoSemCadastroError(
            'O Sisplan encontrou produto sem cadastro. Pedido salvo. '
            'Após cadastrar os produtos, escolha Importar novamente ou Retomar.'
        )
    confirmado = banco.confirmar_gravacao(pedido, resultado.numero, itens_esperados=itens_esperados)
    historico.salvar(EstadoPedido(pedido, confirmado.numero, 'importado', confirmado.empresa))
    resumo.importados.add(pedido)
    registrar_inclusao(pedido, confirmado)
    logger.info('Gravação confirmada: %s / interno %s.', pedido, confirmado.numero)
    recursos.contexto.integracoes.notificar(resultado.operacao, pedido, confirmado.numero)
    if recursos.parada_solicitada():
        resumo.situacoes[pedido] = 'impressao_pendente'
        logger.info('Pedido %s gravado; impressão preservada para retomar.', pedido)
        return
    enviar_impressao(pedido, confirmado.numero, historico, resumo, integracoes=recursos.contexto.integracoes)
