from src.config import CAMPOS
# Third-party libraries
from pywinauto.application import Application


def get_field_index(parent, class_name, campo):
    index = CAMPOS.get(campo)
    if index is None:
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
    definicoes = {
        'numero': ('TEdit', 'numero'),
        'cliente': ('TEdit', 'cliente'),
        'representante': ('TEdit', 'representante'),
        'transporte': ('TEdit', 'transporte'),
        'tabela_preco': ('TEdit', 'tabela_preco'),
        'historico': ('TEdit', 'historico'),
        'tipo_venda': ('TEdit', 'tipo_venda'),
        'operacao': ('TEdit', 'operacao'),
        'data_fatura': ('TDateEditSisp', 'fatura'),
        'data_entrega': ('TDateEditSisp', 'entrega'),
        'data_saida': ('TDateEditSisp', 'saida'),
        'classe_gerencial': ('TEdGrid', 'classe_gerencial'),
        'empresa': ('TComboBox', 'combo_empresa'),
    }

    return {nome: get_field_index(aba_pedido, classe, chave)
            for nome, (classe, chave) in definicoes.items()}


def inicia_app():
    app = Application(backend='win32').connect(
        title=CAMPOS['sisplan'],
        class_name='TApplication'
    )

    main_window = app.window(
        title=CAMPOS['sisplan'],
        class_name='TApplication'
    )
    main_window.restore().set_focus()
    main_window.wait('ready', timeout=10)


    janela_vendas = app.window(
        title_re='.*VenPedidoGrade.*',
        class_name='TfmPrincipal'
    )
    janela_vendas.set_focus()

    pedido_grade = get_field_title(
        janela_vendas, 'TTabSheet', '1002 - Pedido Por Grade'
    )

    aba_pedido = get_field_title(
        janela_vendas, 'TTabSheet', 'Pedido'
    )

    itens_pedido = get_field_title(
        janela_vendas, 'TTabSheet', 'Itens Pedido'
    )

    grid = get_field_index(
        itens_pedido, 'TDBGrid', 'grid'
    )

    campos = mapear_campos(aba_pedido)

    return pedido_grade, aba_pedido, grid, campos


def importa_arq_integracao(xml_path):
    try:
        app_dialog = Application(
            backend='win32'
        ).connect(title='Abrir', class_name='#32770')

        janela = app_dialog.window(
            title='Abrir', class_name='#32770'
        )
        janela.wait('ready', timeout=5)

        nome_field = get_field_index(
            janela, 'Edit', 'nome'
        )

        nome_field.set_focus()
        nome_field.set_edit_text(str(xml_path))
        nome_field.type_keys('{ENTER}')

    except Exception as e:
        raise RuntimeError(f'Erro ao interagir com janela de importação: {e}')

