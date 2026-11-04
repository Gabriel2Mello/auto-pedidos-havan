import unittest

from src.mensagens import mensagem_observacao


class MensagemObservacaoTests(unittest.TestCase):
    def test_padroniza_mensagens_atuais_e_do_historico(self) -> None:
        exemplos = (
            ('Não consegui baixar os arquivos do pedido 2026-037398. Verifique o portal ou a conexão.',
             'Não foi possível baixar os arquivos do pedido. Verifique o portal'),
            ('Não consegui validar o XML do pedido 2026-037398: XML sem itens de compra',
             'Não foi possível validar o XML do pedido: XML sem itens de compra'),
            ('Não encontrei uma gravação única desse pedido no Sisplan para reimprimir.',
             'Não foi encontrada uma gravação única no Sisplan para reimprimir.'),
            ('Os arquivos salvos do pedido 2026-037398 estão ausentes ou inválidos. Use Baixar e conferir para obtê-los novamente.',
             'Os arquivos salvos do pedido estão ausentes ou inválidos. Use Baixar e conferir para obtê-los novamente.'),
            ('Os arquivos do pedido 2026-037398 estão incompletos ou inválidos. Avise o responsável.',
             'Os arquivos do pedido estão incompletos ou inválidos. Avise o responsável.'),
            ('A impressão do pedido 2026-037398 não foi concluída com segurança. Confira a impressora.',
             'Impressão não confirmada. Confira a fila de impressão com o responsável.'),
            ('Pedido 2026-037398: número interno divergente ou cadastro duplicado. Confira o Sisplan antes de continuar.',
             'Número interno divergente ou cadastro duplicado. Confira o Sisplan antes de continuar.'),
            ('Pedido 2026-037398: não há uma correspondência única confirmada no banco.',
             'Não há uma correspondência única confirmada no banco.'),
            ('Pedido 2026-037398: a inclusão anterior não foi confirmada.',
             'A inclusão anterior não foi confirmada.'),
            ('Pedido 2026-037398: o Sisplan gerou número interno suspeito nas duas tentativas.',
             'O Sisplan gerou número interno suspeito nas duas tentativas.'),
            ('Gravação do pedido 2026-037398 / interno 11250 não confirmada com seus itens e quantidades.',
             'Gravação do pedido não confirmada com seus itens e quantidades.'),
            ('Não consegui validar o XML do pedido 2026-037398: Número do XML (2026-999999) difere do pedido 2026-037398',
             'Não foi possível validar o XML do pedido: Número do XML (2026-999999) difere do pedido'),
            ('O pedido 2026-037398 não existe no Portal Havan.',
             'Pedido não encontrado no Portal Havan.'),
        )
        for original, esperado in exemplos:
            with self.subTest(original=original):
                self.assertEqual(mensagem_observacao(original, '2026-037398'), esperado)
                self.assertEqual(mensagem_observacao(esperado, '2026-037398'), esperado)

    def test_preserva_contexto_necessario_e_textos_sem_alteracao(self) -> None:
        exemplos = (
            '',
            'Pedido não encontrado no Portal Havan.',
            'Pedido encontrado, mas link para download ausente. Verifique o portal',
            'A sessão do Portal Havan expirou. Reconecte para continuar ou pare o processamento.',
            'Existe uma inclusão anterior que precisa ser conferida pelo responsável: 2026-999999',
            'Número interno \'1\' fora da faixa: referência 11250, tolerância de 100 números.',
            'Download com recuperação pendente em C:\\Pedidos\\2026-037398. Confira os arquivos.',
            'Falha do pedido 2026-0373980.',
            'Falha do pedido 2026-037398-outro.',
            'Falha do pedido 2026-999999.',
        )
        for original in exemplos:
            with self.subTest(original=original):
                self.assertEqual(mensagem_observacao(original, '2026-037398'), original)

    def test_reduz_cadastro_real_e_demonstracao_inclusive_do_historico(self) -> None:
        exemplos = (
            ('EAN 0123456789012 (Produto sintético / Azul) sem cadastro. '
             'Use Conferir cadastro novamente após corrigir.',
             'EAN 0123456789012 (Produto sintético / Azul) sem cadastro. Confira novamente.'),
            ('Código de barras não cadastrado: 0123456789012 (Produto / Azul). Pedido salvo. '
             'Após cadastrar os produtos, use Conferir cadastro novamente e depois Importe os pedidos aptos.',
             'EAN 0123456789012 (Produto / Azul) sem cadastro. Confira novamente.'),
            ('O Sisplan encontrou produto sem cadastro. Pedido salvo. Após cadastrar os produtos, '
             'use Conferir cadastro novamente e depois Importe os pedidos aptos.',
             'Produto sem cadastro no Sisplan. Confira novamente.'),
            ('Demonstração: produto sem cadastro. Use Conferir cadastro novamente para simular o cadastro corrigido.',
             'Demonstração: produto sem cadastro. Confira novamente.'),
            ('Código de barras não cadastrado: 0123456789012 (Produto / Azul). Pedido salvo.',
             'EAN 0123456789012 (Produto / Azul) sem cadastro. Pedido salvo.'),
        )
        for original, esperado in exemplos:
            with self.subTest(original=original):
                self.assertEqual(mensagem_observacao(original, '2026-037398'), esperado)
                self.assertEqual(mensagem_observacao(esperado, '2026-037398'), esperado)

    def test_preserva_todos_os_produtos_e_distingue_cadastro_ambiguo(self) -> None:
        original = (
            'Código de barras não cadastrado: 0123456789012 (Produto A (kit) / Azul); '
            'Código de barras não cadastrado: 1234567890123 (Produto B / Verde); '
            'Código de barras com cadastro ambíguo: 2345678901234 (Produto C / Branco). '
            'Pedido salvo. Após cadastrar os produtos, '
            'use Conferir cadastro novamente e depois Importe os pedidos aptos.'
        )
        esperado = (
            'EAN 0123456789012 (Produto A (kit) / Azul) sem cadastro; '
            'EAN 1234567890123 (Produto B / Verde) sem cadastro; '
            'Código de barras com cadastro ambíguo: 2345678901234 (Produto C / Branco). Confira novamente.'
        )
        self.assertEqual(mensagem_observacao(original, '2026-037398'), esperado)

    def test_reduz_impressao_sem_perder_alerta_de_outra_copia(self) -> None:
        original = ('A impressão do pedido 2026-037398 não foi concluída com segurança. '
                    'Confira a impressora. O pedido está salvo para retomar ou reimprimir.')
        esperado = 'Impressão não confirmada. Confira a fila de impressão com o responsável.'
        self.assertEqual(mensagem_observacao(original, '2026-037398'), esperado)
        self.assertEqual(mensagem_observacao(esperado, '2026-037398'), esperado)
        especifico = original + ' A fila não respondeu; avise o responsável.'
        self.assertIn('A fila não respondeu; avise o responsável.',
                      mensagem_observacao(especifico, '2026-037398'))
