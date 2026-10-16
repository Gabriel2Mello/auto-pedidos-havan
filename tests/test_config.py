import tempfile
import unittest
from pathlib import Path

from src.config import Configuracao, ConfiguracaoError


class ConfiguracaoTests(unittest.TestCase):
    def test_tolerancia_numero_interno_tem_padrao_e_pode_ser_configurada(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / 'config.toml'
            arquivo.write_text('', encoding='utf-8')
            self.assertEqual(Configuracao.carregar(arquivo, {}).tolerancia_numero_interno, 100)
            arquivo.write_text('tolerancia_numero_interno = 25\n', encoding='utf-8')
            config = Configuracao.carregar(arquivo, {})
            self.assertEqual(config.tolerancia_numero_interno, 25)
            self.assertEqual(config.erro_leitura, '')

    def test_tolerancia_invalida_nao_desativa_protecao(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / 'config.toml'
            for valor in ('0', '-1', 'true', '1.5', '"100"'):
                with self.subTest(valor=valor):
                    arquivo.write_text(f'tolerancia_numero_interno = {valor}\n', encoding='utf-8')
                    config = Configuracao.carregar(arquivo, {})
                    with self.assertRaisesRegex(ConfiguracaoError, 'tolerancia_numero_interno'):
                        config.validar()

    def test_carrega_operacao_do_toml_e_segredos_do_ambiente(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            unrar = raiz / 'UnRAR.exe'
            sumatra = raiz / 'SumatraPDF.exe'
            banco = raiz / 'banco-sisplan.json'
            unrar.touch()
            sumatra.touch()
            banco.touch()
            arquivo = raiz / 'config.toml'
            arquivo.write_text(
                f"unrar_tool = '{unrar}'\n"
                f"sumatra = '{sumatra}'\n"
                f"pasta_pedidos = '{raiz / 'pedidos'}'\n"
                f"banco_config = '{banco}'\n"
                'impressora = "Impressora do estoque"\n',
                encoding='utf-8',
            )

            config = Configuracao.carregar(
                arquivo,
                {
                    'CNPJ_MATRIZ': '00000000000100',
                    'SENHA_PORTAL': 'segredo',
                    'TEAMS_WEBHOOK_URL': 'https://teams.example/webhook',
                },
            )
            config.validar()

        self.assertEqual(config.unrar_tool, unrar)
        self.assertEqual(config.sumatra, sumatra)
        self.assertEqual(config.impressora, 'Impressora do estoque')
        self.assertEqual(config.cnpj_matriz, '00000000000100')
        self.assertEqual(config.senha_portal, 'segredo')
        self.assertEqual(config.banco_config, banco)
        self.assertEqual(config.banco_perfil, 'principal')

    def test_informa_todas_as_configuracoes_ausentes(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            config = Configuracao.carregar(raiz / 'config.toml', {})

            modelo = raiz / 'config.example.toml'
            self.assertTrue(modelo.is_file())
            self.assertIn(
                "unrar_tool = 'C:\\Program Files\\WinRAR\\UnRAR.exe'",
                modelo.read_text(encoding='utf-8'),
            )

        with self.assertRaises(ConfiguracaoError) as contexto:
            config.validar()

        mensagem = str(contexto.exception)
        for configuracao in (
            'Arquivo de configuração não encontrado',
            'unrar_tool',
            'sumatra',
            'pasta_pedidos',
            'impressora',
            'banco_config',
            'CNPJ_MATRIZ',
            'SENHA_PORTAL',
        ):
            self.assertIn(configuracao, mensagem)

    def test_resolve_caminho_relativo_ao_toml_e_seleciona_perfil(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            arquivo = raiz / 'config.toml'
            arquivo.write_text(
                "banco_config = 'privado/banco.json'\nbanco_perfil = 'leitura'\n",
                encoding='utf-8',
            )
            config = Configuracao.carregar(arquivo, {})
            self.assertEqual(config.banco_config, raiz / 'privado' / 'banco.json')
            self.assertEqual(config.banco_perfil, 'leitura')

    def test_retomada_de_impressao_nao_depende_de_portal_ou_unrar(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            sumatra = raiz / 'Sumatra.exe'
            banco = raiz / 'banco.json'
            sumatra.touch()
            banco.touch()
            config = Configuracao(
                unrar_tool=raiz / 'ausente.exe', sumatra=sumatra, pasta_pedidos=raiz,
                impressora='Impressora de teste', cnpj_matriz='', senha_portal='', banco_config=banco,
            )
            config.validar(apenas_impressao=True)
            with self.assertRaises(ConfiguracaoError):
                config.validar()


if __name__ == '__main__':
    unittest.main()
