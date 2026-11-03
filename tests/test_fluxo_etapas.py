"""Barreiras entre preparação, conferência e importação explícita."""
import unittest
from unittest.mock import Mock, patch
from requests.exceptions import Timeout
from tests import test_baixar, test_main
from src import servico_pedidos as servico
from src.baixar import baixar_pedidos
from src.estado import EstadoPedido, EstadoPedidos
from src.banco import BancoSisplanError, PedidoExistente

class FluxoEtapasTests(unittest.TestCase):
    setUp = test_main.FluxoPrevalidacaoTests.setUp
    preparar = test_main.FluxoPrevalidacaoTests.preparar
    caminho = test_main.FluxoPrevalidacaoTests.caminho
    assert_sem_interface = test_main.FluxoPrevalidacaoTests.assert_sem_interface

    def test_pedido_ausente_preserva_mensagem_no_historico_e_confere_o_proximo(self):
        pedido = '2026-037398'
        self.preparar('2026-12345')
        scraper = self.scraper.return_value.__enter__.return_value
        scraper.post.return_value.url = 'https://cliente.havan.com.br/Fornecedor/PedidoCompra/GridIndexPedidoCompra'
        scraper.post.return_value.status_code = 200
        scraper.post.return_value.text = '<div></div>'
        def baixar(sessao, pedidos, **kwargs):
            if pedidos == [pedido]:
                return baixar_pedidos(sessao, pedidos, **kwargs)
            kwargs['ao_baixar']('2026-12345')
            return {'2026-12345': True}
        self.baixar.side_effect = baixar
        decidir = Mock(return_value='encerrar')
        with patch('src.baixar.caminho_pdf', return_value=self.pasta / f'{pedido}.pdf'), \
                patch('src.baixar.salvar_pedido_txt') as salvar, patch('src.baixar.salvar_arquivos') as publicar:
            resultado = servico.processar_pedidos([pedido, '2026-12345'], 'preparar', ao_erro=decidir)
        self.assertEqual(resultado.situacoes, {pedido: 'rejeitado', '2026-12345': 'pronto_importar'})
        mensagem = 'Pedido não encontrado no Portal Havan.'
        salvar.assert_called_once_with(pedido, motivo=mensagem)
        publicar.assert_not_called()
        scraper.get.assert_not_called()
        decidir.assert_not_called()
        with EstadoPedidos(self.estado_path) as historico:
            registro = historico.obter(pedido)
            self.assertEqual((registro.etapa, registro.erro), ('para_baixar', mensagem))
        self.assert_sem_interface()

    def test_falha_de_conexao_e_link_ausente_preservam_motivos_distintos(self):
        pedido = '2026-12345'
        scraper = self.scraper.return_value.__enter__.return_value
        resposta = scraper.post.return_value
        resposta.url = 'https://cliente.havan.com.br/Fornecedor/PedidoCompra/GridIndexPedidoCompra'
        resposta.status_code = 200
        for timeout in (True, False):
            with self.subTest(timeout=timeout):
                scraper.post.side_effect = Timeout('Falha sintética') if timeout else None
                resposta.text = test_baixar.LinksPedidoTests.HTML_PEDIDO.replace('Ordem de compra', 'Outro documento')
                self.baixar.side_effect = baixar_pedidos
                with patch('src.baixar.caminho_pdf', return_value=self.pasta / f'{pedido}.pdf'), \
                        patch('src.baixar.salvar_pedido_txt'), patch('src.baixar.salvar_arquivos') as publicar:
                    resultado = servico.processar_pedidos([pedido], 'preparar')
                self.assertEqual(resultado.situacoes[pedido], 'rejeitado')
                mensagem = (f'Não consegui baixar os arquivos do pedido {pedido}. Verifique o portal ou a conexão.'
                            if timeout else 'Pedido encontrado, mas link para download ausente. Verifique o portal')
                with EstadoPedidos(self.estado_path) as historico:
                    registro = historico.obter(pedido)
                    self.assertEqual((registro.etapa, registro.erro), ('para_baixar', mensagem))
                publicar.assert_not_called()
                scraper.get.assert_not_called()
        self.assert_sem_interface()

    def test_preparacao_persiste_aptidao_sem_importar_e_importacao_revalida(self):
        self.preparar()
        resultado = servico.processar_pedidos(['2026-12345'], 'preparar')
        self.assertEqual(resultado.situacoes, {'2026-12345':'pronto_importar'})
        self.assert_sem_interface()
        with EstadoPedidos(self.estado_path) as h:
            self.assertEqual(h.obter('2026-12345').etapa, 'pronto_importar')
            self.assertTrue(h.obter_itens_esperados('2026-12345'))
        self.baixar.reset_mock(); self.banco.consultar_barras.reset_mock()
        resultado = servico.processar_pedidos(['2026-12345'], 'importar')
        self.baixar.assert_not_called()
        self.banco.consultar_barras.assert_called_once()
        self.assertEqual(resultado.importados, {'2026-12345'})

    def test_separa_existentes_sem_cadastro_e_aptos_sem_pausar(self):
        self.preparar('2026-12345', barra='9999999999999')
        self.preparar('2026-67890')
        self.banco.consultar_pedidos.return_value={'2026-99999':[PedidoExistente('777',2)]}
        decidir=Mock(return_value='encerrar')
        r=servico.processar_pedidos(['2026-99999','2026-12345','2026-67890'], 'preparar', ao_erro=decidir)
        self.assertEqual(r.situacoes, {'2026-99999':'existente','2026-12345':'sem_cadastro','2026-67890':'pronto_importar'})
        decidir.assert_not_called(); self.assert_sem_interface()
        self.assertTrue(all('2026-99999' not in c.args[1] for c in self.baixar.call_args_list))

    def test_revalidar_cadastro_reaproveita_arquivos_e_exige_importacao_posterior(self):
        self.preparar(); cadastradas=self.banco.consultar_barras.return_value
        self.banco.consultar_barras.return_value={}
        servico.processar_pedidos(['2026-12345'], 'preparar')
        self.banco.consultar_barras.return_value=cadastradas; self.baixar.reset_mock()
        r=servico.processar_pedidos(['2026-12345'], 'revalidar')
        self.assertEqual(r.situacoes['2026-12345'], 'pronto_importar')
        self.baixar.assert_not_called(); self.assert_sem_interface()
        with EstadoPedidos(self.estado_path) as h: self.assertEqual(h.obter('2026-12345').erro,'')

    def test_cadastro_alterado_entre_preparo_e_importacao_nao_importa(self):
        self.preparar(); servico.processar_pedidos(['2026-12345'], 'preparar')
        self.banco.consultar_barras.return_value={}
        r=servico.processar_pedidos(['2026-12345'], 'importar')
        self.assertEqual(r.situacoes['2026-12345'], 'sem_cadastro'); self.assert_sem_interface()

    def test_outro_operador_inseriu_apos_preparo_nao_importa(self):
        self.preparar(); servico.processar_pedidos(['2026-12345'], 'preparar')
        self.banco.consultar_pedidos.return_value={'2026-12345':[PedidoExistente('101',2)]}
        r=servico.processar_pedidos(['2026-12345'], 'importar')
        self.assertEqual(r.situacoes['2026-12345'],'existente'); self.assert_sem_interface()

    def test_arquivo_removido_apos_preparo_nao_baixa_na_importacao(self):
        self.preparar(); servico.processar_pedidos(['2026-12345'], 'preparar')
        self.caminho('2026-12345').unlink(); self.baixar.reset_mock()
        r=servico.processar_pedidos(['2026-12345'], 'importar')
        self.assertEqual(r.situacoes['2026-12345'],'rejeitado')
        self.baixar.assert_not_called(); self.assert_sem_interface()

    def test_banco_indisponivel_nao_vira_produto_sem_cadastro(self):
        self.preparar(); self.banco.consultar_barras.side_effect=BancoSisplanError('indisponível')
        with self.assertRaises(BancoSisplanError): servico.processar_pedidos(['2026-12345'], 'preparar')
        with EstadoPedidos(self.estado_path) as h: self.assertEqual(h.obter('2026-12345').etapa,'baixado')
        self.assert_sem_interface()

    def test_preparar_nao_reconcilia_nem_imprime_pedido_ja_importado(self):
        with EstadoPedidos(self.estado_path) as h: h.salvar(EstadoPedido('2026-12345','100','impressao_incerta',2))
        self.banco.consultar_pedidos.return_value={'2026-12345':[PedidoExistente('100',2)]}
        r=servico.processar_pedidos(['2026-12345'],'preparar')
        self.assertEqual(r.situacoes['2026-12345'],'aguardando')
        self.assert_sem_interface()
        with EstadoPedidos(self.estado_path) as h: self.assertEqual(h.obter('2026-12345').etapa,'impressao_incerta')
