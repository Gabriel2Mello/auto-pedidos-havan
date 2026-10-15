import io
import logging
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.logs import setup_logging


class LogsTests(unittest.TestCase):
    def test_pythonw_sem_console_continua_registrando_no_arquivo(self) -> None:
        root = logging.getLogger()
        anteriores, nivel = root.handlers[:], root.level
        with tempfile.TemporaryDirectory() as pasta:
            try:
                with patch('src.logs.sys.stdout', None):
                    codigo = setup_logging(Path(pasta), console=False)
                    root.info('Interface sem console')
                texto = (Path(pasta) / 'auto-pedidos.log').read_text(encoding='utf-8')
                self.assertIn(codigo, texto)
                self.assertIn('Interface sem console', texto)
                self.assertFalse(any(h.get_name() == 'auto-pedidos-console' for h in root.handlers))
            finally:
                for h in root.handlers[:]:
                    if h not in anteriores:
                        root.removeHandler(h)
                        h.close()
                root.handlers = anteriores
                root.setLevel(nivel)

    def test_preserva_historico_identifica_execucoes_e_rotaciona(self) -> None:
        root = logging.getLogger()
        anteriores = root.handlers[:]
        nivel = root.level
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            arquivo = raiz / 'auto-pedidos.log'
            arquivo.write_text('execução anterior\n', encoding='utf-8')
            try:
                console = io.StringIO()
                with patch('src.logs.sys.stdout', console):
                    setup_logging(raiz)
                    root.info('primeira execução nova')
                    setup_logging(raiz)
                    root.info('segunda execução nova')
                    try:
                        raise RuntimeError('detalhe técnico para o suporte')
                    except RuntimeError:
                        root.exception('Não foi possível concluir esta etapa.')
                    texto = arquivo.read_text(encoding='utf-8')
                    self.assertIn('execução anterior', texto)
                    self.assertIn('primeira execução nova', texto)
                    self.assertIn('segunda execução nova', texto)
                    self.assertIn('Traceback', texto)
                    self.assertNotIn('Traceback', console.getvalue())
                    self.assertNotIn('detalhe técnico para o suporte', console.getvalue())
                    self.assertEqual(len(set(re.findall(r'\[([0-9a-f]{12})\]', texto))), 2)
                    self.assertEqual(sum(h.get_name() == 'auto-pedidos-arquivo' for h in root.handlers), 1)
                    handler = next(h for h in root.handlers if h.get_name() == 'auto-pedidos-arquivo')
                    handler.maxBytes = 100
                    root.info('mensagem para acionar a rotação')
                    self.assertTrue((raiz / 'auto-pedidos.log.1').is_file())
                    self.assertIn('segunda execução nova', (raiz / 'auto-pedidos.log.1').read_text(encoding='utf-8'))
            finally:
                for handler in root.handlers[:]:
                    if handler not in anteriores:
                        root.removeHandler(handler)
                        handler.close()
                root.handlers = anteriores
                root.setLevel(nivel)
