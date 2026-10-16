"""Consultas de pré-validação; não realiza gravações no Sisplan."""

from src.erros import BancoSisplanError as BancoSisplanError, GravacaoNaoConfirmadaError as GravacaoNaoConfirmadaError
import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from statistics import median_low
from time import monotonic, sleep
from types import TracebackType
from typing import Sequence, cast

from pg8000.dbapi import Connection, connect

from src.config import CLIENTE_HAVAN
from src.logs import get_logger
from src.pedidos import ItemEsperado
from src.seguranca import registrar_segredos

logger = get_logger(__name__)


def registrar_erro_banco(erro: Exception, etapa: str) -> None:
    """Diagnóstico sem reproduzir parâmetros de conexão ou senhas do driver."""
    sqlstate = ''
    if erro.args and isinstance(erro.args[0], dict):
        detalhes = cast(dict[str, object], erro.args[0])
        codigo = detalhes.get('C', '')
        sqlstate = codigo if isinstance(codigo, str) else ''
    logger.error('Banco Sisplan: etapa=%s tipo=%s sqlstate=%s errno=%s',
                 etapa, type(erro).__name__, sqlstate, getattr(erro, 'errno', ''))


@dataclass(frozen=True)
class ParametrosBanco:
    host: str
    port: int
    database: str
    user: str = field(repr=False)
    password: str = field(repr=False)


def carregar_parametros(arquivo: Path, perfil: str) -> ParametrosBanco:
    try:
        dados = json.loads(arquivo.read_text(encoding='utf-8'))
        valores = dados['perfis'][perfil]
        nomes = ('PGHOST', 'PGPORT', 'PGDATABASE', 'PGUSER', 'PGPASSWORD')
        if not all(
            isinstance(valores[nome], str) and valores[nome].strip()
            for nome in nomes
        ):
            raise ValueError('Parâmetros incompletos')
        porta = int(valores['PGPORT'])
        if not 1 <= porta <= 65535:
            raise ValueError('Porta inválida')
        registrar_segredos(valores['PGPASSWORD'])
        return ParametrosBanco(
            host=valores['PGHOST'], port=porta, database=valores['PGDATABASE'],
            user=valores['PGUSER'], password=valores['PGPASSWORD'],
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        logger.error('Configuração do banco: arquivo=%s perfil=%s tipo=%s linha=%s coluna=%s',
                     arquivo, perfil, type(error).__name__,
                     getattr(error, 'lineno', ''), getattr(error, 'colno', ''))
        # Não propagar detalhes do JSON ou do driver, que podem conter segredos.
        raise BancoSisplanError(
            'Configuração do banco inválida. Confira banco_config e banco_perfil.'
        ) from None


@dataclass(frozen=True)
class PedidoExistente:
    numero: str
    empresa: int | None


@dataclass(frozen=True)
class ProdutoCadastrado:
    codigo: str
    cor: str
    tamanho: str


class BancoSisplan:
    def __init__(self, arquivo: Path, perfil: str = 'principal') -> None:
        self._parametros = carregar_parametros(arquivo, perfil)
        self._conexao: Connection | None = None

    def __enter__(self) -> 'BancoSisplan':
        parametros = self._parametros
        try:
            self._conexao = connect(
                host=parametros.host, port=parametros.port,
                database=parametros.database, user=parametros.user,
                password=parametros.password, timeout=10,
                application_name='auto_pedidos_havan_leitura',
            )
        except Exception as error:
            registrar_erro_banco(error, 'conexão')
            raise BancoSisplanError(
                'Não foi possível conectar ao banco Sisplan. '
                'Confira a rede, as credenciais e as permissões.'
            ) from None
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._conexao is not None:
            try:
                self._conexao.close()
            except Exception:
                # A conexão só executa leituras; não mascarar o erro original.
                pass
            finally:
                self._conexao = None

    def reconectar(self) -> None:
        """Chamado somente depois de o operador autorizar outra tentativa."""
        self.__exit__(None, None, None)
        self.__enter__()

    def _consultar(self, sql: str, parametros: tuple[object, ...]) -> list[list[object]]:
        conexao = self._conexao
        if conexao is None:
            raise BancoSisplanError('Conexão com o banco Sisplan não iniciada.')
        try:
            cursor = conexao.cursor()
            try:
                # Cada consulta termina sua transação antes de aguardar portal/GUI.
                cursor.execute('SET TRANSACTION READ ONLY')
                cursor.execute("SET LOCAL statement_timeout = '8000ms'")
                cursor.execute("SET LOCAL lock_timeout = '1500ms'")
                cursor.execute(sql, parametros)
                linhas = cast(Sequence[Sequence[object]], cursor.fetchall())
                return [list(linha) for linha in linhas]
            finally:
                conexao.rollback()
                cursor.close()
        except Exception as error:
            registrar_erro_banco(error, 'consulta')
            self.__exit__(None, None, None)
            raise BancoSisplanError(
                'Falha ao consultar o banco Sisplan. '
                'Importação interrompida antes de incluir o próximo pedido.'
            ) from None

    def consultar_pedidos(
        self, pedidos: Sequence[str],
    ) -> dict[str, list[PedidoExistente]]:
        if not pedidos:
            return {}
        linhas = self._consultar(
            'SELECT ped_cli, numero, emp_id FROM sisplan.pedido_001 '
            'WHERE codcli = %s AND ped_cli = ANY(%s)',
            (CLIENTE_HAVAN, list(pedidos)),
        )
        resultado: dict[str, list[PedidoExistente]] = {}
        for pedido, numero, empresa in linhas:
            resultado.setdefault(str(pedido), []).append(
                PedidoExistente(str(numero), int(str(empresa)) if empresa is not None else None)
            )
        return resultado

    def consultar_referencia_numero(self) -> int:
        """Usa a ordem de inclusão, sem deixar um número isolado definir a faixa."""
        linhas = self._consultar(
            'SELECT numero FROM sisplan.pedido_001 '
            "WHERE BTRIM(numero::text) ~ '^[0-9]+$' "
            'ORDER BY id DESC LIMIT 5', (),
        )
        numeros = [int(str(linha[0]).strip()) for linha in linhas]
        if len(numeros) < 3 or min(numeros) <= 0:
            raise BancoSisplanError(
                'Não há números internos recentes suficientes para conferir a sequência. '
                'Solicite a conferência do Sisplan ao responsável antes de incluir pedidos.'
            )
        referencia = median_low(numeros)
        logger.info('Referência dos números internos: %s (pedidos recentes: %s).', referencia, numeros)
        return referencia

    def consultar_barras(
        self, barras: Sequence[str],
    ) -> dict[str, set[ProdutoCadastrado]]:
        if not barras:
            return {}
        linhas = self._consultar(
            'SELECT DISTINCT pa.barra, pa.codigo, pa.cor, pa.tam '
            'FROM sisplan.pa_iten_001 pa '
            'JOIN sisplan.produto_001 p ON p.codigo = pa.codigo '
            'WHERE pa.barra = ANY(%s)',
            (list(barras),),
        )
        resultado: dict[str, set[ProdutoCadastrado]] = {}
        for barra, codigo, cor, tamanho in linhas:
            resultado.setdefault(str(barra), set()).add(
                ProdutoCadastrado(str(codigo), str(cor), str(tamanho))
            )
        return resultado

    def confirmar_gravacao(
        self, pedido: str, numero: str, timeout: float = 10, intervalo: float = 0.5,
        *, itens_esperados: Sequence[ItemEsperado] | None = None,
    ) -> PedidoExistente:
        """Aguarda o cabeçalho e seus itens ficarem visíveis em leitura no banco."""
        numero = numero.strip()
        if not numero:
            raise GravacaoNaoConfirmadaError('Número interno vazio; gravação não confirmada.')
        if itens_esperados is not None and not itens_esperados:
            raise GravacaoNaoConfirmadaError('Lista de itens esperados vazia; gravação não confirmada.')
        limite = monotonic() + timeout
        divergencias: list[str] = []
        while True:
            linhas = self._consultar(
                'SELECT p.numero, p.emp_id, '
                'EXISTS (SELECT 1 FROM sisplan.ped_iten_001 i WHERE i.id_ped = p.id) '
                'FROM sisplan.pedido_001 p WHERE p.codcli = %s AND p.ped_cli = %s',
                (CLIENTE_HAVAN, pedido),
            )
            if linhas:
                if len(linhas) != 1 or str(linhas[0][0]).strip() != numero:
                    raise GravacaoNaoConfirmadaError(
                        f'Pedido {pedido}: número interno divergente ou cadastro duplicado. '
                        'Confira o Sisplan antes de continuar.'
                    )
                if linhas[0][2] is True:
                    divergencias = self.divergencias_itens(pedido, numero, itens_esperados) if itens_esperados is not None else []
                    if not divergencias:
                        empresa = linhas[0][1]
                        return PedidoExistente(numero, int(str(empresa)) if empresa is not None else None)
            restante = limite - monotonic()
            if restante <= 0:
                if divergencias:
                    logger.error('Pedido %s / interno %s: itens divergentes: %s', pedido, numero, '; '.join(divergencias))
                raise GravacaoNaoConfirmadaError(
                    f'Gravação do pedido {pedido} / interno {numero} não confirmada '
                    'com seus itens e quantidades. Nenhuma impressão foi enviada. Confira o log.'
                )
            sleep(min(intervalo, restante))

    def divergencias_itens(
        self, pedido: str, numero: str, esperados: Sequence[ItemEsperado],
    ) -> list[str]:
        linhas = self._consultar(
            'SELECT i.codigo, i.cor, i.tam, SUM(COALESCE(i.qtde, 0)) '
            'FROM sisplan.ped_iten_001 i JOIN sisplan.pedido_001 p ON p.id = i.id_ped '
            'WHERE p.codcli = %s AND p.ped_cli = %s AND p.numero = %s '
            'GROUP BY i.codigo, i.cor, i.tam', (CLIENTE_HAVAN, pedido, numero),
        )
        gravados = {(str(codigo), str(cor), str(tamanho)): Decimal(str(qtde))
                    for codigo, cor, tamanho, qtde in linhas}
        previstos: dict[tuple[str, str, str], Decimal] = {}
        for item in esperados:
            chave = (item.codigo, item.cor, item.tamanho)
            previstos[chave] = previstos.get(chave, Decimal(0)) + item.quantidade
        return [f'{codigo}/{cor}/{tam}: XML={previstos.get((codigo, cor, tam), Decimal(0))} '
                f'Sisplan={gravados.get((codigo, cor, tam), Decimal(0))}'
                for codigo, cor, tam in sorted(previstos.keys() | gravados.keys())
                if previstos.get((codigo, cor, tam)) != gravados.get((codigo, cor, tam))]
