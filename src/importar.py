from time import sleep
from typing import Literal
import xml.etree.ElementTree as ET

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
    salvar_promocional_txt,
)

logger = get_logger(__name__)


def importar_pedido(pedido: str, pedido_grade: WindowSpecification, aba_pedido: WindowSpecification, grid: WindowSpecification, campos: dict[str, WindowSpecification]) -> tuple[str, bool | None]:
    logger.info_split(f'Importando: {pedido}')

    try:
        pedido_grade.click_input(coords=COORD_ABA_PEDIDO)
        send_keys(ATALHOS['incluir'])
        sleep(0.3)

        campos['numero'].type_keys('{TAB}')
        numero_interno = campos['numero'].window_text()

        xml_path =  caminho_xml(pedido)
        xml_root =  carregar_xml(xml_path)
        dados_xml = extrair_dados_xml(xml_root)

        preencher_dados_fixos(campos)

        if dados_xml['operacao'] == 'ITENS PROMOCIONAIS PARA COMERCIALIZACAO':
            campos['observacao_2'].set_text('PROMOCIONAL')
            print('PEDIDO PROMOCIONAL')
            sleep(0.1)
            salvar_promocional_txt(pedido)

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

        sleep(1)
        importa_arq_integracao(xml_path)
        sleep(0.5)
        invalido = handle_produto_sem_cadastro(pedido)

        pedido_grade.click_input(coords=COORD_ABA_PEDIDO)

        if invalido:
            send_keys(ATALHOS['desistir'])
            sleep(0.2)
            send_keys(ATALHOS['sim'])
        else:
            send_keys(ATALHOS['gravar'])

            sleep(0.5)
            invalido = handle_aviso_duplicado()

        return numero_interno, invalido

    except Exception as e:
        logger.debug(f'Erro no Sisplan: {e}', exc_info=True)
        raise SisplanError() from e


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
        'data_entrega': formata_data(campos_xml['data_entrega'], 1),
        'produto':  normalizar(campos_xml['produto']),
        'operacao': campos_xml['operacao'],
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
    sleep(0.1)


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

