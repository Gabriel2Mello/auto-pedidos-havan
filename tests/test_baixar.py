import unittest

from src.baixar import links_pedido


class LinksPedidoTests(unittest.TestCase):
    HTML_PEDIDO = '''
        <div class="hvn-group">
            <dl>
                <dt>Pedido</dt><dd>2026-12345</dd>
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
        with self.assertRaisesRegex(RuntimeError, 'não encontrado'):
            links_pedido(self.HTML_PEDIDO, '2026-99999')


if __name__ == '__main__':
    unittest.main()
