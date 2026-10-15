import unittest
from unittest.mock import MagicMock, patch

from src.baixar import html_grid_pedido, baixar_pedidos, baixar_arquivos
from src.login import conferir_sessao
from src.erros import (SessaoPortalExpiradaError)


class SessaoTests(unittest.TestCase):
    def test_download_sem_console_no_pythonw_preserva_resultado_e_checkpoint(self) -> None:
        for sucesso in (True, False):
            with self.subTest(sucesso=sucesso):
                checkpoint = MagicMock()
                with (patch('src.baixar.sys.stdout', None), patch('src.baixar.sys.stderr', None),
                      patch('src.baixar.processar_unico', return_value=('2026-12345', sucesso, 'erro simulado')),
                      patch('src.baixar.salvar_pedido_txt') as salvar):
                    self.assertEqual(baixar_pedidos(MagicMock(), ['2026-12345'], ao_baixar=checkpoint),
                                     {'2026-12345': sucesso})
                if sucesso:
                    checkpoint.assert_called_once_with('2026-12345')
                    salvar.assert_not_called()
                else:
                    checkpoint.assert_not_called()
                    salvar.assert_called_once()

    def resposta(self, url: str, texto: str = '', status: int = 200) -> MagicMock:
        response = MagicMock()
        response.url, response.text, response.status_code = url, texto, status
        return response

    def test_detecta_login_por_redirecionamento_html_e_http401(self) -> None:
        for resposta in (
            self.resposta('https://cliente.havan.com.br/Fornecedor/Login/Index'),
            self.resposta('https://cliente.havan.com.br/Fornecedor/PedidoCompra', '<form><input name="SenhaMd5"></form>'),
            self.resposta('https://cliente.havan.com.br/Fornecedor/PedidoCompra', status=401),
        ):
            with self.subTest(url=resposta.url), self.assertRaises(SessaoPortalExpiradaError):
                conferir_sessao(resposta, html=True)
        conferir_sessao(self.resposta('https://cliente.havan.com.br/Fornecedor/PedidoCompra', '<div>Pedidos</div>'), html=True)

    def test_grade_nao_converte_sessao_expirada_em_pedido_inexistente(self) -> None:
        scraper = MagicMock()
        scraper.post.return_value = self.resposta('https://cliente.havan.com.br/Fornecedor/Login/Index')
        with self.assertRaises(SessaoPortalExpiradaError):
            html_grid_pedido(scraper, '2026-12345')

    @patch('src.baixar.baixar_arquivos', side_effect=SessaoPortalExpiradaError())
    def test_expiracao_chega_ao_fluxo_sem_salvar_baixado(self, baixar: MagicMock) -> None:
        checkpoint = MagicMock()
        with patch('src.baixar.tqdm'), self.assertRaises(SessaoPortalExpiradaError):
            baixar_pedidos(MagicMock(), ['2026-12345'], ao_baixar=checkpoint)
        checkpoint.assert_not_called()

    @patch('src.baixar.extrair_xml')
    @patch('src.baixar.links_pedido', return_value=('https://exemplo/p.pdf', 'https://exemplo/p.rar'))
    @patch('src.baixar.html_grid_pedido', return_value='<div>Pedido</div>')
    def test_arquivo_redirecionado_ao_login_nao_e_tratado_como_rar(self, grade: MagicMock, links: MagicMock, extrair: MagicMock) -> None:
        scraper = MagicMock()
        scraper.get.return_value = self.resposta('https://cliente.havan.com.br/Fornecedor/Login/Index')
        with self.assertRaises(SessaoPortalExpiradaError):
            baixar_arquivos(scraper, '2026-12345')
        extrair.assert_not_called()
