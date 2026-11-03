"""Mensagens para o operador, independentes da interface escolhida."""
import re

from src.erros import (
    BancoSisplanError, ConfiguracaoError, EstadoEmUsoError, EstadoError, PedidoRejeitadoError,
    SisplanError, SessaoPortalExpiradaError, NumeroInternoForaSequenciaError,
)


def mensagem_observacao(texto: str, pedido: str) -> str:
    """Padroniza a coluna sem modificar o diagnóstico salvo no histórico."""
    texto = texto.replace(
        f'O pedido {pedido} não existe no Portal Havan.',
        'Pedido não encontrado no Portal Havan.',
    )
    numero = re.escape(pedido)
    texto = re.sub(rf'^Pedido {numero}:\s*', '', texto)
    texto = re.sub(
        rf'^Gravação do pedido {numero} / interno \S+ não confirmada ',
        'Gravação do pedido não confirmada ', texto,
    )
    texto = re.sub(rf'\bdo pedido {numero}(?![\w-])', 'do pedido', texto)
    texto = texto.replace('Não consegui', 'Não foi possível')
    texto = texto.replace(
        'Não encontrei uma gravação única desse pedido no Sisplan para reimprimir.',
        'Não foi encontrada uma gravação única no Sisplan para reimprimir.',
    )
    texto = texto.replace(
        'Não foi possível baixar os arquivos do pedido. Verifique o portal ou a conexão.',
        'Não foi possível baixar os arquivos do pedido. Verifique o portal',
    )
    return texto[:1].upper() + texto[1:]


def mensagem_erro(erro: Exception) -> str:
    if isinstance(erro, NumeroInternoForaSequenciaError):
        return str(erro)
    if isinstance(erro, SessaoPortalExpiradaError):
        return str(erro)
    if isinstance(erro, ConfiguracaoError):
        return ('A configuração precisa ser corrigida. Pare este processamento, ajuste o arquivo '
                'e solicite novamente a etapa para aplicar os valores. '
                'Se alterou variáveis de ambiente do Windows, reabra o programa.')
    if isinstance(erro, EstadoEmUsoError):
        return ('Outra execução ainda está aberta ou terminando uma etapa. '
                'Feche-a pelo botão Encerrar e reabra o atalho após ela terminar.')
    if isinstance(erro, EstadoError):
        return 'Não consegui salvar ou ler o andamento. Avise o responsável antes de continuar.'
    if isinstance(erro, BancoSisplanError):
        return 'Não consegui confirmar as informações no Sisplan. Verifique a conexão ou avise o responsável.'
    if isinstance(erro, SisplanError):
        return 'Não consegui concluir uma ação na tela do Sisplan. É necessário conferir a tela.'
    if isinstance(erro, PedidoRejeitadoError):
        return str(erro)
    return 'Não foi possível concluir esta etapa. Os detalhes estão no log.'
