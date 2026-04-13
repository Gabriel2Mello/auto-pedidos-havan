import logging
import re
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed

import rarfile
from bs4 import BeautifulSoup
from tqdm import tqdm

from src.config import (
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
    'Referer': PEDIDO_INDEX_URL,
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
        xml_file = next((f for f in rf.namelist() if f.lower().endswith('.xml')), None)
        if not xml_file:
            raise FileNotFoundError('RAR sem arquivo XML.')

        return rf.read(xml_file)


def links_pedido(html_content, pedido):
    soup = BeautifulSoup(html_content, 'lxml')

    for grupo in soup.select('div.hvn-group'):
        dts = grupo.find_all('dt')
        dd_pedido = None

        for dt in dts:
            if 'pedido' in dt.get_text().lower():
                dd_pedido = dt.find_next_sibling('dd')
                break

        if not dd_pedido:
            continue

        try:
            numero_extraido = str(dd_pedido.contents[0]).strip()
        except (IndexError, AttributeError):
            continue

        if numero_extraido != pedido:
            continue

        ordem = grupo.select_one('a[title*="Ordem de compra"]')
        integracao = grupo.select_one('a[title*="Arq. de integra"]')

        if not ordem or not integracao:
            raise RuntimeError('Pedido encontrado, mas link ausente')

        ordem_url = f"{ORIGIN}{ordem['href']}"
        integracao_url = f"{ORIGIN}{integracao['href']}"

        return ordem_url, integracao_url

    raise RuntimeError(f'Pedido {pedido} não encontrado na grade')


def baixar_arquivos(scraper, pedido):
    html_grid = html_grid_pedido(scraper, pedido)
    url_pdf, url_rar = links_pedido(html_grid, pedido)

    with ThreadPoolExecutor(max_workers=2) as executor:
        f_pdf = executor.submit(scraper.get, url_pdf)
        f_rar = executor.submit(scraper.get, url_rar)

        response_pdf = f_pdf.result()
        response_rar = f_rar.result()

    response_pdf.raise_for_status()
    response_rar.raise_for_status()

    return response_pdf.content, extrair_xml(response_rar.content)


def salvar_arquivos(pdf, xml, pedido):
    arquivos = {
        caminho_pdf(pedido): pdf,
        caminho_xml(pedido): xml
    }

    for path, data in arquivos.items():
        path.parent.mkdir(parents=True, exist_ok=True)

        path.write_bytes(data)


def processar_unico(scraper, pedido):
    try:
        pdf, xml = baixar_arquivos(scraper, pedido)
        salvar_arquivos(pdf, xml, pedido)

        return pedido, True

    except Exception as e:
        logger.error(f'Erro no pedido {pedido}: {e}')
        return pedido, False


def baixar_pedidos(scraper, numero_pedidos, max_threads=10):
    resultados = {}
    print('\nIniciando processo de download...')

    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = {
            executor.submit(processar_unico, scraper, pedido): pedido
            for pedido in numero_pedidos
        }

        tqdm_args= {
            'total': len(futures),
            'desc': 'Baixando',
            'bar_format': '{l_bar}{bar:20}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]'
        }

        for future in tqdm(as_completed(futures), **tqdm_args):
            pedido, sucesso = future.result()
            resultados[pedido] = sucesso

    exibir_resumo(resultados)


def exibir_resumo(resultados):
    print('\nRESUMO DOS PEDIDOS:')
    for pedido, sucesso in resultados.items():
        status = 'Baixado' if sucesso else 'Falhou'
        print(f'{pedido}: {status}')

