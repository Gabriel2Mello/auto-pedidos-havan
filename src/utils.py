import ctypes
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from io import BytesIO
from pathlib import Path
from time import sleep
from typing import cast

import rarfile
import requests
from pywinauto.keyboard import send_keys
from pywinauto import WindowSpecification

from src.logs import get_logger
from src.pedidos import normalizar_pedidos
from src.config import (
    BASE_PATH_PEDIDOS,
    UNRAR_TOOL,
    TEAMS_WEBHOOK_URL,
)

logger = get_logger(__name__)


def set_app_id() -> None:
    try:
        my_app_id = 'g2mello.autopedidoshavan.v1'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(my_app_id)
    except Exception:
        pass


def input_pedido() -> list[str] | None:
    pedidos = normalizar_pedidos(input('Pedido: '))
    if not pedidos:
        return None
    return pedidos


def caminho_xml(pedido: str) -> Path:
    caminho = BASE_PATH_PEDIDOS / str(pedido)
    return caminho / f'arq_de_integracao {pedido}.xml'


def caminho_pdf(pedido: str) -> Path:
    caminho = BASE_PATH_PEDIDOS / str(pedido)
    return caminho / f'ordem_de_compra {pedido}.pdf'


def carregar_xml(arquivo: str | Path) -> ET.Element:
    return ET.parse(arquivo).getroot()


def extrair_xml(content: bytes) -> bytes:
    rarfile.UNRAR_TOOL = str(UNRAR_TOOL)
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
    motivo_formatado = ' '.join(motivo.split())
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


def enviar_alerta_teams(
    pedido: str,
    numero_interno: str = '',
    mensagem: str = '',
) -> None:
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
                            'text': f'{mensagem}',
                            'weight': 'Bolder',
                            'size': 'large',
                            'color': 'Accent',
                        },
                        {
                            'type': 'TextBlock',
                            'text': f'{pedido}',
                            'weight': 'Bolder',
                            'size': 'large',
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
        if response.status_code in {200, 202}:
            logger.info('Alerta enviado para o Teams.')
        else:
            logger.debug(
                'Falha ao enviar alerta para o Teams. %s: %s',
                response.status_code,
                response.text,
            )

    except Exception as error:
        logger.debug('Falha ao enviar alerta para Teams: %s', error)


def send_keys_sleep(keys: str, sleep_time: float = 0.1) -> None:
    send_keys(keys)
    sleep(sleep_time)


def aguardar_campo(campo: WindowSpecification, timeout: int = 5) -> WindowSpecification:
    campo.wait('ready', timeout=timeout)
    return campo


class LoginInvalidoError(Exception):
    """Exceção para quando o site retorna 200, mas falhou o login"""

    def __init__(self, message: str = 'CNPJ ou senha inválidos') -> None:
        super().__init__(message)


class SisplanError(Exception):
    def __init__(self, message: str = 'Falha na tela do Sisplan') -> None:
        super().__init__(message)
