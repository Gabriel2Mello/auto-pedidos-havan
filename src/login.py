from typing import TYPE_CHECKING
from requests.exceptions import Timeout, RequestException

from src.logs import get_logger
from src.utils import LoginInvalidoError
from src.config import (
    USER_AGENT,
    ORIGIN,
    BASE_URL,
    CNPJ_MATRIZ,
    SENHA_PORTAL
)

if TYPE_CHECKING:
    from cloudscraper import ScraperMock

LOGIN_INDEX_URL   = f'{BASE_URL}/Login/Index'
FAZER_LOGIN_URL   = f'{BASE_URL}/Login/FazerLogin?Length=5'
PEDIDO_COMPRA_URL = f'{BASE_URL}/PedidoCompra/Index'

logger = get_logger(__name__)


def configurar_sessao(scraper: 'ScraperMock') -> None:
    scraper.headers.update({
        'User-Agent': USER_AGENT,
        'Origin': ORIGIN
    })


def realizar_login(scraper: 'ScraperMock') -> None:
    logger.info_split('Entrando no Portal Havan')
    configurar_sessao(scraper)

    payload = {
        'TipoLogin': '0',
        'Documento': CNPJ_MATRIZ,
        'SenhaMd5':  SENHA_PORTAL
    }

    try:
        scraper.get(url=LOGIN_INDEX_URL).raise_for_status()

        scraper.post(
            url=FAZER_LOGIN_URL,
            headers={'Referer': LOGIN_INDEX_URL},
            data=payload,
            timeout=(5,10),
            allow_redirects=True
        ).raise_for_status()

        get_pedido_compra(scraper)
        logger.info('Sucesso')

    except LoginInvalidoError as e:
        logger.debug('Redirecionado para login via JS')
        raise RuntimeError(e)

    except Timeout as e:
        logger.debug(f'Timeout no Login Havan: {e}')
        raise RuntimeError('Site demorou muito para responder')

    except RequestException as e:
        logger.debug(f'Erro no site da Havan: {e}')
        raise RuntimeError('Falha de comunicação com o site')

    except Exception as e:
        logger.debug(f'ERRO DESCONHECIDO NO LOGIN: {e}', exc_info=True)
        raise RuntimeError('Ocorreu um erro inesperado no Login')


def get_pedido_compra(scraper: 'ScraperMock') -> None:
    response = scraper.get(
        url=PEDIDO_COMPRA_URL,
        headers={'Referer': BASE_URL},
        allow_redirects=True
    )
    response.raise_for_status()

    if "window.location='/Fornecedor/Login/Index'" in response.text:
        raise LoginInvalidoError()

