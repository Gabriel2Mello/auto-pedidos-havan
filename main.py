import warnings
warnings.filterwarnings('ignore', category=UserWarning, module='pywinauto')
from time import perf_counter

from cloudscraper import create_scraper

from src.logs import setup_logging, get_logger
from src.login import realizar_login
from src.baixar import baixar_pedidos
from src.handle_app import inicia_app
from src.importar import importar_pedido
from src.imprimir import processar_impressao

logger = get_logger(__name__)


def input_pedido():
    pedidos_input = input('Pedido: ').strip()
    return [p.strip() for p in pedidos_input.split(',') if p.strip()]

def main():
    numero_pedidos = input_pedido()

    if not numero_pedidos:
        logger.info_split('Nenhum pedido informado. Encerrando...')
        return

    start_time = perf_counter()

    try:
        resultados = {}
        with create_scraper() as scraper:
            realizar_login(scraper)
            resultados = baixar_pedidos(scraper, numero_pedidos)

        pedido_grade, aba_pedido, grid, campos = inicia_app()

        for pedido in numero_pedidos:
            try:
                if not resultados[pedido]: continue

                logger.info_split(f'Importando: {pedido}')
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

            except Exception as e:
                logger.error_split(f'Erro no pedido {pedido}: {e}')

    except Exception as e:
        logger.critical_split(f'Erro fatal: {e}')

    finally:
        elapsed_time = perf_counter() - start_time
        logger.info_split(f'Terminado em {elapsed_time:0.2f} segundos.')
        input('Pressione Enter para fechar...')


if __name__ == '__main__':
    setup_logging()
    main()

