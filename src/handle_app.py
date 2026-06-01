from time import sleep
from pathlib import Path

from pywinauto import WindowSpecification
from pywinauto.application import Application
from pywinauto.keyboard import send_keys

from src.config import CAMPOS, ATALHOS
from src.logs import get_logger
from src.utils import SisplanError

logger = get_logger(__name__)


def get_field_index(parent: WindowSpecification, class_name: str, campo: str) -> WindowSpecification:
    index = CAMPOS.get(campo)
    if index is None:
        raise RuntimeError(f'Campo não mapeado: {campo}')

    return parent.child_window(
        class_name=class_name,
        found_index=int(index)
    )


def get_field_title(parent: WindowSpecification, class_name: str, title: str) -> WindowSpecification:
    return parent.child_window(
        class_name=class_name,
        title=title
    )


def mapear_campos(aba_pedido: WindowSpecification) -> dict[str, WindowSpecification]:
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

    return {nome: get_field_index(aba_pedido, classe, chave)
            for nome, (classe, chave) in definicoes.items()}


def inicia_app() -> tuple[WindowSpecification, WindowSpecification, WindowSpecification, dict[str, WindowSpecification]]:
    logger.debug('Iniciando aplicação')
    try:
        app: Application = Application(backend='win32').connect(
            title=CAMPOS['sisplan'],
            class_name='TApplication'
        )

        main_window: WindowSpecification = app.window(
            title=CAMPOS['sisplan'],
            class_name='TApplication'
        )
        _ = main_window.restore().set_focus()
        main_window.wait('ready', timeout=5)


        janela_vendas: WindowSpecification = app.window(
            title_re='.*VenPedidoGrade.*',
            class_name='TfmPrincipal'
        )
        _ = janela_vendas.set_focus()

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

    except Exception as e:
        logger.debug(f'Erro na janela do Sisplan: {e}', exc_info=True)
        raise SisplanError('Não foi possível encontrar a tela "1002 - Pedido por Grade" do Sisplan') from e


def importa_arq_integracao(xml_path: str | Path) -> None:
    logger.debug('Importando pedido Havan no grid')
    try:
        app_dialog: Application = Application(
            backend='win32'
        ).connect(title='Abrir', class_name='#32770')

        janela: WindowSpecification = app_dialog.window(
            title='Abrir', class_name='#32770'
        )
        janela.wait('ready', timeout=5)

        nome_field: WindowSpecification = get_field_index(
            janela, 'Edit', 'nome'
        )

        _ = nome_field.set_focus()
        _ = nome_field.set_edit_text(str(xml_path))
        _ = nome_field.type_keys('{ENTER}')

    except Exception as e:
        logger.debug(f'Erro na tela "Abrir" ao importar o Pedido Havan no Grid: {e}')
        raise SisplanError(f'Erro ao interagir com janela de importação Pedido Havan') from e


def handle_aviso_duplicado() -> bool:
    try:
        app_dialog: Application = Application(
            backend='win32'
        ).connect(title='Aviso', class_name='TfmAviso')

        aviso: WindowSpecification = app_dialog.window(
            title='Aviso', class_name='TfmAviso'
        )

        if aviso.exists(timeout=1):
            logger.info('Pedido já existe. Cancelando duplicidade...')
            send_keys(ATALHOS['nao'])
            sleep(0.2)
            send_keys(ATALHOS['desistir'])
            sleep(0.2)
            send_keys(ATALHOS['sim'])

            return True

        return False
    except:
      return False

