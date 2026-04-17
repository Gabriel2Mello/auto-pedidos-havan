from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.exceptions import Timeout, RequestException

from bs4 import BeautifulSoup
from tqdm import tqdm

from src.logs import get_logger
from src.config import (
    BASE_URL,
    ORIGIN,
    CONTENT_TYPE
)
from src.utils import (
    caminho_pdf,
    caminho_xml,
    extrair_xml
)

logger = get_logger(__name__)


GRID_PEDIDO_URL =  f'{BASE_URL}/PedidoCompra/GridIndexPedidoCompra'
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

    try:
        response = scraper.post(
            url=GRID_PEDIDO_URL,
            headers=DEFAULT_HEADERS,
            data=payload,
            timeout=(5,5)
        )
        response.raise_for_status()
        return response.text

    except Timeout as e:
        logger.debug(f'Timeout(Grid Havan) no pedido {pedido}: {e}')
        raise RuntimeError('Site da Havan demorou muito para responder')

    except RequestException as e:
        logger.debug(f'Pedido {pedido} erro no site da Havan: {e}')
        raise RuntimeError('Falha de comunicação com a Havan')

    except Exception as e:
        logger.debug(f'ERRO DESCONHECIDO NO GRID: {e}', exc_info=True)
        raise RuntimeError('Ocorreu um erro inesperado no Grid do site')


def links_pedido(html_content, pedido):
    soup = BeautifulSoup(html_content, 'lxml')

    for grupo in soup.select('div.hvn-group'):
        dts = grupo.find_all('dt')
        dd_pedido = None

        for dt in dts:
            if 'pedido' in dt.get_text().lower():
                dd_pedido = dt.find_next_sibling('dd')
                break

        if not dd_pedido: continue

        try:
            numero_extraido = str(dd_pedido.contents[0]).strip()
        except (IndexError, AttributeError):
            continue

        if numero_extraido != pedido: continue

        ordem = grupo.select_one('a[title*="Ordem de compra"]')
        integracao = grupo.select_one('a[title*="Arq. de integra"]')

        if not ordem or not integracao:
            raise RuntimeError('Pedido encontrado, mas link ausente')

        ordem_url =      f"{ORIGIN}{ordem['href']}"
        integracao_url = f"{ORIGIN}{integracao['href']}"

        return ordem_url, integracao_url

    raise RuntimeError(f'Pedido não encontrado na grade')


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
    if len(str(pedido)) < 9:
        return pedido, False, 'Número de pedido muito curto'

    try:
        pdf, xml = baixar_arquivos(scraper, pedido)
        salvar_arquivos(pdf, xml, pedido)
        return pedido, True, None

    except Exception as e:
        return pedido, False, str(e)


def baixar_pedidos(scraper, numero_pedidos, max_threads=10):
    resultados = {}
    logger.info_split('Iniciando processo de download...')

    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = {
            executor.submit(processar_unico, scraper, pedido): pedido
            for pedido in numero_pedidos
        }

        tqdm_args= {
            'total': len(futures),
            'desc': 'Baixando',
            'bar_format': '{l_bar}{bar:20}| {n_fmt}/{total_fmt} [{elapsed}]'
        }

        with tqdm(as_completed(futures), **tqdm_args) as pbar:
            for future in pbar:
                pedido, sucesso, erro = future.result()
                resultados[pedido] = sucesso

                if not sucesso:
                    pbar.write(f'Erro no pedido {pedido}: {erro}')

    exibir_resumo(resultados)
    return resultados


def exibir_resumo(resultados):
    logger.info_split('RESUMO DOS PEDIDOS:')
    for pedido, sucesso in resultados.items():
        status = 'Baixado' if sucesso else 'Falhou'
        logger.info(f'{pedido}: {status}')

