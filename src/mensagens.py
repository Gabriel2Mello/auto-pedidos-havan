"""Mensagens para o operador, independentes da interface escolhida."""
from src.erros import (
    BancoSisplanError, ConfiguracaoError, EstadoEmUsoError, EstadoError, PedidoRejeitadoError,
    SisplanError, SessaoPortalExpiradaError, NumeroInternoForaSequenciaError,
)


def mensagem_erro(erro: Exception) -> str:
    if isinstance(erro, NumeroInternoForaSequenciaError):
        return str(erro)
    if isinstance(erro, SessaoPortalExpiradaError):
        return str(erro)
    if isinstance(erro, ConfiguracaoError):
        return ('A configuração precisa ser corrigida. Pare este processamento, ajuste o arquivo '
                'e inicie outro processamento ou use Retomar para aplicar os valores. '
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
