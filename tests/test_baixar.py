import unittest

from src.baixar import links_pedido
from src.erros import PedidoNaoEncontradoPortalError


class LinksPedidoTests(unittest.TestCase):
    HTML_PEDIDO = '''
        <div class="hvn-group">
            <dl>
                <dt>Pedido</dt>
                <dd>
                    2026-12345
                    <div class="tags-pedido-status tag-nota-agendada">
                        Liberado
                    </div>
                </dd>
            </dl>
            <a title="Ordem de compra" href="/documentos/pedido.pdf"></a>
            <a title="Arq. de integração" href="/documentos/pedido.rar"></a>
        </div>
    '''

    def test_localiza_links_e_monta_urls_absolutas(self) -> None:
        self.assertEqual(
            links_pedido(self.HTML_PEDIDO, '2026-12345'),
            (
                'https://cliente.havan.com.br/documentos/pedido.pdf',
                'https://cliente.havan.com.br/documentos/pedido.rar',
            ),
        )

    def test_rejeita_pedido_que_nao_esta_na_grade(self) -> None:
        for html in (self.HTML_PEDIDO, '<div></div>'):
            with self.subTest(html=html), self.assertRaises(PedidoNaoEncontradoPortalError) as erro:
                links_pedido(html, '2026-037398')
            self.assertEqual(str(erro.exception), 'Pedido não encontrado no Portal Havan.')

    def test_pedido_encontrado_sem_link_nao_e_tratado_como_inexistente(self) -> None:
        html = self.HTML_PEDIDO.replace('Ordem de compra', 'Outro documento')
        with self.assertRaisesRegex(RuntimeError, 'Pedido encontrado, mas link ausente') as erro:
            links_pedido(html, '2026-12345')
        self.assertNotIsInstance(erro.exception, PedidoNaoEncontradoPortalError)


if __name__ == '__main__':
    unittest.main()
