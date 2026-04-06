# Standart library
from src.config import CAMPOS
# Third-party libraries
from pywinauto.application import Application


def get_field_index(parent, class_name, campo):
    try:
        index = CAMPOS[campo]
    except KeyError:
        raise RuntimeError(f'Campo não mapeado: {campo}')

    return parent.child_window(
        class_name=class_name,
        found_index=index
    )


def get_field_title(parent, class_name, title):
    return parent.child_window(
        class_name=class_name,
        title=title
    )


def mapear_campos(aba_pedido):
    return {
        'numero': get_field_index(
            aba_pedido, 'TEdit', 'numero'
        ),
        'cliente': get_field_index(
            aba_pedido, 'TEdit', 'cliente'
        ),
        'representante': get_field_index(
            aba_pedido, 'TEdit', 'representante'
        ),
        'transporte': get_field_index(
            aba_pedido, 'TEdit', 'transporte'
        ),
        'tabela_preco': get_field_index(
            aba_pedido, 'TEdit', 'tabela_preco'
        ),
        'historico': get_field_index(
            aba_pedido, 'TEdit', 'historico'
        ),
        'tipo_venda': get_field_index(
            aba_pedido, 'TEdit', 'tipo_venda'
        ),
        'operacao': get_field_index(
            aba_pedido, 'TEdit', 'operacao'
        ),
        'data_fatura': get_field_index(
            aba_pedido, 'TDateEditSisp', 'fatura'
        ),
        'data_entrega': get_field_index(
            aba_pedido, 'TDateEditSisp', 'entrega'
        ),
        'data_saida': get_field_index(
            aba_pedido, 'TDateEditSisp', 'saida'
        ),
        'classe_gerencial': get_field_index(
            aba_pedido, 'TEdGrid', 'classe_gerencial'
        ),
        'empresa': get_field_index(
            aba_pedido, 'TComboBox', 'combo_empresa'
        ),
    }


def inicia_app():
    app = Application(backend='win32').connect(
        title=CAMPOS['sisplan'],
        class_name='TApplication'
    )

    dlg = app.window(
        title=CAMPOS['sisplan'],
        class_name='TApplication'
    )

    dlg.restore()
    dlg.wait('visible', timeout=10)
    dlg.set_focus()

    main = app.window(
        title_re='.*VenPedidoGrade.*',
        class_name='TfmPrincipal'
    )
    main.set_focus()

    pedido_grade = get_field_title(
        main, 'TTabSheet', '1002 - Pedido Por Grade'
    )

    aba_pedido = get_field_title(
        main, 'TTabSheet', 'Pedido'
    )

    itens_pedido = get_field_title(
        main, 'TTabSheet', 'Itens Pedido'
    )

    grid = get_field_index(
        itens_pedido, 'TDBGrid', 'grid'
    )

    campos = mapear_campos(aba_pedido)

    return pedido_grade, aba_pedido, grid, campos


def importa_arq_integracao(xml_path):
    app_abrir = Application(
        backend='win32'
    ).connect(title='Abrir', class_name='#32770')

    janela = app_abrir.window(
        title='Abrir', class_name='#32770'
    )
    janela.wait('visible', timeout=10)

    nome_field = get_field_index(
        janela, 'Edit', 'nome'
    )
    nome_field.set_focus()

    nome_field.set_edit_text(str(xml_path))
    nome_field.type_keys('{ENTER}')

