from src.config import (
    USER_AGENT,
    BASE_URL,
    ORIGIN,
    BASE_PATH_PEDIDOS,
    UNRAR_TOOL,
    CONTENT_TYPE
)
from src.utils import caminho_pdf, caminho_xml

from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed
# Third-party libraries
import rarfile
from bs4 import BeautifulSoup
from tqdm import tqdm

rarfile.UNRAR_TOOL = UNRAR_TOOL

GRID_PEDIDO_URL = f'{BASE_URL}/PedidoCompra/GridIndexPedidoCompra'
PEDIDO_INDEX_URL = f'{BASE_URL}/PedidoCompra/Index'

DEFAULT_HEADERS = {
    'User-Agent': USER_AGENT,
    'Referer': PEDIDO_INDEX_URL,
    'Origin': ORIGIN,
    'Content-Type': CONTENT_TYPE
}

def grid_pedido(scraper, pedido):
    data = {
        'Pedido': f"{pedido}",
        'OpcaoSituacaoPedidoCompra': 'T',
        'OpcaoStatusNotaFiscal': '0'
    }

    response = scraper.post(
        url=GRID_PEDIDO_URL,
        headers=DEFAULT_HEADERS,
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


def salvar(caminho, arquivo):
    with open(caminho, 'wb') as f:
        f.write(arquivo)


def salvar_arquivos(pdf, xml, pedido):
    pasta_pedido = BASE_PATH_PEDIDOS / str(pedido)
    pasta_pedido.mkdir(parents=True, exist_ok=True)

    salvar(caminho_pdf(pedido), pdf)
    salvar(caminho_xml(pedido), xml)


def processar(scraper, pedido):
    try:
        pdf, xml = baixar_arquivos(scraper, pedido)
        salvar_arquivos(pdf, xml, pedido)

        return True

    except Exception as e:
        print(f'Erro no pedido {pedido}: {e}')
        return False


def baixar_pedidos(scraper, numero_pedidos):
    max_threads = 10
    resultados = {}

    print('\nIniciando processo de download...')

    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = {
            executor.submit(processar, scraper, pedido): pedido
            for pedido in numero_pedidos
        }

        format='{l_bar}{bar:20}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]'
        for future in tqdm(
            as_completed(futures),
            total=len(futures),
            desc='Baixando',
            bar_format=format
        ):

            pedido = futures[future]

            try:
                sucesso = future.result()
                resultados[pedido] = sucesso
            except Exception as e:
                print(f'Erro inesperado no pedido {pedido}: {e}')
                resultados[pedido] = False

    print('\nRESUMO DOS PEDIDOS:')
    for pedido, sucesso in resultados.items():
        status = 'Baixado' if sucesso else 'Falhou'
        print(f'{pedido}: {status}')


