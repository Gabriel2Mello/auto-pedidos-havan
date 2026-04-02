from src.login import realizar_login
from src.baixar_pedidos import pool_pedidos
from time import perf_counter
# Third-party libraries
from cloudscraper import create_scraper


def input_pedido():
    pedidos_input = input('Pedido: ').strip()
    return [p.strip() for p in pedidos_input.split(',') if p.strip()]


def main():
    numero_pedidos = input_pedido()

    start_time = perf_counter()

    scraper = create_scraper()
    realizar_login(scraper)

    pool_pedidos(scraper, numero_pedidos)


    """
    for pedido in numero_pedidos:
        try:
            print('\nBaixando pedido:', pedido)

            pdf, xml = baixar_arquivos(scraper, pedido)

            salvar_arquivos(pdf, xml, pedido)

            print(f'Pedido {pedido} concluído')

        except Exception as e:
            print(f'Erro no pedido {pedido}: {e}')
    """

    elapsed_time = perf_counter() - start_time
    print(f'\nDone in {elapsed_time:0.2f} seconds')



if __name__ == '__main__':
    main()
