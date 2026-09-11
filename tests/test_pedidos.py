import unittest
import xml.etree.ElementTree as ET

from src.pedidos import (
    definir_empresa,
    extrair_dados_xml,
    formata_data,
    normalizar,
    normalizar_pedidos,
)


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


if __name__ == '__main__':
    unittest.main()
