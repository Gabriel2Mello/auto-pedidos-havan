from time import sleep
from dataclasses import dataclass
from typing import Callable, Literal, cast

from pywinauto import WindowSpecification
from pywinauto.timings import wait_until

from guias_sisplan import selecionar_guia
from src.logs import get_logger
from src.config import (
    CLIENTE_HAVAN,
    configuracao_atual,
)
from src.handle_app import (
    acionar_botao_pedido,
    cancelar_inclusao,
    importa_arq_integracao,
    handle_aviso_duplicado,
    tratar_avisos_importacao,
)
from src.menu_sisplan import abrir_importacao_havan
from src.pedidos import CodigoEmpresa, extrair_dados_xml
from src.arquivos import (caminho_xml, carregar_xml, formatar_motivo_erro, salvar_pedido_txt)
from src.erros import AbaPedidoIndisponivelError, SisplanError, NumeroInternoForaSequenciaError, XmlSemItensSisplanError
from src.notificacoes import (enviar_alerta_teams)
from src.windows import aguardar_campo

logger = get_logger(__name__)

CamposSisplan = dict[str, WindowSpecification]


OPERACOES_ESPECIAIS = {
    'ITENS PROMOCIONAIS PARA COMERCIALIZACAO': (
        'PROMOCIONAL',
        'PEDIDO PROMOCIONAL',
    ),
    'BONIFICACAO COMERCIAL': ('BONIFICADO', 'PEDIDO BONIFICADO'),
}


@dataclass(frozen=True)
class ResultadoImportacao:
    numero: str
    situacao: Literal['aguarda_confirmacao', 'duplicado', 'sem_cadastro', 'xml_sem_itens']
    operacao: str = ''


class _NumeroInternoSuspeitoError(ValueError):
    pass


def conferir_numero_interno(numero: str, referencia: int) -> None:
    tolerancia = configuracao_atual().tolerancia_numero_interno
    if (not numero.isascii() or not numero.isdigit() or int(numero) <= 0
            or abs(int(numero) - referencia) > tolerancia):
        raise _NumeroInternoSuspeitoError(
            f'Número interno {numero or "vazio"!r} fora da faixa: '
            f'referência {referencia}, tolerância de {tolerancia} números.'
        )


def selecionar_aba_pedido(pedido_grade: WindowSpecification, aba_pedido: WindowSpecification) -> None:
    selecionar_guia(pedido_grade)
    selecionar_guia(aba_pedido)
    aba_pedido.wait('ready', timeout=5)


def importar_pedido(
    pedido: str,
    pedido_grade: WindowSpecification,
    aba_pedido: WindowSpecification,
    grid: WindowSpecification,
    campos: CamposSisplan,
    antes_gravar: Callable[[str], None],
    *, referencia_numero: int, codigo_empresa: CodigoEmpresa,
) -> ResultadoImportacao:
    for tentativa in range(2):
        try:
            selecionar_aba_pedido(pedido_grade, aba_pedido)
            numero_anterior = cast(str, aguardar_campo(campos['numero']).window_text()).strip()
        except Exception as erro:
            raise AbaPedidoIndisponivelError(
                'Não foi possível posicionar o Sisplan na aba Pedido da tela 1002 — Pedido por Grade. '
                'Confira a tela do Sisplan antes de tentar novamente.'
            ) from erro
        try:
            resultado = _importar_uma_tentativa(
                pedido, pedido_grade, aba_pedido, grid, campos, antes_gravar,
                referencia_numero=referencia_numero, codigo_empresa=codigo_empresa,
            )
            if resultado.situacao in ('duplicado', 'sem_cadastro', 'xml_sem_itens'):
                try:
                    pedido_grade.wait('ready', timeout=5)
                    wait_until(5, 0.2, lambda: cast(str, campos['numero'].window_text()).strip() == numero_anterior)
                except Exception as erro:
                    motivo = {'duplicado': 'o aviso de duplicidade',
                              'sem_cadastro': 'o bloqueio de produto sem cadastro',
                              'xml_sem_itens': 'o aviso de XML sem itens'}[resultado.situacao]
                    raise SisplanError(
                        f'Não foi possível confirmar o cancelamento após {motivo}. '
                        'Confira a tela do Sisplan antes de continuar.'
                    ) from erro
                if resultado.situacao == 'sem_cadastro':
                    enviar_alerta_teams(pedido, '', 'PRODUTO SEM CADASTRO')
                if resultado.situacao == 'xml_sem_itens':
                    mensagem = ('O Sisplan não encontrou itens no XML do pedido. A inclusão foi cancelada. '
                                'Confira o arquivo de integração antes de tentar novamente.')
                    salvar_pedido_txt(pedido, motivo=mensagem)
                    raise XmlSemItensSisplanError(mensagem)
            return resultado
        except _NumeroInternoSuspeitoError as error:
            logger.warning('Pedido %s, tentativa %s: %s Cancelando inclusão.', pedido, tentativa + 1, error)
            try:
                selecionar_aba_pedido(pedido_grade, aba_pedido)
                cancelar_inclusao(pedido_grade.process_id())
                pedido_grade.wait('ready', timeout=5)
                # Não repetir se a tela não restaurou o pedido anterior ao Incluir.
                wait_until(5, 0.2, lambda: cast(str, campos['numero'].window_text()).strip() == numero_anterior)
            except Exception as cancelamento:
                mensagem = ('Não foi possível confirmar o cancelamento da inclusão com número '
                            'interno suspeito. Confira e cancele a inclusão no Sisplan antes de reiniciar.')
                logger.exception('Pedido %s: %s', pedido, mensagem)
                salvar_pedido_txt(pedido, motivo=mensagem)
                raise SisplanError(mensagem) from cancelamento
            if tentativa == 0:
                logger.info('Inclusão cancelada. Tentando o mesmo pedido %s mais uma vez.', pedido)
                continue
            mensagem = (f'Pedido {pedido}: o Sisplan gerou número interno suspeito nas duas tentativas. '
                        f'{error} As duas inclusões foram canceladas sem gravar. '
                        'Confira a numeração e a tela do Sisplan com o responsável. '
                        'Após corrigir, escolha tentar este pedido novamente ou pare o processamento.')
            salvar_pedido_txt(pedido, motivo=mensagem)
            raise NumeroInternoForaSequenciaError(mensagem) from error
    raise AssertionError('Tentativas de inclusão esgotadas.')


def _importar_uma_tentativa(
    pedido: str,
    pedido_grade: WindowSpecification,
    aba_pedido: WindowSpecification,
    grid: WindowSpecification,
    campos: CamposSisplan,
    antes_gravar: Callable[[str], None],
    *, referencia_numero: int, codigo_empresa: CodigoEmpresa,
) -> ResultadoImportacao:
    logger.info_split(f'Importando: {pedido}')

    try:
        xml_path = caminho_xml(pedido)
        xml_root = carregar_xml(xml_path)
        dados_xml = extrair_dados_xml(xml_root)
        processo = cast(int, pedido_grade.process_id())

        acionar_botao_pedido(processo, 'Incluir')

        aguardar_campo(campos['numero']).type_keys('{TAB}')
        numero_interno = cast(str, campos['numero'].window_text()).strip()
        conferir_numero_interno(numero_interno, referencia_numero)

        preencher_dados_fixos(campos)

        selecionar_empresa(campos['empresa'], codigo_empresa)

        preencher_datas(
            campos,
            dados_xml['data_fatura'],
            dados_xml['data_entrega']
        )

        selecionar_guia(aba_pedido, 'Itens Pedido')

        abrir_importacao_havan(grid, processo)
        importa_arq_integracao(xml_path, processo)
        aviso_importacao = tratar_avisos_importacao(pedido, processo)

        selecionar_aba_pedido(pedido_grade, aba_pedido)

        if aviso_importacao is not None:
            cancelar_inclusao(processo)
            return ResultadoImportacao('', aviso_importacao)

        processar_operacao_comercial(
            dados_xml['operacao'],
            pedido,
            numero_interno,
            campos
        )
        # O número pode mudar durante o preenchimento ou a importação do XML.
        numero_interno = cast(str, campos['numero'].window_text()).strip()
        conferir_numero_interno(numero_interno, referencia_numero)
        if _codigo_empresa(campos['empresa'].selected_text()) != codigo_empresa:
            raise SisplanError('A empresa de faturamento mudou durante a importação. Confira o pedido no Sisplan.')
        # O estado precisa estar em disco antes de enviar o comando de gravação.
        antes_gravar(numero_interno)
        acionar_botao_pedido(processo, 'Gravar')
        invalido = handle_aviso_duplicado(processo)

        return ResultadoImportacao(
            numero_interno, 'duplicado' if invalido else 'aguarda_confirmacao',
            dados_xml['operacao'],
        )

    except _NumeroInternoSuspeitoError:
        raise
    except Exception as error:
        logger.debug('Erro no Sisplan: %s', error, exc_info=True)
        salvar_pedido_txt(
            pedido,
            motivo=formatar_motivo_erro('Falha na tela do Sisplan', error),
        )
        raise SisplanError() from error


def processar_operacao_comercial(
    operacao_alvo: str,
    pedido: str,
    numero_interno: str,
    campos: CamposSisplan,
) -> None:
    operacao = OPERACOES_ESPECIAIS.get(operacao_alvo)
    if operacao is None:
        return

    observacao, mensagem = operacao
    aguardar_campo(campos['observacao_2']).set_text(observacao)
    logger.info(mensagem)

    sleep(0.1)


def notificar_operacao_confirmada(operacao_alvo: str, pedido: str, numero_interno: str) -> None:
    operacao = OPERACOES_ESPECIAIS.get(operacao_alvo)
    if operacao is None:
        return
    _, mensagem = operacao
    salvar_pedido_txt(pedido, True)
    enviar_alerta_teams(pedido, numero_interno, mensagem)


def preencher_dados_fixos(campos: CamposSisplan) -> None:
    dados = {
        'cliente':       CLIENTE_HAVAN,
        'representante': '00001',
        'transporte':    '00001',
        'tabela_preco':  '004',
        'historico':     '02',
        'tipo_venda':    '1',
        'operacao':      '1',
    }

    for nome, valor in dados.items():
        aguardar_campo(campos[nome]).set_text(valor)

    aguardar_campo(campos['classe_gerencial']).set_focus()
    campos['classe_gerencial'].type_keys('20001{TAB}')
    sleep(0.3)


def preencher_datas(
    campos: CamposSisplan,
    data_fatura: str,
    data_entrega: str,
) -> None:
    aguardar_campo(campos['data_entrega']).set_text(data_entrega)
    aguardar_campo(campos['data_saida']).set_text(data_entrega)
    aguardar_campo(campos['data_fatura']).set_text(data_fatura)


def _codigo_empresa(rotulo: str) -> str:
    codigo, separador, _ = rotulo.partition('-')
    return codigo.strip() if separador else ''


def selecionar_empresa(combo_empresa: WindowSpecification, codigo: CodigoEmpresa) -> None:
    combo_empresa.wait('ready', timeout=5)
    rotulos = cast(list[str], combo_empresa.item_texts())
    indices = [indice for indice, rotulo in enumerate(rotulos) if _codigo_empresa(rotulo) == codigo]
    if len(indices) != 1:
        raise SisplanError(f'Empresa {codigo} ausente ou ambígua no campo Emp. Fat. do Sisplan.')
    indice = indices[0]
    if combo_empresa.selected_index() != indice:
        combo_empresa.select(indice)
    if _codigo_empresa(combo_empresa.selected_text()) != codigo:
        wait_until(3, 0.1, lambda: _codigo_empresa(combo_empresa.selected_text()) == codigo)
