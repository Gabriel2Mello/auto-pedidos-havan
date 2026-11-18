"""Seleção de páginas VCL por mensagens Win32, sem entrada de dispositivos.

Fonte em auto-impressao-ops; cópias independentes declaradas no Hub.
"""

from collections.abc import Callable
from time import monotonic, sleep
from typing import Protocol, cast


TCM_SETCURFOCUS = 0x1330
WM_MDIGETACTIVE = 0x0229
SMTO_ABORTIFHUNG = 0x0002


class ControleWin32(Protocol):
    @property
    def handle(self) -> int: ...
    def class_name(self) -> str: ...
    def window_text(self) -> str: ...
    def children(self, **criterios: object) -> list['ControleWin32']: ...
    def parent(self) -> 'ControleWin32': ...
    def is_visible(self) -> bool: ...
    def is_enabled(self) -> bool: ...
    def send_message_timeout(
        self, message: int, wparam: int = 0, lparam: int = 0,
        timeout: float = 5, timeoutflags: int = SMTO_ABORTIFHUNG,
    ) -> int | str: ...


class EspecificacaoWin32(Protocol):
    def wrapper_object(self) -> ControleWin32: ...


class ControleGuias(ControleWin32, Protocol):
    def tab_count(self) -> int: ...
    def get_tab_text(self, indice: int) -> str: ...
    def get_selected_tab(self) -> int: ...


def _controle_guias(controle: ControleWin32) -> ControleGuias:
    from pywinauto.controls.common_controls import TabControlWrapper

    return cast(ControleGuias, TabControlWrapper(controle.handle))


def _unico(controles: list[ControleWin32], descricao: str) -> ControleWin32:
    if len(controles) != 1:
        raise RuntimeError(f'{descricao}: esperado um controle, encontrados {len(controles)}.')
    return controles[0]


def _filhos(controle: ControleWin32, classe: str) -> list[ControleWin32]:
    # O backend Win32 pode incluir descendentes ao enumerar children().
    return [filho for filho in controle.children(class_name=classe)
            if filho.parent().handle == controle.handle]


def _aguardar(condicao: Callable[[], bool], tempo_limite: float, descricao: str) -> None:
    limite = monotonic() + tempo_limite
    while not condicao():
        if monotonic() >= limite:
            raise RuntimeError(f'Não foi possível confirmar {descricao}.')
        sleep(0.05)


def _mensagem(controle: ControleWin32, mensagem: int, valor: int, tempo_limite: float) -> int:
    retorno = controle.send_message_timeout(
        mensagem, valor, timeout=tempo_limite, timeoutflags=SMTO_ABORTIFHUNG,
    )
    # pywinauto devolve o texto da exceção quando SendMessageTimeout falha.
    if not isinstance(retorno, int):
        raise RuntimeError(f'Falha ao comunicar com as guias do Sisplan: {retorno}')
    return retorno


def _selecionar(
    controle: ControleWin32, pagina: ControleWin32, titulo: str, tempo_limite: float,
) -> None:
    if controle.class_name() != 'TPageControl' or not controle.is_enabled():
        raise RuntimeError(f'O controle da guia {titulo!r} está indisponível.')
    guias = _controle_guias(controle)
    indices = [i for i in range(guias.tab_count()) if guias.get_tab_text(i) == titulo]
    if len(indices) != 1:
        raise RuntimeError(f'Guia {titulo!r} ausente ou ambígua no Sisplan.')
    indice = indices[0]
    _mensagem(guias, TCM_SETCURFOCUS, indice, tempo_limite)
    _aguardar(
        lambda: guias.get_selected_tab() == indice
        and guias.get_tab_text(indice) == titulo
        and pagina.is_visible() and pagina.is_enabled(),
        tempo_limite, f'a seleção da guia {titulo!r}',
    )


def selecionar_guia(
    pagina: object, titulo: str | None = None, *, tempo_limite: float = 5,
) -> None:
    """Seleciona a página resolvida ou uma irmã pelo nome exato."""
    controle = cast(EspecificacaoWin32, pagina).wrapper_object()
    if controle.class_name() != 'TTabSheet':
        raise RuntimeError('A guia de destino não é uma página do Sisplan.')
    pai = controle.parent()
    if titulo is not None:
        controle = _unico(
            [p for p in _filhos(pai, 'TTabSheet') if p.window_text() == titulo],
            f'Guia {titulo!r}',
        )
    _selecionar(pai, controle, controle.window_text(), tempo_limite)


def selecionar_modulo(
    janela: object, codigo: str, classe_formulario: str, *, tempo_limite: float = 5,
) -> None:
    """Resolve o código na ordem atual e confirma o formulário MDI ativo."""
    raiz = cast(EspecificacaoWin32, janela).wrapper_object()
    if not raiz.is_enabled():
        raise RuntimeError('A janela do Sisplan está bloqueada por outro diálogo.')
    controle = _unico(_filhos(raiz, 'TPageControl'), 'Guias principais do Sisplan')
    guias = _controle_guias(controle)
    titulos = [guias.get_tab_text(i) for i in range(guias.tab_count())]
    destinos = [titulo for titulo in titulos if titulo.partition(' - ')[0].strip() == codigo]
    if len(destinos) != 1:
        raise RuntimeError(f'Aba {codigo!r} ausente ou ambígua no Sisplan.')
    titulo = destinos[0]
    pagina = _unico(
        [p for p in _filhos(controle, 'TTabSheet') if p.window_text() == titulo],
        f'Página da aba {codigo}',
    )
    mdi = _unico(_filhos(raiz, 'MDIClient'), 'Área de módulos do Sisplan')
    formulario = _unico(_filhos(mdi, classe_formulario), classe_formulario)
    _selecionar(controle, pagina, titulo, tempo_limite)
    _aguardar(
        lambda: _mensagem(mdi, WM_MDIGETACTIVE, 0, tempo_limite) == formulario.handle
        and formulario.is_visible() and formulario.is_enabled(),
        tempo_limite, f'o formulário {classe_formulario} da aba {codigo}',
    )
