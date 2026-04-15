from src.logs import get_logger

import sys
from pathlib import Path
from os import environ

logger = get_logger(__name__)


def encerrar_por_erro(msg, error_msg):
    logger.debug(error_msg)
    logger.critical(f'AVISO: {msg}')
    input('\nPressione Enter para fechar...')
    sys.exit(1)


_unrar_raw     = environ.get('UNRAR_TOOL', '').strip('"')
_sumatra_raw   = environ.get('SUMATRA', '').strip('"')
_base_path_raw = environ.get('HAVAN_PEDIDOS', '').strip('"')

UNRAR_TOOL        = Path(_unrar_raw)
SUMATRA           = Path(_sumatra_raw)
BASE_PATH_PEDIDOS = Path(_base_path_raw)
CNPJ_MATRIZ  = environ.get('CNPJ_MATRIZ')
SENHA_PORTAL = environ.get('SENHA_PORTAL')
IMPRESSORA   = environ.get('IMPRESSORA_PEDIDO')

if not UNRAR_TOOL.exists():
    encerrar_por_erro('caminho do utilitário de .RAR não é válido.', UNRAR_TOOL)

if not SUMATRA.exists():
    encerrar_por_erro('caminho do utilitário SumatraPDF não é válido.', SUMATRA)

if not BASE_PATH_PEDIDOS:
    encerrar_por_erro('caminho onde os arquivos de importação serão salvos não está configurado.', 'Variável de ambiente HAVAN_PEDIDOS')

if not CNPJ_MATRIZ or not SENHA_PORTAL:
    encerrar_por_erro('Credenciais para o site da Havan não configuradas.', 'Variáveis de ambiente CNPJ_MATRIZ, SENHA_PORTAL')

if not IMPRESSORA:
    encerrar_por_erro('Impressora dos pedidos não configurada.', 'Variável de ambiente IMPRESSORA_PEDIDO')


USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/145.0.0.0 Safari/537.36'
)

ORIGIN       = 'https://cliente.havan.com.br'
BASE_URL     = f'{ORIGIN}/Fornecedor'
CONTENT_TYPE = 'application/x-www-form-urlencoded; charset=UTF-8'


CAMPOS = {
    'sisplan': 'Sisplan - 002 - NUNES ENXOVAIS IND, COM, IMP E EXP LTDA',
    'operacao': 55, 'cliente': 53, 'representante': 51, 'tabela_preco': 49,
    'transporte': 48, 'prazo_entrega': 28, 'prazo_producao': 26,
    'historico': 18, 'tipo_venda': 16, 'numero': 13, 'ped_cliente': 12,
    'saida': 6, 'entrega': 7, 'fatura': 8, 'classe_gerencial': 1, 'grid': 2,
    'nome': 0, 'combo_empresa': 0
}

PRODUTOS_GOVERNADOR = {
    'DIVERTIDA', 'FORMATO', 'ASSENTO CADEIRA', 'GUARDANAPO',
    'AVENTAL', 'TROCADOR', 'ALMOFADA DECOR 38X38 HAVAN BABY',
    'AMAMENTAÇÃO', 'DESCANSO', 'MINI', 'GUIRLANDA', 'ABRAÇO',
    'PESO DE PORTA','ALMOFADA QUADRADA 38X38 TURMA DO ABRACO'
}

COORD_ABA_PEDIDO = (87, 10)
COORD_ITENS_PEDIDO = (150,-13)

ATALHOS = {
    'importar': 'm',
    'havan': 'h',
    'incluir': '%i',
    'desistir': '%d',
    'gravar': '%g',
    'nao': '%n',
    'sim': '%s'
}

