from src.erros import ConfiguracaoError as ConfiguracaoError
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from os import environ
from pathlib import Path
from tomllib import TOMLDecodeError, load
from typing import Generator, Mapping

from src.seguranca import registrar_segredos


MODELO_CONFIG = """# Copie este arquivo como config.toml e ajuste os valores.
# Variáveis de ambiente "CNPJ_MATRIZ", "SENHA_PORTAL" e "TEAMS_WEBHOOK_URL".
unrar_tool = 'C:\\Program Files\\WinRAR\\UnRAR.exe'
sumatra = 'C:\\LocalApps\\SumatraPDF.exe'
pasta_pedidos = 'D:\\Automacao\\ArquivoPedidos'
impressora = "HP LaserJet M402 - Almoxarifado"
banco_config = 'C:\\Configuracao\\banco-sisplan.json'
banco_perfil = "principal"
"""


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


def criar_modelo_config(caminho_config: Path) -> Path:
    caminho_modelo = caminho_config.with_name('config.example.toml')
    if not caminho_modelo.exists():
        caminho_modelo.write_text(MODELO_CONFIG, encoding='utf-8')
    return caminho_modelo


@dataclass(frozen=True)
class Configuracao:
    unrar_tool: Path
    sumatra: Path
    pasta_pedidos: Path
    impressora: str
    cnpj_matriz: str
    senha_portal: str = field(repr=False)
    teams_webhook_url: str = field(default='', repr=False)
    erro_leitura: str = ''
    banco_config: Path = Path()
    banco_perfil: str = 'principal'

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
            try:
                caminho_modelo = criar_modelo_config(caminho)
                erro_leitura = (
                    f'Arquivo de configuração não encontrado: {caminho}. '
                    f'Modelo disponível em: {caminho_modelo}'
                )
            except OSError as error:
                erro_leitura = (
                    f'Arquivo de configuração não encontrado: {caminho}. '
                    f'Não foi possível criar o modelo: {error}'
                )
        except (OSError, TOMLDecodeError) as error:
            erro_leitura = f'Não foi possível ler {caminho}: {error}'

        config = cls(
            unrar_tool=Path(_ler_texto(dados, 'unrar_tool')),
            sumatra=Path(_ler_texto(dados, 'sumatra')),
            pasta_pedidos=Path(_ler_texto(dados, 'pasta_pedidos')),
            impressora=_ler_texto(dados, 'impressora'),
            cnpj_matriz=_ler_segredo(ambiente, 'CNPJ_MATRIZ'),
            senha_portal=_ler_segredo(ambiente, 'SENHA_PORTAL'),
            teams_webhook_url=_ler_segredo(ambiente, 'TEAMS_WEBHOOK_URL'),
            erro_leitura=erro_leitura,
            banco_config=(
                caminho.parent / _ler_texto(dados, 'banco_config')
                if _ler_texto(dados, 'banco_config') else Path()
            ),
            banco_perfil=_ler_texto(dados, 'banco_perfil') or 'principal',
        )
        registrar_segredos(config.senha_portal, config.teams_webhook_url)
        return config

    def validar(self, apenas_impressao: bool = False) -> None:
        erros: list[str] = []

        if self.erro_leitura:
            erros.append(self.erro_leitura)
        if not apenas_impressao and (str(self.unrar_tool) == '.' or not self.unrar_tool.is_file()):
            erros.append('unrar_tool arquivo inválido')
        if str(self.sumatra) == '.' or not self.sumatra.is_file():
            erros.append('sumatra arquivo inválido')
        if str(self.pasta_pedidos) == '.':
            erros.append('pasta_pedidos não foi configurada')
        if not self.impressora:
            erros.append('nome da impressora não foi configurado')
        if str(self.banco_config) == '.' or not self.banco_config.is_file():
            erros.append('banco_config arquivo de conexão inválido')
        if not apenas_impressao and (not self.cnpj_matriz or not self.senha_portal):
            erros.append('CNPJ_MATRIZ e SENHA_PORTAL devem ser configuradas')

        if erros:
            raise ConfiguracaoError(
                f'Configuração com erro: {"; ".join(erros)}.'
            )


CONFIG = Configuracao.carregar()
_configuracao_execucao: ContextVar[Configuracao | None] = ContextVar('havan_configuracao', default=None)


def configuracao_atual() -> Configuracao:
    return _configuracao_execucao.get() or CONFIG


@contextmanager
def usar_configuracao(config: Configuracao) -> Generator[None, None, None]:
    registrar_segredos(config.senha_portal, config.teams_webhook_url)
    token = _configuracao_execucao.set(config)
    try:
        yield
    finally:
        _configuracao_execucao.reset(token)

UNRAR_TOOL = CONFIG.unrar_tool
SUMATRA = CONFIG.sumatra
BASE_PATH_PEDIDOS = CONFIG.pasta_pedidos
IMPRESSORA = CONFIG.impressora
CNPJ_MATRIZ = CONFIG.cnpj_matriz
SENHA_PORTAL = CONFIG.senha_portal
TEAMS_WEBHOOK_URL = CONFIG.teams_webhook_url
CLIENTE_HAVAN = '00022'


def validar_configuracao(apenas_impressao: bool = False) -> None:
    configuracao_atual().validar(apenas_impressao=apenas_impressao)


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
