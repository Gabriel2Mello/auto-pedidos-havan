# Standart library
import xml.etree.ElementTree as ET
from time import sleep
import sys
from os import environ
from pathlib import Path
from datetime import datetime, timedelta
import unicodedata
from time import perf_counter
# Third-party libraries
from pywinauto import Desktop
from pywinauto.keyboard import send_keys
from pywinauto.application import Application

CAMPOS = {
    'sisplan': 'Sisplan - 002 - NUNES ENXOVAIS IND, COM, IMP E EXP LTDA',
    'operacao': 55, 'cliente': 53, 'representante': 51, 'tabela_preco': 49,
    'transporte': 48, 'prazo_entrega': 28, 'prazo_producao': 26, 
    'historico': 18, 'tipo_venda': 16, 'numero': 13, 'ped_cliente': 12, 
    'saida': 6, 'entrega': 7, 'fatura': 8, 'classe_gerencial': 1, 'grid': 2,
    'nome': 0, 'combo_empresa': 0, 'observacao_2': 1
}

PRODUTOS_GOVERNADOR = [
    'DIVERTIDA','FORMATO','ASSENTO','GUARDANAPO',
    'AVENTAL','TROCADOR','ALMOFADA DECOR 38X38 HAVAN BABY',
    'AMAMENTAÇÃO','DESCANSO','MINI','GUIRLANDA','ABRAÇO'
]

COORD_ABA_PEDIDO = (87, 10)
COORD_ITENS_PEDIDO = (150,-13)
ATALHO_IMPORTAR = 'm'
ATALHO_HAVAN = 'h'
ATALHO_INCLUIR = '%i'
ATALHO_DESISTIR = '%d'
ATALHO_GRAVAR = '%g'

BASE_PATH_PEDIDOS = Path(environ['HAVAN_PEDIDOS'])


def formata_data(data_xml, dias=0):
    data = datetime.strptime(data_xml, '%d/%m/%y') + timedelta(days=dias)
    data = data.replace(year=2000 + data.year % 100)

    return data.strftime('%d/%m/%Y')


def caminho_xml(caminho_pedido, ped_cli):
    return caminho_pedido / f'Arq de integracao {ped_cli}.xml'


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


def get_field_index(parent, class_name, campo):
    try:
        index = CAMPOS[campo]
    except KeyError:
        raise RuntimeError(f'Campo não mapeado: {campo}')

    return parent.child_window(
        class_name=class_name,
        found_index=index
    )


def get_field_title(parent, class_name, title):
    return parent.child_window(
        class_name=class_name,
        title=title
    )


def inicia_app():
    app = Application(backend='win32').connect(
        title=CAMPOS['sisplan'],
        class_name='TApplication'
    )

    dlg = app.window(
        title=CAMPOS['sisplan'],
        class_name='TApplication'
    )

    dlg.restore()
    dlg.wait('visible', timeout=10)
    dlg.set_focus()

    main = app.window(
        title_re='.*VenPedidoGrade.*',
        class_name='TfmPrincipal'
    )
    main.set_focus()

    return main


def importa_arq_integracao(xml_path):
    app_abrir = Application(
        backend='win32'
    ).connect(title='Abrir', class_name='#32770')

    janela = app_abrir.window(
        title='Abrir', class_name='#32770'
    )
    janela.wait('visible', timeout=10)

    nome_field = get_field_index(
        janela, 'Edit', 'nome'
    )
    nome_field.set_focus()

    nome_field.set_edit_text(str(xml_path))
    nome_field.type_keys('{ENTER}')


def mapear_campos(aba_pedido):
    return {
        'numero': get_field_index(
            aba_pedido, 'TEdit', 'numero'
        ),
        'cliente': get_field_index(
            aba_pedido, 'TEdit', 'cliente'
        ),
        'representante': get_field_index(
            aba_pedido, 'TEdit', 'representante'
        ),
        'transporte': get_field_index(
            aba_pedido, 'TEdit', 'transporte'
        ),
        'tabela_preco': get_field_index(
            aba_pedido, 'TEdit', 'tabela_preco'
        ),
        'historico': get_field_index(
            aba_pedido, 'TEdit', 'historico'
        ),
        'tipo_venda': get_field_index(
            aba_pedido, 'TEdit', 'tipo_venda'
        ),
        'operacao': get_field_index(
            aba_pedido, 'TEdit', 'operacao'
        ),
        'data_fatura': get_field_index(
            aba_pedido, 'TDateEditSisp', 'fatura'
        ),
        'data_entrega': get_field_index(
            aba_pedido, 'TDateEditSisp', 'entrega'
        ),
        'data_saida': get_field_index(
            aba_pedido, 'TDateEditSisp', 'saida'
        ),
        'classe_gerencial': get_field_index(
            aba_pedido, 'TEdGrid', 'classe_gerencial'
        ),
        'observacao_2': get_field_index(
            aba_pedido, 'TMemo', 'observacao_2'
        ),
    }


def preencher_dados_fixos(campos):
    campos['cliente'].set_text('00022')
    campos['representante'].set_text('00001')
    campos['transporte'].set_text('00001')
    campos['tabela_preco'].set_text('004')
    campos['historico'].set_text('02')
    campos['tipo_venda'].set_text('1')
    campos['operacao'].set_text('1')

    campos['observacao_2'].set_text('PROMOCIONAL')

    campos['classe_gerencial'].set_focus()
    campos['classe_gerencial'].type_keys('20001{TAB}') # VENDA DE PRODUTOS


def preencher_datas(campos, data_fatura, data_entrega):
    campos['data_fatura'].set_text(data_fatura)
    campos['data_entrega'].set_text(data_entrega)
    campos['data_saida'].set_text(data_entrega)


def selecionar_empresa_matriz(aba_pedido):
    combo_empresa = get_field_index(
        aba_pedido, 'TComboBox', 'combo_empresa'
    )

    combo_empresa.set_focus()
    combo_empresa.type_keys('{UP}')


def main():
    start_time = perf_counter()

    main_win = inicia_app()

    pedido_grade = get_field_title(
        main_win, 'TTabSheet', '1002 - Pedido Por Grade'
    )

    aba_pedido = get_field_title(
        main_win, 'TTabSheet', 'Pedido'
    )

    itens_pedido = get_field_title(
        main_win, 'TTabSheet', 'Itens Pedido'
    )

    grid = get_field_index(
        itens_pedido, 'TDBGrid', 'grid'
    )

    campos = mapear_campos(aba_pedido)

    ped_cli = '2026-29276'
    caminho_pedido = BASE_PATH_PEDIDOS / ped_cli

    pedido_grade.click_input(coords=COORD_ABA_PEDIDO)
    send_keys(ATALHO_INCLUIR)

    sleep(1)
    campos['numero'].type_keys('{TAB}')
    numero_interno = campos['numero'].window_text()

    preencher_dados_fixos(campos)

    xml_path = caminho_xml(caminho_pedido, ped_cli)
 
    xml_root = carregar_xml(xml_path)
    produto = produto_xml(xml_root)

    empresa = definir_empresa(produto)
    if empresa == 'MATRIZ':
        selecionar_empresa_matriz(aba_pedido)

    data_fatura, data_entrega = data_xml(xml_root)
    preencher_datas(campos, data_fatura, data_entrega)

    aba_pedido.click_input(coords=COORD_ITENS_PEDIDO)

    grid.click_input(button='right') # OPÇÕES DO GRID
    send_keys(ATALHO_IMPORTAR)
    send_keys(ATALHO_HAVAN)

    sleep(1)
    importa_arq_integracao(xml_path)
    pedido_grade.click_input(coords=COORD_ABA_PEDIDO)

    #send_keys(ATALHO_DESISTIR)


    elapsed_time = perf_counter() - start_time
    print(f"\nDone in {elapsed_time:0.2f} seconds")



if __name__ == "__main__":
    main()

