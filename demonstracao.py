"""Demonstração desktop isolada, sem integrações operacionais."""
import os
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from src.estado import EstadoPedido, EstadoPedidos
from src.resumo import ResumoExecucao
from src.etapas import ETAPAS_FINAIS, ETAPAS_INICIAIS, INCLUSOES_INCERTAS
from src.erros import (BancoSisplanError, EstadoError, GravacaoNaoConfirmadaError,
                       PedidoRejeitadoError, ProdutoSemCadastroError, SessaoPortalExpiradaError, SisplanError)


def cenarios_interface():
    """Roteiros de teste; preparar a lista não altera o histórico nem executa."""
    cenarios = [
        ('geral', 'Lote com sucesso e pendências', 'normal', '999002\n999003\n999004\n999015',
         'Confira e inicie. Deixe cadastro e falha de download pendentes para ver o resumo misto; depois use Retomar.'),
        ('entrada', 'Entrada inválida e repetida', 'normal', '999002\n999002\nINVALIDO\n999015',
         'Confira a contagem e o aviso de repetição. A entrada inválida bloqueia Conferir. Remova INVALIDO, confira e edite a lista para invalidar a conferência.'),
        ('existente', 'Pedido já existente', 'normal', '999001',
         'Inserir deve reconhecer o pedido existente sem nova inclusão ou impressão. Compare com Reimprimir.'),
        ('cadastro', 'Produto sem cadastro e nova tentativa', 'normal', '999003\n999015',
         'Na pausa, deixe pendente e continue. Filtre Produto sem cadastro e use Importar novamente: a nova solicitação simula o cadastro corrigido.'),
        ('download', 'Falha de download e decisões', 'normal', '999004\n999015',
         'Teste Tentar novamente, Deixar pendente e Parar. Uma nova tentativa solicitada simula a conexão recuperada.'),
        ('portal', 'Sessão expirada do portal', 'normal', '999005\n999015',
         'A pausa oferece Reconectar e continuar ou Parar, sem permitir pular. Reconectar simula uma nova sessão válida.'),
        ('banco', 'Banco indisponível', 'normal', '999006\n999015',
         'A consulta falha antes da inclusão. Tentar novamente simula a rede restabelecida; continuar para outro pedido fica bloqueado.'),
        ('retomada', 'Retomar de etapas diferentes', 'normal', '999009\n999010',
         'Execute uma vez para preparar um pedido Baixado e outro No Sisplan. Depois escolha Retomar: só o primeiro deve receber nova inclusão.'),
        ('reimprimir', 'Reimpressão com confirmação', 'reimprimir', '999001',
         'Conferir não envia nada. Iniciar só é liberado ao confirmar outra cópia. A execução reimprime sem contabilizar inclusão.'),
        ('impressao-pendente', 'Impressão pendente recuperável', 'normal', '999012',
         'A inclusão é confirmada, mas a impressora simulada está indisponível antes do envio. Tente novamente ou pare e use Retomar; não deve haver nova inclusão.'),
        ('impressao-incerta', 'Impressão incerta sem reenvio automático', 'normal', '999011',
         'Deixe pendente na pausa. Retomar deve continuar bloqueando o envio; só Reimprimir, com confirmação de outra cópia, libera a impressão.'),
        ('gravacao', 'Gravação incerta e conferência posterior', 'normal', '999007\n999015',
         'A gravação não é confirmada: repetir e pular ficam bloqueados. Pare e use Retomar para simular confirmação no banco, sem reincluir o primeiro pedido.'),
        ('aviso', 'Aviso pendente e existência confirmada', 'normal', '999008\n999015',
         'O aviso cancela a inclusão e bloqueia o lote até conferência. Pare e use Retomar: o pedido vira existente, sem impressão ou nova inclusão. Reimprimir permanece uma ação explícita.'),
        ('cancelamento', 'Cancelamento não confirmado', 'normal', '999014\n999015',
         'O cancelamento por produto sem cadastro não é confirmado. Repetir, pular e novas inclusões ficam bloqueados, inclusive após Retomar. Reabra a demonstração para limpar este bloqueio sintético.'),
        ('paginacao', 'Lista longa, filtros e paginação', 'normal', '\n'.join(str(n) for n in range(999100, 999160)),
         'Confira os 60 pedidos e a rolagem da conferência. Execute para simular pedidos existentes; teste Próxima/Anterior, busca por pedido/número interno e os escopos Lote atual/Todos.'),
        ('parada', 'Parar e encerrar durante o lote', 'normal', '999016\n999017\n999018',
         'Durante o processamento, use Parar. O passo em andamento termina num ponto seguro e os restantes ficam pendentes. Retome; teste também cancelar e confirmar o encerramento.'),
    ]
    return [{'id': id_, 'nome': nome, 'modo': modo, 'entrada': entrada, 'orientacao': orientacao}
            for id_, nome, modo, entrada, orientacao in cenarios]


class FalhaSimulada(Exception):
    def __init__(self, erro, repetir, pular, situacao='falhou'):
        self.erro, self.repetir, self.pular, self.situacao = erro, repetir, pular, situacao


def esperar_etapa():
    Event().wait(.35)


def _processar(pedido, modo, historico, resumo, salvar, parar):
    codigo = pedido.rsplit('-', 1)[-1]
    registro = historico.obter(pedido)
    existente = codigo == '999001' or codigo in {str(n) for n in range(999100, 999160)}
    numero = registro.numero if registro and registro.numero else str(8000 + int(codigo[-3:]))
    if modo == 'reimprimir':
        if not existente and (registro is None or registro.etapa in ETAPAS_INICIAIS or codigo == '999014'):
            raise FalhaSimulada(PedidoRejeitadoError('Demonstração: pedido sem gravação confirmada para reimprimir.'), True, True, 'rejeitado')
        salvar('importado', numero)
        resumo.retomados.add(pedido)
    else:
        if registro is None:
            raise RuntimeError('Pedido de demonstração não foi preservado na fila.')
        if registro.etapa in ETAPAS_FINAIS:
            resumo.situacoes[pedido] = 'existente'
            return
        if registro.etapa in INCLUSOES_INCERTAS:
            if codigo == '999014':
                raise FalhaSimulada(SisplanError('Demonstração: cancelamento ainda não confirmado.'), False, False, 'gravacao_pendente')
            if registro.etapa == 'aviso_pendente':
                salvar('existente', numero)
                resumo.situacoes[pedido] = 'existente'
                return
            salvar('importado', numero)
            resumo.retomados.add(pedido)
        elif registro.etapa in ('impressao_iniciada', 'impressao_incerta'):
            salvar('impressao_incerta', numero)
            raise FalhaSimulada(PedidoRejeitadoError('Demonstração: confira a fila e use Reimprimir para enviar outra cópia.'), False, True, 'impressao_incerta')
        elif registro.etapa in ETAPAS_INICIAIS:
            if existente:
                salvar('existente', numero)
                resumo.situacoes[pedido] = 'existente'
                return
            if any(p != pedido for p in historico.inclusoes_incertas()):
                raise FalhaSimulada(EstadoError('Há uma inclusão sintética anterior sem conferência.'), False, False)
            if not registro.erro:
                erros = {'999004': (PedidoRejeitadoError('Demonstração: falha temporária no download.'), True),
                         '999005': (SessaoPortalExpiradaError(), False),
                         '999006': (BancoSisplanError('Demonstração: banco indisponível antes de incluir.'), False)}
                if codigo in erros:
                    erro, pular = erros[codigo]
                    raise FalhaSimulada(erro, True, pular)
            preparar_pendencia = registro.etapa == 'para_baixar'
            if registro.etapa == 'para_baixar':
                salvar('baixado', '')
                if codigo == '999009':
                    resumo.situacoes[pedido] = 'aguardando'
                    return
            if codigo == '999003' and registro.etapa != 'sem_cadastro':
                salvar('sem_cadastro', '')
                raise FalhaSimulada(ProdutoSemCadastroError('Demonstração: produto sem cadastro. Use Importar novamente para simular o cadastro corrigido.'), True, True, 'sem_cadastro')
            if parar():
                return
            salvar('importacao_iniciada', '')
            if codigo == '999014':
                raise FalhaSimulada(SisplanError('Demonstração: cancelamento por produto sem cadastro não confirmado.'), False, False, 'gravacao_pendente')
            salvar('gravacao_pendente', numero)
            if codigo in ('999007', '999008'):
                if codigo == '999008':
                    salvar('aviso_pendente', '')
                raise FalhaSimulada(GravacaoNaoConfirmadaError('Demonstração: conferência no banco pendente.'), False, False, 'gravacao_pendente')
            # Uma parada não deixa a gravação artificialmente incerta.
            salvar('importado', numero)
            resumo.importados.add(pedido)
            if preparar_pendencia and codigo == '999010':
                resumo.situacoes[pedido] = 'impressao_pendente'
                return
        else:
            resumo.retomados.add(pedido)
        if codigo == '999012' and historico.obter(pedido).etapa == 'importado' and not registro.erro:
            salvar('impressao_pendente', numero)
            raise FalhaSimulada(PedidoRejeitadoError('Demonstração: impressora indisponível antes do envio.'), True, True, 'impressao_pendente')
    if parar():
        resumo.situacoes[pedido] = 'impressao_pendente'
        return
    salvar('pdf_pronto', numero)
    if parar():
        resumo.situacoes[pedido] = 'impressao_pendente'
        return
    salvar('impressao_iniciada', numero)
    if codigo == '999011' and modo != 'reimprimir':
        salvar('impressao_incerta', numero)
        raise FalhaSimulada(PedidoRejeitadoError('Demonstração: retorno do envio incerto; confira a fila antes de reimprimir.'), False, True, 'impressao_incerta')
    salvar('impressao_enviada', numero)
    resumo.situacoes[pedido] = 'impressao_enviada'

def simular(pedidos, modo, *, historico, ao_erro, ao_progresso, parar):
    resumo = ResumoExecucao(dict.fromkeys(pedidos, 'aguardando'))
    for indice, pedido in enumerate(pedidos, 1):
        if parar():
            break
        def salvar(etapa, numero):
            historico.salvar(EstadoPedido(pedido, numero, etapa, 2))
            ao_progresso(pedido, indice, len(pedidos))
            # Listas longas de existentes não precisam de animação por registro.
            if not 999100 <= int(pedido.rsplit('-', 1)[-1]) <= 999159:
                esperar_etapa()
        while not parar():
            ao_progresso(pedido, indice, len(pedidos))
            try:
                _processar(pedido, modo, historico, resumo, salvar, parar)
                break
            except FalhaSimulada as falha:
                registro = historico.obter(pedido)
                if registro is not None:
                    historico.salvar(replace(registro, erro=str(falha.erro)))
                resumo.situacoes[pedido] = falha.situacao
                decisao = ao_erro(pedido, falha.erro, falha.repetir, falha.pular)
                if decisao == 'repetir' and falha.repetir:
                    continue
                if decisao == 'pular' and falha.pular:
                    break
                return resumo
        ao_progresso(pedido, indice, len(pedidos))
    return resumo


def main():
    from desktop_havan import executar
    from src.controlador import EstadoInterface
    from src.interface_web import criar_servidor
    with TemporaryDirectory(prefix='havan-demo-') as pasta:
        anterior = os.environ.get('HAVAN_DESKTOP_DADOS')
        os.environ['HAVAN_DESKTOP_DADOS'] = pasta
        try:
            banco = Path(pasta) / 'estado.sqlite3'
            with EstadoPedidos(banco) as h:
                h.salvar(EstadoPedido(f'{datetime.now().year}-999001', '8001', 'impressao_enviada'))
            log = Path(pasta) / 'demo.log'
            log.write_text('Demonstração sintética de Pedidos Havan.\n', encoding='utf-8')
            estado = EstadoInterface(banco, executor=simular, codigo_execucao='DEMONSTRACAO', arquivo_log=log)
            servidor = None
            try:
                if not estado.pronto.wait(5) or estado.fase != 'PRONTO':
                    raise RuntimeError('O histórico de demonstração não ficou pronto.')
                servidor, _ = criar_servidor(estado, modo_desktop=True)
                servidor.demonstracao = True
                executar(servidor)
            finally:
                estado.encerrar()
                if servidor is not None:
                    servidor.server_close()
                estado.worker.join()
        finally:
            if anterior is None:
                os.environ.pop('HAVAN_DESKTOP_DADOS', None)
            else:
                os.environ['HAVAN_DESKTOP_DADOS'] = anterior
    return 0
