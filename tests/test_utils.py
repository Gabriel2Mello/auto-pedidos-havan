import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.utils import salvar_pedido_txt


class SalvarPedidoTxtTests(unittest.TestCase):
    def test_salva_pedido_com_motivo_na_mesma_linha(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            with patch('src.utils.obter_diretorio_executavel', return_value=Path(pasta)):
                salvar_pedido_txt(
                    '2026-45404',
                    motivo='produto sem\ncadastro',
                )

            conteudo = (Path(pasta) / 'pedidos_com_erro.txt').read_text(
                encoding='utf-8'
            )

        self.assertRegex(
            conteudo,
            r'^\[\d{2}/\d{2}/\d{4} \d{2}:\d{2}\] '
            r'2026-45404, produto sem cadastro\n$',
        )

    def test_mantem_formato_promocional_sem_motivo(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            with patch('src.utils.obter_diretorio_executavel', return_value=Path(pasta)):
                salvar_pedido_txt('2026-45404', promocional=True)

            conteudo = (Path(pasta) / 'PROMOCIONAL.txt').read_text(
                encoding='utf-8'
            )

        self.assertRegex(
            conteudo,
            r'^\[\d{2}/\d{2}/\d{4} \d{2}:\d{2}\] 2026-45404\n$',
        )


if __name__ == '__main__':
    unittest.main()
