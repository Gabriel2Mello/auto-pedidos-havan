"""Redação de segredos compartilhada por logs e mensagens de suporte."""
import re
from threading import RLock
from urllib.parse import parse_qsl, urlsplit

_trava = RLock()
_segredos: set[str] = set()


def registrar_segredos(*valores: str) -> None:
    candidatos: set[str] = set()
    for valor in valores:
        if not valor:
            continue
        candidatos.add(valor)
        if valor.startswith(('http://', 'https://')):
            try:
                partes = urlsplit(valor)
            except ValueError:
                continue
            if partes.path not in ('', '/') or partes.query:
                candidatos.add(partes.path + ('?' + partes.query if partes.query else ''))
            candidatos.update(v for _, v in parse_qsl(partes.query) if v)
    with _trava:
        _segredos.update(v for v in candidatos if v)


def redigir(texto: str) -> str:
    with _trava:
        segredos = sorted(_segredos, key=len, reverse=True)
    for segredo in segredos:
        if len(segredo) >= 4:
            texto = texto.replace(segredo, '[oculto]')
        else:
            texto = re.sub(r'(?<!\w)' + re.escape(segredo) + r'(?!\w)', '[oculto]', texto)
    # Defesa adicional para URLs antigas e exceções de bibliotecas HTTP.
    texto = re.sub(r'https?://[^\s\'"<>]+',
                   lambda m: '[url de integração oculta]' if any(
                       chave in m.group().lower() for chave in ('webhook', 'sig=', 'token=', 'key='))
                   else m.group(), texto)
    return texto
