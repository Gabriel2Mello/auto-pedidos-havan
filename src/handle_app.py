from pathlib import Path
from time import sleep
from typing import cast

from pywinauto import WindowSpecification
from pywinauto.application import Application
from pywinauto.findwindows import ElementNotFoundError, find_element
from pywinauto.timings import TimeoutError as JanelaTimeoutError
from pywinauto.timings import wait_until_passes

from src.config import CAMPOS, ATALHOS
from src.logs import get_logger
from src.erros import (SisplanError)
from src.arquivos import (salvar_pedido_txt)
from src.windows import (send_keys_sleep, aguardar_campo)

logger = get_logger(__name__)


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


def get_field_title(
    parent: WindowSpecification,
    class_name: str,
    title: str,
) -> WindowSpecification:
    return parent.child_window(
        class_name=class_name,
        title=title
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
            title_re='.*VenPedidoGrade.*',
            class_name='TfmPrincipal'
        )
        janela_vendas.set_focus()

        pedido_grade: WindowSpecification = get_field_title(
            janela_vendas, 'TTabSheet', '1002 - Pedido Por Grade'
        )

        aba_pedido: WindowSpecification = get_field_title(
            janela_vendas, 'TTabSheet', 'Pedido'
        )

        itens_pedido: WindowSpecification = get_field_title(
            janela_vendas, 'TTabSheet', 'Itens Pedido'
        )

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
        janela.set_focus()

        nome_field: WindowSpecification = get_field_index(
            janela, 'Edit', 'nome'
        )

        nome_field.set_focus()
        nome_field.set_edit_text(str(xml_path))
        nome_field.type_keys('{ENTER}')

    except Exception as error:
        logger.debug(
            'Erro na tela "Abrir" ao importar o Pedido Havan no Grid: %s',
            error,
        )
        raise SisplanError(
            'Erro ao interagir com janela de importação Pedido Havan'
        ) from error


def localizar_aviso(
    titulo: str, classe: str, timeout: int, processo: int,
) -> WindowSpecification | None:
    """Somente ausência na busca é opcional; falhas de interação são fatais."""
    try:
        if processo <= 0:
            raise SisplanError('Processo do Sisplan inválido.')
        # Application.connect(process=...) ignora título/classe nesta biblioteca.
        # Buscar primeiro dentro do processo e conectar pelo handle encontrado.
        elemento = wait_until_passes(
            timeout, 0.2, find_element, ElementNotFoundError,
            title=titulo, class_name=classe, process=processo,
            backend='win32', visible_only=True,
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


def handle_produto_sem_cadastro(pedido: str, processo: int) -> bool:
    bloqueio = localizar_aviso('Bloqueio', '#32770', 2, processo)
    if bloqueio is None:
        return False
    try:
        bloqueio.set_focus()
        logger.info('Produto sem cadastro. Ignorando...')
        aguardar_campo(bloqueio).OK.click()
        sleep(0.2)
        send_keys_sleep(ATALHOS['fechar'], 0.2)
        salvar_pedido_txt(pedido, motivo='produto sem cadastro')
        return True
    except Exception as error:
        raise SisplanError('Falha ao tratar a janela de produto sem cadastro.') from error


def handle_aviso_duplicado(processo: int) -> bool:
    aviso = localizar_aviso('Aviso', 'TfmAviso', 3, processo)
    if aviso is None:
        return False
    try:
        aviso.set_focus()
        logger.info('Pedido já existe. Cancelando duplicidade...')
        send_keys_sleep(ATALHOS['nao'], 0.2)
        send_keys_sleep(ATALHOS['desistir'], 0.2)
        send_keys_sleep(ATALHOS['sim'])
        return True
    except Exception as error:
        raise SisplanError('Falha ao tratar a janela de pedido duplicado.') from error
