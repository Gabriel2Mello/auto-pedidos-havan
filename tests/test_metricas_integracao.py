"""Confirma que estatísticas não geram inclusões nem contam retomadas duas vezes."""
from contextlib import ExitStack
from decimal import Decimal
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from metricas_nunes import consultar_metricas
from src.banco import GravacaoNaoConfirmadaError, PedidoExistente
from src.config import CONFIG
from src.estado import EstadoPedido, EstadoPedidos
from src.importar import ResultadoImportacao
from src.pedidos import ItemEsperado
from src.resumo import ResumoExecucao
import src.servico_pedidos as servico


class TestMetricasIntegracao(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.raiz = Path(self.temp.name)
        ambiente = patch.dict(os.environ, {'NUNES_METRICAS_DADOS': str(self.raiz / 'metricas')})
        ambiente.start(); self.addCleanup(ambiente.stop)
        self.pedido = '2026-12345'
        self.banco = MagicMock()
        self.banco.consultar_pedidos.return_value = {}
        self.banco.confirmar_gravacao.return_value = PedidoExistente('100', 2)
        self.resumo = ResumoExecucao({self.pedido: 'aguardando'})
        self.integracoes = servico.Integracoes(importar=self.importar,
            sisplan=lambda: (MagicMock(), MagicMock(), MagicMock(), {}),
            imprimir=lambda *args, **kwargs: 'impressao_enviada', notificar=lambda *args: None)
        self.recursos = servico.RecursosExecucao(ExitStack(), servico.ContextoExecucao(CONFIG, self.integracoes))

    def importar(self, *args, **kwargs):
        args[-1]('100')
        return ResultadoImportacao('100', 'aguarda_confirmacao')

    def totais(self):
        return consultar_metricas({'inicio': '2026-01-01', 'fim': '2099-12-31'})['totais']

    def test_conta_somente_gravacao_confirmada_e_retoma_sem_duplicar(self):
        with EstadoPedidos(self.raiz / 'estado.sqlite3') as historico, \
             patch('src.servico_pedidos.conferir_arquivos_baixados', return_value=True), \
             patch('src.servico_pedidos.validar_pedido_baixado', return_value=[ItemEsperado('P1', 'C1', 'T1', Decimal(1))]):
            historico.salvar(EstadoPedido(self.pedido, '', 'baixado'))
            servico.importar_novo(self.pedido, self.banco, historico, self.resumo, self.recursos)
            self.assertEqual(self.totais()['pedido_inserido'], 1)
            servico.retomar_impressao(self.pedido, '100', self.banco, historico, self.resumo, forcar=True, integracoes=self.integracoes)
            self.assertEqual(self.totais()['pedido_inserido'], 1)

    def test_gravacao_nao_confirmada_nao_conta_e_recuperacao_conta_uma_vez(self):
        with EstadoPedidos(self.raiz / 'estado.sqlite3') as historico, \
             patch('src.servico_pedidos.conferir_arquivos_baixados', return_value=True), \
             patch('src.servico_pedidos.validar_pedido_baixado', return_value=[ItemEsperado('P1', 'C1', 'T1', Decimal(1))]):
            historico.salvar(EstadoPedido(self.pedido, '', 'baixado'))
            self.banco.confirmar_gravacao.side_effect = GravacaoNaoConfirmadaError('sintetico')
            with self.assertRaises(GravacaoNaoConfirmadaError):
                servico.importar_novo(self.pedido, self.banco, historico, self.resumo, self.recursos)
            self.assertEqual(self.totais()['pedido_inserido'], 0)
            self.banco.confirmar_gravacao.side_effect = None
            servico.retomar_impressao(self.pedido, '100', self.banco, historico, self.resumo, integracoes=self.integracoes)
            self.assertEqual(self.totais()['pedido_inserido'], 1)

    def test_falha_na_estatistica_nao_repete_inclusao(self):
        with EstadoPedidos(self.raiz / 'estado.sqlite3') as historico, \
             patch('src.servico_pedidos.conferir_arquivos_baixados', return_value=True), \
             patch('src.servico_pedidos.validar_pedido_baixado', return_value=[ItemEsperado('P1', 'C1', 'T1', Decimal(1))]), \
             patch('src.servico_pedidos.registrar_evento', return_value=False):
            historico.salvar(EstadoPedido(self.pedido, '', 'baixado'))
            servico.importar_novo(self.pedido, self.banco, historico, self.resumo, self.recursos)
            self.assertEqual(self.resumo.situacoes[self.pedido], 'impressao_enviada')
            self.banco.confirmar_gravacao.assert_called_once()

    def test_reimprimir_aviso_pendente_nao_exige_xml_nem_conta_nova_inclusao(self):
        self.banco.consultar_pedidos.return_value = {self.pedido: [PedidoExistente('100', 2)]}
        for preservar_itens in (False, True):
            with self.subTest(preservar_itens=preservar_itens), \
                 EstadoPedidos(self.raiz / f'estado-aviso-{preservar_itens}.sqlite3') as historico, \
                 patch('src.servico_pedidos.validar_pedido_baixado') as validar, \
                 patch('src.servico_pedidos.importar_novo') as importar, \
                 patch('src.servico_pedidos.enviar_impressao') as imprimir:
                historico.salvar(EstadoPedido(self.pedido, '', 'aviso_pendente'))
                if preservar_itens:
                    historico.salvar_itens_esperados(self.pedido, [ItemEsperado('P1', 'C1', 'T1', Decimal(1))])
                self.banco.confirmar_gravacao.reset_mock()
                servico.processar_um_pedido(self.pedido, 'reimprimir', self.banco,
                                           historico, self.resumo, self.recursos)
                self.banco.confirmar_gravacao.assert_called_once_with(self.pedido, '100')
                self.assertEqual(self.totais()['pedido_inserido'], 0)
                self.assertEqual(historico.obter(self.pedido).etapa, 'importado')
                validar.assert_not_called()
                importar.assert_not_called()
                imprimir.assert_called_once_with(self.pedido, '100', historico, self.resumo,
                                                 forcar=True, integracoes=self.integracoes)

    def test_reimprimir_aviso_sem_confirmacao_preserva_bloqueio_e_nao_conta_inclusao(self):
        self.banco.consultar_pedidos.return_value = {self.pedido: [PedidoExistente('100', 2)]}
        self.banco.confirmar_gravacao.side_effect = GravacaoNaoConfirmadaError('Gravação não confirmada')
        with EstadoPedidos(self.raiz / 'estado.sqlite3') as historico, \
             patch('src.servico_pedidos.enviar_impressao') as imprimir:
            historico.salvar(EstadoPedido(self.pedido, '', 'aviso_pendente'))
            with self.assertRaises(GravacaoNaoConfirmadaError):
                servico.processar_um_pedido(self.pedido, 'reimprimir', self.banco,
                                           historico, self.resumo, self.recursos)
            self.assertEqual(historico.inclusoes_incertas(), [self.pedido])
            self.assertEqual(self.totais()['pedido_inserido'], 0)
            imprimir.assert_not_called()

    def test_existentes_e_falhas_por_lote_nao_aumentam_inseridos(self):
        banco = MagicMock()
        banco.__enter__.return_value = self.banco
        contexto = servico.ContextoExecucao(CONFIG, servico.Integracoes(banco=lambda *args: banco))
        def existente(pedido, modo, consulta, estado, resumo, recursos, encontrados):
            resumo.situacoes[pedido] = 'existente'
        with EstadoPedidos(self.raiz / 'estado.sqlite3') as historico, \
             patch('src.servico_pedidos.validar_configuracao'), \
             patch('src.servico_pedidos.processar_um_pedido', side_effect=existente):
            servico.processar_pedidos([self.pedido], historico=historico, contexto=contexto)
        with EstadoPedidos(self.raiz / 'estado.sqlite3') as historico, \
             patch('src.servico_pedidos.validar_configuracao'), \
             patch('src.servico_pedidos.processar_um_pedido', side_effect=RuntimeError('sintetico')):
            with self.assertRaises(RuntimeError):
                servico.processar_pedidos([self.pedido], historico=historico, contexto=contexto)
        self.assertEqual(self.totais()['pedido_existente'], 1)
        self.assertEqual(self.totais()['pedido_falhou'], 1)
        self.assertEqual(self.totais()['pedido_inserido'], 0)
