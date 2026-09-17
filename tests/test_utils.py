import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.utils import (
    MAX_CARACTERES_MOTIVO,
    formatar_motivo_erro,
    salvar_pedido_txt,
)


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

    def test_combina_mensagem_amigavel_com_detalhe_tecnico(self) -> None:
        motivo = formatar_motivo_erro(
            'Falha na tela do Sisplan',
            RuntimeError("{'title_re': '.*VenPedidoGrade.*'}"),
        )

        self.assertEqual(
            motivo,
            "Falha na tela do Sisplan, {'title_re': '.*VenPedidoGrade.*'}",
        )

    def test_limita_motivo_extenso_e_mantem_em_uma_linha(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            with patch('src.utils.obter_diretorio_executavel', return_value=Path(pasta)):
                salvar_pedido_txt(
                    '2026-45404',
                    motivo=f"detalhe\n{'x' * 600}",
                )

            conteudo = (Path(pasta) / 'pedidos_com_erro.txt').read_text(
                encoding='utf-8'
            )

        motivo_salvo = conteudo.rstrip('\n').split(', ', maxsplit=1)[1]
        self.assertEqual(len(motivo_salvo), MAX_CARACTERES_MOTIVO)
        self.assertNotIn('\n', motivo_salvo)
        self.assertTrue(motivo_salvo.endswith('...'))


if __name__ == '__main__':
    unittest.main()
