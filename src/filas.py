"""Validação dos arquivos locais para retomar sem repetir downloads concluídos."""

import xml.etree.ElementTree as ET

from pypdf import PdfReader

from src.logs import get_logger
from src.pedidos import validar_xml_pedido
from src.arquivos import (caminho_pdf, caminho_xml)

logger = get_logger(__name__)


def conferir_arquivos_baixados(pedido: str) -> bool:
    try:
        root = ET.parse(caminho_xml(pedido)).getroot()
        validar_xml_pedido(root, pedido)
        with caminho_pdf(pedido).open('rb') as arquivo:
            if not PdfReader(arquivo).pages:
                raise ValueError('Ordem de compra sem páginas')
        return True
    except Exception:
        logger.warning('Pedido %s: arquivos locais ausentes ou inválidos; download necessário.', pedido, exc_info=True)
        return False
