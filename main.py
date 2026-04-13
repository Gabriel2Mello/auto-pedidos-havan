from time import perf_counter
import logging

from cloudscraper import create_scraper

from src.login import realizar_login
from src.baixar import baixar_pedidos
from src.handle_app import inicia_app
from src.importar import importar_pedido
from src.imprimir import processar_impressao

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def input_pedido():
    pedidos_input = input('Pedido: ').strip()
    return [p.strip() for p in pedidos_input.split(',') if p.strip()]


def main():
    numero_pedidos = input_pedido()

    if not numero_pedidos:
        logger.warning('Nenhum pedido informado. Encerrando...')
        return

    start_time = perf_counter()

    try:
        """
        with create_scraper() as scraper:
            realizar_login(scraper)
            baixar_pedidos(scraper, numero_pedidos)
        """
        pedido_grade, aba_pedido, grid, campos = inicia_app()

        for pedido in numero_pedidos:
            try:
                print(f'\nImportando: {pedido}')
                numero_interno = importar_pedido(
                    pedido,
                    pedido_grade,
                    aba_pedido,
                    grid,
                    campos
                )

                print(f'\nInterno: {numero_interno}')
                processar_impressao(pedido, numero_interno)

            except Exception as e:
                logger.error(f'Erro no pedido {pedido}: {e}')

    except Exception as e:
        logger.critical(f'Erro fatal: {e}')

    finally:
        elapsed_time = perf_counter() - start_time
        print(f'\nTerminado em {elapsed_time:0.2f} segundos.')


if __name__ == '__main__':
    main()

