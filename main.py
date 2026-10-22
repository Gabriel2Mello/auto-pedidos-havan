"""Entrada de console; o fluxo compartilhado fica em src.servico_pedidos."""

import argparse
import sys
from time import perf_counter

from src.banco import BancoSisplanError
from src.config import diretorio_aplicacao
from src.estado import EstadoError, EstadoPedidos
from src.logs import get_logger, setup_logging
from src.contratos import Modo
from src.menu import escolher_operacao, perguntar_apos_erro
from src.pedidos import analisar_entrada_pedidos
from src.servico_pedidos import processar_pedidos as processar_pedidos
from src.windows import set_app_id

logger = get_logger(__name__)


def main() -> int:
    try:
        setup_logging()
    except (OSError, ValueError) as error:
        print('Não foi possível abrir o arquivo de log. Nenhum pedido foi processado.')
        print(f'Arquivo: {diretorio_aplicacao() / "auto-pedidos.log"}')
        print(f'Informe ao responsável: {type(error).__name__}: {error}')
        try:
            input('Pressione Enter para fechar...')
        except (EOFError, KeyboardInterrupt):
            pass
        return 1
    parser = argparse.ArgumentParser(description='Automação de pedidos Havan')
    modos = parser.add_mutually_exclusive_group()
    modos.add_argument('--retomar', action='store_true', help='Retoma a fila pendente.')
    modos.add_argument('--reimprimir', metavar='PEDIDOS', help='Reenvia a impressão dos pedidos informados.')
    modos.add_argument('--reiniciar', metavar='PEDIDOS', help='Uso do responsável: nova tentativa após cancelar a inclusão anterior.')
    args = parser.parse_args()
    modo_cli: Modo | None = None
    pedidos_cli: list[str] = []
    try:
        if args.retomar:
            modo_cli = 'retomar'
        elif args.reimprimir is not None:
            modo_cli = 'reimprimir'
            pedidos_cli = analisar_entrada_pedidos(args.reimprimir)
        elif args.reiniciar is not None:
            modo_cli = 'reiniciar'
            pedidos_cli = analisar_entrada_pedidos(args.reiniciar)
    except ValueError as erro:
        parser.error(str(erro))
    if sys.platform == 'win32':
        set_app_id()
    codigo = 0
    try:
        with EstadoPedidos() as historico:
            while True:
                escolha = (modo_cli, pedidos_cli) if modo_cli is not None else escolher_operacao(historico)
                if escolha is None:
                    break
                modo, pedidos = escolha
                while True:
                    inicio = perf_counter()
                    try:
                        resumo = processar_pedidos(pedidos, modo, historico=historico, ao_erro=perguntar_apos_erro)
                        if any(situacao not in ('existente', 'impressao_enviada') for situacao in resumo.situacoes.values()):
                            codigo = 1
                        break
                    except Exception as error:
                        logger.exception('Falha ao iniciar o processamento; modo=%s pedidos=%s.', modo, pedidos)
                        decisao = perguntar_apos_erro(
                            pedidos[0] if pedidos else 'início do processamento', error,
                            isinstance(error, BancoSisplanError), False,
                        )
                        if decisao != 'repetir':
                            codigo = 1
                            break
                    finally:
                        logger.info('Tempo desta tentativa: %.2f segundos.', perf_counter() - inicio)
                if modo_cli is not None:
                    break
    except (EstadoError, KeyboardInterrupt) as error:
        codigo = 130 if isinstance(error, KeyboardInterrupt) else 1
        logger.exception('Execução encerrada sem iniciar novas ações: %s', error)
        print('O programa foi encerrado. As etapas já salvas serão preservadas.')
        if isinstance(error, EstadoError):
            input('Avise o responsável e envie auto-pedidos.log. Pressione Enter para fechar...')
    if modo_cli is not None:
        input('Pressione Enter para fechar...')
    return codigo


if __name__ == '__main__':
    from integracao_hub import executar_console
    raise SystemExit(executar_console('pedidos-havan', 'Pedidos Havan', main))
