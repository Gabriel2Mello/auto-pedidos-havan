from src.config import USER_AGENT, BASE_URL, ORIGIN, BASE_PATH_PEDIDOS, UNRAR_TOOL, CONTENT_TYPE
from io import BytesIO
# Third-party libraries
import rarfile
from bs4 import BeautifulSoup

rarfile.UNRAR_TOOL = UNRAR_TOOL

def grid_pedido(scraper, pedido):
    headers = {
        'User-Agent': USER_AGENT,
        'Referer': BASE_URL + '/PedidoCompra/Index',
        'Origin': ORIGIN,
        'Content-Type': CONTENT_TYPE
    }

    data = {
        'Pedido': f"{pedido}",
        'OpcaoSituacaoPedidoCompra': 'T',
        'OpcaoStatusNotaFiscal': '0'
    }

    response = scraper.post(
        url=BASE_URL + '/PedidoCompra/GridIndexPedidoCompra',
        headers=headers,
        data=data
    )
    response.raise_for_status()

    return response.text


def extrair_xml(content):
    with rarfile.RarFile(BytesIO(content)) as rf:
        nome_xml = rf.namelist()[0]

        with rf.open(nome_xml) as f:
            return f.read()


def baixar_arquivos(scraper, pedido):
    html_grid = grid_pedido(scraper, pedido)

    soup = BeautifulSoup(html_grid, 'html.parser')

    for grupo in soup.select('div.hvn-group'):
        pedido_texto = grupo.select_one('dt + dd')

        if not pedido_texto:
            continue

        numero = str(pedido_texto.contents[0]).strip()

        if numero == pedido:
            ordem = grupo.select_one('a[title*="Ordem de compra"]')
            integracao = grupo.select_one('a[title*="Arq. de integra"]')

            if not ordem or not integracao:
                raise RuntimeError('Pedido não encontrado')

            ordem_url = ORIGIN + str(ordem['href'])
            integracao_url = ORIGIN + str(integracao['href'])

            ordem_pdf = scraper.get(ordem_url)
            integracao_rar = scraper.get(integracao_url)

            ordem_pdf.raise_for_status()
            integracao_rar.raise_for_status()

            return ordem_pdf.content, extrair_xml(integracao_rar.content)

    raise RuntimeError(f'Pedido {pedido} não encontrado')


def salvar_arquivos(pdf, xml, pedido):
    pasta_havan = BASE_PATH_PEDIDOS / 'Havan Pedidos'
    pasta_pedido = pasta_havan / str(pedido)

    pasta_pedido.mkdir(parents=True, exist_ok=True)

    with open(
        pasta_pedido / f'Ordem de compra {pedido}.pdf', 'wb'
    ) as f:
        f.write(pdf)

    with open(
        pasta_pedido / f'Arq de integracao {pedido}.xml', 'wb'
    ) as f:
        f.write(xml)

