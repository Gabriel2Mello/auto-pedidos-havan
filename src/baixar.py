import logging
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed

import rarfile
from bs4 import BeautifulSoup
from tqdm import tqdm

from src.config import (
    USER_AGENT,
    BASE_URL,
    ORIGIN,
    UNRAR_TOOL,
    CONTENT_TYPE
)
from src.utils import caminho_pdf, caminho_xml

logger = logging.getLogger(__name__)

rarfile.UNRAR_TOOL = UNRAR_TOOL

GRID_PEDIDO_URL = f'{BASE_URL}/PedidoCompra/GridIndexPedidoCompra'
PEDIDO_INDEX_URL = f'{BASE_URL}/PedidoCompra/Index'

DEFAULT_HEADERS = {
    'User-Agent': USER_AGENT,
    'Referer': PEDIDO_INDEX_URL,
    'Origin': ORIGIN,
    'Content-Type': CONTENT_TYPE
}


def html_grid_pedido(scraper, pedido):
    payload = {
        'Pedido': str(pedido),
        'OpcaoSituacaoPedidoCompra': 'T',
        'OpcaoStatusNotaFiscal': '0'
    }

    response = scraper.post(
        url=GRID_PEDIDO_URL,
        headers=DEFAULT_HEADERS,
        data=payload
    )
    response.raise_for_status()

    return response.text


def extrair_xml(content):
    with rarfile.RarFile(BytesIO(content)) as rf:
        xml_files = [f for f in rf.namelist() if f.lower().endswith('.xml')]
        if not xml_files:
            raise FileNotFoundError('RAR sem arquivo XML.')

        with rf.open(xml_files[0]) as f:
            return f.read()


def links_pedido(html_content, pedido):
    soup = BeautifulSoup(html_content, 'lxml')

    for grupo in soup.select('div.hvn-group'):
        tag_pedido = grupo.select_one('dt + dd')

        if not tag_pedido or not tag_pedido.contents:
            continue

        numero = str(tag_pedido.contents[0]).strip()

        if numero != str(pedido):
            continue

        ordem_href = grupo.select_one('a[title*="Ordem de compra"]')
        integracao_href = grupo.select_one('a[title*="Arq. de integra"]')

        if not ordem_href or not integracao_href:
            raise RuntimeError('Pedido encontrado, mas link ausente')

        ordem_url = f"{ORIGIN}{ordem_href['href']}"
        integracao_url = f"{ORIGIN}{integracao_href['href']}"

        return ordem_url, integracao_url

    raise RuntimeError(f'Pedido {pedido} não encontrado')


def baixar_arquivos(scraper, pedido):
    html_grid = html_grid_pedido(scraper, pedido)
    url_pdf, url_rar = links_pedido(html_grid, pedido)

    response_pdf = scraper.get(url_pdf)
    response_rar = scraper.get(url_rar)

    response_pdf.raise_for_status()
    response_rar.raise_for_status()

    return response_pdf.content, extrair_xml(response_rar.content)


def salvar_arquivos(pdf, xml, pedido):
    arquivos = {
        caminho_pdf(pedido): pdf,
        caminho_xml(pedido): xml
    }

    for caminho, conteudo in arquivos.items():
        caminho.parent.mkdir(parents=True, exist_ok=True)

        with open(caminho, 'wb') as f:
            f.write(conteudo)


def processar_unico(scraper, pedido):
    try:
        pdf, xml = baixar_arquivos(scraper, pedido)
        salvar_arquivos(pdf, xml, pedido)

        return pedido, True

    except Exception as e:
        logger.error(f'\nErro no pedido {pedido}: {e}')
        return pedido, False


def baixar_pedidos(scraper, numero_pedidos, max_threads=10):
    resultados = {}

    print('\nIniciando processo de download...')

    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = {
            executor.submit(processar_unico, scraper, pedido): pedido
            for pedido in numero_pedidos
        }

        tqdm_format='{l_bar}{bar:20}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]'
        for future in tqdm(
            as_completed(futures),
            total=len(futures),
            desc='Baixando',
            bar_format=tqdm_format):

            pedido, sucesso = future.result()
            resultados[pedido] = sucesso


    print('\nRESUMO DOS PEDIDOS:')
    for pedido, sucesso in resultados.items():
        status = 'Baixado' if sucesso else 'Falhou'
        print(f'{pedido}: {status}')

