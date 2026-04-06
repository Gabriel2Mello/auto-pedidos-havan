# Standart library
from src.config import PRODUTOS_GOVERNADOR, BASE_PATH_PEDIDOS, COORD_ABA_PEDIDO, ATALHO_INCLUIR, COORD_ITENS_PEDIDO, ATALHO_IMPORTAR, ATALHO_HAVAN, ATALHO_DESISTIR
from src.handle_app import importa_arq_integracao
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import unicodedata
from time import sleep
# Third-party libraries
from pywinauto.keyboard import send_keys


PATH_HAVAN = BASE_PATH_PEDIDOS / 'Havan Pedidos'

def formata_data(data_xml, dias=0):
    data = datetime.strptime(data_xml, '%d/%m/%y') + timedelta(days=dias)
    data = data.replace(year=2000 + data.year % 100)

    return data.strftime('%d/%m/%Y')


def caminho_xml(caminho_pedido, ped_cli):
    return caminho_pedido / f'arq_de_integracao {ped_cli}.xml'


def carregar_xml(arquivo):
    tree = ET.parse(arquivo)
    return tree.getroot()


def data_xml(root):
    data_fatura = root.findtext(
        'DadosEntregaFaturamento/PrazoPagamento/PrevisaoData'
    )
    data_entrega = root.findtext(
        'DadosEntregaFaturamento/DataInicialSemanaEntrega'
    )

    if not data_fatura or not data_entrega:
        raise RuntimeError('Data no xml não encontrada')

    return formata_data(data_fatura), formata_data(data_entrega, 1)


def normalizar(texto):
    if texto is None:
        raise RuntimeError('Texto não encontrado')

    return unicodedata.normalize('NFKD', texto)\
        .encode('ASCII', 'ignore')\
        .decode()\
        .upper()


def produto_xml(root):
    produto = root.findtext(
        'ItensOrdemCompra/ItemOrdemCompra/DescricaoProduto'
    )

    if not produto:
        raise RuntimeError('Produto não encontrado')

    return normalizar(produto)


def definir_empresa(produto):
    return 'MATRIZ' if any(
        normalizar(p) in produto for p in PRODUTOS_GOVERNADOR
    ) else 'FILIAL'


def preencher_dados_fixos(campos):
    sleep(1)
    campos['cliente'].set_text('00022')
    sleep(1)
    campos['representante'].set_text('00001')
    sleep(1)
    campos['transporte'].set_text('00001')
    sleep(1)
    campos['tabela_preco'].set_text('004')
    sleep(1)
    campos['historico'].set_text('02')
    sleep(1)
    campos['tipo_venda'].set_text('1')
    sleep(1)
    campos['operacao'].set_text('1')
    sleep(1)

    campos['classe_gerencial'].set_focus()
    sleep(1)
    campos['classe_gerencial'].type_keys('20001{TAB}')
    sleep(1)


def preencher_datas(campos, data_fatura, data_entrega):
    sleep(1)
    campos['data_fatura'].set_text(data_fatura)
    sleep(1)
    campos['data_entrega'].set_text(data_entrega)
    sleep(1)
    campos['data_saida'].set_text(data_entrega)
    sleep(1)


def selecionar_empresa_matriz(combo_empresa):
    combo_empresa.set_focus()
    sleep(1)
    combo_empresa.type_keys('{UP}')
    sleep(1)


def importar_pedido(pedido, pedido_grade, aba_pedido, grid, campos):
    caminho_pedido = PATH_HAVAN / pedido

    pedido_grade.click_input(coords=COORD_ABA_PEDIDO)
    send_keys(ATALHO_INCLUIR)

    sleep(1)
    campos['numero'].type_keys('{TAB}')
    numero_interno = campos['numero'].window_text()

    preencher_dados_fixos(campos)

    xml_path = caminho_xml(caminho_pedido, pedido)
    xml_root = carregar_xml(xml_path)

    produto = produto_xml(xml_root)

    empresa = definir_empresa(produto)
    if empresa == 'MATRIZ':
        selecionar_empresa_matriz(campos['empresa'])

    data_fatura, data_entrega = data_xml(xml_root)
    preencher_datas(campos, data_fatura, data_entrega)

    aba_pedido.click_input(coords=COORD_ITENS_PEDIDO)

    grid.click_input(button='right') # OPÇÕES DO GRID
    send_keys(ATALHO_IMPORTAR)
    send_keys(ATALHO_HAVAN)

    sleep(1)
    importa_arq_integracao(xml_path)
    pedido_grade.click_input(coords=COORD_ABA_PEDIDO)

    send_keys(ATALHO_DESISTIR)

    return numero_interno
