import xml.etree.ElementTree as ET
from time import sleep

from pywinauto.keyboard import send_keys

from src.config import (
    PRODUTOS_GOVERNADOR,
    COORD_ABA_PEDIDO,
    COORD_ITENS_PEDIDO,
    ATALHOS
)
from src.handle_app import importa_arq_integracao
from src.utils import caminho_xml, formata_data, normalizar


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
    campos['cliente'].set_text('00022')
    campos['representante'].set_text('00001')
    campos['transporte'].set_text('00001')
    campos['tabela_preco'].set_text('004')
    campos['historico'].set_text('02')
    campos['tipo_venda'].set_text('1')
    campos['operacao'].set_text('1')

    campos['classe_gerencial'].set_focus()
    sleep(1)
    campos['classe_gerencial'].type_keys('20001{TAB}')
    sleep(1)


def preencher_datas(campos, data_fatura, data_entrega):
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
    pedido_grade.click_input(coords=COORD_ABA_PEDIDO)
    send_keys(ATALHOS['incluir'])

    sleep(1)
    campos['numero'].type_keys('{TAB}')
    numero_interno = campos['numero'].window_text()

    preencher_dados_fixos(campos)

    xml_path = caminho_xml(pedido)
    xml_root = carregar_xml(xml_path)

    produto = produto_xml(xml_root)

    empresa = definir_empresa(produto)
    if empresa == 'MATRIZ':
        selecionar_empresa_matriz(campos['empresa'])

    data_fatura, data_entrega = data_xml(xml_root)
    preencher_datas(campos, data_fatura, data_entrega)

    aba_pedido.click_input(coords=COORD_ITENS_PEDIDO)

    grid.click_input(button='right') # OPÇÕES DO GRID
    send_keys(ATALHOS['importar'])
    send_keys(ATALHOS['havan'])

    sleep(1)
    importa_arq_integracao(xml_path)
    pedido_grade.click_input(coords=COORD_ABA_PEDIDO)

    send_keys(ATALHOS['desistir'])

    return numero_interno

