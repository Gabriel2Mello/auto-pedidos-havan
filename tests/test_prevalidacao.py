import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from src.banco import ProdutoCadastrado
from src.pedidos import ItemEsperado, VariacaoPedido
from src.prevalidacao import pendencias_barras, validar_pedido_baixado
from src.erros import PedidoRejeitadoError, ProdutoSemCadastroError
from tests.fixtures import xml_pedido


class PendenciasBarrasTests(unittest.TestCase):
    def test_distingue_produto_ausente_de_cadastro_ambiguo(self) -> None:
        produto = ProdutoCadastrado('P1', 'C1', 'T1')
        for cadastradas, tipo in (
            ({}, ProdutoSemCadastroError),
            ({'0123456789012': {produto, ProdutoCadastrado('P2', 'C1', 'T1')}}, PedidoRejeitadoError),
        ):
            with self.subTest(tipo=tipo):
                banco = MagicMock()
                banco.consultar_barras.return_value = cadastradas
                with patch('src.prevalidacao.carregar_xml', return_value=xml_pedido()), patch('src.prevalidacao.salvar_pedido_txt'):
                    with self.assertRaises(tipo) as erro:
                        validar_pedido_baixado(banco, '2026-12345')
                self.assertIs(type(erro.exception), tipo)

    def test_soma_variacoes_que_apontam_para_mesmo_produto_cor_tamanho(self) -> None:
        root = xml_pedido(barras_por_item=(('0123456789012', '1234567890123'),))
        quantidades = root.findall('.//QuantidadePrimariaTotalSolicitada')
        quantidades[0].text, quantidades[1].text = '2', '3,5'
        produto = ProdutoCadastrado('P1', 'C1', 'T1')
        banco = MagicMock()
        banco.consultar_barras.return_value = {'0123456789012': {produto}, '1234567890123': {produto}}
        with patch('src.prevalidacao.carregar_xml', return_value=root):
            itens = validar_pedido_baixado(banco, '2026-12345')
        self.assertEqual(itens, [ItemEsperado('P1', 'C1', 'T1', Decimal('5.5'))])

    def test_bloqueia_barra_ausente_e_ambigua_mas_aceita_mesma_combinacao(self) -> None:
        produto = ProdutoCadastrado('P1', 'AZUL', 'UNICO')
        variacoes = [
            VariacaoPedido('0123456789012', 'PRODUTO A', 'AZUL'),
            VariacaoPedido('1234567890123', 'PRODUTO B', 'VERDE'),
            VariacaoPedido('2345678901234', 'PRODUTO C', 'BRANCO'),
        ]
        pendencias = pendencias_barras(variacoes, {
            '0123456789012': {produto, produto},
            '2345678901234': {produto, ProdutoCadastrado('P2', 'BRANCO', 'UNICO')},
        })
        self.assertEqual(len(pendencias), 2)
        self.assertIn('não cadastrado: 1234567890123', pendencias[0])
        self.assertIn('PRODUTO B / VERDE', pendencias[0])
        self.assertIn('ambíguo: 2345678901234', pendencias[1])

    def test_nao_repete_mesma_pendencia(self) -> None:
        variacao = VariacaoPedido('0123456789012', 'PRODUTO', 'AZUL')
        self.assertEqual(len(pendencias_barras([variacao, variacao], {})), 1)
