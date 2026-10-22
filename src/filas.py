"""Validação dos arquivos locais para retomar sem repetir downloads concluídos."""

import xml.etree.ElementTree as ET
from io import BytesIO

from pypdf import PdfReader

from src.logs import get_logger
from src.pedidos import validar_xml_pedido
from src.arquivos import (caminho_pdf, caminho_xml)
from src.gravacao_download import verificar_download_pendente

logger = get_logger(__name__)


def validar_arquivos_baixados(pdf: bytes, xml: bytes, pedido: str) -> None:
    validar_xml_pedido(ET.fromstring(xml), pedido)
    with BytesIO(pdf) as arquivo:
        if not PdfReader(arquivo).pages:
            raise ValueError('Ordem de compra sem páginas')


def conferir_arquivos_baixados(pedido: str) -> bool:
    # Recuperação pendente exige intervenção, não equivale a arquivo ausente.
    verificar_download_pendente(caminho_pdf(pedido).parent)
    try:
        validar_arquivos_baixados(caminho_pdf(pedido).read_bytes(), caminho_xml(pedido).read_bytes(), pedido)
        return True
    except FileNotFoundError:
        logger.debug('Pedido %s: arquivos locais ausentes; download necessário.', pedido)
        return False
    except Exception:
        logger.warning('Pedido %s: arquivos locais ausentes ou inválidos; download necessário.', pedido, exc_info=True)
        return False
