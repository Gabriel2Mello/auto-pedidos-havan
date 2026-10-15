import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from re import fullmatch
from typing import Literal, TypedDict

from src.config import PRODUTOS_GOVERNADOR


class DadosPedido(TypedDict):
    data_fatura: str
    data_entrega: str
    produto: str
    operacao: str


def normalizar_pedidos(entrada: str, ano: int | None = None) -> list[str]:
    """Valida os números, completa o ano e remove repetições preservando a ordem."""
    if not entrada.strip():
        return []

    ano_pedido = ano if ano is not None else datetime.now().year
    pedidos: list[str] = []

    for item in entrada.split(','):
        pedido = item.strip()
        if not pedido:
            continue

        if fullmatch(r'[0-9]{4,}', pedido):
            pedido = f'{ano_pedido}-{pedido}'

        if (
            fullmatch(r'[0-9]{4}-[0-9]{4,}', pedido)
            and len(pedido) <= 50
            and pedido not in pedidos
        ):
            pedidos.append(pedido)

    return pedidos


def analisar_entrada_pedidos(entrada: str, *, permitir_vazio: bool = False, ano: int | None = None) -> list[str]:
    """Recusa a lista inteira se algum numero estiver incorreto."""
    texto = entrada.replace('\r', '\n').replace('\n', ',')
    invalidos = [item.strip() for item in texto.split(',')
                 if item.strip() and not normalizar_pedidos(item, ano)]
    if invalidos:
        raise ValueError('Não entendi estes números: ' + ', '.join(invalidos)[:400] + '. Confira e digite a lista novamente.')
    pedidos = normalizar_pedidos(texto, ano)
    if not pedidos and not permitir_vazio:
        raise ValueError('Informe pelo menos um pedido.')
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


@dataclass(frozen=True)
class VariacaoPedido:
    barra: str
    produto: str
    variacao: str
    quantidade: Decimal = Decimal('1')


@dataclass(frozen=True)
class ItemEsperado:
    codigo: str
    cor: str
    tamanho: str
    quantidade: Decimal


def validar_xml_pedido(root: ET.Element, pedido: str) -> list[VariacaoPedido]:
    """Valida a identificação, os dados e todas as barras antes da inclusão."""
    numero_xml = root.findtext('NumeroOrdemCompra', '').strip()
    if numero_xml != pedido:
        raise ValueError(
            f'Número do XML ({numero_xml or "vazio"}) difere do pedido {pedido}'
        )

    # Valida também os campos e datas usados pela importação na interface.
    extrair_dados_xml(root)
    itens = root.findall('./ItensOrdemCompra/ItemOrdemCompra')
    if not itens:
        raise ValueError('XML sem itens de compra')

    resultado: list[VariacaoPedido] = []
    for item in itens:
        produto = item.findtext('DescricaoProduto', '').strip()
        if not produto:
            raise ValueError('Item do XML sem descrição do produto')
        variacoes = item.findall('./DetalhamentoVariacoesItem/VariacaoItem')
        if not variacoes:
            raise ValueError(f'Produto sem variações no XML: {produto}')
        for variacao in variacoes:
            barra = variacao.findtext('CodigoBarrasVariacao', '').strip()
            descricao = variacao.findtext('DescricaoVariacaoCompleta', '').strip()
            if not fullmatch(r'[0-9]{13}', barra):
                raise ValueError(
                    f'Código de barras inválido: {barra or "vazio"} '
                    f'({produto} / {descricao})'
                )
            texto_quantidade = variacao.findtext('QuantidadePrimariaTotalSolicitada', '').strip()
            try:
                quantidade = Decimal(texto_quantidade.replace(',', '.'))
            except InvalidOperation:
                raise ValueError(f'Quantidade inválida no XML: {barra}') from None
            if not quantidade.is_finite() or quantidade <= 0:
                raise ValueError(f'Quantidade inválida no XML: {barra}')
            resultado.append(VariacaoPedido(barra, produto, descricao, quantidade))
    return resultado

