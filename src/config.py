import sys
from dataclasses import dataclass
from os import environ
from pathlib import Path
from tomllib import TOMLDecodeError, load
from typing import Mapping


class ConfiguracaoError(ValueError):
    """Indica que uma configuração obrigatória está ausente ou inválida."""


def diretorio_aplicacao() -> Path:
    """Retorna a pasta do executável ou a raiz do projeto em desenvolvimento."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _ler_segredo(ambiente: Mapping[str, str], nome: str) -> str:
    return ambiente.get(nome, '').strip().strip('"')


def _ler_texto(dados: dict[str, object], nome: str) -> str:
    valor = dados.get(nome, '')
    return valor.strip() if isinstance(valor, str) else ''


@dataclass(frozen=True)
class Configuracao:
    unrar_tool: Path
    sumatra: Path
    pasta_pedidos: Path
    impressora: str
    cnpj_matriz: str
    senha_portal: str
    teams_webhook_url: str = ''
    erro_leitura: str = ''

    @classmethod
    def carregar(
        cls,
        arquivo: Path | None = None,
        ambiente: Mapping[str, str] = environ,
    ) -> 'Configuracao':
        caminho = arquivo or diretorio_aplicacao() / 'config.toml'
        dados: dict[str, object] = {}
        erro_leitura = ''

        try:
            with caminho.open('rb') as config_file:
                dados = load(config_file)
        except FileNotFoundError:
            erro_leitura = f'Arquivo de configuração não encontrado: {caminho}'
        except (OSError, TOMLDecodeError) as error:
            erro_leitura = f'Não foi possível ler {caminho}: {error}'

        return cls(
            unrar_tool=Path(_ler_texto(dados, 'unrar_tool')),
            sumatra=Path(_ler_texto(dados, 'sumatra')),
            pasta_pedidos=Path(_ler_texto(dados, 'pasta_pedidos')),
            impressora=_ler_texto(dados, 'impressora'),
            cnpj_matriz=_ler_segredo(ambiente, 'CNPJ_MATRIZ'),
            senha_portal=_ler_segredo(ambiente, 'SENHA_PORTAL'),
            teams_webhook_url=_ler_segredo(ambiente, 'TEAMS_WEBHOOK_URL'),
            erro_leitura=erro_leitura,
        )

    def validar(self) -> None:
        erros: list[str] = []

        if self.erro_leitura:
            erros.append(self.erro_leitura)
        if str(self.unrar_tool) == '.' or not self.unrar_tool.is_file():
            erros.append('unrar_tool deve apontar para um arquivo válido')
        if str(self.sumatra) == '.' or not self.sumatra.is_file():
            erros.append('sumatra deve apontar para um arquivo válido')
        if str(self.pasta_pedidos) == '.':
            erros.append('pasta_pedidos não foi configurada')
        if not self.impressora:
            erros.append('impressora não foi configurada')
        if not self.cnpj_matriz or not self.senha_portal:
            erros.append('CNPJ_MATRIZ e SENHA_PORTAL devem ser configuradas')

        if erros:
            raise ConfiguracaoError(
                f'Configuração inválida: {"; ".join(erros)}.'
            )


CONFIG = Configuracao.carregar()

UNRAR_TOOL = CONFIG.unrar_tool
SUMATRA = CONFIG.sumatra
BASE_PATH_PEDIDOS = CONFIG.pasta_pedidos
IMPRESSORA = CONFIG.impressora
CNPJ_MATRIZ = CONFIG.cnpj_matriz
SENHA_PORTAL = CONFIG.senha_portal
TEAMS_WEBHOOK_URL = CONFIG.teams_webhook_url


def validar_configuracao() -> None:
    CONFIG.validar()


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
