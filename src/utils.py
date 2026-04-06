from src.config import BASE_PATH_PEDIDOS
from datetime import datetime, timedelta
import unicodedata

def formata_data(data_xml, dias=0):
    data = datetime.strptime(data_xml, '%d/%m/%y') + timedelta(days=dias)
    data = data.replace(year=2000 + data.year % 100)

    return data.strftime('%d/%m/%Y')


def caminho_xml(pedido):
    caminho = BASE_PATH_PEDIDOS / pedido
    return caminho / f'arq_de_integracao {pedido}.xml'


def caminho_pdf(pedido):
    caminho = BASE_PATH_PEDIDOS / pedido
    return caminho / f'ordem_de_compra {pedido}.pdf'


def normalizar(texto):
    if texto is None:
        raise RuntimeError('Texto não encontrado')

    return unicodedata.normalize('NFKD', texto)\
        .encode('ASCII', 'ignore')\
        .decode()\
        .upper()
