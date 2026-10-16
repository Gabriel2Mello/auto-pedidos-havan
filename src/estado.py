"""Histórico local das etapas, persistido antes de ações que não devem se repetir."""

from src.erros import EstadoError as EstadoError
from src.erros import EstadoEmUsoError
import errno
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import TracebackType
from typing import IO, Sequence

from src.config import diretorio_aplicacao
from src.logs import get_logger
from src.pedidos import ItemEsperado

from src.etapas import ETAPAS, ETAPAS_FINAIS, Etapa, fila_da_etapa

logger = get_logger(__name__)


@dataclass(frozen=True)
class EstadoPedido:
    pedido: str
    numero: str
    etapa: Etapa
    empresa: int | None = None
    pdf: str = ''
    erro: str = ''


class EstadoPedidos:
    def __init__(self, caminho: Path | None = None) -> None:
        self.caminho = caminho or diretorio_aplicacao() / 'estado-pedidos.sqlite3'
        self._conexao: sqlite3.Connection | None = None
        self._trava: IO[bytes] | None = None

    def __enter__(self) -> 'EstadoPedidos':
        try:
            self._trava = self.caminho.with_suffix('.lock').open('a+b')
            self._trava.seek(0, os.SEEK_END)
            if self._trava.tell() == 0:
                self._trava.write(b'0')
                self._trava.flush()
            self._trava.seek(0)
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(self._trava.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self._trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as erro:
                if erro.errno in (errno.EACCES, errno.EAGAIN):
                    raise EstadoEmUsoError('Outra execução ainda possui o histórico local.') from None
                raise
        except EstadoEmUsoError:
            self._fechar()
            raise
        except OSError:
            logger.exception('Histórico: falha ao adquirir a trava; arquivo=%s.', self.caminho)
            self._fechar()
            raise EstadoError(
                'Histórico local indisponível ou outra execução está em andamento. '
                'Confira a pasta da aplicação e feche a outra execução.'
            ) from None
        try:
            self._conexao = sqlite3.connect(self.caminho, timeout=2)
            self._conexao.row_factory = sqlite3.Row
            self._conexao.execute('PRAGMA synchronous = FULL')
            self._conexao.execute(
                'CREATE TABLE IF NOT EXISTS pedidos ('
                'pedido TEXT PRIMARY KEY, numero TEXT NOT NULL, etapa TEXT NOT NULL, '
                'empresa INTEGER, pdf TEXT NOT NULL, erro TEXT NOT NULL, atualizado_em TEXT NOT NULL)'
            )
            self._conexao.execute(
                'CREATE TABLE IF NOT EXISTS itens_esperados ('
                'pedido TEXT NOT NULL, codigo TEXT NOT NULL, cor TEXT NOT NULL, '
                'tamanho TEXT NOT NULL, quantidade TEXT NOT NULL, '
                'PRIMARY KEY (pedido,codigo,cor,tamanho))'
            )
            self._conexao.commit()
        except sqlite3.Error as error:
            self._registrar_erro(error, 'abrir')
            self._fechar()
            raise EstadoError('Não foi possível abrir o histórico local dos pedidos.') from None
        return self

    def _registrar_erro(self, erro: Exception, operacao: str) -> None:
        logger.exception('Histórico: operação=%s arquivo=%s sqlite_code=%s sqlite_name=%s',
                         operacao, self.caminho, getattr(erro, 'sqlite_errorcode', ''),
                         getattr(erro, 'sqlite_errorname', ''))

    def _fechar(self) -> None:
        try:
            if self._conexao is not None:
                self._conexao.close()
        finally:
            self._conexao = None
            if self._trava is not None:
                self._trava.close()  # O sistema operacional libera a trava, inclusive após falha.
                self._trava = None

    def __exit__(
        self, exc_type: type[BaseException] | None, exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._fechar()

    def _conectar(self) -> sqlite3.Connection:
        if self._conexao is None:
            raise EstadoError('Histórico local não iniciado.')
        return self._conexao

    def obter(self, pedido: str) -> EstadoPedido | None:
        try:
            linha = self._conectar().execute(
                'SELECT pedido,numero,etapa,empresa,pdf,erro FROM pedidos WHERE pedido=?', (pedido,),
            ).fetchone()
            if linha is not None and linha['etapa'] not in ETAPAS:
                raise EstadoError('Histórico contém uma etapa desconhecida. Avise o responsável.')
            return EstadoPedido(**dict(linha)) if linha is not None else None
        except (sqlite3.Error, TypeError) as error:
            self._registrar_erro(error, 'ler pedido')
            raise EstadoError('Não foi possível ler o histórico do pedido.') from None

    def listar(self) -> list[EstadoPedido]:
        try:
            linhas = self._conectar().execute(
                "SELECT pedido,numero,etapa,empresa,pdf,erro FROM pedidos "
                "ORDER BY CASE WHEN etapa IN (?,?) THEN 1 ELSE 0 END, rowid DESC", ETAPAS_FINAIS
            ).fetchall()
            if any(linha['etapa'] not in ETAPAS for linha in linhas):
                raise EstadoError('Histórico contém uma etapa desconhecida. Avise o responsável.')
            return [EstadoPedido(**dict(linha)) for linha in linhas]
        except (sqlite3.Error, TypeError) as error:
            self._registrar_erro(error, 'listar pedidos')
            raise EstadoError('Não foi possível listar os pedidos.') from None

    def salvar(self, estado: EstadoPedido) -> None:
        if estado.etapa not in ETAPAS:
            raise EstadoError('Não foi possível reconhecer a etapa do pedido.')
        try:
            conexao = self._conectar()
            with conexao:
                conexao.execute(
                    'INSERT INTO pedidos VALUES (?,?,?,?,?,?,?) '
                    'ON CONFLICT(pedido) DO UPDATE SET numero=excluded.numero, etapa=excluded.etapa, '
                    'empresa=excluded.empresa, pdf=excluded.pdf, erro=excluded.erro, '
                    'atualizado_em=excluded.atualizado_em',
                    (estado.pedido, estado.numero, estado.etapa, estado.empresa,
                     estado.pdf, estado.erro, datetime.now(timezone.utc).isoformat()),
                )
        except sqlite3.Error as error:
            self._registrar_erro(error, 'salvar etapa')
            raise EstadoError('Não foi possível salvar a etapa do pedido. Execução interrompida.') from None
        logger.debug('Histórico atualizado: pedido=%s etapa=%s numero=%s erro=%s',
                     estado.pedido, estado.etapa, estado.numero, estado.erro)

    def adicionar_pedidos(self, pedidos: Sequence[str]) -> None:
        """Persiste a lista inteira numa transação, preservando etapas já existentes."""
        try:
            conexao = self._conectar()
            agora = datetime.now(timezone.utc).isoformat()
            with conexao:
                conexao.executemany(
                    "INSERT INTO pedidos VALUES (?, '', 'para_baixar', NULL, '', '', ?) "
                    'ON CONFLICT(pedido) DO NOTHING',
                    [(pedido, agora) for pedido in dict.fromkeys(pedidos)],
                )
        except sqlite3.Error as error:
            self._registrar_erro(error, 'salvar lista')
            raise EstadoError('Não foi possível salvar a lista de pedidos. Nenhum processamento foi iniciado.') from None
        logger.info('Lista preservada no histórico: %s pedido(s) informado(s).', len(set(pedidos)))

    def pendentes(self) -> list[str]:
        try:
            return [linha[0] for linha in self._conectar().execute(
                "SELECT pedido FROM pedidos WHERE etapa NOT IN (?,?) ORDER BY rowid", ETAPAS_FINAIS
            )]
        except sqlite3.Error as error:
            self._registrar_erro(error, 'consultar pendências')
            raise EstadoError('Não foi possível consultar as etapas pendentes.') from None

    def filas(self) -> dict[str, int]:
        """As filas são visões do mesmo histórico; não há movimentação entre arquivos."""
        filas: dict[str, int] = dict.fromkeys(('para_baixar', 'baixados', 'importados', 'enviados'), 0)
        try:
            for etapa, quantidade in self._conectar().execute('SELECT etapa,count(*) FROM pedidos GROUP BY etapa'):
                try:
                    fila = fila_da_etapa(etapa)
                except ValueError:
                    raise EstadoError('Histórico contém etapa desconhecida. Avise o responsável.') from None
                filas[fila] += quantidade
            return filas
        except sqlite3.Error as error:
            self._registrar_erro(error, 'consultar filas')
            raise EstadoError('Não foi possível consultar as filas internas.') from None

    def inclusoes_incertas(self) -> list[str]:
        try:
            return [linha[0] for linha in self._conectar().execute(
                "SELECT pedido FROM pedidos WHERE etapa IN ('importacao_iniciada','gravacao_pendente') ORDER BY rowid"
            )]
        except sqlite3.Error as error:
            self._registrar_erro(error, 'conferir inclusões')
            raise EstadoError('Não foi possível conferir as inclusões pendentes.') from None

    def liberar_importacao(self, pedido: str) -> None:
        """Usado somente por --reiniciar, após conferir ausência no banco."""
        try:
            conexao = self._conectar()
            with conexao:
                conexao.execute(
                    "UPDATE pedidos SET etapa='baixado', numero='', empresa=NULL, pdf='', erro='' "
                    "WHERE pedido=? AND etapa IN ('importacao_iniciada','gravacao_pendente')", (pedido,),
                )
        except sqlite3.Error as error:
            self._registrar_erro(error, 'liberar inclusão')
            raise EstadoError('Não foi possível liberar a nova tentativa de importação.') from None

    def salvar_itens_esperados(self, pedido: str, itens: Sequence[ItemEsperado]) -> None:
        if not itens or any(not i.quantidade.is_finite() or i.quantidade <= 0 for i in itens):
            raise EstadoError('Itens esperados ausentes ou inválidos. Inclusão bloqueada.')
        try:
            conexao = self._conectar()
            with conexao:
                conexao.execute('DELETE FROM itens_esperados WHERE pedido=?', (pedido,))
                conexao.executemany('INSERT INTO itens_esperados VALUES (?,?,?,?,?)',
                                   [(pedido, i.codigo, i.cor, i.tamanho, str(i.quantidade)) for i in itens])
        except sqlite3.Error as error:
            self._registrar_erro(error, 'salvar itens esperados')
            raise EstadoError('Não foi possível salvar os itens esperados. Inclusão bloqueada.') from None
        logger.debug('Pedido %s: %s combinação(ões) preservada(s) para conferir a gravação.', pedido, len(itens))

    def obter_itens_esperados(self, pedido: str) -> list[ItemEsperado]:
        try:
            linhas = self._conectar().execute(
                'SELECT codigo,cor,tamanho,quantidade FROM itens_esperados WHERE pedido=? '
                'ORDER BY codigo,cor,tamanho', (pedido,),
            )
            itens = [ItemEsperado(codigo, cor, tamanho, Decimal(quantidade))
                     for codigo, cor, tamanho, quantidade in linhas]
            if any(not i.quantidade.is_finite() or i.quantidade <= 0 for i in itens):
                raise ValueError('Quantidade inválida no histórico de itens')
            return itens
        except (sqlite3.Error, InvalidOperation, ValueError) as error:
            self._registrar_erro(error, 'ler itens esperados')
            raise EstadoError('Não foi possível conferir os itens esperados no histórico.') from None
