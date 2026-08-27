import sys
from time import perf_counter, sleep

from cloudscraper import create_scraper

from src.baixar import baixar_pedidos
from src.config import ConfiguracaoError, validar_configuracao
from src.handle_app import inicia_app
from src.importar import importar_pedido
from src.imprimir import processar_impressao
from src.logs import setup_logging, get_logger
from src.login import realizar_login
from src.utils import SisplanError, input_pedido, set_app_id

setup_logging()
logger = get_logger(__name__)


def main() -> None:
    if sys.platform == 'win32':
        set_app_id()

    try:
        validar_configuracao()
    except ConfiguracaoError as error:
        logger.critical(f'AVISO: {error}')
        _ = input('\nPressione Enter para fechar...')
        return

    numero_pedidos = input_pedido()
    if not numero_pedidos:
        logger.info_split('Nenhum pedido informado. Encerrando...')
        sleep(2)
        return

    start_time = perf_counter()

    try:
        with create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True
            }
        ) as scraper:
            realizar_login(scraper)
            resultados = baixar_pedidos(scraper, numero_pedidos)

        pedido_grade, aba_pedido, grid, campos = inicia_app()
        for pedido in numero_pedidos:
            try:
                if not resultados.get(pedido):
                    continue

                numero_interno, invalido = importar_pedido(
                    pedido,
                    pedido_grade,
                    aba_pedido,
                    grid,
                    campos
                )
                if invalido:
                    continue
                logger.info(f'Número interno: {numero_interno}')

                processar_impressao(pedido, numero_interno)

            except (KeyboardInterrupt, SystemExit, SisplanError):
                raise

            except Exception as error:
                logger.exception('Erro inesperado no pedido %s: %s', pedido, error)

    except SisplanError as error:
        logger.critical_split(f'Erro fatal: {error}')
    except Exception as error:
        logger.exception('Erro fatal inesperado: %s', error)

    finally:
        elapsed_time = perf_counter() - start_time
        logger.info_split(f'Terminado em {elapsed_time:0.2f} segundos.')
        _ = input('Pressione Enter para fechar...')


if __name__ == '__main__':
    main()

