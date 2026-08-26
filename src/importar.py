from time import sleep
from typing import Literal
import xml.etree.ElementTree as ET
from typing import cast

from pywinauto import WindowSpecification
from pywinauto.keyboard import send_keys

from src.logs import get_logger
from src.config import (
    PRODUTOS_GOVERNADOR,
    COORD_ABA_PEDIDO,
    COORD_ITENS_PEDIDO,
    ATALHOS
)
from src.handle_app import (
    importa_arq_integracao,
    handle_aviso_duplicado,
    handle_produto_sem_cadastro,
)
from src.utils import (
    caminho_xml,
    formata_data,
    normalizar,
    carregar_xml,
    SisplanError,
    salvar_pedido_txt,
    enviar_alerta_teams,
    send_keys_sleep,
)

logger = get_logger(__name__)


def importar_pedido(pedido: str, pedido_grade: WindowSpecification, aba_pedido: WindowSpecification, grid: WindowSpecification, campos: dict[str, WindowSpecification]) -> tuple[str, bool | None]:
    logger.info_split(f'Importando: {pedido}')

    try:
        pedido_grade.click_input(coords=COORD_ABA_PEDIDO)
        send_keys_sleep(ATALHOS['incluir'], 0.3)

        campos['numero'].type_keys('{TAB}')
        numero_interno: str = cast(str, campos['numero'].window_text())

        xml_path =  caminho_xml(pedido)
        xml_root =  carregar_xml(xml_path)
        dados_xml = extrair_dados_xml(xml_root)

        preencher_dados_fixos(campos)
        processar_operacao_comercial(
            dados_xml['operacao'],
            pedido,
            numero_interno,
            campos
        )

        if definir_empresa(dados_xml['produto']) == 'MATRIZ':
            selecionar_empresa_matriz(campos['empresa'])

        preencher_datas(
            campos,
            dados_xml['data_fatura'],
            dados_xml['data_entrega']
        )

        aba_pedido.click_input(coords=COORD_ITENS_PEDIDO)

        grid.click_input(button='right') # OPÇÕES DO GRID
        send_keys(ATALHOS['importar'])
        send_keys(ATALHOS['havan'])

        importa_arq_integracao(xml_path)
        invalido = handle_produto_sem_cadastro(pedido)

        pedido_grade.click_input(coords=COORD_ABA_PEDIDO)

        if invalido:
            send_keys_sleep(ATALHOS['desistir'], 0.2)
            send_keys(ATALHOS['sim'])
        else:
            send_keys(ATALHOS['gravar'])
            invalido = handle_aviso_duplicado()

        return numero_interno, invalido

    except Exception as e:
        logger.debug(f'Erro no Sisplan: {e}', exc_info=True)
        raise SisplanError() from e


def processar_operacao_comercial(
    operacao_alvo: str,
    pedido: str,
    numero_interno: str,
    campos: dict[str, WindowSpecification],
) -> None:
    mapeamento_operacoes = {
        'ITENS PROMOCIONAIS PARA COMERCIALIZACAO': {
            'obs': 'PROMOCIONAL',
            'mensagem': 'PEDIDO PROMOCIONAL',
        },
        'BONIFICACAO COMERCIAL': {
            'obs': 'BONIFICADO',
            'mensagem': 'PEDIDO BONIFICADO',
        },
    }

    if operacao_alvo in mapeamento_operacoes:
        operacao = mapeamento_operacoes[operacao_alvo]

        campos['observacao_2'].set_text(operacao['obs'])
        print(operacao['mensagem'])

        sleep(0.1)
        salvar_pedido_txt(pedido, True)
        enviar_alerta_teams(pedido, numero_interno, operacao['mensagem'])


def extrair_dados_xml(root: ET.Element) -> dict[str, str]:
    logger.debug('Extraindo dados do xml')

    campos_xml = {
        'data_fatura':  root.findtext('.//PrazoPagamento/PrevisaoData', ''),
        'data_entrega': root.findtext('.//DataInicialSemanaEntrega', ''),
        'produto':      root.findtext('.//DescricaoProduto', ''),
        'operacao':     root.findtext('.//Operacao', ''),
    }

    if not all(campos_xml.values()):
        raise RuntimeError('Dados não encontrados no XML')

    return {
        'data_fatura':  formata_data(campos_xml['data_fatura']),
        'data_entrega': formata_data(campos_xml['data_entrega']),
        'produto':  normalizar(campos_xml['produto']),
        'operacao': normalizar(campos_xml['operacao']),
    }


def definir_empresa(produto: str) -> Literal['MATRIZ', 'FILIAL']:
    return 'MATRIZ' if any(
        normalizar(p) in produto for p in PRODUTOS_GOVERNADOR
    ) else 'FILIAL'


def preencher_dados_fixos(campos: dict[str, WindowSpecification]) -> None:
    dados = {
        'cliente':       '00022',
        'representante': '00001',
        'transporte':    '00001',
        'tabela_preco':  '004',
        'historico':     '02',
        'tipo_venda':    '1',
        'operacao':      '1'
    }

    for nome, valor in dados.items():
        campos[nome].set_text(valor)

    campos['classe_gerencial'].set_focus()
    campos['classe_gerencial'].type_keys('20001{TAB}')
    sleep(0.3)


def preencher_datas(campos: dict[str, WindowSpecification], data_fatura: str, data_entrega: str) -> None:
    campos['data_fatura'].set_text(data_fatura)
    sleep(0.1)
    campos['data_entrega'].set_text(data_entrega)
    sleep(0.1)
    campos['data_saida'].set_text(data_entrega)
    sleep(0.1)


def selecionar_empresa_matriz(combo_empresa: WindowSpecification) -> None:
    combo_empresa.set_focus()
    combo_empresa.type_keys('{UP}')
    sleep(0.1)

