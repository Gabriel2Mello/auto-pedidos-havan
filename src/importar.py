import xml.etree.ElementTree as ET
from time import sleep

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
    handle_aviso_duplicado
)
from src.utils import (
        caminho_xml,
        formata_data,
        normalizar
)

logger = get_logger(__name__)


def carregar_xml(arquivo):
    return ET.parse(arquivo).getroot()


def extrair_dados_xml(root):
    logger.debug('Extraindo dados do xml')
    data_fatura = root.findtext('.//PrazoPagamento/PrevisaoData')
    data_entrega = root.findtext('.//DataInicialSemanaEntrega')

    produto_raw = root.findtext('.//DescricaoProduto')

    if not all([data_fatura, data_entrega, produto_raw]):
        raise RuntimeError('Dados não encontrados no XML')

    return {
        'data_fatura': formata_data(data_fatura),
        'data_entrega': formata_data(data_entrega, 1),
        'produto': normalizar(produto_raw)
    }


def definir_empresa(produto):
    return 'MATRIZ' if any(
        normalizar(p) in produto for p in PRODUTOS_GOVERNADOR
    ) else 'FILIAL'


def preencher_dados_fixos(campos):
    dados = {
        'cliente': '00022',
        'representante': '00001',
        'transporte': '00001',
        'tabela_preco': '004',
        'historico': '02',
        'tipo_venda': '1',
        'operacao': '1'
    }

    for nome, valor in dados.items():
        campos[nome].set_text(valor)

    campos['classe_gerencial'].set_focus()
    campos['classe_gerencial'].type_keys('20001{TAB}')


def preencher_datas(campos, data_fatura, data_entrega):
    campos['data_fatura'].set_text(data_fatura)
    sleep(0.5)
    campos['data_entrega'].set_text(data_entrega)
    sleep(0.5)
    campos['data_saida'].set_text(data_entrega)
    sleep(0.5)


def selecionar_empresa_matriz(combo_empresa):
    combo_empresa.set_focus()
    combo_empresa.type_keys('{UP}')
    sleep(0.5)


def importar_pedido(pedido, pedido_grade, aba_pedido, grid, campos):
    logger.debug('Iniciando processo de importação no Sisplan')
    pedido_grade.click_input(coords=COORD_ABA_PEDIDO)
    send_keys(ATALHOS['incluir'])
    sleep(0.5)

    campos['numero'].type_keys('{TAB}')
    numero_interno = campos['numero'].window_text()

    xml_path = caminho_xml(pedido)
    xml_root = carregar_xml(xml_path)
    dados_xml = extrair_dados_xml(xml_root)

    preencher_dados_fixos(campos)

    if definir_empresa(dados_xml['produto']) == 'MATRIZ':
        selecionar_empresa_matriz(campos['empresa'])

    preencher_datas(
        campos, dados_xml['data_fatura'], dados_xml['data_entrega']
    )

    aba_pedido.click_input(coords=COORD_ITENS_PEDIDO)

    grid.click_input(button='right') # OPÇÕES DO GRID
    send_keys(ATALHOS['importar'])
    send_keys(ATALHOS['havan'])

    sleep(1)
    importa_arq_integracao(xml_path)
    pedido_grade.click_input(coords=COORD_ABA_PEDIDO)

    send_keys(ATALHOS['gravar'])

    sleep(0.2)
    duplicado = handle_aviso_duplicado(pedido)

    return numero_interno, duplicado

