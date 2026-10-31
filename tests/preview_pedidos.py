"""Prévia isolada: histórico temporário, executor sintético, nenhuma integração real.

Execute com o Python do projeto: python -m tests.preview_pedidos
Os números terminados em 003 simulam falta de cadastro; 004 pausam para decisão.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from src.controlador import EstadoInterface
from src.estado import EstadoPedido, EstadoPedidos
from src.interface_web import criar_servidor
from src.resumo import ResumoExecucao


def executar(pedidos, modo, *, historico, ao_erro, ao_progresso, parar):
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
    with TemporaryDirectory(prefix='havan-previa-') as pasta:
        banco = Path(pasta) / 'estado.sqlite3'
        with EstadoPedidos(banco) as h:
            for indice, etapa in enumerate(('impressao_enviada', 'para_baixar', 'sem_cadastro', 'impressao_incerta'), 1):
                h.salvar(EstadoPedido(f'2026-99900{indice}', str(8000+indice) if indice in (1,4) else '', etapa,
                                     erro='Exemplo sintético para conferência.' if indice in (3,4) else ''))
        estado = EstadoInterface(banco, executor=executar, codigo_execucao='PREVIA-SINTETICA', arquivo_log=Path(pasta)/'previa.log')
        estado.pronto.wait(5)
        servidor, _ = criar_servidor(estado)
        print(f'http://127.0.0.1:{servidor.server_port}', flush=True)
        try:
            servidor.serve_forever(poll_interval=.1)
        finally:
            servidor.server_close()
            estado.worker.join(10)


if __name__ == '__main__':
    main()
