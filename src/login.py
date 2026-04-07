from src.config import (
    USER_AGENT,
    ORIGIN,
    BASE_URL,
    CNPJ_MATRIZ,
    SENHA_PORTAL
)

LOGIN_INDEX_URL   = f'{BASE_URL}/Login/Index'
FAZER_LOGIN_URL   = f'{BASE_URL}/Login/FazerLogin?Length=5'
PEDIDO_COMPRA_URL = f'{BASE_URL}/PedidoCompra/Index'


def configurar_sessao(scraper):
    scraper.headers.update({
        'User-Agent': USER_AGENT,
        'Origin': ORIGIN
    })


def realizar_login(scraper):
    configurar_sessao(scraper)

    payload = {
        'TipoLogin': '0',
        'Documento': CNPJ_MATRIZ,
        'SenhaMd5': SENHA_PORTAL
    }

    scraper.get(url=LOGIN_INDEX_URL).raise_for_status()

    scraper.post(
        url=FAZER_LOGIN_URL,
        headers={'Referer': LOGIN_INDEX_URL},
        data=payload,
        allow_redirects=True
    ).raise_for_status()

    get_pedido_compra(scraper)


def get_pedido_compra(scraper):
    scraper.get(
        url=PEDIDO_COMPRA_URL,
        headers={'Referer': BASE_URL},
        allow_redirects=True
    ).raise_for_status()

