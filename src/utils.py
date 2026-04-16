from datetime import datetime, timedelta
from io import BytesIO
import unicodedata
import xml.etree.ElementTree as ET

import rarfile
from src.config import BASE_PATH_PEDIDOS, UNRAR_TOOL

rarfile.UNRAR_TOOL = UNRAR_TOOL

def input_pedido():
    pedidos_input = input('Pedido: ').strip()
    return [p.strip() for p in pedidos_input.split(',') if p.strip()]


def formata_data(data_xml, dias=0):
    data = datetime.strptime(data_xml, '%d/%m/%y') + timedelta(days=dias)
    return data.strftime('%d/%m/%Y')


def caminho_xml(pedido):
    caminho = BASE_PATH_PEDIDOS / str(pedido)
    return caminho / f'arq_de_integracao {pedido}.xml'


def caminho_pdf(pedido):
    caminho = BASE_PATH_PEDIDOS / str(pedido)
    return caminho / f'ordem_de_compra {pedido}.pdf'


def normalizar(texto):
    if not texto:
        raise RuntimeError('Texto não encontrado')

    return unicodedata.normalize('NFKD', texto)\
        .encode('ASCII', 'ignore')\
        .decode()\
        .upper()


def carregar_xml(arquivo):
    return ET.parse(arquivo).getroot()


def extrair_xml(content):
    with rarfile.RarFile(BytesIO(content)) as rf:
        xml_file = next(
            (f for f in rf.namelist()
             if f.lower().endswith('.xml')),
            None
        )

        if not xml_file:
            raise FileNotFoundError('.RAR sem arquivo XML')

        return rf.read(xml_file)

