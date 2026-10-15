import sqlite3
import tempfile
import unittest
from pathlib import Path
from decimal import Decimal

from src.estado import EstadoError, EstadoPedido, EstadoPedidos
from src.pedidos import ItemEsperado


class EstadoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.caminho = Path(self.pasta.name) / 'estado.sqlite3'

    def test_persiste_etapas_apos_reabrir_e_lista_apenas_pendentes(self) -> None:
        with EstadoPedidos(self.caminho) as historico:
            historico.salvar(EstadoPedido('2026-12345', '100', 'gravacao_pendente'))
            historico.salvar(EstadoPedido('2026-67890', '101', 'impressao_enviada', 2, 'arquivo.pdf'))
        with EstadoPedidos(self.caminho) as historico:
            self.assertEqual(historico.pendentes(), ['2026-12345'])
            registro = historico.obter('2026-67890')
            self.assertEqual((registro.numero, registro.empresa, registro.pdf), ('101', 2, 'arquivo.pdf'))

    def test_segunda_execucao_e_bloqueada_e_trava_e_liberada_ao_sair(self) -> None:
        with EstadoPedidos(self.caminho):
            with self.assertRaises(EstadoError):
                with EstadoPedidos(self.caminho):
                    self.fail('Execuções simultâneas não podem imprimir o mesmo pedido')
        with EstadoPedidos(self.caminho) as historico:
            self.assertEqual(historico.pendentes(), [])

    def test_arquivo_corrompido_nao_e_substituido(self) -> None:
        self.caminho.write_bytes(b'historico danificado')
        with self.assertRaises(EstadoError):
            with EstadoPedidos(self.caminho):
                self.fail('Não deveria abrir o histórico')
        self.assertEqual(self.caminho.read_bytes(), b'historico danificado')

    def test_causa_original_do_sqlite_fica_no_log_tecnico(self) -> None:
        self.caminho.write_bytes(b'historico danificado')
        with self.assertLogs('src.estado', level='ERROR') as logs:
            with self.assertRaises(EstadoError):
                with EstadoPedidos(self.caminho):
                    pass
        texto = '\n'.join(logs.output)
        self.assertIn('file is not a database', texto)
        self.assertIn('SQLITE_NOTADB', texto)
        self.assertIn(str(self.caminho), texto)

    def test_itens_persistem_apos_reabrir_e_substituicao_e_atomica(self) -> None:
        item = ItemEsperado('P1', 'C1', 'T1', Decimal('12.50'))
        with EstadoPedidos(self.caminho) as historico:
            historico.salvar_itens_esperados('2026-12345', [item])
        with EstadoPedidos(self.caminho) as historico:
            self.assertEqual(historico.obter_itens_esperados('2026-12345'), [item])
            with self.assertRaises(EstadoError):
                historico.salvar_itens_esperados('2026-12345', [item, item])
            self.assertEqual(historico.obter_itens_esperados('2026-12345'), [item])

    def test_abre_historico_antigo_preservando_fila_e_cria_tabela_de_itens(self) -> None:
        conn = sqlite3.connect(self.caminho)
        try:
            conn.execute('CREATE TABLE pedidos (pedido TEXT PRIMARY KEY, numero TEXT NOT NULL, '
                         'etapa TEXT NOT NULL, empresa INTEGER, pdf TEXT NOT NULL, erro TEXT NOT NULL, atualizado_em TEXT NOT NULL)')
            conn.execute("INSERT INTO pedidos VALUES ('2026-12345','100','gravacao_pendente',2,'','','')")
            conn.commit()
        finally:
            conn.close()
        with EstadoPedidos(self.caminho) as historico:
            self.assertEqual(historico.pendentes(), ['2026-12345'])
            self.assertEqual(historico.obter_itens_esperados('2026-12345'), [])

    def test_reiniciar_so_remove_importacao_pendente(self) -> None:
        with EstadoPedidos(self.caminho) as historico:
            historico.salvar(EstadoPedido('2026-12345', '100', 'gravacao_pendente'))
            historico.salvar(EstadoPedido('2026-67890', '101', 'importado'))
            historico.liberar_importacao('2026-12345')
            historico.liberar_importacao('2026-67890')
            self.assertEqual(historico.obter('2026-12345').etapa, 'baixado')
            self.assertIsNotNone(historico.obter('2026-67890'))

    def test_falha_de_persistencia_e_explicita(self) -> None:
        with EstadoPedidos(self.caminho) as historico:
            conn = sqlite3.connect(self.caminho)
            conn.execute('DROP TABLE pedidos')
            conn.commit()
            conn.close()
            with self.assertRaises(EstadoError):
                historico.salvar(EstadoPedido('2026-12345', '100', 'importado'))

    def test_adiciona_lista_inteira_sem_reiniciar_etapas_e_preserva_ordem(self) -> None:
        with EstadoPedidos(self.caminho) as historico:
            historico.adicionar_pedidos(['2026-12345', '2026-67890', '2026-12345'])
            historico.salvar(EstadoPedido('2026-12345', '100', 'importado'))
            historico.adicionar_pedidos(['2026-67890', '2026-12345', '2026-99999'])
            self.assertEqual(historico.obter('2026-12345').numero, '100')
            self.assertEqual(historico.pendentes(), ['2026-12345', '2026-67890', '2026-99999'])

    def test_lista_e_gravada_atomicamente_se_um_item_falhar(self) -> None:
        with EstadoPedidos(self.caminho) as historico:
            conexao = sqlite3.connect(self.caminho)
            try:
                conexao.execute("CREATE TRIGGER falhar BEFORE INSERT ON pedidos WHEN NEW.pedido='2026-67890' BEGIN SELECT RAISE(ABORT,'disco'); END")
                conexao.commit()
            finally:
                conexao.close()
            with self.assertRaises(EstadoError):
                historico.adicionar_pedidos(['2026-12345', '2026-67890'])
            self.assertIsNone(historico.obter('2026-12345'))
            self.assertIsNone(historico.obter('2026-67890'))

    def test_filas_sao_visoes_do_mesmo_historico(self) -> None:
        with EstadoPedidos(self.caminho) as historico:
            historico.adicionar_pedidos(['2026-11111', '2026-22222', '2026-33333', '2026-44444'])
            historico.salvar(EstadoPedido('2026-22222', '', 'baixado'))
            historico.salvar(EstadoPedido('2026-33333', '100', 'impressao_incerta'))
            historico.salvar(EstadoPedido('2026-44444', '101', 'impressao_enviada'))
            self.assertEqual(historico.filas(), {'para_baixar': 1, 'baixados': 1, 'importados': 1, 'enviados': 1})
            self.assertEqual(historico.pendentes(), ['2026-11111', '2026-22222', '2026-33333'])
