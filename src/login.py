from typing import TYPE_CHECKING

from requests.exceptions import RequestException, Timeout

from src.logs import get_logger
from src.utils import LoginInvalidoError
from src.config import (
    DEFAULT_HEADERS,
    BASE_URL,
    CNPJ_MATRIZ,
    SENHA_PORTAL,
)

if TYPE_CHECKING:
    from cloudscraper import ScraperMock

LOGIN_INDEX_URL = f'{BASE_URL}/Login/Index'
FAZER_LOGIN_URL = f'{BASE_URL}/Login/FazerLogin?Length=5'
PEDIDO_COMPRA_URL = f'{BASE_URL}/PedidoCompra/Index'
REQUEST_TIMEOUT = (5, 10)

logger = get_logger(__name__)


def configurar_sessao(scraper: 'ScraperMock') -> None:
    scraper.headers.update(DEFAULT_HEADERS)


def realizar_login(scraper: 'ScraperMock') -> None:
    logger.info_split('Entrando no Portal Havan')
    configurar_sessao(scraper)

    payload = {
        'TipoLogin': '0',
        'Documento': CNPJ_MATRIZ,
        'SenhaMd5': SENHA_PORTAL,
    }

    try:
        scraper.get(
            url=LOGIN_INDEX_URL,
            timeout=REQUEST_TIMEOUT,
        ).raise_for_status()

        scraper.post(
            url=FAZER_LOGIN_URL,
            headers={'Referer': LOGIN_INDEX_URL},
            data=payload,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True
        ).raise_for_status()

        get_pedido_compra(scraper)
        logger.info('Sucesso')

    except LoginInvalidoError as error:
        logger.debug('Redirecionado para login via JS')
        raise RuntimeError(str(error)) from error

    except Timeout as error:
        logger.debug('Timeout no Login Havan: %s', error)
        raise RuntimeError('Site demorou muito para responder') from error

    except RequestException as error:
        logger.debug('Erro no site da Havan: %s', error)
        raise RuntimeError('Falha de comunicação com o site') from error

    except Exception as error:
        logger.debug('ERRO DESCONHECIDO NO LOGIN: %s', error, exc_info=True)
        raise RuntimeError('Ocorreu um erro inesperado no Login') from error


def get_pedido_compra(scraper: 'ScraperMock') -> None:
    response = scraper.get(
        url=PEDIDO_COMPRA_URL,
        headers={'Referer': BASE_URL},
        allow_redirects=True,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()

    if 'Login/Index' in response.url:
        raise LoginInvalidoError()

