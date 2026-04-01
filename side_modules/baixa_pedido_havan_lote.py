# Standart library
from os import environ
from time import perf_counter
from io import BytesIO
from os import getcwd
from pathlib import Path
# Third-party libraries
import cloudscraper
from bs4 import BeautifulSoup
import rarfile

rarfile.UNRAR_TOOL = environ['UNRAR_TOOL']

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0'

ORIGIN = 'https://cliente.havan.com.br'
BASE_URL = ORIGIN + '/Fornecedor'

def login(scraper):
    headers = {
        'User-Agent': USER_AGENT,
        'Referer': USER_AGENT + '/informativo',
        'Origin': ORIGIN
    }

    payload = {
        'TipoLogin': '0',
        'Documento': environ['CNPJ_MATRIZ'],
        'SenhaMd5': environ['SENHA_PORTAL']
    }

    scraper.get(
        url=BASE_URL + '/Login/Index'
    ).raise_for_status()

    scraper.post(
        url=BASE_URL + '/Login/FazerLogin?Length=5',
        headers=headers,
        data=payload,
        allow_redirects=True
    ).raise_for_status()


def get_pedido_compra(scraper):
    headers = {
        'User-Agent': USER_AGENT,
        'Referer': BASE_URL
    }

    scraper.get(
        url=BASE_URL + '/PedidoCompra/Index',
        headers=headers,
        allow_redirects=True
    ).raise_for_status()


def grid_pedido(scraper, pedido):
    headers = {
        'User-Agent': USER_AGENT,
        'Referer': BASE_URL + '/PedidoCompra/Index',
        'Origin': ORIGIN,
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
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


def baixar_arquivos(scraper, html, pedido):
    soup = BeautifulSoup(html, 'html.parser')

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

    raise RuntimeError(f"Pedido {pedido} não encontrado")


def salvar_arquivos(pdf, xml, pedido):
    base_dir = Path(getcwd())

    pasta_havan = base_dir / 'Havan Pedidos'
    pasta_pedido = pasta_havan / str(pedido)

    pasta_pedido.mkdir(parents=True, exist_ok=True)

    with open(pasta_pedido / f"Ordem de compra {pedido}.pdf", 'wb') as f:
        f.write(pdf)

    with open(pasta_pedido / f"Arq de integracao {pedido}.xml", 'wb') as f:
        f.write(xml)



def main():
    start_time = perf_counter()

    pedidos_input = input("Pedido: ").strip()
    numero_pedidos = [p.strip() for p in pedidos_input.split(',') if p.strip()]

    print('Processando...')

    scraper = cloudscraper.create_scraper()

    login(scraper)
    get_pedido_compra(scraper)

    for pedido in numero_pedidos:
        try:
            print('\nBaixando pedido: ', pedido)

            html_grid = grid_pedido(scraper, pedido)

            pdf, xml = baixar_arquivos(scraper, html_grid, pedido)

            salvar_arquivos(pdf, xml, pedido)

            print(f"Pedido {pedido} concluído")

        except Exception as e:
            print(f"Erro no pedido {pedido}: {e}")


    elapsed_time = perf_counter() - start_time
    print(f"\nDone in {elapsed_time:0.2f} seconds")



if __name__ == "__main__":
    main()

