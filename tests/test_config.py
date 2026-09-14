import tempfile
import unittest
from pathlib import Path

from src.config import Configuracao, ConfiguracaoError


class ConfiguracaoTests(unittest.TestCase):
    def test_carrega_operacao_do_toml_e_segredos_do_ambiente(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            unrar = raiz / 'UnRAR.exe'
            sumatra = raiz / 'SumatraPDF.exe'
            unrar.touch()
            sumatra.touch()
            arquivo = raiz / 'config.toml'
            arquivo.write_text(
                f"unrar_tool = '{unrar}'\n"
                f"sumatra = '{sumatra}'\n"
                f"pasta_pedidos = '{raiz / 'pedidos'}'\n"
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
            'CNPJ_MATRIZ',
            'SENHA_PORTAL',
        ):
            self.assertIn(configuracao, mensagem)


if __name__ == '__main__':
    unittest.main()
