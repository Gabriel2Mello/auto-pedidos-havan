"""Abre Pedidos Havan no navegador do próprio computador."""

import sys
from integracao_hub import IntegracaoLocal, executar_interface


def informar_falha(mensagem: str) -> None:
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, mensagem, 'Pedidos Havan', 0x10)
    else:
        print(mensagem, file=sys.stderr)


def main(publicacao: IntegracaoLocal) -> int:
    try:
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
        codigo = setup_logging(console=sys.stdout is not None)
    except (OSError, ValueError) as erro:
        publicacao.registrar_falha(erro)
        informar_falha(f'Não foi possível abrir auto-pedidos.log. Nenhum pedido foi iniciado.\n'
                       f'Informe ao responsável: {type(erro).__name__}: {erro}')
        return 1
    set_app_id()
    estado = EstadoInterface(codigo_execucao=codigo)
    servidor = None
    try:
        servidor, _ = criar_servidor(estado)
        url = f'http://127.0.0.1:{servidor.server_port}'
        get_logger(__name__).info('Interface local iniciada: %s', url)
        servidor_ativo = servidor
        publicacao.publicar(servidor, estado.encerrar,
            lambda: {'encerrando': estado.encerrando, 'paginas': len(servidor_ativo.paginas)})
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
    raise SystemExit(executar_interface('pedidos-havan', 'Pedidos Havan', True, main))
