from src.login import realizar_login
from src.baixar import baixar_pedidos
from src.handle_app import inicia_app
from src.importar import importar_pedido
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

    baixar_pedidos(scraper, numero_pedidos)

    pedido_grade, aba_pedido, grid, campos = inicia_app()

    for pedido in numero_pedidos:
        try:
            numero_interno = importar_pedido(pedido, pedido_grade, aba_pedido, grid, campos)
            print(f'\nInterno: {numero_interno}')


        except Exception as e:
            print(f'Erro no pedido {pedido}: {e}')


    elapsed_time = perf_counter() - start_time
    print(f'\nTerminado {elapsed_time:0.2f} segundos')



if __name__ == '__main__':
    main()

