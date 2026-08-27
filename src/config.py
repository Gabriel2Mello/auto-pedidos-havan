from os import environ
from pathlib import Path


class ConfiguracaoError(ValueError):
    """Indica que uma configuração obrigatória está ausente ou inválida."""


def _ler_variavel(nome: str) -> str:
    return environ.get(nome, '').strip().strip('"')


_unrar_raw = _ler_variavel('UNRAR_TOOL')
_sumatra_raw = _ler_variavel('SUMATRA')
_base_path_raw = _ler_variavel('HAVAN_PEDIDOS')

UNRAR_TOOL = Path(_unrar_raw)
SUMATRA = Path(_sumatra_raw)
BASE_PATH_PEDIDOS = Path(_base_path_raw)
TEAMS_WEBHOOK_URL = _ler_variavel('TEAMS_WEBHOOK_URL')
CNPJ_MATRIZ = _ler_variavel('CNPJ_MATRIZ')
SENHA_PORTAL = _ler_variavel('SENHA_PORTAL')
IMPRESSORA = _ler_variavel('IMPRESSORA_PEDIDO')


def validar_configuracao() -> None:
    """Valida as dependências externas antes de iniciar a automação."""
    erros: list[str] = []

    if not _unrar_raw or not UNRAR_TOOL.is_file():
        erros.append('UNRAR_TOOL deve apontar para um arquivo válido')
    if not _sumatra_raw or not SUMATRA.is_file():
        erros.append('SUMATRA deve apontar para um arquivo válido')
    if not _base_path_raw:
        erros.append('HAVAN_PEDIDOS não foi configurada')
    if not CNPJ_MATRIZ or not SENHA_PORTAL:
        erros.append('CNPJ_MATRIZ e SENHA_PORTAL devem ser configuradas')
    if not IMPRESSORA:
        erros.append('IMPRESSORA_PEDIDO não foi configurada')

    if erros:
        detalhes = '; '.join(erros)
        raise ConfiguracaoError(f'Configuração inválida: {detalhes}.')


ORIGIN = 'https://cliente.havan.com.br'
BASE_URL = f'{ORIGIN}/Fornecedor'
CONTENT_TYPE = (
    'application/x-www-form-urlencoded; charset=UTF-8'
)

DEFAULT_HEADERS = {
    'Origin': ORIGIN,
    'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept': '*/*',
}

CAMPOS = {
    'sisplan': 'Sisplan - 002 - NUNES ENXOVAIS IND, COM, IMP E EXP LTDA',
    'operacao': 55,
    'cliente': 53,
    'representante': 51,
    'tabela_preco': 49,
    'transporte': 48,
    'prazo_entrega': 28,
    'prazo_producao': 26,
    'historico': 18,
    'tipo_venda': 16,
    'numero': 13,
    'ped_cliente': 12,
    'saida': 6,
    'entrega': 7,
    'fatura': 8,
    'classe_gerencial': 1,
    'grid': 2,
    'nome': 0,
    'combo_empresa': 0,
    'observacao_2': 1,
}

PRODUTOS_GOVERNADOR = {
    'ALMOFADA DECOR 38X38 HAVAN BABY',
    'ALMOFADA QUADRADA 38X38 TURMA DO ABRACO',
    'ALMOFADA TURMA DO ABRACO',
    'AMAMENTACAO',
    'ASSENTO CADEIRA',
    'AVENTAL',
    'DESCANSO',
    'DIVERTIDA',
    'GUARDANAPO',
    'GUIRLANDA',
    'MINI ALMOFADA',
    'PESO DE PORTA',
    'TROCADOR',
    'EDREDOM',
    'SACO DORMIR',
}

COORD_ABA_PEDIDO = (87, 10)
COORD_ITENS_PEDIDO = (150, -13)

ATALHOS = {
    'importar': 'm',
    'havan':    'h',
    'incluir':  '%i',
    'desistir': '%d',
    'gravar':   '%g',
    'nao':      '%n',
    'sim':      '%s',
    'fechar':   '%f',
}

