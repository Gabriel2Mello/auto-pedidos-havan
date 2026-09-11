import unittest
from pathlib import Path
from unittest.mock import patch

from src import config


class ValidarConfiguracaoTests(unittest.TestCase):
    def test_informa_todas_as_configuracoes_ausentes(self) -> None:
        valores_invalidos = {
            '_unrar_raw': '',
            '_sumatra_raw': '',
            '_base_path_raw': '',
            'UNRAR_TOOL': Path(),
            'SUMATRA': Path(),
            'CNPJ_MATRIZ': '',
            'SENHA_PORTAL': '',
            'IMPRESSORA': '',
        }

        with patch.multiple(config, **valores_invalidos):
            with self.assertRaises(config.ConfiguracaoError) as contexto:
                config.validar_configuracao()

        mensagem = str(contexto.exception)
        for variavel in (
            'UNRAR_TOOL',
            'SUMATRA',
            'HAVAN_PEDIDOS',
            'CNPJ_MATRIZ',
            'SENHA_PORTAL',
            'IMPRESSORA_PEDIDO',
        ):
            self.assertIn(variavel, mensagem)


if __name__ == '__main__':
    unittest.main()
