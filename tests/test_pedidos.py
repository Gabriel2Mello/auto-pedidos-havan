import unittest
import xml.etree.ElementTree as ET
from decimal import Decimal

from src.pedidos import (
    definir_empresa,
    extrair_dados_xml,
    formata_data,
    normalizar,
    normalizar_pedidos,
    validar_xml_pedido,
)
from tests.fixtures import xml_pedido


class NormalizarPedidosTests(unittest.TestCase):
    def test_completa_pedidos_e_ignora_itens_invalidos(self) -> None:
        entrada = '12345, 2025-98765, , 42'

        resultado = normalizar_pedidos(entrada, ano=2026)

        self.assertEqual(
            resultado,
            ['2026-12345', '2025-98765'],
        )

    def test_retorna_lista_vazia_para_entrada_em_branco(self) -> None:
        self.assertEqual(normalizar_pedidos('   ', ano=2026), [])

    def test_elimina_duplicados_depois_de_completar_ano(self) -> None:
        self.assertEqual(
            normalizar_pedidos('12345, 2026-12345, 67890, 12345', ano=2026),
            ['2026-12345', '2026-67890'],
        )

    def test_rejeita_texto_caminhos_e_ano_invalido(self) -> None:
        self.assertEqual(
            normalizar_pedidos('abcde, ../123456, 26-12345, 2026-12, 1234x', ano=2026),
            [],
        )


class DadosPedidoTests(unittest.TestCase):
    def test_normaliza_texto_e_formata_data(self) -> None:
        self.assertEqual(normalizar('Bonificação'), 'BONIFICACAO')
        self.assertEqual(formata_data('26/08/26', dias=1), '27/08/2026')

    def test_extrai_e_normaliza_dados_do_xml(self) -> None:
        root = ET.fromstring(
            '''
            <Pedido>
                <PrazoPagamento><PrevisaoData>26/08/26</PrevisaoData></PrazoPagamento>
                <DataInicialSemanaEntrega>30/08/26</DataInicialSemanaEntrega>
                <DescricaoProduto>Almofada Turma do Abraço</DescricaoProduto>
                <Operacao>Bonificação Comercial</Operacao>
            </Pedido>
            '''
        )

        self.assertEqual(
            extrair_dados_xml(root),
            {
                'data_fatura': '26/08/2026',
                'data_entrega': '30/08/2026',
                'produto': 'ALMOFADA TURMA DO ABRACO',
                'operacao': 'BONIFICACAO COMERCIAL',
            },
        )

    def test_rejeita_xml_incompleto(self) -> None:
        with self.assertRaisesRegex(RuntimeError, 'Dados não encontrados'):
            extrair_dados_xml(ET.fromstring('<Pedido />'))

    def test_define_empresa_pela_descricao_do_produto(self) -> None:
        self.assertEqual(
            definir_empresa('KIT ALMOFADA TURMA DO ABRACO AZUL'),
            'MATRIZ',
        )
        self.assertEqual(definir_empresa('TOALHA DE BANHO'), 'FILIAL')


class ValidarXmlTests(unittest.TestCase):
    def test_quantidade_decimal_e_preservada_sem_arredondamento_binario(self) -> None:
        root = xml_pedido()
        campo = root.find('.//QuantidadePrimariaTotalSolicitada')
        assert campo is not None
        campo.text = '12,500000'
        self.assertEqual(validar_xml_pedido(root, '2026-12345')[0].quantidade, Decimal('12.5'))

    def test_quantidade_ausente_negativa_zero_ou_nao_finita_bloqueia_xml(self) -> None:
        for texto in ('', 'abc', '0', '-1', 'NaN', 'Infinity'):
            root = xml_pedido()
            campo = root.find('.//QuantidadePrimariaTotalSolicitada')
            assert campo is not None
            campo.text = texto
            with self.subTest(texto=texto), self.assertRaisesRegex(ValueError, 'Quantidade inválida'):
                validar_xml_pedido(root, '2026-12345')

    def test_percorre_todos_os_itens_e_variacoes_e_preserva_zero(self) -> None:
        root = xml_pedido('2026-12345   ', (
            ('0123456789012', '1234567890123'), ('2345678901234',),
        ))
        resultado = validar_xml_pedido(root, '2026-12345')
        self.assertEqual(
            [v.barra for v in resultado],
            ['0123456789012', '1234567890123', '2345678901234'],
        )
        self.assertEqual(resultado[-1].produto, 'PRODUTO 1')

    def test_rejeita_numero_diferente_ou_ausente(self) -> None:
        for numero in ('2026-99999', ''):
            with self.subTest(numero=numero):
                with self.assertRaisesRegex(ValueError, 'difere do pedido'):
                    validar_xml_pedido(xml_pedido(numero), '2026-12345')

    def test_rejeita_barra_vazia_longa_ou_nao_numerica(self) -> None:
        for barra in ('', '1234567890123456', '123456789012x'):
            with self.subTest(barra=barra):
                with self.assertRaisesRegex(ValueError, 'Código de barras inválido'):
                    validar_xml_pedido(xml_pedido(barras_por_item=((barra,),)), '2026-12345')

    def test_rejeita_xml_sem_itens_ou_variacoes(self) -> None:
        with self.assertRaises((ValueError, RuntimeError)):
            validar_xml_pedido(xml_pedido(barras_por_item=()), '2026-12345')
        with self.assertRaisesRegex(ValueError, 'sem variações'):
            validar_xml_pedido(xml_pedido(barras_por_item=((),)), '2026-12345')

    def test_valida_datas_antes_da_interface(self) -> None:
        root = xml_pedido()
        campo = root.find('DataInicialSemanaEntrega')
        assert campo is not None
        campo.text = '31/02/26'
        with self.assertRaises(ValueError):
            validar_xml_pedido(root, '2026-12345')


if __name__ == '__main__':
    unittest.main()
