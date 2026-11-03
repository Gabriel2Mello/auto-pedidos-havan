import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import unittest
from unittest.mock import patch

from dataclasses import replace
from src.config import CONFIG, Configuracao, configuracao_atual, usar_configuracao
from src.controlador import EstadoInterface, executar_fluxo
from src.resumo import ResumoExecucao
from src.impressoras import caminho_preferencia, ler_impressora, salvar_impressora
from tests import test_interface_web as interface


class PreferenciaTests(unittest.TestCase):
    def setUp(self):
        pasta = TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.raiz = Path(pasta.name)
        ambiente = patch.dict(os.environ, {'HAVAN_IMPRESSORA_DADOS': pasta.name})
        ambiente.start()
        self.addCleanup(ambiente.stop)

    def test_preferencia_prevalece_sobre_toml_sem_alterar_arquivo(self):
        arquivo = self.raiz / 'config.toml'
        arquivo.write_text('impressora = "Fila do TOML"\n', encoding='utf-8')
        self.assertEqual(Configuracao.carregar(arquivo).impressora, 'Fila do TOML')
        salvar_impressora('Fila de teste \\ servidor ç')
        self.assertEqual(Configuracao.carregar(arquivo).impressora, 'Fila de teste \\ servidor ç')
        self.assertEqual(arquivo.read_text(encoding='utf-8'), 'impressora = "Fila do TOML"\n')
        self.assertEqual(list(self.raiz.glob('*.tmp')), [])

    def test_preferencia_corrompida_nao_troca_silenciosamente_destino(self):
        for conteudo in ('{', '[]', '{}', '{"impressora":42}', '{"impressora":""}'):
            caminho_preferencia().write_text(conteudo, encoding='utf-8')
            with self.subTest(conteudo=conteudo), self.assertRaises(ValueError):
                ler_impressora('outra fila')
        salvar_impressora('Fila corrigida')
        self.assertEqual(ler_impressora('outra fila'), 'Fila corrigida')

    def test_falha_ao_gravar_preserva_preferencia_anterior(self):
        salvar_impressora('Anterior')
        with patch('src.impressoras.os.replace', side_effect=OSError('falha sintética')):
            with self.assertRaisesRegex(ValueError, 'salvar a impressora'):
                salvar_impressora('Nova')
        self.assertEqual(ler_impressora(''), 'Anterior')
        self.assertEqual(list(self.raiz.glob('*.tmp')), [])

    def test_adaptador_passa_configuracao_congelada_ao_servico(self):
        config = replace(CONFIG, impressora='Fila do lote')
        with usar_configuracao(config), patch('src.servico_pedidos.processar_pedidos') as processar:
            executar_fluxo([], 'reimprimir', historico=None,
                           ao_erro=lambda *args: 'encerrar',
                           ao_progresso=lambda *args: None, parar=lambda: False)
        self.assertIs(processar.call_args.kwargs['contexto'].configuracao, config)

    def test_executor_padrao_rele_configuracao_ao_aceitar_lote(self):
        config = replace(CONFIG, impressora='Fila atualizada no TOML')
        executado = Event()
        def concluir(*args, **kwargs):
            executado.set()
            return ResumoExecucao({})
        estado = EstadoInterface(self.raiz / 'estado.sqlite3', impressora='Fila anterior')
        try:
            self.assertTrue(estado.pronto.wait(3))
            dados = {'modo':'preparar', 'pedidos':'12345', 'solicitacao':'config-atualizada'}
            dados['conferencia'] = estado.conferir(dados)['id']
            with patch('src.controlador.Configuracao.carregar', return_value=config) as carregar, \
                    patch('src.servico_pedidos.processar_pedidos', side_effect=concluir) as processar:
                estado.iniciar(dados)
                self.assertTrue(executado.wait(3))
                estado.encerrar()
                estado.worker.join(3)
                self.assertFalse(estado.worker.is_alive())
                carregar.assert_called_once_with()
                self.assertEqual(processar.call_args.kwargs['contexto'].configuracao.impressora,
                                 'Fila atualizada no TOML')
        finally:
            estado.encerrar()
            estado.worker.join(3)


class ImpressoraHTTPTests(interface.BaseInterface):
    # Reutiliza o servidor autenticado e executor sintético dos testes da interface.
    requisitar = interface.ApiTests.requisitar
    requisitar_recusa = interface.ApiTests.requisitar_recusa
    fechar_http = interface.ApiTests.fechar_http

    def setUp(self):
        super().setUp()
        self.servidor, self.token = interface.criar_servidor(self.estado)
        self.http = Thread(target=self.servidor.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
        self.http.start()
        self.addCleanup(self.fechar_http)
        self.estado.impressora = 'Fila A'
        self.estado.listar_filas = lambda: ['Fila A', 'Fila B']
        self.salvas = []
        self.estado.salvar_fila = self.salvas.append

    def test_listar_e_selecionar_exigem_autenticacao_e_fila_instalada(self):
        self.assertEqual(self.requisitar('/api/impressoras', token=False)[0], 403)
        self.requisitar_recusa('/api/impressora', {'impressora':'Fila B'}, token=False, status_esperado=403)
        self.requisitar_recusa('/api/impressora', {'impressora':'Fila B'}, origem='https://outro.example', status_esperado=403)
        self.assertEqual(self.requisitar('/api/impressora', {'impressora':'inexistente'})[0], 400)
        self.assertEqual(self.salvas, [])
        resposta = json.loads(self.requisitar('/api/impressoras')[2])
        self.assertEqual(resposta['impressoras'], ['Fila A', 'Fila B'])
        self.assertEqual(self.requisitar('/api/impressora', {'impressora':'Fila B'})[0], 200)
        self.assertEqual(self.salvas, ['Fila B'])
        self.assertEqual(self.estado.situacao()['impressora'], 'Fila B')
        self.assertEqual(self.chamadas, [])

    def test_fila_ausente_e_falha_de_listagem_exibem_aviso(self):
        self.estado.listar_filas = lambda: []
        self.assertIn('não está instalada', self.estado.listar_impressoras()['aviso_impressora'])
        self.estado.impressora = ''
        self.assertIn('Nenhuma impressora', self.estado.listar_impressoras()['aviso_impressora'])
        def falhar():
            raise RuntimeError('Serviço de impressão indisponível')
        self.estado.listar_filas = falhar
        self.assertIn('indisponível', self.estado.listar_impressoras()['aviso_impressora'])

    def test_troca_invalida_conferencia_e_lote_mantem_impressora(self):
        dados = {'modo':'reimprimir', 'pedidos':'12345', 'solicitacao':'teste-fila',
                 'confirmado':True, 'impressora':'Fila A'}
        dados['conferencia'] = self.estado.conferir(dados)['id']
        self.estado.selecionar_impressora('Fila B')
        self.assertEqual(self.requisitar('/api/iniciar', dados)[0], 409)
        dados['conferencia'] = self.estado.conferir(dados)['id']
        self.assertEqual(self.requisitar('/api/iniciar', dados)[0], 409)
        dados['impressora'] = 'Fila B'
        selecionadas = []
        def executar(*args, **kwargs):
            selecionadas.append(configuracao_atual().impressora)
            self.executado.set()
            self.liberar.wait(3)
            selecionadas.append(configuracao_atual().impressora)
            return super(ImpressoraHTTPTests, self).executar(*args, **kwargs)
        self.executor = executar
        self.assertEqual(self.requisitar('/api/iniciar', dados)[0], 200)
        self.assertTrue(self.executado.wait(2))
        self.assertEqual(self.requisitar('/api/impressora', {'impressora':'Fila A'})[0], 409)
        self.liberar.set()
        self.aguardar(lambda: self.estado.fase == 'CONCLUIDO')
        self.assertEqual(selecionadas, ['Fila B', 'Fila B'])

    def test_falha_salvar_nao_altera_selecao(self):
        def falhar(nome):
            raise ValueError('Falha sintética ao salvar')
        self.estado.salvar_fila = falhar
        self.assertEqual(self.requisitar('/api/impressora', {'impressora':'Fila B'})[0], 400)
        self.assertEqual(self.estado.impressora, 'Fila A')
