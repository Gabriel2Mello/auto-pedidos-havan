"""Abre Pedidos Havan no navegador do próprio computador."""

import sys
import logging
from contextlib import ExitStack
from integracao_hub import IntegracaoLocal, MedidorAbertura, executar_interface
from sincronizar_estatisticas import Sincronizador


def informar_falha(mensagem: str) -> None:
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, mensagem, 'Pedidos Havan', 0x10)
    else:
        print(mensagem, file=sys.stderr)


def main(publicacao: IntegracaoLocal, *, desktop=False) -> int:
    with MedidorAbertura('pedidos-havan') as medidor, ExitStack() as recursos:
        with medidor.etapa('sincronizacao'):
            sincronizador = recursos.enter_context(Sincronizador(aplicacao='pedidos-havan', relatar=logging.getLogger(__name__).info))
        try:
            return executar_painel(publicacao, medidor, desktop=desktop)
        finally:
            recursos.close()
            if sincronizador.worker is not None:
                sincronizador.worker.join()


def executar_painel(publicacao: IntegracaoLocal, medidor: MedidorAbertura | None = None, *, desktop=False) -> int:
    medidor = medidor or MedidorAbertura('pedidos-havan')
    try:
        with medidor.etapa('importacoes'):
            from src.controlador import EstadoInterface
            from src.interface_web import criar_servidor
            from src.logs import get_logger, setup_logging
            from src.windows import set_app_id
    except ImportError as erro:
        publicacao.registrar_falha(erro)
        informar_falha('Faltam dependências da instalação. Solicite ao responsável a instalação '
                       'de requirements.txt no Python usado por este atalho.')
        return 1
    try:
        with medidor.etapa('log_operacional'):
            codigo = setup_logging(console=sys.stdout is not None)
    except (OSError, ValueError) as erro:
        publicacao.registrar_falha(erro)
        informar_falha(f'Não foi possível abrir auto-pedidos.log. Nenhum pedido foi iniciado.\n'
                       f'Informe ao responsável: {type(erro).__name__}: {erro}')
        return 1
    with medidor.etapa('identidade_windows'):
        set_app_id()
    with medidor.etapa('estado_e_worker'):
        estado = EstadoInterface(codigo_execucao=codigo, medidor_abertura=medidor)
    servidor = None
    try:
        with medidor.etapa('servidor_local'):
            servidor, _ = criar_servidor(estado, modo_desktop=desktop)
        url = f'http://127.0.0.1:{servidor.server_port}'
        get_logger(__name__).info('Interface local iniciada: %s', url)
        servidor_ativo = servidor
        with medidor.etapa('publicacao'):
            if desktop:
                publicacao.registro['desktop'] = 1
            publicacao.publicar(servidor, servidor.encerrar,
                lambda: {'encerrando': estado.encerrando, 'paginas': len(servidor_ativo.paginas)})
        if desktop:
            from desktop_havan import executar
            executar(servidor)
        else:
            servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    except Exception as erro:
        publicacao.registrar_falha(erro)
        get_logger(__name__).exception('Falha ao iniciar ou manter a interface local.')
        informar_falha('Não consegui abrir o painel. Avise o responsável e envie auto-pedidos.log.')
        return 1
    finally:
        estado.encerrar()
        if servidor is not None:
            servidor.server_close()
        # A thread termina somente após preservar a ação em andamento.
        estado.worker.join()
    return 0


if __name__ == '__main__':
    if '--demo' in sys.argv:
        from demonstracao import main as demonstrar
        raise SystemExit(demonstrar())
    if '--web' in sys.argv:
        sys.argv.remove('--web')
        raise SystemExit(executar_interface('pedidos-havan', 'Pedidos Havan', True, main))
    from desktop_havan import iniciar
    raise SystemExit(iniciar())
