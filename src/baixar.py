from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from requests.exceptions import RequestException, Timeout
from tqdm import tqdm

from src.logs import get_logger
from src.config import (
    BASE_URL,
    ORIGIN,
    CONTENT_TYPE,
)
from src.utils import (
    caminho_pdf,
    caminho_xml,
    extrair_xml,
    salvar_pedido_txt,
)

if TYPE_CHECKING:
    from cloudscraper import ScraperMock

logger = get_logger(__name__)

GRID_PEDIDO_URL = f'{BASE_URL}/PedidoCompra/GridIndexPedidoCompra'
PEDIDO_INDEX_URL = f'{BASE_URL}/PedidoCompra/Index'
REQUEST_TIMEOUT = (5, 10)

DEFAULT_HEADERS = {
    'Referer': PEDIDO_INDEX_URL,
    'Content-Type': CONTENT_TYPE,
}


def baixar_pedidos(
    scraper: 'ScraperMock',
    numero_pedidos: list[str],
    max_threads: int = 1,
) -> dict[str, bool]:
    resultados: dict[str, bool] = {}
    logger.info_split('Iniciando processo de download...')

    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures: dict[Future[tuple[str, bool, str | None]], str] = {
            executor.submit(processar_unico, scraper, pedido): pedido
            for pedido in numero_pedidos
        }

        with tqdm(
            total=len(futures),
            desc='Baixando',
            bar_format='{l_bar}{bar:20}| {n_fmt}/{total_fmt} [{elapsed}]'
        ) as pbar:
            for future in as_completed(futures):
                pedido, sucesso, erro = future.result()

                resultados[pedido] = sucesso

                if not sucesso:
                    pbar.write(f'Erro no pedido {pedido}: {erro}')

                pbar.update()

    exibir_resumo(resultados)
    return resultados


def processar_unico(
    scraper: 'ScraperMock',
    pedido: str,
) -> tuple[str, bool, str | None]:
    if len(pedido) < 9:
        return pedido, False, 'Número de pedido muito curto'

    try:
        pdf, xml = baixar_arquivos(scraper, pedido)
        salvar_arquivos(pdf, xml, pedido)
        return pedido, True, None

    except Exception as error:
        return pedido, False, str(error)


def baixar_arquivos(scraper: 'ScraperMock', pedido: str) -> tuple[bytes, bytes]:
    html_grid = html_grid_pedido(scraper, pedido)
    url_pdf, url_rar = links_pedido(html_grid, pedido)

    with ThreadPoolExecutor(max_workers=2) as executor:
        f_pdf = executor.submit(scraper.get, url_pdf, timeout=REQUEST_TIMEOUT)
        f_rar = executor.submit(scraper.get, url_rar, timeout=REQUEST_TIMEOUT)

        response_pdf = f_pdf.result()
        response_rar = f_rar.result()

    response_pdf.raise_for_status()
    response_rar.raise_for_status()

    return response_pdf.content, extrair_xml(response_rar.content)


def html_grid_pedido(scraper: 'ScraperMock', pedido: str) -> str:
    payload = {
        'Pedido': str(pedido),
        'OpcaoSituacaoPedidoCompra': 'T',
        'OpcaoStatusNotaFiscal': '0',
    }

    try:
        response = scraper.post(
            url=GRID_PEDIDO_URL,
            headers=DEFAULT_HEADERS,
            data=payload,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.text

    except Timeout as error:
        logger.debug('Timeout(Grid Havan) no pedido %s: %s', pedido, error)
        raise RuntimeError(
            'Site da Havan demorou muito para responder'
        ) from error

    except RequestException as error:
        logger.debug('Pedido %s erro no site da Havan: %s', pedido, error)
        raise RuntimeError('Falha de comunicação com a Havan') from error

    except Exception as error:
        logger.debug('ERRO DESCONHECIDO NO GRID: %s', error, exc_info=True)
        raise RuntimeError(
            'Ocorreu um erro inesperado no Grid do site'
        ) from error


def links_pedido(html_content: str, pedido: str) -> tuple[str, str]:
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

        if dd_pedido.get_text(strip=True) != pedido:
            continue

        ordem = grupo.select_one('a[title*="Ordem de compra"]')
        integracao = grupo.select_one('a[title*="Arq. de integra"]')

        if not ordem or not integracao:
            raise RuntimeError('Pedido encontrado, mas link ausente')

        ordem_url = urljoin(ORIGIN, str(ordem['href']))
        integracao_url = urljoin(ORIGIN, str(integracao['href']))

        return ordem_url, integracao_url

    raise RuntimeError('Pedido não encontrado na grade')


def salvar_arquivos(pdf: bytes, xml: bytes, pedido: str) -> None:
    arquivos = {
        caminho_pdf(pedido): pdf,
        caminho_xml(pedido): xml,
    }

    for path, data in arquivos.items():
        path.parent.mkdir(parents=True, exist_ok=True)

        path.write_bytes(data)


def exibir_resumo(resultados: dict[str, bool]) -> None:
    logger.info_split('RESUMO DOS PEDIDOS:')
    for pedido, sucesso in resultados.items():
        status = 'Baixado' if sucesso else 'Falhou'
        logger.info(f'{pedido}: {status}')

    for pedido, sucesso in resultados.items():
        if not sucesso:
            salvar_pedido_txt(pedido)

