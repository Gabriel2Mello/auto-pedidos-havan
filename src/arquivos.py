"""Caminhos, XML e registros de arquivos da automacao."""
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import cast

import rarfile

from src.config import configuracao_atual
from src.logs import get_logger

logger = get_logger(__name__)
MAX_CARACTERES_MOTIVO = 500


def caminho_xml(pedido: str) -> Path:
    caminho = configuracao_atual().pasta_pedidos / str(pedido)
    return caminho / f'arq_de_integracao {pedido}.xml'


def caminho_pdf(pedido: str) -> Path:
    caminho = configuracao_atual().pasta_pedidos / str(pedido)
    return caminho / f'ordem_de_compra {pedido}.pdf'


def carregar_xml(arquivo: str | Path) -> ET.Element:
    return ET.parse(arquivo).getroot()


def extrair_xml(content: bytes) -> bytes:
    rarfile.UNRAR_TOOL = str(configuracao_atual().unrar_tool)
    with rarfile.RarFile(BytesIO(content)) as rf:
        arquivos = cast(list[str], rf.namelist())

        xml_file: str | None = next(
            (f for f in arquivos
             if f.lower().endswith('.xml')),
            None
        )

        if not xml_file:
            raise FileNotFoundError('.RAR sem arquivo XML')

        return cast(bytes, rf.read(xml_file))


def obter_diretorio_executavel() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(sys.argv[0]).parent.absolute()


def formatar_motivo_erro(mensagem: str, erro: Exception) -> str:
    detalhe = str(erro).strip()
    return f'{mensagem}, {detalhe}' if detalhe else mensagem


def normalizar_motivo(motivo: str) -> str:
    motivo_formatado = ' '.join(motivo.split())
    if len(motivo_formatado) <= MAX_CARACTERES_MOTIVO:
        return motivo_formatado
    return f'{motivo_formatado[:MAX_CARACTERES_MOTIVO - 3]}...'


def salvar_pedido_txt(
    pedido: str,
    promocional: bool = False,
    motivo: str = '',
) -> None:
    if not pedido:
        return

    nome_arquivo = 'PROMOCIONAL.txt' if promocional else 'pedidos_com_erro.txt'
    pasta_destino = obter_diretorio_executavel()
    arquivo_destino = pasta_destino / nome_arquivo

    agora = datetime.now().strftime('%d/%m/%Y %H:%M')
    motivo_formatado = normalizar_motivo(motivo)
    sufixo = f', {motivo_formatado}' if motivo_formatado else ''

    try:
        with arquivo_destino.open('a', encoding='utf-8') as arquivo:
            arquivo.write(f'[{agora}] {pedido}{sufixo}\n')

        logger.info(f'Adicionado ao arquivo: {nome_arquivo}')

    except OSError as error:
        logger.debug(
            'Não foi possível atualizar o arquivo %s: %s',
            nome_arquivo,
            error,
        )
