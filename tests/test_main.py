import tempfile
import unittest
import xml.etree.ElementTree as ET
from contextlib import ExitStack
from pathlib import Path
from decimal import Decimal
from threading import Event
from unittest.mock import MagicMock, patch
from pypdf import PdfWriter

import src.servico_pedidos as main
from src.banco import BancoSisplanError, PedidoExistente, ProdutoCadastrado, GravacaoNaoConfirmadaError
from src.estado import EstadoPedido, EstadoPedidos
from src.importar import ResultadoImportacao
from src.prevalidacao import PedidoRejeitadoError
from tests.fixtures import xml_pedido
from src.pedidos import ItemEsperado
from src.erros import SessaoPortalExpiradaError, NumeroInternoForaSequenciaError, ProdutoSemCadastroError, SisplanError


class FluxoPrevalidacaoTests(unittest.TestCase):
    def test_download_pendente_bloqueia_portal_e_inclusao_antes_da_retomada(self) -> None:
        self.preparar()
        with EstadoPedidos(self.estado_path) as historico:
            historico.adicionar_pedidos(['2026-12345'])
        (self.pasta / '.nunes-download-interrompido').mkdir()
        with self.assertRaises(RuntimeError) as erro:
            main.processar_pedidos(['2026-12345'])
        self.assertIn('recuperação pendente', str(erro.exception))
        self.login.assert_not_called()
        self.baixar.assert_not_called()
        self.assert_sem_interface()
        with EstadoPedidos(self.estado_path) as historico:
            registro = historico.obter('2026-12345')
            assert registro is not None
            self.assertEqual(registro.etapa, 'para_baixar')
        self.assertEqual(main.opcoes_seguras(main.DownloadPendenteError('pendente'), registro), (False, True))
        incerto = EstadoPedido('2026-12345', '', 'importacao_iniciada')
        self.assertEqual(main.opcoes_seguras(main.DownloadPendenteError('pendente'), incerto), (False, False))

    def test_parar_depois_do_download_preserva_arquivos_sem_iniciar_inclusao(self) -> None:
        self.preparar()
        parada = Event()
        def baixar(*args, **kwargs):
            parada.set()
            return {'2026-12345': True}
        self.baixar.side_effect = baixar
        main.processar_pedidos(['2026-12345'], parar=parada.is_set)
        self.assert_sem_interface()
        with EstadoPedidos(self.estado_path) as historico:
            self.assertEqual(historico.obter('2026-12345').etapa, 'baixado')

    def test_parar_durante_inclusao_confirma_gravacao_e_deixa_impressao_pendente(self) -> None:
        self.preparar()
        parada = Event()
        def importar(*args, **kwargs):
            args[-1]('100')
            parada.set()
            return ResultadoImportacao('100', 'aguarda_confirmacao')
        self.importar.side_effect = importar
        main.processar_pedidos(['2026-12345'], parar=parada.is_set)
        self.banco.confirmar_gravacao.assert_called_once()
        self.imprimir.assert_not_called()
        with EstadoPedidos(self.estado_path) as historico:
            self.assertEqual(historico.obter('2026-12345').etapa, 'importado')

    def setUp(self) -> None:
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.pasta = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.estado_path = self.pasta / 'estado.sqlite3'
        self.stack.enter_context(patch('src.servico_pedidos.EstadoPedidos', side_effect=lambda: EstadoPedidos(self.estado_path)))
        self.stack.enter_context(patch('src.servico_pedidos.validar_configuracao'))
        self.banco = MagicMock()
        banco_classe = self.stack.enter_context(patch('src.servico_pedidos.BancoSisplan'))
        banco_classe.return_value.__enter__.return_value = self.banco
        self.banco.consultar_pedidos.return_value = {}
        self.banco.consultar_referencia_numero.return_value = 100
        self.banco.confirmar_gravacao.return_value = PedidoExistente('100', 2)
        self.banco.consultar_barras.return_value = {
            '0123456789012': {ProdutoCadastrado('P1', 'C1', 'T1')},
        }
        self.scraper = self.stack.enter_context(patch('src.servico_pedidos.create_scraper'))
        self.login = self.stack.enter_context(patch('src.servico_pedidos.realizar_login'))
        self.baixar = self.stack.enter_context(patch('src.servico_pedidos.baixar_pedidos'))
        self.app = self.stack.enter_context(patch('src.servico_pedidos.inicia_app'))
        self.app.return_value = (MagicMock(), MagicMock(), MagicMock(), {})
        self.importar = self.stack.enter_context(patch('src.servico_pedidos.importar_pedido'))
        def simular_importacao(*args: object, **kwargs: object) -> ResultadoImportacao:
            args[-1]('100')
            return ResultadoImportacao('100', 'aguarda_confirmacao')
        self.importar.side_effect = simular_importacao
        self.imprimir = self.stack.enter_context(patch('src.servico_pedidos.processar_impressao'))
        self.imprimir.return_value = 'impressao_enviada'
        self.notificar = self.stack.enter_context(patch('src.servico_pedidos.notificar_operacao_confirmada'))
        self.salvar_erro = self.stack.enter_context(patch('src.prevalidacao.salvar_pedido_txt'))
        self.stack.enter_context(patch('src.prevalidacao.caminho_xml', side_effect=self.caminho))
        self.stack.enter_context(patch('src.filas.caminho_xml', side_effect=self.caminho))
        self.stack.enter_context(patch('src.filas.caminho_pdf', side_effect=lambda pedido: self.pasta / f'{pedido}.pdf'))

    def caminho(self, pedido: str) -> Path:
        return self.pasta / f'{pedido}.xml'

    def preparar(self, pedido: str = '2026-12345', barra: str = '0123456789012') -> None:
        ET.ElementTree(xml_pedido(pedido, ((barra,),))).write(
            self.caminho(pedido), encoding='utf-8', xml_declaration=True,
        )
        writer = PdfWriter()
        writer.add_blank_page(width=595, height=842)
        with (self.pasta / f'{pedido}.pdf').open('wb') as arquivo:
            writer.write(arquivo)
        resultados = self.baixar.return_value
        if not isinstance(resultados, dict):
            resultados = {}
        resultados[pedido] = True
        self.baixar.return_value = resultados

    def assert_sem_interface(self) -> None:
        self.app.assert_not_called()
        self.importar.assert_not_called()
        self.imprimir.assert_not_called()

    def test_todos_existentes_encerram_antes_de_portal_e_interface(self) -> None:
        self.banco.consultar_pedidos.return_value = {
            '2026-12345': [PedidoExistente('100', 1)],
            '2026-67890': [PedidoExistente('101', 2)],
        }
        main.processar_pedidos(['2026-12345', '2026-67890'])
        self.scraper.assert_not_called()
        self.baixar.assert_not_called()
        self.assert_sem_interface()

    def test_falha_inicial_de_banco_impede_portal_e_interface(self) -> None:
        self.banco.consultar_pedidos.side_effect = BancoSisplanError('Banco indisponível')
        with self.assertRaises(BancoSisplanError):
            main.processar_pedidos(['2026-12345'])
        self.scraper.assert_not_called()
        self.assert_sem_interface()

    def test_barra_ausente_rejeita_pedido_inteiro_e_registra_motivo(self) -> None:
        self.preparar()
        self.banco.consultar_barras.return_value = {}
        with self.assertRaises(PedidoRejeitadoError):
            main.processar_pedidos(['2026-12345'])
        self.assert_sem_interface()
        self.assertIn('0123456789012', self.salvar_erro.call_args.kwargs['motivo'])

    def test_barra_ambigua_impede_inclusao(self) -> None:
        self.preparar()
        self.banco.consultar_barras.return_value['0123456789012'].add(
            ProdutoCadastrado('P2', 'C2', 'T2')
        )
        with self.assertRaises(PedidoRejeitadoError):
            main.processar_pedidos(['2026-12345'])
        self.assert_sem_interface()

    def test_sem_cadastro_preserva_pendencia_e_so_importa_apos_cadastro_e_solicitacao(self) -> None:
        self.preparar()
        cadastradas = self.banco.consultar_barras.return_value
        self.banco.consultar_barras.return_value = {}
        resumo = main.processar_pedidos(['2026-12345'], ao_erro=lambda *args: 'pular')
        self.assertEqual(resumo.situacoes['2026-12345'], 'sem_cadastro')
        with EstadoPedidos(self.estado_path) as historico:
            self.assertEqual(historico.obter('2026-12345').etapa, 'sem_cadastro')
            self.assertIn('0123456789012', historico.obter('2026-12345').erro)
            self.assertEqual(historico.pendentes(), ['2026-12345'])
        with self.assertRaises(ProdutoSemCadastroError):
            main.processar_pedidos([], modo='retomar')
        self.assert_sem_interface()
        self.banco.consultar_barras.return_value = cadastradas
        self.baixar.reset_mock()
        resumo = main.processar_pedidos([], modo='retomar')
        self.baixar.assert_not_called()
        self.importar.assert_called_once()
        self.assertEqual(resumo.importados, {'2026-12345'})
        with EstadoPedidos(self.estado_path) as historico:
            self.assertNotEqual(historico.obter('2026-12345').etapa, 'sem_cadastro')
            self.assertEqual(historico.obter('2026-12345').erro, '')

    def test_sem_cadastro_detectado_no_sisplan_tambem_fica_salvo_para_nova_importacao(self) -> None:
        self.preparar()
        self.importar.side_effect = None
        self.importar.return_value = ResultadoImportacao('', 'sem_cadastro')
        resumo = main.processar_pedidos(['2026-12345'], ao_erro=lambda *args: 'pular')
        self.assertEqual(resumo.situacoes['2026-12345'], 'sem_cadastro')
        self.banco.confirmar_gravacao.assert_not_called()
        self.imprimir.assert_not_called()
        with EstadoPedidos(self.estado_path) as historico:
            registro = historico.obter('2026-12345')
            self.assertEqual((registro.etapa, registro.numero), ('sem_cadastro', ''))
        self.importar.return_value = ResultadoImportacao('100', 'aguarda_confirmacao')
        main.processar_pedidos(['2026-12345'])
        self.assertEqual(self.importar.call_count, 2)
        self.banco.confirmar_gravacao.assert_called_once()

    def test_nova_tentativa_sem_cadastro_confere_duplicidade_antes_de_importar(self) -> None:
        self.salvar_estado('sem_cadastro', '')
        self.banco.consultar_pedidos.return_value = {'2026-12345': [PedidoExistente('100', 2)]}
        resumo = main.processar_pedidos(['2026-12345'])
        self.assertEqual(resumo.situacoes['2026-12345'], 'existente')
        self.baixar.assert_not_called()
        self.assert_sem_interface()

    def test_cancelamento_sem_cadastro_incerto_bloqueia_repetir_e_proximo_pedido(self) -> None:
        self.preparar('2026-12345')
        self.preparar('2026-67890')
        self.importar.side_effect = SisplanError('Não foi possível confirmar o cancelamento após produto sem cadastro.')
        decisoes = []
        def ao_erro(pedido, erro, repetir, pular):
            decisoes.append((pedido, repetir, pular))
            return 'pular'
        main.processar_pedidos(['2026-12345', '2026-67890'], ao_erro=ao_erro)
        self.assertEqual(decisoes, [('2026-12345', False, False)])
        self.importar.assert_called_once()
        self.banco.confirmar_gravacao.assert_not_called()
        self.imprimir.assert_not_called()
        with EstadoPedidos(self.estado_path) as historico:
            self.assertEqual(historico.obter('2026-12345').etapa, 'importacao_iniciada')
            self.assertEqual(historico.obter('2026-67890').etapa, 'para_baixar')
            self.assertEqual(historico.inclusoes_incertas(), ['2026-12345'])

    def test_sem_cadastro_com_arquivos_ausentes_permite_baixar_de_novo(self) -> None:
        self.preparar()
        self.salvar_estado('sem_cadastro', '')
        self.caminho('2026-12345').unlink()
        self.baixar.side_effect = lambda *args, **kwargs: (self.preparar() or {'2026-12345': True})
        main.processar_pedidos(['2026-12345'], ao_erro=lambda *args: 'repetir')
        self.baixar.assert_called_once()
        self.importar.assert_called_once()

    def test_xml_divergente_ou_malformado_impede_inclusao(self) -> None:
        for texto in ('<OrdemCompra/>', '<quebrado'):
            with self.subTest(texto=texto):
                self.caminho('2026-12345').write_text(texto, encoding='utf-8')
                self.baixar.return_value = {'2026-12345': True}
                with self.assertRaises(PedidoRejeitadoError):
                    main.processar_pedidos(['2026-12345'])
                self.assert_sem_interface()

    def test_importa_e_imprime_somente_pedido_apto_do_lote(self) -> None:
        self.preparar('2026-12345', '1234567890123')
        self.preparar('2026-67890')
        main.processar_pedidos(['2026-12345', '2026-67890'], ao_erro=lambda *args: 'pular')
        self.app.assert_called_once()
        self.importar.assert_called_once()
        self.assertEqual(self.importar.call_args.args[0], '2026-67890')
        self.assertEqual(self.imprimir.call_args.args[:2], ('2026-67890', '100'))

    def test_reconsulta_duplicidade_antes_de_incluir(self) -> None:
        self.preparar()
        self.banco.consultar_pedidos.side_effect = [
            {}, {'2026-12345': [PedidoExistente('102', 2)]},
        ]
        main.processar_pedidos(['2026-12345'])
        self.importar.assert_not_called()
        self.imprimir.assert_not_called()

    def test_falha_na_consulta_de_barras_impede_interface(self) -> None:
        self.preparar()
        self.banco.consultar_barras.side_effect = BancoSisplanError('Timeout')
        with self.assertRaises(BancoSisplanError):
            main.processar_pedidos(['2026-12345'])
        self.assert_sem_interface()

    def test_falha_na_reconsulta_interrompe_lote_antes_do_proximo_pedido(self) -> None:
        self.preparar('2026-12345')
        self.preparar('2026-67890')
        self.banco.consultar_pedidos.side_effect = [{}, {}, BancoSisplanError('Timeout')]
        with self.assertRaises(BancoSisplanError):
            main.processar_pedidos(['2026-12345', '2026-67890'])
        self.importar.assert_called_once()
        self.assertEqual(self.importar.call_args.args[0], '2026-12345')

    def test_download_falhou_nao_usa_arquivo_antigo(self) -> None:
        self.preparar()
        self.baixar.return_value = {'2026-12345': False}
        with self.assertRaises(PedidoRejeitadoError):
            main.processar_pedidos(['2026-12345'])
        self.assert_sem_interface()

    def test_preserva_bloqueio_de_duplicidade_da_interface(self) -> None:
        self.preparar()
        self.importar.side_effect = None
        self.importar.return_value = ResultadoImportacao('', 'duplicado')
        with self.assertRaises(GravacaoNaoConfirmadaError):
            main.processar_pedidos(['2026-12345'])
        self.importar.assert_called_once()
        self.imprimir.assert_not_called()
        with EstadoPedidos(self.estado_path) as historico:
            self.assertEqual(historico.obter('2026-12345').etapa, 'aviso_pendente')
            self.assertEqual(historico.pendentes(), ['2026-12345'])
        # Nem Retomar nem Reiniciar convertem ausência no banco em outra inclusão.
        for modo in ('retomar', 'reiniciar'):
            with self.assertRaises(GravacaoNaoConfirmadaError):
                main.processar_pedidos(['2026-12345'], modo=modo)
        self.importar.assert_called_once()

    def test_duplicidade_cancelada_nao_deixa_numero_provisorio_preso_na_fila(self) -> None:
        self.preparar()
        self.banco.consultar_pedidos.side_effect = [{}, {}, {'2026-12345': [PedidoExistente('102', 2)]}]
        def duplicado(*args, **kwargs):
            args[-1]('100')
            return ResultadoImportacao('100', 'duplicado')
        self.importar.side_effect = duplicado
        main.processar_pedidos(['2026-12345'])
        with EstadoPedidos(self.estado_path) as historico:
            self.assertEqual(historico.obter('2026-12345').numero, '102')
            self.assertEqual(historico.obter('2026-12345').etapa, 'existente')
            self.assertEqual(historico.pendentes(), [])
        self.imprimir.assert_not_called()

    def test_aviso_com_consulta_indisponivel_preserva_estado_apos_reabrir(self) -> None:
        self.preparar()
        self.importar.side_effect = None
        self.importar.return_value = ResultadoImportacao('100', 'duplicado')
        self.banco.consultar_pedidos.side_effect = [{}, {}, BancoSisplanError('Rede indisponível')]
        with self.assertRaises(BancoSisplanError):
            main.processar_pedidos(['2026-12345'])
        with EstadoPedidos(self.estado_path) as historico:
            self.assertEqual(historico.obter('2026-12345').etapa, 'aviso_pendente')
            self.assertEqual(historico.inclusoes_incertas(), ['2026-12345'])
        self.banco.consultar_pedidos.side_effect = None
        self.banco.consultar_pedidos.return_value = {'2026-12345': [PedidoExistente('102', 2)]}
        main.processar_pedidos([], modo='retomar')
        self.importar.assert_called_once()
        self.imprimir.assert_not_called()
        self.banco.confirmar_gravacao.assert_not_called()
        with EstadoPedidos(self.estado_path) as historico:
            self.assertEqual(historico.obter('2026-12345').etapa, 'existente')
            self.assertEqual(historico.pendentes(), [])

    def test_aviso_ambiguo_nao_sai_da_fila_nem_imprime(self) -> None:
        self.preparar()
        self.importar.side_effect = None
        self.importar.return_value = ResultadoImportacao('100', 'duplicado')
        ambiguos = {'2026-12345': [PedidoExistente('101', 1), PedidoExistente('102', 2)]}
        self.banco.consultar_pedidos.side_effect = [{}, {}, ambiguos]
        with self.assertRaises(GravacaoNaoConfirmadaError):
            main.processar_pedidos(['2026-12345'])
        with EstadoPedidos(self.estado_path) as historico:
            self.assertEqual(historico.obter('2026-12345').etapa, 'aviso_pendente')
        self.imprimir.assert_not_called()

    def salvar_estado(self, etapa: str = 'importado', numero: str = '100') -> None:
        with EstadoPedidos(self.estado_path) as historico:
            historico.salvar(EstadoPedido('2026-12345', numero, etapa, 2))

    def test_gravacao_nao_confirmada_impede_impressao_e_preserva_pendencia(self) -> None:
        self.preparar()
        self.banco.confirmar_gravacao.side_effect = BancoSisplanError('Gravação não confirmada')
        with self.assertRaises(BancoSisplanError):
            main.processar_pedidos(['2026-12345'])
        self.imprimir.assert_not_called()
        self.notificar.assert_not_called()
        with EstadoPedidos(self.estado_path) as historico:
            registro = historico.obter('2026-12345')
            self.assertEqual((registro.numero, registro.etapa), ('100', 'gravacao_pendente'))
            self.assertIn('Gravação não confirmada', registro.erro)

    def test_retoma_somente_impressao_sem_portal_ou_interface(self) -> None:
        self.salvar_estado('pdf_pronto')
        self.banco.consultar_pedidos.return_value = {'2026-12345': [PedidoExistente('100', 2)]}
        resumo = main.processar_pedidos([], modo='retomar')
        self.scraper.assert_not_called()
        self.app.assert_not_called()
        self.importar.assert_not_called()
        self.imprimir.assert_called_once()
        self.banco.confirmar_gravacao.assert_called_once_with('2026-12345', '100')
        self.assertEqual(resumo.retomados, {'2026-12345'})
        self.assertEqual(resumo.situacoes['2026-12345'], 'impressao_enviada')

    def test_reimpressao_explicita_de_pedido_antigo_confere_numero_no_banco(self) -> None:
        self.banco.consultar_pedidos.return_value = {'2026-109335': [PedidoExistente('11250', 2)]}
        self.banco.confirmar_gravacao.return_value = PedidoExistente('11250', 2)
        main.processar_pedidos(['2026-109335'], modo='reimprimir')
        self.assertEqual(self.imprimir.call_args.args[:2], ('2026-109335', '11250'))
        self.assertTrue(self.imprimir.call_args.kwargs['forcar'])
        self.scraper.assert_not_called()
        self.app.assert_not_called()

    def test_pendencia_sem_correspondencia_nao_reimporta_automaticamente(self) -> None:
        self.salvar_estado('gravacao_pendente')
        with self.assertRaises(BancoSisplanError):
            main.processar_pedidos(['2026-12345', '2026-67890'])
        self.scraper.assert_not_called()
        self.assert_sem_interface()

    def test_reiniciar_libera_apenas_inclusao_pendente_ausente_do_banco(self) -> None:
        self.salvar_estado('gravacao_pendente')
        self.preparar()
        main.processar_pedidos(['2026-12345'], modo='reiniciar')
        self.importar.assert_called_once()

    def test_resumo_separa_importacao_confirmada_de_impressao_pendente(self) -> None:
        self.preparar()
        self.imprimir.return_value = 'impressao_pendente'
        resumo = main.processar_pedidos(['2026-12345'], ao_erro=lambda *args: 'pular')
        self.assertEqual(resumo.importados, {'2026-12345'})
        self.assertEqual(resumo.situacoes['2026-12345'], 'impressao_pendente')

    def test_interrupcao_de_envio_preserva_incerteza_e_pedido_seguinte_nao_e_incluido(self) -> None:
        self.preparar('2026-12345')
        self.preparar('2026-67890')
        def interromper(pedido, numero, historico, forcar=False):
            historico.salvar(EstadoPedido(pedido, numero, 'impressao_iniciada', 2))
            raise KeyboardInterrupt()
        self.imprimir.side_effect = interromper
        with patch('src.servico_pedidos.ResumoExecucao.exibir') as exibir:
            with self.assertRaises(KeyboardInterrupt):
                main.processar_pedidos(['2026-12345', '2026-67890'])
            exibir.assert_called_once()
        self.importar.assert_called_once()
        with EstadoPedidos(self.estado_path) as historico:
            self.assertEqual(historico.obter('2026-12345').etapa, 'impressao_iniciada')
            self.assertEqual(historico.obter('2026-67890').etapa, 'para_baixar')

    def test_pendencia_de_gravacao_confirmada_na_retomada_nao_reimporta(self) -> None:
        self.preparar()
        self.salvar_estado('gravacao_pendente')
        self.banco.consultar_pedidos.return_value = {'2026-12345': [PedidoExistente('100', 2)]}
        main.processar_pedidos([], modo='retomar')
        self.importar.assert_not_called()
        self.scraper.assert_not_called()
        self.imprimir.assert_called_once()

    def test_banco_so_reconecta_apos_decisao_e_reconfere_pedido(self) -> None:
        self.banco.consultar_pedidos.side_effect = [BancoSisplanError('Rede'),
            {'2026-12345': [PedidoExistente('100', 2)]},
            {'2026-12345': [PedidoExistente('100', 2)]}]
        def decidir(*args):
            self.banco.reconectar.assert_not_called()
            return 'repetir'
        main.processar_pedidos(['2026-12345'], ao_erro=decidir)
        self.banco.reconectar.assert_called_once()
        self.importar.assert_not_called()

    def test_sessao_expirada_reconecta_somente_por_escolha_e_reaproveita_pendencia(self) -> None:
        self.preparar()
        self.baixar.side_effect = [SessaoPortalExpiradaError(), {'2026-12345': True}]
        def decidir(pedido, erro, repetir, continuar):
            self.assertIsInstance(erro, SessaoPortalExpiradaError)
            self.assertEqual((repetir, continuar), (True, False))
            self.assertEqual(self.login.call_count, 1)
            return 'repetir'
        main.processar_pedidos(['2026-12345'], ao_erro=decidir)
        self.assertEqual(self.scraper.call_count, 2)
        self.assertEqual(self.login.call_count, 2)
        self.importar.assert_called_once()

    def test_cancelar_sessao_expirada_preserva_lote_sem_novo_login(self) -> None:
        self.baixar.side_effect = SessaoPortalExpiradaError()
        main.processar_pedidos(['2026-12345', '2026-67890'], ao_erro=lambda *args: 'encerrar')
        self.assertEqual(self.login.call_count, 1)
        with EstadoPedidos(self.estado_path) as historico:
            self.assertEqual(historico.pendentes(), ['2026-12345', '2026-67890'])
        self.assert_sem_interface()

    def test_itens_sao_preservados_antes_da_interface_e_conferidos_antes_de_imprimir(self) -> None:
        self.preparar()
        def iniciar():
            # O arquivo pode ser lido por outra conexão sem adquirir a trava da aplicação.
            import sqlite3
            from contextlib import closing
            with closing(sqlite3.connect(self.estado_path)) as conn:
                self.assertEqual(conn.execute('SELECT quantidade FROM itens_esperados').fetchone(), ('1',))
            return (MagicMock(), MagicMock(), MagicMock(), {})
        self.app.side_effect = iniciar
        self.banco.confirmar_gravacao.side_effect = GravacaoNaoConfirmadaError('Itens incompletos')
        main.processar_pedidos(['2026-12345'], ao_erro=lambda *args: 'encerrar')
        self.assertEqual(self.banco.confirmar_gravacao.call_args.kwargs['itens_esperados'],
                         [ItemEsperado('P1', 'C1', 'T1', Decimal(1))])
        self.imprimir.assert_not_called()
        self.notificar.assert_not_called()

    def test_retomada_incerta_usa_itens_preservados_sem_reconsultar_cadastro(self) -> None:
        itens = [ItemEsperado('P1', 'C1', 'T1', Decimal(5))]
        with EstadoPedidos(self.estado_path) as historico:
            historico.salvar(EstadoPedido('2026-12345', '100', 'gravacao_pendente'))
            historico.salvar_itens_esperados('2026-12345', itens)
        self.banco.consultar_pedidos.return_value = {'2026-12345': [PedidoExistente('100', 2)]}
        main.processar_pedidos([], modo='retomar')
        self.banco.confirmar_gravacao.assert_called_once_with('2026-12345', '100', itens_esperados=itens)
        self.banco.consultar_barras.assert_not_called()
        self.importar.assert_not_called()

    def test_falha_ao_preservar_itens_impede_primeira_interacao_com_erp(self) -> None:
        from src.estado import EstadoError
        self.preparar()
        with patch.object(EstadoPedidos, 'salvar_itens_esperados', side_effect=EstadoError('Disco cheio')):
            decisao = MagicMock(return_value='encerrar')
            main.processar_pedidos(['2026-12345'], ao_erro=decisao)
        self.assert_sem_interface()
        self.assertEqual(decisao.call_args.args[2:], (False, False))

    def test_lista_inteira_fica_salva_mesmo_se_conexao_inicial_falhar(self) -> None:
        self.banco.consultar_pedidos.side_effect = BancoSisplanError('Rede indisponível')
        with self.assertRaises(BancoSisplanError):
            main.processar_pedidos(['2026-12345', '2026-67890'])
        with EstadoPedidos(self.estado_path) as historico:
            self.assertEqual(historico.pendentes(), ['2026-12345', '2026-67890'])
            self.assertEqual(historico.obter('2026-12345').etapa, 'para_baixar')

    def test_retoma_download_concluido_sem_portal(self) -> None:
        self.preparar()
        self.salvar_estado('baixado', numero='')
        main.processar_pedidos([], modo='retomar')
        self.scraper.assert_not_called()
        self.baixar.assert_not_called()
        self.importar.assert_called_once()

    def test_erro_pausa_antes_do_proximo_pedido_e_retomada_preserva_download(self) -> None:
        self.preparar('2026-12345')
        self.preparar('2026-67890')
        self.banco.consultar_barras.return_value = {}
        decisao = MagicMock(return_value='encerrar')
        resumo = main.processar_pedidos(['2026-12345', '2026-67890'], ao_erro=decisao)
        self.baixar.assert_called_once()
        self.assertEqual(resumo.situacoes['2026-67890'], 'aguardando')
        with EstadoPedidos(self.estado_path) as historico:
            self.assertEqual(historico.obter('2026-12345').etapa, 'sem_cadastro')
            self.assertEqual(historico.obter('2026-67890').etapa, 'para_baixar')
        self.assertEqual(decisao.call_args.args[2:], (True, True))
        self.banco.consultar_barras.return_value = {'0123456789012': {ProdutoCadastrado('P1', 'C1', 'T1')}}
        self.baixar.reset_mock()
        main.processar_pedidos([], modo='retomar')
        self.baixar.assert_called_once()
        self.assertEqual(self.baixar.call_args.args[1], ['2026-67890'])
        self.assertEqual(self.importar.call_count, 2)

    def test_tenta_novamente_so_depois_da_decisao_do_operador(self) -> None:
        self.preparar()
        self.baixar.side_effect = [{'2026-12345': False}, {'2026-12345': True}]
        def responder(pedido, erro, repetir, continuar):
            self.assertEqual(self.baixar.call_count, 1)
            self.assertEqual(self.importar.call_count, 0)
            self.assertTrue(repetir)
            return 'repetir'
        main.processar_pedidos(['2026-12345'], ao_erro=responder)
        self.assertEqual(self.baixar.call_count, 2)
        self.importar.assert_called_once()

    def test_nao_reinicia_inclusao_incerta_mesmo_se_callback_pedir_repetir(self) -> None:
        from src.erros import SisplanError
        self.preparar()
        self.importar.side_effect = SisplanError('Erro durante a inclusão')
        decisao = MagicMock(return_value='repetir')
        main.processar_pedidos(['2026-12345', '2026-67890'], ao_erro=decisao)
        self.importar.assert_called_once()
        self.assertEqual(decisao.call_args.args[2:], (False, False))
        with EstadoPedidos(self.estado_path) as historico:
            self.assertEqual(historico.obter('2026-12345').etapa, 'importacao_iniciada')
            self.assertEqual(historico.obter('2026-67890').etapa, 'para_baixar')

    def test_duas_anomalias_pausam_lote_e_preservam_pedido_para_tentativa_manual(self) -> None:
        self.preparar('2026-12345')
        self.preparar('2026-67890')
        self.importar.side_effect = NumeroInternoForaSequenciaError('Duas inclusões canceladas')
        decisao = MagicMock(return_value='encerrar')
        main.processar_pedidos(['2026-12345', '2026-67890'], ao_erro=decisao)
        self.assertEqual(decisao.call_args.args[2:], (True, False))
        self.importar.assert_called_once()
        self.banco.confirmar_gravacao.assert_not_called()
        self.imprimir.assert_not_called()
        self.notificar.assert_not_called()
        with EstadoPedidos(self.estado_path) as historico:
            self.assertEqual(historico.obter('2026-12345').etapa, 'baixado')
            self.assertEqual(historico.obter('2026-12345').numero, '')
            self.assertEqual(historico.obter('2026-67890').etapa, 'para_baixar')

    def test_repeticao_apos_anomalias_so_ocorre_apos_decisao_do_operador(self) -> None:
        self.preparar()
        simular = self.importar.side_effect
        def importar(*args, **kwargs):
            if self.importar.call_count == 1:
                raise NumeroInternoForaSequenciaError('Duas inclusões canceladas')
            return simular(*args, **kwargs)
        self.importar.side_effect = importar
        def decidir(*args):
            self.assertEqual(self.importar.call_count, 1)
            return 'repetir'
        main.processar_pedidos(['2026-12345'], ao_erro=decidir)
        self.assertEqual(self.importar.call_count, 2)
        self.assertEqual(self.banco.consultar_referencia_numero.call_count, 2)
        self.baixar.assert_called_once()
        self.imprimir.assert_called_once()

    def test_falha_na_referencia_impede_abrir_inclusao(self) -> None:
        self.preparar()
        self.banco.consultar_referencia_numero.side_effect = BancoSisplanError('Referência indisponível')
        with self.assertRaises(BancoSisplanError):
            main.processar_pedidos(['2026-12345'])
        self.assert_sem_interface()
        with EstadoPedidos(self.estado_path) as historico:
            self.assertEqual(historico.obter('2026-12345').etapa, 'baixado')

    def test_arquivos_removidos_de_pedido_baixado_exigem_novo_download(self) -> None:
        self.preparar()
        self.salvar_estado('baixado', numero='')
        (self.pasta / '2026-12345.pdf').unlink()
        self.baixar.return_value = {'2026-12345': False}
        main.processar_pedidos([], modo='retomar', ao_erro=MagicMock(side_effect=['repetir', 'encerrar']))
        self.baixar.assert_called_once()
        self.assert_sem_interface()
        with EstadoPedidos(self.estado_path) as historico:
            self.assertEqual(historico.obter('2026-12345').etapa, 'para_baixar')

    def test_erro_fica_no_log_com_identificacao_e_traceback(self) -> None:
        self.banco.consultar_pedidos.side_effect = BancoSisplanError('Falha de leitura')
        with self.assertLogs('src.servico_pedidos', level='ERROR') as capturado:
            main.processar_pedidos(['2026-12345'], ao_erro=lambda *args: 'encerrar')
        self.assertIn('pedido 2026-12345', '\n'.join(capturado.output))
        self.assertIn('Traceback', '\n'.join(capturado.output))

    def test_pular_pedido_existente_remove_apenas_da_fila_pendente(self) -> None:
        self.banco.consultar_pedidos.return_value = {'2026-12345': [PedidoExistente('100', 2)]}
        main.processar_pedidos(['2026-12345'])
        with EstadoPedidos(self.estado_path) as historico:
            self.assertEqual(historico.pendentes(), [])
            self.assertEqual(historico.obter('2026-12345').etapa, 'existente')


class MigracaoAvisoTests(unittest.TestCase):
    def test_existente_antigo_sem_numero_volta_a_ficar_pendente_sem_perder_erro(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / 'estado.sqlite3'
            with EstadoPedidos(caminho) as historico:
                historico.salvar(EstadoPedido('2026-12345', '', 'existente', erro='Diagnóstico preservado'))
            with EstadoPedidos(caminho) as reaberto:
                registro = reaberto.obter('2026-12345')
                self.assertEqual(registro.etapa, 'aviso_pendente')
                self.assertEqual(registro.erro, 'Diagnóstico preservado')
                self.assertEqual(reaberto.pendentes(), ['2026-12345'])
                self.assertEqual(reaberto.inclusoes_incertas(), ['2026-12345'])
