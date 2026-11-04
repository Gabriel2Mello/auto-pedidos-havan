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
         'Baixe e confira. Revise dois aptos, um sem cadastro e um download pendente. Importe apenas os aptos; corrija os demais pelas ações da lista.'),
        ('entrada', 'Entrada inválida e repetida', 'normal', '999002\n999002\nINVALIDO\n999015',
         'Confira a contagem. A entrada inválida bloqueia Baixar e conferir. Remova INVALIDO e prepare a lista; os repetidos são contados uma vez.'),
        ('existente', 'Pedido já existente', 'normal', '999001',
         'Baixar e conferir reconhece o existente sem download, nova inclusão ou impressão.'),
        ('cadastro', 'Produto sem cadastro e nova tentativa', 'normal', '999003\n999015',
         'Baixe e confira. Filtre Produtos sem cadastro e use Conferir cadastro novamente: simula cadastro corrigido e libera a importação, que exige outro clique.'),
        ('download', 'Falha de download e decisões', 'normal', '999004\n999015',
         'Baixe e confira: o download falho fica em Outras pendências. Use Baixar e conferir na linha para simular recuperação; depois importe o apto.'),
        ('portal', 'Sessão expirada do portal', 'normal', '999005\n999015',
         'A pausa oferece Reconectar e continuar ou Parar, sem permitir pular. Reconectar simula uma nova sessão válida.'),
        ('banco', 'Banco indisponível', 'normal', '999006\n999015',
         'A consulta falha antes da inclusão. Tentar novamente simula a rede restabelecida; continuar para outro pedido fica bloqueado.'),
        ('retomada', 'Retomar de etapas diferentes', 'normal', '999009\n999010',
         'Baixe e confira e importe os aptos. Um pedido ficará com impressão pendente. Use Retomar impressão na linha, sem nova inclusão.'),
        ('impressao-pendente', 'Impressão pendente recuperável', 'normal', '999012',
         'Baixe, confira e importe. A impressora falha após a gravação. Tente novamente ou pare e use Retomar impressão na linha, sem nova inclusão.'),
        ('impressao-incerta', 'Impressão incerta sem reenvio automático', 'normal', '999011',
         'Baixe, confira e importe. Deixe pendente na pausa; Confira a fila de impressão com o responsável.'),
        ('gravacao', 'Gravação incerta e conferência posterior', 'normal', '999007\n999015',
         'Após baixar, conferir e importar, repetir e pular ficam bloqueados. Pare e use Conferir gravação no Sisplan na linha, sem reincluir.'),
        ('aviso', 'Aviso pendente e existência confirmada', 'normal', '999008\n999015',
         'Após baixar, conferir e importar, pare no aviso e use Conferir gravação no Sisplan na linha. O pedido vira existente sem impressão ou nova inclusão.'),
        ('cancelamento', 'Cancelamento não confirmado', 'normal', '999014\n999015',
         'Baixe, confira e importe. O cancelamento não confirmado bloqueia repetir, pular e novas inclusões, inclusive após conferir gravação. Teste por último e reabra para limpar.'),
        ('paginacao', 'Lista longa, filtros e paginação', 'normal', '\n'.join(str(n) for n in range(999100, 999160)),
         'Baixe e confira os 60 existentes; teste paginação, busca, filtros e os escopos Lote em conferência/Todos. Não há aptos para importar.'),
        ('parada', 'Parar e encerrar durante o lote', 'normal', '999016\n999017\n999018',
         'Pare durante o preparo ou a importação. Confira os estados salvos e solicite a próxima ação pela lista. Teste cancelar e confirmar o encerramento.'),
    ]
    return [{'id': id_, 'nome': nome, 'modo': modo, 'entrada': entrada, 'orientacao': orientacao}
            for id_, nome, modo, entrada, orientacao in cenarios]


class FalhaSimulada(Exception):
    def __init__(self, erro, repetir, pular, situacao='falhou'):
        self.erro, self.repetir, self.pular, self.situacao = erro, repetir, pular, situacao


def esperar_etapa():
    Event().wait(.35)


def _preparar(pedido, modo, historico, resumo, salvar, parar):
    registro = historico.obter(pedido)
    if registro is None:
        raise RuntimeError('Pedido de demonstração não preservado.')
    codigo = pedido.rsplit('-', 1)[-1]
    if registro.etapa not in ETAPAS_INICIAIS:
        resumo.situacoes[pedido] = 'existente' if registro.etapa in ETAPAS_FINAIS else 'aguardando'
        return
    if codigo == '999001' or 999100 <= int(codigo) <= 999159:
        salvar('existente', str(8000 + int(codigo[-3:])))
        resumo.situacoes[pedido] = 'existente'
        return
    if not registro.erro:
        erros = {'999004': (PedidoRejeitadoError('Demonstração: download não concluído. Use Baixar e conferir novamente.'), True),
                 '999005': (SessaoPortalExpiradaError(), False),
                 '999006': (BancoSisplanError('Demonstração: banco indisponível.'), False)}
        if codigo in erros:
            erro, pular = erros[codigo]
            raise FalhaSimulada(erro, True, pular)
    if modo == 'revalidar' and registro.etapa == 'para_baixar':
        raise FalhaSimulada(PedidoRejeitadoError('Arquivos ausentes. Use Baixar e conferir.'), False, True)
    salvar('baixado', '')
    if codigo == '999003' and modo != 'revalidar':
        salvar('sem_cadastro', '')
        raise FalhaSimulada(ProdutoSemCadastroError('EAN 0123456789012 (Produto sintético / Azul) sem cadastro. Use Conferir cadastro novamente após corrigir.'), True, True, 'sem_cadastro')
    if not parar():
        salvar('pronto_importar', '')
        resumo.situacoes[pedido] = 'pronto_importar'


def _processar(pedido, modo, historico, resumo, salvar, parar):
    codigo = pedido.rsplit('-', 1)[-1]
    registro = historico.obter(pedido)
    existente = codigo == '999001' or codigo in {str(n) for n in range(999100, 999160)}
    numero = registro.numero if registro and registro.numero else str(8000 + int(codigo[-3:]))
    if modo in ('preparar', 'revalidar'):
        _preparar(pedido, modo, historico, resumo, salvar, parar)
        return
    if modo == 'importar' and (registro is None or registro.etapa != 'pronto_importar' or registro.erro):
        raise FalhaSimulada(PedidoRejeitadoError('Pedido não está pronto para importar.'), False, True)
    if modo == 'recuperar' and (registro is None or registro.etapa in (*ETAPAS_INICIAIS, *ETAPAS_FINAIS)):
        raise FalhaSimulada(PedidoRejeitadoError('Recuperar não pode incluir pedidos novos.'), False, False)
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
        raise FalhaSimulada(PedidoRejeitadoError('Demonstração: confira a fila de impressão com o responsável.'), False, True, 'impressao_incerta')
    elif registro.etapa in ETAPAS_INICIAIS:
        if existente:
            salvar('existente', numero)
            resumo.situacoes[pedido] = 'existente'
            return
        if any(p != pedido for p in historico.inclusoes_incertas()):
            raise FalhaSimulada(EstadoError('Há uma inclusão sintética anterior sem conferência.'), False, False)
        if modo != 'importar' and not registro.erro:
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
        if modo != 'importar' and codigo == '999003' and registro.etapa != 'sem_cadastro':
            salvar('sem_cadastro', '')
            raise FalhaSimulada(ProdutoSemCadastroError('Demonstração: produto sem cadastro. Use Conferir cadastro novamente para simular o cadastro corrigido.'), True, True, 'sem_cadastro')
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
        if (preparar_pendencia or modo == 'importar') and codigo == '999010':
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
    if codigo == '999011':
        salvar('impressao_incerta', numero)
        raise FalhaSimulada(PedidoRejeitadoError('Demonstração: retorno do envio incerto; confira a fila de impressão com o responsável.'), False, True, 'impressao_incerta')
    salvar('impressao_enviada', numero)
    resumo.situacoes[pedido] = 'impressao_enviada'

def simular(pedidos, modo, *, historico, ao_erro, ao_progresso, parar):
    if modo not in ('normal', 'retomar', 'preparar', 'revalidar', 'importar', 'recuperar', 'reiniciar'):
        raise ValueError('Operação não disponível.')
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
                if modo in ('preparar', 'revalidar') and isinstance(falha.erro, PedidoRejeitadoError):
                    break
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
            estado = EstadoInterface(banco, executor=simular, codigo_execucao='DEMONSTRACAO', arquivo_log=log,
                                     impressora='Impressora de teste',
                                     listar_filas=lambda: ['Impressora de teste', 'PDF de teste'],
                                     salvar_fila=lambda nome: None)
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
