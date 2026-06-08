from time import sleep, perf_counter
import ctypes
import sys
from src.logs import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)

from cloudscraper import create_scraper

from src.login import realizar_login
from src.baixar import baixar_pedidos
from src.handle_app import inicia_app
from src.importar import importar_pedido
from src.imprimir import processar_impressao
from src.utils import input_pedido, SisplanError


def set_app_id() -> None:
    try:
        my_app_id = 'g2mello.autopedidoshavan.v1'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(my_app_id)
    except Exception:
        pass


def main() -> None:
    if sys.platform == 'win32':
        set_app_id()

    numero_pedidos = input_pedido()
    if not numero_pedidos:
        logger.info_split('Nenhum pedido informado. Encerrando...')
        sleep(2)
        return

    start_time = perf_counter()

    try:
        with create_scraper() as scraper:
            realizar_login(scraper)
            resultados = baixar_pedidos(scraper, numero_pedidos)

        pedido_grade, aba_pedido, grid, campos = inicia_app()
        for pedido in numero_pedidos:
            try:
                if not resultados.get(pedido): continue

                numero_interno, duplicado = importar_pedido(
                    pedido,
                    pedido_grade,
                    aba_pedido,
                    grid,
                    campos
                )
                if duplicado: continue
                logger.info(f'Número interno: {numero_interno}')

                processar_impressao(pedido, numero_interno)

            except (KeyboardInterrupt, SystemExit, SisplanError):
                raise

            except Exception as e:
                logger.error(f'Erro no pedido: {e}')

    except (SisplanError, Exception) as e:
        logger.critical_split(f'Erro fatal: {e}')

    finally:
        elapsed_time = perf_counter() - start_time
        logger.info_split(f'Terminado em {elapsed_time:0.2f} segundos.')
        _ = input('Pressione Enter para fechar...')


if __name__ == '__main__':
    main()

