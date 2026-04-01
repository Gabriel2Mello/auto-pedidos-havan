from src.config import USER_AGENT, ORIGIN, BASE_URL, CNPJ_MATRIZ, SENHA_PORTAL


def realizar_login(scraper):
    headers = {
        'User-Agent': USER_AGENT,
        'Referer': USER_AGENT + '/informativo',
        'Origin': ORIGIN
    }

    payload = {
        'TipoLogin': '0',
        'Documento': CNPJ_MATRIZ,
        'SenhaMd5': SENHA_PORTAL
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

    get_pedido_compra(scraper)


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

