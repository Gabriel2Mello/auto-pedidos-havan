import xml.etree.ElementTree as ET


def xml_pedido(
    pedido: str = '2026-12345',
    barras_por_item: tuple[tuple[str, ...], ...] = (('0123456789012',),),
) -> ET.Element:
    root = ET.fromstring(
        '<OrdemCompra><Operacao>NORMAL</Operacao>'
        '<PrazoPagamento><PrevisaoData>15/10/26</PrevisaoData></PrazoPagamento>'
        '<DataInicialSemanaEntrega>20/10/26</DataInicialSemanaEntrega>'
        '</OrdemCompra>'
    )
    ET.SubElement(root, 'NumeroOrdemCompra').text = pedido
    itens = ET.SubElement(root, 'ItensOrdemCompra')
    for indice, barras in enumerate(barras_por_item):
        item = ET.SubElement(itens, 'ItemOrdemCompra')
        ET.SubElement(item, 'DescricaoProduto').text = f'PRODUTO {indice}'
        detalhe = ET.SubElement(item, 'DetalhamentoVariacoesItem')
        for barra in barras:
            variacao = ET.SubElement(detalhe, 'VariacaoItem')
            ET.SubElement(variacao, 'CodigoBarrasVariacao').text = barra
            ET.SubElement(variacao, 'DescricaoVariacaoCompleta').text = 'AZUL'
            ET.SubElement(variacao, 'QuantidadePrimariaTotalSolicitada').text = '1'
    return root
