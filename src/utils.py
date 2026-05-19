from datetime import datetime, timedelta
from io import BytesIO
import unicodedata
import xml.etree.ElementTree as ET

import rarfile

from src.logs import get_logger
from src.config import BASE_PATH_PEDIDOS, UNRAR_TOOL

logger = get_logger(__name__)
rarfile.UNRAR_TOOL = UNRAR_TOOL


def input_pedido(ano=None):
    if not ano:
        ano = str(datetime.now().year)

    pedidos_input = input('Pedido: ').strip()
    if not pedidos_input:
        return None

    return [f"{ano}-{p.strip()}" for p in pedidos_input.split(',') if p.strip()]


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


class LoginInvalidoError(Exception):
    """Exceção para quando o site retorna 200, mas falhou o login"""
    def __init__(self, message="CNPJ ou senha inválidos"):
        self.message = message
        super().__init__(self.message)


class SisplanError(Exception):
    def __init__(self, message="Falha na tela do Sisplan"):
        self.message = message
        super().__init__(self.message)

