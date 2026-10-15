"""Notificacoes opcionais; falhas nao repetem a importacao."""
import requests

from src.config import configuracao_atual
from src.logs import get_logger

logger = get_logger(__name__)


def enviar_alerta_teams(
    pedido: str,
    numero_interno: str = '',
    mensagem: str = '',
) -> None:
    webhook = configuracao_atual().teams_webhook_url
    if not webhook:
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
        response = requests.post(webhook, json=payload, timeout=10)
        if response.status_code in {200, 202}:
            logger.info('Alerta enviado para o Teams.')
        else:
            logger.debug(
                'Falha ao enviar alerta para o Teams. status=%s',
                response.status_code,
            )

    except Exception as error:
        logger.debug('Falha ao enviar alerta para Teams: tipo=%s', type(error).__name__)
