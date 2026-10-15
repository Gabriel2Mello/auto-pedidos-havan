"""Interface de console para o operador, sem exigir argumentos de terminal."""

from src.contratos import DecisaoErro as DecisaoErro, Modo as Modo
from src.estado import EstadoPedidos
from src.erros import ConfiguracaoError, SessaoPortalExpiradaError
from src.mensagens import mensagem_erro as mensagem_erro
from src.pedidos import analisar_entrada_pedidos


def ler_pedidos() -> list[str]:
    while True:
        entrada = input('Digite os pedidos separados por vírgula (Enter para voltar): ')
        if not entrada.strip():
            return []
        try:
            pedidos = analisar_entrada_pedidos(entrada)
        except ValueError as erro:
            print(str(erro))
            continue
        if pedidos:
            return pedidos
        print('Nenhum número válido. Exemplo: 109335, 2026-109336.')


def escolher_operacao(historico: EstadoPedidos) -> tuple[Modo, list[str]] | None:
    while True:
        filas = historico.filas()
        pendentes = len(historico.pendentes())
        print('\nPEDIDOS HAVAN')
        print(f'A baixar: {filas["para_baixar"]} | Baixados: {filas["baixados"]} | '
              f'No Sisplan: {filas["importados"]} | Enviados para impressão: {filas["enviados"]}')
        if pendentes:
            print(f'Existem {pendentes} pedido(s) pendente(s). Escolha 2 para retomar.')
        print('1 - Inserir pedidos')
        print(f'2 - Retomar ({pendentes} pendentes)')
        print('3 - Reimprimir pedidos')
        print('0 - Sair')
        dica = ' (Enter para retomar)' if pendentes else ''
        escolha = input(f'Escolha uma opção{dica}: ').strip()
        if escolha == '0':
            return None
        if escolha == '2' or (not escolha and pendentes):
            if pendentes:
                return 'retomar', []
            print('Não existem pedidos pendentes.')
            continue
        if escolha in ('1', '3'):
            pedidos = ler_pedidos()
            if not pedidos:
                continue
            modo: Modo = 'normal' if escolha == '1' else 'reimprimir'
            if modo == 'normal':
                historico.adicionar_pedidos(pedidos)
            return modo, pedidos
        print('Opção inválida. Digite 1, 2, 3 ou 0.')


def perguntar_apos_erro(
    pedido: str, erro: Exception, pode_repetir: bool, pode_continuar: bool,
) -> DecisaoErro:
    print(f'\nO processamento parou no pedido {pedido}.')
    print(mensagem_erro(erro))
    print('Para o suporte, envie auto-pedidos.log e informe o código de execução exibido ao abrir.')
    if isinstance(erro, ConfiguracaoError):
        print('Os valores do arquivo serão lidos ao iniciar outro processamento ou Retomar.')
    elif not pode_repetir:
        print('Uma nova tentativa automática poderia repetir uma inclusão ou impressão. '
              'Confira o Sisplan ou a impressora com o responsável.')
        if pode_continuar:
            print('Para enviar outra cópia, confira a impressão e use a opção 3 - Reimprimir no menu.')
    while True:
        if pode_repetir:
            if isinstance(erro, SessaoPortalExpiradaError):
                print('1 - Reconectar ao Portal Havan e continuar este pedido')
            else:
                print('1 - Corrigi o problema e quero tentar este pedido novamente')
        if pode_continuar:
            print('2 - Deixar este pedido pendente e continuar os próximos')
        print('0 - Parar este processamento e voltar ao menu')
        escolha = input('O que deseja fazer? ').strip()
        if escolha == '1' and pode_repetir:
            return 'repetir'
        if escolha == '2' and pode_continuar:
            return 'pular'
        if escolha == '0':
            return 'encerrar'
        print('Escolha uma das opções exibidas.')
