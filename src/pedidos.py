import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Literal, TypedDict

from src.config import PRODUTOS_GOVERNADOR


class DadosPedido(TypedDict):
    data_fatura: str
    data_entrega: str
    produto: str
    operacao: str


def normalizar_pedidos(entrada: str, ano: int | None = None) -> list[str]:
    """Limpa uma entrada CSV e completa pedidos curtos com o ano informado."""
    if not entrada.strip():
        return []

    ano_pedido = ano if ano is not None else datetime.now().year
    pedidos: list[str] = []

    for item in entrada.split(','):
        pedido = item.strip()
        if not pedido:
            continue

        if len(pedido) < 9:
            pedido = f'{ano_pedido}-{pedido}'

        if len(pedido) >= 9:
            pedidos.append(pedido)

    return pedidos


def formata_data(data_xml: str, dias: int = 0) -> str:
    data = datetime.strptime(data_xml, '%d/%m/%y') + timedelta(days=dias)
    return data.strftime('%d/%m/%Y')


def normalizar(texto: str) -> str:
    if not texto:
        raise RuntimeError('Texto não encontrado')

    return (
        unicodedata.normalize('NFKD', texto)
        .encode('ASCII', 'ignore')
        .decode()
        .upper()
    )


def extrair_dados_xml(root: ET.Element) -> DadosPedido:
    campos_xml = {
        'data_fatura': root.findtext('.//PrazoPagamento/PrevisaoData', ''),
        'data_entrega': root.findtext('.//DataInicialSemanaEntrega', ''),
        'produto': root.findtext('.//DescricaoProduto', ''),
        'operacao': root.findtext('.//Operacao', ''),
    }

    if not all(campos_xml.values()):
        raise RuntimeError('Dados não encontrados no XML')

    return {
        'data_fatura': formata_data(campos_xml['data_fatura']),
        'data_entrega': formata_data(campos_xml['data_entrega']),
        'produto': normalizar(campos_xml['produto']),
        'operacao': normalizar(campos_xml['operacao']),
    }


def definir_empresa(produto: str) -> Literal['MATRIZ', 'FILIAL']:
    return (
        'MATRIZ'
        if any(normalizar(nome) in produto for nome in PRODUTOS_GOVERNADOR)
        else 'FILIAL'
    )

