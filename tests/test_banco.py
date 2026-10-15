import json
import tempfile
import unittest
from pathlib import Path
from decimal import Decimal
from unittest.mock import MagicMock, patch

from src.banco import (
    BancoSisplan, BancoSisplanError, PedidoExistente, ProdutoCadastrado,
    carregar_parametros, GravacaoNaoConfirmadaError,
)
from src.pedidos import ItemEsperado


class BancoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.arquivo = Path(self.pasta.name) / 'banco.json'
        self.valores = {
            'PGHOST': 'db.example', 'PGPORT': '5432', 'PGDATABASE': 'teste',
            'PGUSER': 'usuario_teste', 'PGPASSWORD': 'senha_sigilo_teste',
        }
        self.salvar_config()

    def salvar_config(self) -> None:
        self.arquivo.write_text(
            json.dumps({'perfis': {'principal': self.valores}}), encoding='utf-8',
        )

    def test_carrega_perfil_sem_expor_credenciais_no_repr(self) -> None:
        parametros = carregar_parametros(self.arquivo, 'principal')
        self.assertEqual(parametros.port, 5432)
        self.assertEqual(parametros.password, self.valores['PGPASSWORD'])
        self.assertNotIn(self.valores['PGPASSWORD'], repr(parametros))
        self.assertNotIn(self.valores['PGUSER'], repr(parametros))

    def test_rejeita_configuracao_incompleta_porta_e_perfil_ausente(self) -> None:
        for porta in ('', 'abc', '0', '65536'):
            with self.subTest(porta=porta):
                self.valores['PGPORT'] = porta
                self.salvar_config()
                with self.assertRaises(BancoSisplanError):
                    carregar_parametros(self.arquivo, 'principal')
        with self.assertRaises(BancoSisplanError):
            carregar_parametros(self.arquivo, 'inexistente')
        self.arquivo.write_text('[]', encoding='utf-8')
        with self.assertRaises(BancoSisplanError):
            carregar_parametros(self.arquivo, 'principal')

    @patch('src.banco.connect')
    def test_consulta_pedidos_das_duas_empresas_com_parametros(self, conectar: MagicMock) -> None:
        conexao = conectar.return_value
        cursor = conexao.cursor.return_value
        cursor.fetchall.return_value = [
            ['2026-12345', '100', 1], ['2026-12345', '101', 2],
        ]
        with BancoSisplan(self.arquivo) as banco:
            resultado = banco.consultar_pedidos(['2026-12345'])
        self.assertEqual(resultado, {
            '2026-12345': [PedidoExistente('100', 1), PedidoExistente('101', 2)],
        })
        chamadas = cursor.execute.call_args_list
        self.assertEqual(chamadas[0].args, ('SET TRANSACTION READ ONLY',))
        self.assertIn('statement_timeout', chamadas[1].args[0])
        self.assertIn('lock_timeout', chamadas[2].args[0])
        sql, parametros = chamadas[3].args
        self.assertEqual(parametros, ('00022', ['2026-12345']))
        self.assertNotIn('2026-12345', sql)
        self.assertNotIn('emp_id =', sql.lower())
        conexao.rollback.assert_called_once()
        conexao.commit.assert_not_called()
        conexao.close.assert_called_once()

    @patch('src.banco.connect')
    def test_agrupa_estoques_iguais_sem_esconder_barra_ambigua(self, conectar: MagicMock) -> None:
        conectar.return_value.cursor.return_value.fetchall.return_value = [
            ['0123456789012', 'P1', 'C1', 'T1'],
            ['0123456789012', 'P1', 'C1', 'T1'],
            ['0123456789012', 'P2', 'C2', 'T2'],
        ]
        with BancoSisplan(self.arquivo) as banco:
            resultado = banco.consultar_barras(['0123456789012'])
        self.assertEqual(resultado['0123456789012'], {
            ProdutoCadastrado('P1', 'C1', 'T1'), ProdutoCadastrado('P2', 'C2', 'T2'),
        })

    @patch('src.banco.connect')
    def test_falha_de_consulta_nao_retorna_ausencia_nem_expoe_segredo(self, conectar: MagicMock) -> None:
        conexao = conectar.return_value
        conexao.cursor.return_value.execute.side_effect = RuntimeError('senha_sigilo_teste')
        with BancoSisplan(self.arquivo) as banco:
            with self.assertRaises(BancoSisplanError) as contexto:
                banco.consultar_pedidos(['2026-12345'])
        self.assertNotIn('senha_sigilo_teste', str(contexto.exception))
        self.assertTrue(contexto.exception.__suppress_context__)
        conexao.rollback.assert_called_once()

    @patch('src.banco.connect', side_effect=RuntimeError('senha_sigilo_teste'))
    def test_falha_de_conexao_nao_expoe_segredo(self, conectar: MagicMock) -> None:
        with self.assertRaises(BancoSisplanError) as contexto:
            with BancoSisplan(self.arquivo):
                self.fail('Não deveria abrir a conexão')
        self.assertNotIn('senha_sigilo_teste', str(contexto.exception))

    @patch('src.banco.connect')
    def test_nao_consulta_listas_vazias(self, conectar: MagicMock) -> None:
        with BancoSisplan(self.arquivo) as banco:
            self.assertEqual(banco.consultar_pedidos([]), {})
            self.assertEqual(banco.consultar_barras([]), {})
        conectar.return_value.cursor.assert_not_called()

    @patch('src.banco.BancoSisplan._consultar')
    def test_confirmacao_aguarda_itens_e_confere_numero_interno(self, consultar: MagicMock) -> None:
        consultar.side_effect = [[], [['100', 2, False]], [['100', 2, True]]]
        banco = BancoSisplan(self.arquivo)
        self.assertEqual(
            banco.confirmar_gravacao('2026-12345', '100', intervalo=0),
            PedidoExistente('100', 2),
        )
        self.assertEqual(consultar.call_count, 3)
        self.assertIn('i.id_ped = p.id', consultar.call_args.args[0])

    @patch('src.banco.BancoSisplan._consultar')
    def test_confirmacao_rejeita_divergencia_duplicidade_e_falta_de_itens(self, consultar: MagicMock) -> None:
        banco = BancoSisplan(self.arquivo)
        for linhas in ([], [['100', 2, False]], [['101', 2, True]], [['100', 2, True], ['100', 1, True]]):
            with self.subTest(linhas=linhas):
                consultar.return_value = linhas
                with self.assertRaises(GravacaoNaoConfirmadaError):
                    banco.confirmar_gravacao('2026-12345', '100', timeout=0)

    @patch('src.banco.BancoSisplan._consultar', side_effect=BancoSisplanError('Rede'))
    def test_confirmacao_nao_trata_falha_de_banco_como_ausencia(self, consultar: MagicMock) -> None:
        with self.assertRaises(BancoSisplanError):
            BancoSisplan(self.arquivo).confirmar_gravacao('2026-12345', '100', timeout=0)

    def test_confirmacao_rejeita_numero_vazio(self) -> None:
        with self.assertRaises(GravacaoNaoConfirmadaError):
            BancoSisplan(self.arquivo).confirmar_gravacao('2026-12345', '', timeout=0)

    @patch('src.banco.connect')
    def test_conexao_quebrada_e_fechada_e_reconexao_explicita_abre_outra(self, conectar: MagicMock) -> None:
        quebrada, nova = MagicMock(), MagicMock()
        quebrada.cursor.return_value.execute.side_effect = ConnectionResetError('Rede caiu')
        nova.cursor.return_value.fetchall.return_value = []
        conectar.side_effect = [quebrada, nova]
        with BancoSisplan(self.arquivo) as banco:
            with self.assertRaises(BancoSisplanError):
                banco.consultar_pedidos(['2026-12345'])
            quebrada.close.assert_called_once()
            self.assertEqual(conectar.call_count, 1)
            banco.reconectar()
            self.assertEqual(banco.consultar_pedidos(['2026-12345']), {})
        self.assertEqual(conectar.call_count, 2)
        nova.close.assert_called_once()

    @patch('src.banco.BancoSisplan._consultar')
    def test_confere_quantidades_agregadas_e_aguarda_importacao_completa(self, consultar: MagicMock) -> None:
        consultar.side_effect = [
            [['100', 2, True]], [['P1', 'C1', 'T1', Decimal(1)]],
            [['100', 2, True]], [['P1', 'C1', 'T1', Decimal('3.000000')]],
        ]
        itens = [ItemEsperado('P1', 'C1', 'T1', Decimal(1)), ItemEsperado('P1', 'C1', 'T1', Decimal(2))]
        resultado = BancoSisplan(self.arquivo).confirmar_gravacao('2026-12345', '100', intervalo=0, itens_esperados=itens)
        self.assertEqual(resultado.numero, '100')
        self.assertEqual(consultar.call_count, 4)
        sql, parametros = consultar.call_args.args
        self.assertIn('SUM(COALESCE(i.qtde, 0))', sql)
        self.assertEqual(parametros, ('00022', '2026-12345', '100'))

    @patch('src.banco.BancoSisplan._consultar')
    def test_item_ausente_excedente_ou_quantidade_diferente_bloqueia_confirmacao(self, consultar: MagicMock) -> None:
        itens = [ItemEsperado('P1', 'C1', 'T1', Decimal(3))]
        for gravados in ([], [['P1', 'C1', 'T1', Decimal(2)]],
                         [['P1', 'C1', 'T1', Decimal(3)], ['P2', 'C1', 'T1', Decimal(1)]],
                         [['P1', 'C2', 'T1', Decimal(3)]]):
            with self.subTest(gravados=gravados):
                consultar.side_effect = [[['100', 2, True]], gravados]
                with self.assertLogs('src.banco', level='ERROR') as logs:
                    with self.assertRaises(GravacaoNaoConfirmadaError):
                        BancoSisplan(self.arquivo).confirmar_gravacao('2026-12345', '100', timeout=0, itens_esperados=itens)
                self.assertIn('XML=', '\n'.join(logs.output))
                self.assertIn('Sisplan=', '\n'.join(logs.output))

    def test_lista_vazia_de_itens_esperados_nao_aprova_so_cabecalho(self) -> None:
        with self.assertRaises(GravacaoNaoConfirmadaError):
            BancoSisplan(self.arquivo).confirmar_gravacao('2026-12345', '100', itens_esperados=[])
