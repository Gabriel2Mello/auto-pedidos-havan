"""Central em processo isolado, com pedidos e configurações sintéticos."""
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import monotonic, sleep
import unittest
from unittest.mock import Mock, patch

import havan
import main
import sincronizar_estatisticas as sync
from contrato_estatisticas import ConfiguracaoCliente, serializar
from metricas_nunes import registrar_evento
from src.banco import PedidoExistente
from src.estado import EstadoPedidos
from src.servico_pedidos import registrar_inclusao

RAIZ = Path(__file__).resolve().parents[1]


class TestEstatisticasCentrais(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = Path(self.enterContext(TemporaryDirectory()))
        self.metricas = self.pasta / 'metricas'
        self.arquivo = self.pasta / 'cliente.json'
        self.enterContext(patch.dict(os.environ, {
            'NUNES_METRICAS_DADOS': str(self.metricas),
            'NUNES_CENTRAL_CONFIG': str(self.arquivo),
        }))
        self.processo: subprocess.Popen[bytes] | None = None
        self.addCleanup(self.fechar)
        self.abrir()

    def abrir(self) -> None:
        endereco = self.pasta / 'porta.txt'
        endereco.unlink(missing_ok=True)
        script = (
            'import sys;from pathlib import Path;'
            'sys.path.insert(0,sys.argv[1]);from central import Armazem,Servidor;'
            'p=Path(sys.argv[2]);'
            's=Servidor(Armazem(p/"central.sqlite3","c"*32),"token_sintetico_"*3,0);'
            '(p/"porta.tmp").write_text(str(s.server_port));'
            '(p/"porta.tmp").replace(p/"porta.txt");s.serve_forever(poll_interval=.01)'
        )
        self.processo = subprocess.Popen(
            [sys.executable, '-I', '-c', script, str(RAIZ.parent / 'nunes-estatisticas'), str(self.pasta)],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        limite = monotonic() + 10
        while True:
            try:
                porta = endereco.read_text()
            except (FileNotFoundError, PermissionError):
                porta = ''  # O Windows pode bloquear brevemente o arquivo temporário recém-publicado.
            if porta:
                break
            if self.processo.poll() is not None or monotonic() >= limite:
                self.fail('A central sintética não iniciou.')
            sleep(.02)
        self.config: ConfiguracaoCliente = {
            'protocolo': 1, 'central_id': 'c' * 32, 'token': 'token_sintetico_' * 3,
            'url': 'http://127.0.0.1:' + porta,
        }
        self.arquivo.write_text(serializar(self.config), encoding='utf-8')

    def fechar(self) -> None:
        if self.processo is not None:
            if self.processo.poll() is None:
                self.processo.terminate()  # Somente o processo sintético deste teste.
            self.processo.communicate(timeout=5)
            self.processo = None

    def cliente(self) -> sync.Cliente:
        return sync.Cliente(self.config, self.metricas, aplicacao='pedidos-havan')

    def resumo(self) -> dict[str, object]:
        return sync.requisitar(self.config, '/v1/resumo?aplicacao=pedidos-havan')

    def registrar(self) -> None:
        registrar_inclusao('2026-12345', PedidoExistente('100', 1))
        self.assertTrue(registrar_evento('pedido_existente', 'lote1:existente', '2026-12345'))
        self.assertTrue(registrar_evento('pedido_falhou', 'lote1:falha', '2026-12346'))

    def test_historico_tres_indicadores_e_reenvio_sem_duplicacao(self) -> None:
        self.registrar(); self.registrar()
        self.assertTrue(registrar_evento('arquivo_transferido', 'arquivo-sintetico', '1234', tipo='busca_pdf'))
        self.assertEqual(self.cliente().sincronizar()['confirmados_neste_ciclo'], 3)
        self.assertEqual(self.resumo()['tipos'], {'pedido_inserido': 1, 'pedido_existente': 1, 'pedido_falhou': 1})
        self.assertEqual(self.cliente().sincronizar()['confirmados_neste_ciclo'], 0)
        self.assertEqual(len(sync.Cliente(self.config, self.metricas).pendentes()), 1)

    def test_novo_lote_conta_ocorrencias_sem_aumentar_inseridos(self) -> None:
        self.registrar(); self.cliente().sincronizar()
        registrar_inclusao('2026-12345', PedidoExistente('100', 1))
        self.assertTrue(registrar_evento('pedido_existente', 'lote2:existente', '2026-12345'))
        self.assertTrue(registrar_evento('pedido_falhou', 'lote2:falha', '2026-12346'))
        self.assertEqual(self.cliente().sincronizar()['confirmados_neste_ciclo'], 2)
        self.assertEqual(self.resumo()['tipos'], {'pedido_inserido': 1, 'pedido_existente': 2, 'pedido_falhou': 2})

    def test_desligamento_retorno_e_reinicio_conservam_pendencias_e_totais(self) -> None:
        self.registrar(); self.fechar()
        with self.assertRaises(OSError):
            self.cliente().sincronizar()
        self.assertEqual(len(self.cliente().pendentes()), 3)
        self.abrir()
        with sync.Sincronizador(aplicacao='pedidos-havan', relatar=lambda _: None):
            pass
        self.assertEqual(self.resumo()['total'], 3)
        self.fechar(); self.abrir()
        self.assertEqual(self.cliente().sincronizar()['pendentes'], 0)
        self.assertEqual(self.resumo()['total'], 3)

    def test_resposta_perdida_apos_commit_reenvia_sem_duplicar(self) -> None:
        self.registrar()
        original = sync.requisitar
        def perder(config: ConfiguracaoCliente, caminho: str, dados: object = None) -> dict[str, object]:
            resposta = original(config, caminho, dados)
            if dados is not None:
                raise OSError('resposta sintética perdida')
            return resposta
        with patch.object(sync, 'requisitar', side_effect=perder), self.assertRaises(OSError):
            self.cliente().sincronizar()
        self.assertEqual(self.resumo()['total'], 3)
        self.assertEqual(len(self.cliente().pendentes()), 3)
        self.assertEqual(self.cliente().sincronizar()['pendentes'], 0)
        self.assertEqual(self.resumo()['total'], 3)

    def test_fila_mista_conserva_instante_original_e_arquivos(self) -> None:
        with patch('metricas_nunes._abrir', side_effect=sqlite3.OperationalError('sintetico')), self.assertLogs(level='WARNING'):
            self.registrar()
            self.assertTrue(registrar_evento('documento_baixado', 'cofre-sintetico', '123', empresa='MATRIZ', tipo='nfe'))
        arquivos = {p: p.read_bytes() for p in (self.metricas / 'recuperar').glob('*.json')}
        self.assertEqual(self.cliente().sincronizar()['confirmados_neste_ciclo'], 3)
        self.assertEqual({p: p.read_bytes() for p in arquivos}, arquivos)
        esperados = {json.loads(conteudo)['id']: json.loads(conteudo)['ocorrido_em']
                     for conteudo in arquivos.values() if json.loads(conteudo)['evento'].startswith('pedido_')}
        with closing(sqlite3.connect(self.pasta / 'central.sqlite3')) as banco:
            salvos = [json.loads(linha[0]) for linha in banco.execute('SELECT payload FROM eventos')]
        self.assertEqual({r['id']: r['ocorrido_em'] for r in salvos}, esperados)

    def test_web_e_console_sincronizam_sem_executar_negocio(self) -> None:
        servidor = Mock()
        servidor.serve_forever.side_effect = self.registrar
        with patch('src.logs.setup_logging', return_value='execucao-sintetica'), \
                patch('src.windows.set_app_id'), patch('src.controlador.EstadoInterface'), \
                patch('src.interface_web.criar_servidor', return_value=(servidor, 'local')):
            self.assertEqual(havan.main(Mock()), 0)
        self.assertEqual(self.resumo()['total'], 3)
        def escolher(_historico: EstadoPedidos) -> None:
            registrar_inclusao('2026-12347', PedidoExistente('101', 2))
            return None
        with patch.object(sys, 'argv', ['main.py']), patch('main.setup_logging'), \
                patch('main.set_app_id'), patch('main.EstadoPedidos', side_effect=lambda: EstadoPedidos(self.pasta / 'estado.sqlite3')), \
                patch('main.escolher_operacao', side_effect=escolher):
            self.assertEqual(main.main(), 0)
        self.assertEqual(self.resumo()['total'], 4)

    def test_cliente_individual_sem_repositorios_irmaos(self) -> None:
        self.registrar()
        destino = self.pasta / 'individual'; destino.mkdir()
        for nome in ('contrato_estatisticas.py', 'sincronizar_estatisticas.py', 'metricas_nunes.py'):
            shutil.copy2(RAIZ / nome, destino / nome)
        script = ('import sys;sys.path.insert(0,sys.argv[1]);'
                  'import sincronizar_estatisticas as s;'
                  'c=s.ler_configuracao();assert c is not None;'
                  'assert s.Cliente(c,aplicacao="pedidos-havan").sincronizar()["pendentes"]==0')
        resultado = subprocess.run([sys.executable, '-I', '-c', script, str(destino)],
                                  cwd=destino, capture_output=True, timeout=10)
        self.assertEqual(resultado.returncode, 0, resultado.stderr.decode(errors='replace'))
        self.assertEqual(self.resumo()['total'], 3)

    def test_sem_vinculo_nao_cria_worker_nem_requisicao(self) -> None:
        with patch.dict(os.environ, {'NUNES_CENTRAL_CONFIG': ''}), \
                patch.object(sync, '__file__', str(self.pasta / 'sincronizar_estatisticas.py')), \
                patch.object(sync, 'requisitar') as pedir:
            with sync.Sincronizador(aplicacao='pedidos-havan') as worker:
                self.assertIsNone(worker.worker)
            pedir.assert_not_called()


if __name__ == '__main__':
    unittest.main()
