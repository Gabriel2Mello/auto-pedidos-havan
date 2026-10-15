"""Seleciona os pedidos aptos antes de qualquer inclusão pela interface."""

from src.erros import PedidoRejeitadoError as PedidoRejeitadoError
import xml.etree.ElementTree as ET
from typing import Sequence
from decimal import Decimal

from src.banco import BancoSisplan, ProdutoCadastrado
from src.logs import get_logger
from src.pedidos import ItemEsperado, VariacaoPedido, validar_xml_pedido
from src.arquivos import (caminho_xml, carregar_xml, salvar_pedido_txt)

logger = get_logger(__name__)


def validar_pedido_baixado(banco: BancoSisplan, pedido: str) -> list[ItemEsperado]:
    try:
        variacoes = validar_xml_pedido(carregar_xml(caminho_xml(pedido)), pedido)
    except (OSError, ET.ParseError, ValueError, RuntimeError) as error:
        registrar_rejeicao(pedido, [f'XML inválido: {error}'])
        raise PedidoRejeitadoError(f'Não consegui validar o XML do pedido {pedido}: {error}') from error
    cadastradas = banco.consultar_barras(sorted({v.barra for v in variacoes}))
    pendencias = pendencias_barras(variacoes, cadastradas)
    if pendencias:
        registrar_rejeicao(pedido, pendencias)
        raise PedidoRejeitadoError('; '.join(pendencias))
    totais: dict[ProdutoCadastrado, Decimal] = {}
    for variacao in variacoes:
        produto = next(iter(cadastradas[variacao.barra]))
        totais[produto] = totais.get(produto, Decimal(0)) + variacao.quantidade
    return [ItemEsperado(p.codigo, p.cor, p.tamanho, quantidade)
            for p, quantidade in totais.items()]


def pendencias_barras(
    variacoes: Sequence[VariacaoPedido],
    cadastradas: dict[str, set[ProdutoCadastrado]],
) -> list[str]:
    pendencias: list[str] = []
    for variacao in variacoes:
        produtos = cadastradas.get(variacao.barra, set())
        if len(produtos) == 1:
            continue
        situacao = 'não cadastrado' if not produtos else 'com cadastro ambíguo'
        pendencias.append(
            f'Código de barras {situacao}: {variacao.barra} '
            f'({variacao.produto} / {variacao.variacao})'
        )
    return list(dict.fromkeys(pendencias))


def registrar_rejeicao(pedido: str, motivos: Sequence[str]) -> None:
    for motivo in motivos:
        logger.error('Pedido %s ignorado: %s', pedido, motivo)
        # Uma linha por pendência evita perder barras no limite de tamanho do TXT.
        salvar_pedido_txt(pedido, motivo=motivo)
