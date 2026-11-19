from pathlib import Path
from typing import Literal, cast

import win32con
import win32gui
from pywinauto import WindowSpecification
from pywinauto.application import Application
from pywinauto.findwindows import ElementNotFoundError, find_element
from pywinauto.timings import TimeoutError as JanelaTimeoutError
from pywinauto.timings import wait_until_passes

from guias_sisplan import selecionar_guia, selecionar_modulo
from src.config import CAMPOS
from src.logs import get_logger
from src.erros import (SisplanError)
from src.arquivos import (salvar_pedido_txt)

logger = get_logger(__name__)

AVISO_XML_SEM_ITENS = 'Nenhum item encontrado no arquivo selecionado.'
RELATORIO_PRODUTOS_NAO_ENCONTRADOS = 'Itens não encontrados na grade de produtos'
AVISO_PRODUTOS_NAO_ENCONTRADOS = 'Existem itens não encontrados na grade de produtos.'
CONFIRMACAO_CANCELAMENTO = 'Deseja Cancelar as Alterações ?'
AvisoImportacao = Literal['sem_cadastro', 'xml_sem_itens']


def get_field_index(
    parent: WindowSpecification,
    class_name: str,
    campo: str,
) -> WindowSpecification:
    index = CAMPOS.get(campo)
    if index is None:
        raise RuntimeError(f'Campo não mapeado: {campo}')

    return parent.child_window(
        class_name=class_name,
        found_index=int(index)
    )


def mapear_campos(
    aba_pedido: WindowSpecification,
) -> dict[str, WindowSpecification]:
    definicoes: dict[str, tuple[str, str]] = {
        'numero':        ('TEdit', 'numero'),
        'cliente':       ('TEdit', 'cliente'),
        'representante': ('TEdit', 'representante'),
        'transporte':    ('TEdit', 'transporte'),
        'tabela_preco':  ('TEdit', 'tabela_preco'),
        'historico':     ('TEdit', 'historico'),
        'tipo_venda':    ('TEdit', 'tipo_venda'),
        'operacao':      ('TEdit', 'operacao'),
        'data_fatura':   ('TDateEditSisp', 'fatura'),
        'data_entrega':  ('TDateEditSisp', 'entrega'),
        'data_saida':    ('TDateEditSisp', 'saida'),
        'classe_gerencial': ('TEdGrid', 'classe_gerencial'),
        'empresa':       ('TComboBox', 'combo_empresa'),
        'observacao_2':  ('TMemo', 'observacao_2'),
    }

    return {
        nome: get_field_index(aba_pedido, classe, chave)
        for nome, (classe, chave) in definicoes.items()
    }


def inicia_app() -> tuple[
    WindowSpecification,
    WindowSpecification,
    WindowSpecification,
    dict[str, WindowSpecification],
]:
    logger.debug('Iniciando aplicação')
    try:
        app: Application = Application(backend='win32').connect(
            title=CAMPOS['sisplan'],
            class_name='TApplication',
            timeout=2
        )

        main_window: WindowSpecification = app.window(
            title=CAMPOS['sisplan'],
            class_name='TApplication'
        )
        main_window.restore().set_focus()
        main_window.wait('ready', timeout=5)

        janela_vendas: WindowSpecification = app.window(
            class_name='TfmPrincipal', visible_only=False,
        )
        selecionar_modulo(janela_vendas, '1002', 'TfmVenPedidoGrade')
        janela_vendas.set_focus()

        pedido_grade: WindowSpecification = janela_vendas.child_window(
            class_name='TTabSheet', title='1002 - Pedido Por Grade', visible_only=False,
        )
        formulario = janela_vendas.child_window(class_name='TfmVenPedidoGrade', visible_only=False)
        aba_pedido: WindowSpecification = formulario.child_window(
            class_name='TTabSheet', title='Pedido', visible_only=False,
        )
        itens_pedido: WindowSpecification = formulario.child_window(
            class_name='TTabSheet', title='Itens Pedido', visible_only=False,
        )
        selecionar_guia(aba_pedido)

        grid: WindowSpecification = get_field_index(
            itens_pedido, 'TDBGrid', 'grid'
        )

        campos = mapear_campos(aba_pedido)

        return pedido_grade, aba_pedido, grid, campos

    except Exception as error:
        logger.debug('Erro na janela do Sisplan: %s', error, exc_info=True)
        raise SisplanError(
            'Não foi possível encontrar a tela '
            '"1002 - Pedido por Grade" do Sisplan'
        ) from error


def importa_arq_integracao(xml_path: str | Path, processo: int) -> None:
    logger.debug('Importando pedido Havan no grid')
    try:
        janela = localizar_aviso('Abrir', '#32770', 2, processo)
        if janela is None:
            raise SisplanError('Janela Abrir do Sisplan não encontrada.')
        nome_field: WindowSpecification = get_field_index(
            janela, 'Edit', 'nome'
        )
        abrir = janela.child_window(class_name='Button', control_id=win32con.IDOK)
        nome_field.wait('ready', timeout=5)
        abrir.wait('ready', timeout=5)
        caminho = str(xml_path)
        nome_field.set_edit_text(caminho)
        if nome_field.window_text() != caminho:
            raise SisplanError('O Sisplan não confirmou o caminho do XML selecionado.')
        janela.set_focus()
        win32gui.PostMessage(abrir.wrapper_object().handle, win32con.BM_CLICK, 0, 0)
        janela.wait_not('visible', timeout=5)

    except Exception as error:
        logger.debug(
            'Erro na tela "Abrir" ao importar o Pedido Havan no Grid: %s',
            error,
        )
        raise SisplanError(
            'Erro ao interagir com janela de importação Pedido Havan'
        ) from error


def localizar_aviso(
    titulo: str | tuple[str, ...], classe: str, timeout: int, processo: int,
) -> WindowSpecification | None:
    """Somente ausência na busca é opcional; falhas de interação são fatais."""
    try:
        if processo <= 0:
            raise SisplanError('Processo do Sisplan inválido.')
        # Application.connect(process=...) ignora título/classe nesta biblioteca.
        # Buscar primeiro dentro do processo e conectar pelo handle encontrado.
        criterios: dict[str, object]
        if isinstance(titulo, str):
            criterios = {'title': titulo}
        else:
            criterios = {'predicate_func': lambda elemento: elemento.rich_text in titulo}
        elemento = wait_until_passes(
            timeout, 0.2, find_element, ElementNotFoundError,
            class_name=classe, process=processo, backend='win32', visible_only=True,
            **criterios,
        )
        handle = cast(int, elemento.handle)
        app_dialog: Application = Application(backend='win32').connect(
            handle=handle,
        )
    except ElementNotFoundError:
        return None
    except JanelaTimeoutError as error:
        if isinstance(getattr(error, 'original_exception', None), ElementNotFoundError):
            return None
        raise SisplanError(f'Falha ao procurar a janela "{titulo}".') from error
    except Exception as error:
        raise SisplanError(f'Falha ao procurar a janela "{titulo}".') from error

    try:
        janela = app_dialog.window(handle=handle)
        janela.wait('ready', timeout=timeout)
        return janela
    except Exception as error:
        raise SisplanError(f'Janela "{titulo}" encontrada, mas indisponível.') from error


def tratar_avisos_importacao(pedido: str, processo: int) -> AvisoImportacao | None:
    aviso = localizar_aviso(('Bloqueio', 'Informação'), '#32770', 2, processo)
    if aviso is None:
        return None
    if aviso.window_text() == 'Informação':
        textos = aviso.wrapper_object().descendants(class_name='Static')
        if not any(c.is_visible() and c.window_text().strip() == AVISO_XML_SEM_ITENS for c in textos):
            raise SisplanError('Aviso de importação desconhecido. Confira a tela do Sisplan.')
        try:
            botao = aviso.child_window(class_name='Button', title='OK', enabled_only=True)
            botao.wait('ready', timeout=5)
            area = botao.client_rect()
            aviso.set_focus()
            botao.click(coords=(area.width() // 2, area.height() // 2))
            aviso.wait_not('visible', timeout=5)
        except Exception as error:
            raise SisplanError('O Sisplan não encontrou itens no XML. Não foi possível fechar o aviso.') from error
        return 'xml_sem_itens'
    try:
        if not _tem_mensagem(aviso, AVISO_PRODUTOS_NAO_ENCONTRADOS):
            raise SisplanError('O bloqueio não corresponde a produtos não encontrados.')
        logger.info('Produto sem cadastro. Ignorando...')
        _clicar_botao(aviso, aviso.child_window(class_name='Button', title='OK'))
        aviso.wait_not('visible', timeout=5)
        relatorio = localizar_aviso(RELATORIO_PRODUTOS_NAO_ENCONTRADOS, 'TForm', 5, processo)
        if relatorio is None:
            raise SisplanError('O relatório de produtos não encontrados não apareceu.')
        _clicar_botao(relatorio, relatorio.child_window(class_name='TBitBtn', title='&Fechar'))
        relatorio.wait_not('visible', timeout=5)
        salvar_pedido_txt(pedido, motivo='produto sem cadastro')
        return 'sem_cadastro'
    except Exception as error:
        raise SisplanError('Falha ao tratar a janela de produto sem cadastro.') from error


def _clicar_botao(janela: WindowSpecification, botao: WindowSpecification) -> None:
    botao.wait('ready', timeout=5)
    controle = botao.wrapper_object()
    area = controle.client_rect()
    if area.width() <= 0 or area.height() <= 0:
        raise SisplanError('Botão do Sisplan sem área de clique.')
    janela.set_focus()
    controle.click(coords=(area.width() // 2, area.height() // 2))


def _tem_mensagem(janela: WindowSpecification, mensagem: str) -> bool:
    return any(controle.is_visible() and controle.window_text().strip() == mensagem
               for controle in janela.wrapper_object().descendants(class_name='Static'))


def _confirmar_cancelamento(processo: int) -> None:
    confirmacao = localizar_aviso('Atenção', '#32770', 5, processo)
    if confirmacao is None or not _tem_mensagem(confirmacao, CONFIRMACAO_CANCELAMENTO):
        raise SisplanError('A confirmação de cancelamento esperada não foi encontrada no Sisplan.')
    sim = confirmacao.child_window(class_name='Button', title='&Sim', control_id=6)
    _clicar_botao(confirmacao, sim)
    confirmacao.wait_not('visible', timeout=5)


def acionar_botao_pedido(
    processo: int, comando: Literal['Incluir', 'Gravar', 'Desistir'],
) -> WindowSpecification:
    app = Application(backend='win32').connect(process=processo)
    principal = app.window(class_name='TfmPrincipal')
    formulario = principal.child_window(class_name='TfmVenPedidoGrade')
    botao = formulario.child_window(class_name='TBitBtn', title=f'&{comando}')
    principal.wait('ready', timeout=5)
    _clicar_botao(principal, botao)
    if comando == 'Incluir':
        formulario.child_window(class_name='TBitBtn', title='&Desistir').wait('ready', timeout=5)
    return botao


def cancelar_inclusao(processo: int) -> None:
    desistir = acionar_botao_pedido(processo, 'Desistir')
    _confirmar_cancelamento(processo)
    desistir.wait_not('visible', timeout=5)


def handle_aviso_duplicado(processo: int) -> bool:
    aviso = localizar_aviso('Aviso', 'TfmAviso', 3, processo)
    if aviso is None:
        return False
    try:
        botoes = aviso.wrapper_object().descendants(class_name='TBitBtn')
        if sorted(b.window_text() for b in botoes if b.is_visible()) != ['&Não', '&Sim']:
            raise SisplanError('O aviso do Sisplan tem opções diferentes das esperadas.')
        nao = aviso.child_window(class_name='TBitBtn', title='&Não')
        _clicar_botao(aviso, nao)
        aviso.wait_not('visible', timeout=5)

        logger.info('Aviso do Sisplan recusado. Cancelando a inclusão antes de conferir no banco...')
        cancelar_inclusao(processo)
        return True
    except Exception as error:
        raise SisplanError('Falha ao tratar a janela de pedido duplicado.') from error
