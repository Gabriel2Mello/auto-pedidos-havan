from typing import TYPE_CHECKING

from requests.exceptions import RequestException, Timeout

from src.logs import get_logger
from src.protocolo_login_havan import entrar_no_portal
from src.erros import (LoginInvalidoError, SessaoPortalExpiradaError)
from src.config import (
    DEFAULT_HEADERS,
    BASE_URL,
    configuracao_atual,
)

if TYPE_CHECKING:
    from cloudscraper import ScraperMock, ResponseMock

REQUEST_TIMEOUT = (5, 10)

logger = get_logger(__name__)


def conferir_sessao(response: 'ResponseMock', *, html: bool = False) -> None:
    voltou_login = '/login/' in response.url.lower() or response.status_code == 401
    if html:
        texto = response.text.lower()
        voltou_login = voltou_login or ('<form' in texto and 'senhamd5' in texto)
    if voltou_login:
        raise SessaoPortalExpiradaError()


def configurar_sessao(scraper: 'ScraperMock') -> None:
    scraper.headers.update(DEFAULT_HEADERS)


def realizar_login(scraper: 'ScraperMock') -> None:
    logger.info_split('Entrando no Portal Havan')
    configurar_sessao(scraper)

    config = configuracao_atual()
    try:
        url = entrar_no_portal(scraper, base=BASE_URL, documento=config.cnpj_matriz,
                              senha=config.senha_portal, timeout=REQUEST_TIMEOUT)
        if 'Login/Index' in url:
            raise LoginInvalidoError()
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
