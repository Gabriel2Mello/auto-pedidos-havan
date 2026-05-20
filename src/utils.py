from datetime import datetime, timedelta
from io import BytesIO
from typing import cast
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

import rarfile

from src.logs import get_logger
from src.config import BASE_PATH_PEDIDOS, UNRAR_TOOL

logger = get_logger(__name__)
rarfile.UNRAR_TOOL = UNRAR_TOOL


def input_pedido(ano: str | None=None) -> list[str] | None:
    if not ano:
        ano = str(datetime.now().year)

    pedidos_input = input('Pedido: ').strip()
    if not pedidos_input:
        return None

    return [f"{ano}-{p.strip()}" for p in pedidos_input.split(',') if p.strip()]


def formata_data(data_xml: str, dias: int=0) -> str:
    data = datetime.strptime(data_xml, '%d/%m/%y') + timedelta(days=dias)
    return data.strftime('%d/%m/%Y')


def caminho_xml(pedido: str) -> Path:
    caminho = BASE_PATH_PEDIDOS / str(pedido)
    return caminho / f'arq_de_integracao {pedido}.xml'


def caminho_pdf(pedido: str) -> Path:
    caminho = BASE_PATH_PEDIDOS / str(pedido)
    return caminho / f'ordem_de_compra {pedido}.pdf'


def normalizar(texto: str) -> str:
    if not texto:
        raise RuntimeError('Texto não encontrado')

    return unicodedata.normalize('NFKD', texto)\
        .encode('ASCII', 'ignore')\
        .decode()\
        .upper()


def carregar_xml(arquivo: str | Path) -> ET.Element:
    return ET.parse(arquivo).getroot()


def extrair_xml(content: bytes) -> bytes:
    with rarfile.RarFile(BytesIO(content)) as rf:
        arquivos = cast(list[str], rf.namelist())

        xml_file: str | None = next(
            (f for f in arquivos
             if f.lower().endswith('.xml')),
            None
        )

        if not xml_file:
            raise FileNotFoundError('.RAR sem arquivo XML')

        return cast(bytes, rf.read(xml_file))


class LoginInvalidoError(Exception):
    """Exceção para quando o site retorna 200, mas falhou o login"""
    def __init__(self, message: str="CNPJ ou senha inválidos") -> None:
        super().__init__(message)


class SisplanError(Exception):
    def __init__(self, message: str="Falha na tela do Sisplan") -> None:
        super().__init__(message)

