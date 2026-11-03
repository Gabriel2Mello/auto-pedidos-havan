"""Filas do Windows (mesma enumeração da Impressão de OPs) e preferência Havan."""
import ctypes
from ctypes import wintypes
import json
import logging
import os
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile
from typing import Mapping


def listar_impressoras_windows() -> list[str]:
    if sys.platform != 'win32':
        raise RuntimeError('A seleção de impressoras requer o Windows.')

    class PRINTER_INFO_4W(ctypes.Structure):
        _fields_ = [('pPrinterName', wintypes.LPWSTR),
                    ('pServerName', wintypes.LPWSTR), ('Attributes', wintypes.DWORD)]

    try:
        enumerar = ctypes.WinDLL('winspool.drv', use_last_error=True).EnumPrintersW
        enumerar.argtypes = [wintypes.DWORD, wintypes.LPWSTR, wintypes.DWORD,
                             ctypes.c_void_p, wintypes.DWORD,
                             ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD)]
        enumerar.restype = wintypes.BOOL
        tamanho, quantidade = wintypes.DWORD(), wintypes.DWORD()
        # LOCAL | CONNECTIONS, nível 4: consulta o cache local, sem abrir cada fila remota.
        if enumerar(6, None, 4, None, 0, ctypes.byref(tamanho), ctypes.byref(quantidade)):
            return []
        erro = ctypes.get_last_error()
        if erro != 122:  # ERROR_INSUFFICIENT_BUFFER
            raise ctypes.WinError(erro)
        # O conjunto de filas pode mudar entre a consulta do tamanho e a leitura.
        for _ in range(3):
            buffer = ctypes.create_string_buffer(tamanho.value)
            if enumerar(6, None, 4, buffer, len(buffer), ctypes.byref(tamanho), ctypes.byref(quantidade)):
                filas = ctypes.cast(buffer, ctypes.POINTER(PRINTER_INFO_4W))
                return sorted({filas[i].pPrinterName for i in range(quantidade.value)
                               if filas[i].pPrinterName}, key=str.casefold)
            erro = ctypes.get_last_error()
            if erro != 122:
                raise ctypes.WinError(erro)
        raise RuntimeError('A lista de impressoras mudou durante a consulta. Atualize a lista.')
    except OSError as erro:
        logging.exception('Falha ao consultar impressoras do Windows')
        raise RuntimeError('Não foi possível listar as impressoras. Verifique o serviço de impressão do Windows e atualize a lista.') from erro


def caminho_preferencia(ambiente: Mapping[str, str] = os.environ) -> Path:
    pasta = ambiente.get('HAVAN_IMPRESSORA_DADOS')
    base = Path(ambiente.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local')
    return (Path(pasta) if pasta else base / 'Nunes' / 'PedidosHavan') / 'impressora.json'


def ler_impressora(padrao: str, ambiente: Mapping[str, str] = os.environ) -> str:
    try:
        dados = json.loads(caminho_preferencia(ambiente).read_text(encoding='utf-8'))
        nome = dados.get('impressora') if isinstance(dados, dict) else None
        if not isinstance(nome, str) or not nome.strip():
            raise ValueError('Preferência de impressora inválida.')
        return nome
    except FileNotFoundError:
        return padrao
    except (OSError, ValueError):
        logging.warning('Não foi possível ler a preferência de impressora Havan', exc_info=True)
        raise ValueError('Não foi possível ler a impressora salva. Selecione a impressora novamente.') from None


def salvar_impressora(nome: str) -> None:
    destino = caminho_preferencia()
    temporario = None
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(mode='w', encoding='utf-8', dir=destino.parent,
                                suffix='.tmp', delete=False) as arquivo:
            temporario = Path(arquivo.name)
            json.dump({'impressora': nome}, arquivo, ensure_ascii=False)
            arquivo.write('\n')
        os.replace(temporario, destino)
    except OSError:
        logging.exception('Não foi possível salvar a impressora Havan')
        raise ValueError('Não foi possível salvar a impressora. Verifique a permissão da pasta de configurações.') from None
    finally:
        if temporario is not None:
            try:
                temporario.unlink(missing_ok=True)
            except OSError:
                logging.warning('Não foi possível remover o arquivo temporário de preferência Havan')
