"""Preferências visuais separadas da seleção operacional de impressora."""
import json
from integracao_hub import gravar_registro
import os
from pathlib import Path


def caminho_preferencia():
    pasta = os.environ.get('HAVAN_DESKTOP_DADOS')
    return (Path(pasta) if pasta else Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'Nunes' / 'PedidosHavan') / 'desktop.json'



def arquivo():
    return caminho_preferencia().with_name('desktop-tema.json')


def ler_tema():
    try:
        dados = json.loads(arquivo().read_text(encoding='utf-8'))
        tema = dados.get('tema') if isinstance(dados, dict) else None
        return tema if tema in ('claro', 'escuro') else 'escuro'
    except (OSError, ValueError):
        return 'escuro'


def salvar_tema(tema):
    if tema not in ('claro', 'escuro'):
        raise ValueError('Tema inválido.')
    destino = arquivo()
    destino.parent.mkdir(parents=True, exist_ok=True)
    gravar_registro(destino, {'tema': tema})
