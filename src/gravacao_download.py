"""Publicação recuperável do par PDF/XML, sem alterar os nomes usados pelo robô."""
import os
from pathlib import Path
import shutil
from tempfile import mkdtemp

from src.logs import get_logger

logger = get_logger(__name__)
PREFIXO_PREPARACAO = '.nunes-download-'


class DownloadPendenteError(RuntimeError):
    """Há arquivos preservados que precisam de conferência antes da retomada."""


def verificar_download_pendente(pasta: Path) -> None:
    try:
        pendente = next((item for item in pasta.iterdir() if item.name.startswith(PREFIXO_PREPARACAO)), None)
    except FileNotFoundError:
        return
    if pendente is not None:
        raise DownloadPendenteError(
            f'Download com recuperação pendente em {pendente}. '
            'Não importe nem repita o download; peça ao responsável para conferir os arquivos.'
        )


def _gravar(caminho: Path, conteudo: bytes) -> None:
    with caminho.open('xb') as arquivo:
        _ = arquivo.write(conteudo)
        arquivo.flush()
        os.fsync(arquivo.fileno())
    if caminho.read_bytes() != conteudo:
        raise OSError(f'Gravação incompleta do download em {caminho}.')


def _copiar_anterior(origem: Path, destino: Path) -> None:
    with origem.open('rb') as entrada, destino.open('xb') as saida:
        shutil.copyfileobj(entrada, saida)
        saida.flush()
        os.fsync(saida.fileno())


def _limpar_preparacao(temporario: Path, pasta: Path) -> None:
    if temporario.parent.resolve() != pasta.resolve() or not temporario.name.startswith(PREFIXO_PREPARACAO):
        raise ValueError('Diretório de preparação fora da pasta do pedido.')
    try:
        shutil.rmtree(temporario)
    except OSError as erro:
        raise DownloadPendenteError(
            f'Não foi possível limpar a preparação em {temporario}. '
            'Confira os arquivos com o responsável antes de retomar.'
        ) from erro


def publicar_download(pdf: Path, xml: Path, conteudo_pdf: bytes, conteudo_xml: bytes) -> None:
    """Prepara ambos, preserva os anteriores e restaura em falhas capturadas.

    Dois replaces não constituem uma transação. A pasta de preparação permanece
    como bloqueio quando o processo cai ou não consegue restaurar os anteriores.
    """
    pasta = pdf.parent
    if xml.parent != pasta or pdf == xml:
        raise ValueError('PDF e XML devem ter destinos distintos na mesma pasta.')
    verificar_download_pendente(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    temporario = Path(mkdtemp(prefix=PREFIXO_PREPARACAO, dir=pasta))
    destinos = (pdf, xml)
    anteriores: dict[Path, bool] = {}
    publicacao_iniciada = False
    try:
        novos, copias = temporario / 'novos', temporario / 'anteriores'
        novos.mkdir()
        copias.mkdir()
        _gravar(novos / pdf.name, conteudo_pdf)
        _gravar(novos / xml.name, conteudo_xml)
        for destino in destinos:
            try:
                _ = destino.stat()
            except FileNotFoundError:
                anteriores[destino] = False
            else:
                anteriores[destino] = True
                _copiar_anterior(destino, copias / destino.name)
        publicacao_iniciada = True
        for destino in destinos:
            os.replace(novos / destino.name, destino)
    except BaseException as erro:
        falhas: list[str] = []
        if publicacao_iniciada:
            for destino in destinos:
                try:
                    if anteriores[destino]:
                        os.replace(temporario / 'anteriores' / destino.name, destino)
                    else:
                        destino.unlink(missing_ok=True)
                except OSError:
                    logger.exception('Falha ao restaurar %s; cópia em %s.', destino, temporario)
                    falhas.append(destino.name)
        if falhas:
            raise DownloadPendenteError(
                f'Não foi possível restaurar {", ".join(falhas)}. Arquivos preservados em {temporario}. '
                'Não importe nem repita o download; peça ao responsável para conferir os arquivos.'
            ) from erro
        _limpar_preparacao(temporario, pasta)
        raise
    _limpar_preparacao(temporario, pasta)
