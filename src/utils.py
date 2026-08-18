import ctypes
import sys
from datetime import datetime, timedelta
from io import BytesIO
from typing import cast
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
import requests
from time import sleep

import rarfile
from pywinauto.keyboard import send_keys

from src.logs import get_logger
from src.config import (
    BASE_PATH_PEDIDOS,
    UNRAR_TOOL,
    TEAMS_WEBHOOK_URL,
)

logger = get_logger(__name__)
rarfile.UNRAR_TOOL = UNRAR_TOOL


def set_app_id() -> None:
    try:
        my_app_id = 'g2mello.autopedidoshavan.v1'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(my_app_id)
    except Exception:
        pass


def input_pedido() -> list[str] | None:
    pedidos_input = input('Pedido: ').strip()
    if not pedidos_input:
        return None

    ano_atual = str(datetime.now().year)
    pedidos_finais = []

    for p in pedidos_input.split(','):
        pedido_limpo = p.strip()
        if not pedido_limpo:
            continue

        if len(pedido_limpo) < 9:
            pedido_limpo = f"{ano_atual}-{pedido_limpo}"

        if len(pedido_limpo) >= 9:
            pedidos_finais.append(pedido_limpo)

    return pedidos_finais if pedidos_finais else None


def formata_data(data_xml: str, dias: int=0) -> str:
    data = datetime.strptime(data_xml, '%d/%m/%y') + timedelta(days=dias)
    return data.strftime('%d/%m/%Y')


def caminho_xml(pedido: str) -> Path:
    caminho = BASE_PATH_PEDIDOS / str(pedido)
    return caminho / f'arq_de_integracao {pedido}.xml'


def caminho_pdf(pedido: str) -> Path:
    caminho = BASE_PATH_PEDIDOS / str(pedido)
    return caminho / f'ordem_de_compra {pedido}.pdf'


def normalizar(texto: str) -> str:
    if not texto:
        raise RuntimeError('Texto não encontrado')

    return unicodedata.normalize('NFKD', texto)\
        .encode('ASCII', 'ignore')\
        .decode()\
        .upper()


def carregar_xml(arquivo: str | Path) -> ET.Element:
    return ET.parse(arquivo).getroot()


def extrair_xml(content: bytes) -> bytes:
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
    else:
        return Path(sys.argv[0]).parent.absolute()


def salvar_pedido_txt(pedido: str, promocional: bool = False) -> None:
    if not pedido:
        return

    nome_arquivo = 'PROMOCIONAL.txt' if promocional else 'pedidos_com_erro.txt'
    pasta_destino = obter_diretorio_executavel()
    arquivo_destino = pasta_destino / nome_arquivo

    agora = datetime.now().strftime('%d/%m/%Y %H:%M')

    try:
        with open(arquivo_destino, 'a', encoding='utf-8') as f:
            f.write(f"[{agora}] {pedido}\n")

        if promocional:
            logger.info(f"Adicionado ao arquivo: {nome_arquivo}")
        else:
            logger.info_split(f"Adicionado ao arquivo: {nome_arquivo}")

    except Exception as e:
        logger.debug(f"Não foi possível atualizar o arquivo {nome_arquivo}: {e}")


def enviar_alerta_teams(pedido: str, numero_interno: str = "", mensagem: str = "") -> None:
    if not TEAMS_WEBHOOK_URL:
        logger.debug('URL do Teams não configurada.')
        return

    payload = {
        'type': 'message',
        'attachments': [
            {
                'contentType': 'application/vnd.microsoft.card.adaptive',
                'content': {
                    '$schema': 'http://adaptivecards.io/schemas/adaptive-card.json',
                    'type': 'AdaptiveCard',
                    'version': '1.0',
                    'body': [
                        {
                            'type': 'TextBlock',
                            'text': f'{mensagem}: {pedido}',
                            'weight': 'Bolder',
                            'size': 'large',
                            'color': 'Accent'
                        },
                        {
                            'type': 'TextBlock',
                            'text': f'Número interno: {numero_interno}',
                            'wrap': True
                        }
                    ]
                }
            }
        ]
    }

    try:
        response = requests.post(TEAMS_WEBHOOK_URL, json=payload, timeout=10)
        if response.status_code == 200 or response.status_code == 202:
            logger.info(f'Alerta enviado para o Teams.')
        else:
            logger.debug(f'Falha ao enviar alerta para o Teams. {response.status_code}: {response.text}')
    except Exception as e:
        logger.debug(f'Falha ao enviar alerta para Teams: {e}')


def send_keys_sleep(keys: str, sleep_time: float = 0.1) -> None:
    send_keys(keys)
    sleep(sleep_time)


class LoginInvalidoError(Exception):
    """Exceção para quando o site retorna 200, mas falhou o login"""
    def __init__(self, message: str='CNPJ ou senha inválidos') -> None:
        super().__init__(message)


class SisplanError(Exception):
    def __init__(self, message: str='Falha na tela do Sisplan') -> None:
        super().__init__(message)

