import subprocess
import tempfile
import unittest
from dataclasses import replace
from src.config import CONFIG, usar_configuracao
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

from pypdf import PdfReader, PdfWriter

from src.estado import EstadoError, EstadoPedido, EstadoPedidos
from src.imprimir import ResultadoImpressao, adicionar_numero, imprimir_pdf, processar_impressao


class ImpressaoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.pasta = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.historico = self.stack.enter_context(EstadoPedidos(self.pasta / 'estado.sqlite3'))
        self.pedido = '2026-109335'
        self.numero = '11250'
        self.pasta_pedido = self.pasta / self.pedido
        self.pasta_pedido.mkdir()
        self.origem = self.pasta_pedido / f'ordem_de_compra {self.pedido}.pdf'
        self.final = self.pasta_pedido / f'{self.numero} {self.pedido}.pdf'
        writer = PdfWriter()
        writer.add_blank_page(width=595, height=842)
        with self.origem.open('wb') as arquivo:
            writer.write(arquivo)
        self.historico.salvar(EstadoPedido(self.pedido, self.numero, 'importado', 2))
        self.stack.enter_context(usar_configuracao(replace(CONFIG, pasta_pedidos=self.pasta)))
        self.stack.enter_context(patch('src.imprimir.caminho_pdf', return_value=self.origem))
        self.enviar = self.stack.enter_context(patch('src.imprimir.imprimir_pdf'))
        self.enviar.return_value = ResultadoImpressao('enviada')

    def test_numera_pdf_com_numero_sisplan_e_preserva_origem(self) -> None:
        original = self.origem.read_bytes()
        self.assertEqual(processar_impressao(self.pedido, self.numero, self.historico), 'impressao_enviada')
        self.assertTrue(self.final.is_file())
        self.assertEqual(PdfReader(self.final).metadata.title, 'Pedido 11250')
        self.assertIn('11250', PdfReader(self.final).pages[0].extract_text())
        self.assertEqual(self.origem.read_bytes(), original)
        self.assertEqual(self.historico.obter(self.pedido).etapa, 'impressao_enviada')

    def test_pdf_existente_pode_ser_reimpresso_sem_arquivo_original(self) -> None:
        adicionar_numero(self.origem, self.final, self.numero)
        self.origem.unlink()
        processar_impressao(self.pedido, self.numero, self.historico, forcar=True)
        self.enviar.assert_called_once_with(self.final)

    def test_falha_de_pdf_nao_envia_impressao_e_permanece_pendente(self) -> None:
        self.origem.write_bytes(b'pdf invalido')
        self.assertEqual(processar_impressao(self.pedido, self.numero, self.historico), 'impressao_pendente')
        self.enviar.assert_not_called()
        self.assertEqual(self.historico.obter(self.pedido).etapa, 'impressao_pendente')

    def test_queda_durante_envio_nao_repete_automaticamente(self) -> None:
        self.enviar.side_effect = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            processar_impressao(self.pedido, self.numero, self.historico)
        self.assertEqual(self.historico.obter(self.pedido).etapa, 'impressao_iniciada')
        self.enviar.side_effect = None
        self.enviar.reset_mock()
        self.assertEqual(processar_impressao(self.pedido, self.numero, self.historico), 'impressao_incerta')
        self.enviar.assert_not_called()
        self.assertEqual(
            processar_impressao(self.pedido, self.numero, self.historico, forcar=True),
            'impressao_enviada',
        )
        self.enviar.assert_called_once()

    def test_falha_definitiva_de_envio_pode_ser_retomada(self) -> None:
        self.enviar.return_value = ResultadoImpressao('pendente', 'Executável indisponível')
        self.assertEqual(processar_impressao(self.pedido, self.numero, self.historico), 'impressao_pendente')
        self.enviar.return_value = ResultadoImpressao('enviada')
        self.assertEqual(processar_impressao(self.pedido, self.numero, self.historico), 'impressao_enviada')

    def test_falha_ao_salvar_checkpoint_impede_envio(self) -> None:
        with patch.object(self.historico, 'salvar', side_effect=EstadoError('Disco cheio')):
            with self.assertRaises(EstadoError):
                processar_impressao(self.pedido, self.numero, self.historico)
        self.enviar.assert_not_called()

    def test_nao_imprime_pedido_sem_confirmacao(self) -> None:
        self.historico.salvar(EstadoPedido(self.pedido, self.numero, 'gravacao_pendente'))
        with self.assertRaises(EstadoError):
            processar_impressao(self.pedido, self.numero, self.historico)
        self.enviar.assert_not_called()

    def test_falha_de_geracao_nao_trunca_pdf_final_anterior(self) -> None:
        self.final.write_bytes(b'final anterior')
        with patch('src.imprimir.PdfWriter.write', side_effect=OSError('Disco cheio')):
            self.assertFalse(adicionar_numero(self.origem, self.final, self.numero))
        self.assertEqual(self.final.read_bytes(), b'final anterior')
        self.assertEqual(list(self.pasta_pedido.glob('*.tmp')), [])


class EnvioSumatraTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.arquivo = Path(self.pasta.name) / 'pedido.pdf'
        self.arquivo.write_bytes(b'conteudo')

    @patch('src.imprimir.subprocess.run')
    def test_saida_zero_registra_envio_sem_afirmar_impressao_fisica(self, executar: MagicMock) -> None:
        self.assertEqual(imprimir_pdf(self.arquivo).situacao, 'enviada')

    @patch('src.imprimir.subprocess.run')
    def test_timeout_e_saida_com_erro_sao_incertos(self, executar: MagicMock) -> None:
        for erro in (
            subprocess.TimeoutExpired(['sumatra'], 15),
            subprocess.CalledProcessError(1, ['sumatra']),
        ):
            with self.subTest(erro=erro):
                executar.side_effect = erro
                self.assertEqual(imprimir_pdf(self.arquivo).situacao, 'incerta')

    @patch('src.imprimir.subprocess.run', side_effect=FileNotFoundError('Sumatra ausente'))
    def test_falha_antes_de_iniciar_permite_nova_tentativa(self, executar: MagicMock) -> None:
        self.assertEqual(imprimir_pdf(self.arquivo).situacao, 'pendente')
