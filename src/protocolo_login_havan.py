"""Sequência HTTP do login no portal Havan (componente 1.0.0)."""
from typing import Protocol


class RespostaLogin(Protocol):
    @property
    def url(self) -> str: ...

    def raise_for_status(self) -> None: ...


class SessaoLogin(Protocol):
    def get(self, url: str, /, **opcoes: object) -> RespostaLogin: ...

    def post(self, url: str, /, **opcoes: object) -> RespostaLogin: ...


def entrar_no_portal(sessao: SessaoLogin, *, base: str, documento: str,
                    senha: str, timeout: tuple[float, float]) -> str:
    """Executa o protocolo e devolve a URL para o chamador validar a sessão."""
    entrada = f'{base}/Login/Index'
    sessao.get(entrada, timeout=timeout).raise_for_status()
    sessao.post(f'{base}/Login/FazerLogin?Length=5', headers={'Referer': entrada},
                data={'TipoLogin': '0', 'Documento': documento, 'SenhaMd5': senha},
                timeout=timeout, allow_redirects=True).raise_for_status()
    resposta = sessao.get(f'{base}/PedidoCompra/Index', headers={'Referer': base},
                          timeout=timeout, allow_redirects=True)
    resposta.raise_for_status()
    return resposta.url
