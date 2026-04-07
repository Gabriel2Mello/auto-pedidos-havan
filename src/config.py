from pathlib import Path
from os import environ

UNRAR_TOOL   = environ['UNRAR_TOOL']
CNPJ_MATRIZ  = environ['CNPJ_MATRIZ']
SENHA_PORTAL = environ['SENHA_PORTAL']
SUMATRA      = environ['SUMATRA']
IMPRESSORA   = environ['IMPRESSORA_PEDIDO']

USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/145.0.0.0 Safari/537.36'
)

ORIGIN       = 'https://cliente.havan.com.br'
BASE_URL     = f'{ORIGIN}/Fornecedor'
CONTENT_TYPE = 'application/x-www-form-urlencoded; charset=UTF-8'

BASE_PATH_PEDIDOS = Path(environ['HAVAN_PEDIDOS'])


CAMPOS = {
    'sisplan': 'Sisplan - 002 - NUNES ENXOVAIS IND, COM, IMP E EXP LTDA',
    'operacao': 55, 'cliente': 53, 'representante': 51, 'tabela_preco': 49,
    'transporte': 48, 'prazo_entrega': 28, 'prazo_producao': 26,
    'historico': 18, 'tipo_venda': 16, 'numero': 13, 'ped_cliente': 12,
    'saida': 6, 'entrega': 7, 'fatura': 8, 'classe_gerencial': 1, 'grid': 2,
    'nome': 0, 'combo_empresa': 0
}

PRODUTOS_GOVERNADOR = [
    'DIVERTIDA', 'FORMATO', 'ASSENTO CADEIRA', 'GUARDANAPO',
    'AVENTAL', 'TROCADOR', 'ALMOFADA DECOR 38X38 HAVAN BABY',
    'AMAMENTAÇÃO', 'DESCANSO', 'MINI', 'GUIRLANDA', 'ABRAÇO',
    'PESO DE PORTA'
]

COORD_ABA_PEDIDO = (87, 10)
COORD_ITENS_PEDIDO = (150,-13)

ATALHOS = {
    'importar': 'm',
    'havan': 'h',
    'incluir': '%i',
    'desistir': '%d',
    'gravar': '%g'
}

