"""Publicação do download somente com arquivos sintéticos temporários."""
from contextlib import ExitStack
from io import BytesIO
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from typing import IO
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

from pypdf import PdfWriter

from src.arquivos import caminho_pdf, caminho_xml
from src.baixar import baixar_pedidos, salvar_arquivos
from src.config import Configuracao, usar_configuracao
from src.filas import conferir_arquivos_baixados
from src.gravacao_download import DownloadPendenteError
from tests.fixtures import xml_pedido


PEDIDO = '2026-12345'


class GravacaoDownloadTests(unittest.TestCase):
    def setUp(self) -> None:
        pilha = self.enterContext(ExitStack())
        self.pasta = Path(pilha.enter_context(tempfile.TemporaryDirectory()))
        config = Configuracao(Path('unrar-sintetico'), Path('sumatra-sintetico'),
                              self.pasta, 'Impressora sintética', '00000000000000', 'senha-sintetica')
        pilha.enter_context(usar_configuracao(config))
        self.pdf, self.xml = caminho_pdf(PEDIDO), caminho_xml(PEDIDO)
        self.pdf.parent.mkdir()
        self.anteriores = (b'PDF anterior preservado', b'XML anterior preservado')
        self.pdf.write_bytes(self.anteriores[0])
        self.xml.write_bytes(self.anteriores[1])
        writer = PdfWriter()
        writer.add_blank_page(width=595, height=842)
        buffer = BytesIO()
        writer.write(buffer)
        self.novos = (buffer.getvalue(), ET.tostring(xml_pedido()))
        pilha.enter_context(patch('src.baixar.salvar_pedido_txt'))

    def conferir_anteriores(self) -> None:
        self.assertEqual((self.pdf.read_bytes(), self.xml.read_bytes()), self.anteriores)

    def test_xml_de_outro_pedido_pdf_invalido_e_pdf_sem_paginas_preservam_anteriores(self) -> None:
        vazio = BytesIO()
        PdfWriter().write(vazio)
        for pdf, xml in ((self.novos[0], ET.tostring(xml_pedido('2026-99999'))),
                         (b'<html>login</html>', self.novos[1]),
                         (vazio.getvalue(), self.novos[1])):
            with self.subTest(pdf_valido=pdf == self.novos[0]), self.assertRaises(Exception):
                salvar_arquivos(pdf, xml, PEDIDO)
            self.conferir_anteriores()

    def test_segundo_arquivo_falha_na_preparacao_sem_modificar_os_anteriores(self) -> None:
        abrir = Path.open
        def falhar(caminho: Path, mode: str = 'r', buffering: int = -1,
                   encoding: str | None = None, errors: str | None = None,
                   newline: str | None = None) -> IO[bytes] | IO[str]:
            if caminho.suffix == '.xml' and any(letra in mode for letra in ('w', 'x')):
                raise PermissionError('Escrita XML sintética indisponível')
            return abrir(caminho, mode, buffering, encoding, errors, newline)
        with patch.object(Path, 'open', falhar), self.assertRaises(OSError):
            salvar_arquivos(*self.novos, PEDIDO)
        self.conferir_anteriores()

    def test_segunda_publicacao_falha_e_restaura_os_dois_anteriores(self) -> None:
        substituir = os.replace
        falhou = False
        def falhar(origem: Path, destino: Path) -> None:
            nonlocal falhou
            if Path(destino) == self.xml and not falhou:
                falhou = True
                raise PermissionError('Publicação XML sintética indisponível')
            return substituir(origem, destino)
        with patch('os.replace', side_effect=falhar), self.assertRaises(OSError):
            salvar_arquivos(*self.novos, PEDIDO)
        self.assertTrue(falhou)
        self.conferir_anteriores()

    def test_sucesso_publica_par_validado_e_so_entao_confirma_download(self) -> None:
        callback = Mock()
        def confirmar(pedido: str) -> None:
            self.assertEqual(pedido, PEDIDO)
            self.assertEqual((self.pdf.read_bytes(), self.xml.read_bytes()), self.novos)
            self.assertTrue(conferir_arquivos_baixados(pedido))
            callback(pedido)
        with patch('src.baixar.baixar_arquivos', return_value=self.novos), patch('src.baixar.tqdm'):
            self.assertEqual(baixar_pedidos(Mock(), [PEDIDO], ao_baixar=confirmar), {PEDIDO: True})
        callback.assert_called_once_with(PEDIDO)

    def test_falha_de_fsync_preserva_anteriores_sem_confirmar_download(self) -> None:
        callback = Mock()
        with patch('os.fsync', side_effect=OSError('Sincronização sintética indisponível')), \
                patch('src.baixar.baixar_arquivos', return_value=self.novos), patch('src.baixar.tqdm'):
            self.assertEqual(baixar_pedidos(Mock(), [PEDIDO], ao_baixar=callback), {PEDIDO: False})
        callback.assert_not_called()
        self.conferir_anteriores()

    def test_falha_de_rollback_preserva_copia_e_bloqueia_outro_download(self) -> None:
        substituir = os.replace
        def falhar(origem: Path, destino: Path) -> None:
            if Path(destino) == self.xml or Path(origem).parent.name == 'anteriores':
                raise PermissionError('Publicação ou restauração sintética indisponível')
            return substituir(origem, destino)
        with patch('os.replace', side_effect=falhar), self.assertRaises(RuntimeError) as erro:
            salvar_arquivos(*self.novos, PEDIDO)
        pastas = list(self.pdf.parent.glob('.nunes-download-*'))
        self.assertEqual(len(pastas), 1)
        self.assertIn(str(pastas[0]), str(erro.exception))
        self.assertEqual((pastas[0] / 'anteriores' / self.pdf.name).read_bytes(), self.anteriores[0])
        self.assertEqual((pastas[0] / 'anteriores' / self.xml.name).read_bytes(), self.anteriores[1])
        with self.assertRaises(DownloadPendenteError):
            conferir_arquivos_baixados(PEDIDO)
        callback = Mock()
        with patch('src.baixar.baixar_arquivos') as baixar, patch('src.baixar.tqdm'), self.assertRaises(DownloadPendenteError):
            baixar_pedidos(Mock(), [PEDIDO], ao_baixar=callback)
        baixar.assert_not_called()
        callback.assert_not_called()

    def test_falha_na_publicacao_sem_destinos_anteriores_volta_a_ausencia(self) -> None:
        self.pdf.unlink()
        self.xml.unlink()
        substituir = os.replace
        def falhar(origem: Path, destino: Path) -> None:
            if destino == self.xml:
                raise PermissionError('XML sintético bloqueado')
            substituir(origem, destino)
        with patch('os.replace', side_effect=falhar), self.assertRaises(OSError):
            salvar_arquivos(*self.novos, PEDIDO)
        self.assertFalse(self.pdf.exists())
        self.assertFalse(self.xml.exists())
        self.assertEqual(list(self.pdf.parent.iterdir()), [])

    def test_falha_de_sincronizacao_da_copia_anterior_impede_publicacao(self) -> None:
        with patch('os.fsync', side_effect=[None, None, None, OSError('Cópia anterior indisponível')]), \
                self.assertRaises(OSError):
            salvar_arquivos(*self.novos, PEDIDO)
        self.conferir_anteriores()
        self.assertEqual(set(self.pdf.parent.iterdir()), {self.pdf, self.xml})

    def test_sem_permissao_de_conferir_pendencias_nao_publica(self) -> None:
        with patch.object(Path, 'iterdir', side_effect=PermissionError('Listagem sintética negada')), \
                self.assertRaises(PermissionError):
            salvar_arquivos(*self.novos, PEDIDO)
        self.conferir_anteriores()

    def test_queda_do_processo_entre_publicacoes_deixa_recuperacao_bloqueada(self) -> None:
        # Até o par misturado continuaria legível: é a pendência que deve bloqueá-lo.
        self.anteriores = (self.novos[0] + b'\n%anterior\n', self.novos[1] + b'\n')
        self.pdf.write_bytes(self.anteriores[0])
        self.xml.write_bytes(self.anteriores[1])
        self.assertTrue(conferir_arquivos_baixados(PEDIDO))
        fonte_pdf, fonte_xml = self.pasta / 'novo.pdf', self.pasta / 'novo.xml'
        fonte_pdf.write_bytes(self.novos[0])
        fonte_xml.write_bytes(self.novos[1])
        codigo = '''
import os, sys
from pathlib import Path
from src.baixar import salvar_arquivos
from src.config import Configuracao, usar_configuracao
from src.arquivos import caminho_pdf
pasta = Path(sys.argv[1])
config = Configuracao(Path('unrar'), Path('sumatra'), pasta, 'sintetica', '00000000000000', 'sintetica')
substituir = os.replace
def cair(origem, destino):
    substituir(origem, destino)
    if Path(destino) == caminho_pdf('2026-12345'):
        os._exit(23)
os.replace = cair
with usar_configuracao(config):
    salvar_arquivos((pasta / 'novo.pdf').read_bytes(), (pasta / 'novo.xml').read_bytes(), '2026-12345')
'''
        processo = subprocess.run([sys.executable, '-B', '-c', codigo, str(self.pasta)],
                                  cwd=Path(__file__).resolve().parents[1], capture_output=True, timeout=15)
        self.assertEqual(processo.returncode, 23, processo.stderr.decode(errors='replace'))
        self.assertEqual(self.pdf.read_bytes(), self.novos[0])
        self.assertEqual(self.xml.read_bytes(), self.anteriores[1])
        with self.assertRaises(DownloadPendenteError):
            conferir_arquivos_baixados(PEDIDO)
        with self.assertRaises(RuntimeError):
            salvar_arquivos(*self.novos, PEDIDO)
        copia = next(self.pdf.parent.glob('.nunes-download-*')) / 'anteriores'
        self.assertEqual((copia / self.pdf.name).read_bytes(), self.anteriores[0])
        self.assertEqual((copia / self.xml.name).read_bytes(), self.anteriores[1])
