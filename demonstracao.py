"""Demonstração desktop isolada, sem integrações operacionais."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from src.estado import EstadoPedido, EstadoPedidos
from src.resumo import ResumoExecucao

def simular(pedidos, modo, *, historico, ao_erro, ao_progresso, parar):
    resumo = ResumoExecucao(dict.fromkeys(pedidos, 'aguardando'))
    for indice, pedido in enumerate(pedidos, 1):
        if parar():
            break
        ao_progresso(pedido, indice, len(pedidos))
        if pedido.endswith('004'):
            decisao = ao_erro(pedido, ValueError('Falha sintética de demonstração.'), True, True)
            if decisao == 'encerrar':
                break
            if decisao == 'pular':
                resumo.situacoes[pedido] = 'falhou'
                continue
        for etapa in ('baixado', 'gravacao_pendente', 'importado', 'impressao_enviada'):
            if parar():
                break
            if pedido.endswith('003'):
                etapa = 'sem_cadastro'
            historico.salvar(EstadoPedido(pedido, '' if etapa in ('baixado','sem_cadastro') else str(9000+indice), etapa,
                                         erro='Produto sintético sem cadastro.' if etapa == 'sem_cadastro' else ''))
            Event().wait(.65)
            if etapa == 'sem_cadastro':
                break
        registro = historico.obter(pedido)
        resumo.situacoes[pedido] = registro.etapa if registro else 'aguardando'
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
                h.salvar(EstadoPedido('2026-999001', '8001', 'impressao_enviada'))
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
