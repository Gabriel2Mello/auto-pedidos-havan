"""Inicialização do histórico e diagnóstico sem consultar pedidos ou Sisplan."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import havan
from integracao_hub import MedidorAbertura
from src.controlador import EstadoInterface


class TestAbertura(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(patch.dict(os.environ, {'NUNES_HUB_DADOS': str(self.pasta)}))
        self.enterContext(patch('sincronizar_estatisticas.ler_configuracao', return_value=None))

    def etapas(self) -> list[dict[str, object]]:
        return [json.loads(linha) for linha in
                (self.pasta / 'logs/pedidos-havan-abertura.log').read_text(encoding='utf-8').splitlines()]

    def test_historico_pronto_e_distinto_de_criar_worker(self) -> None:
        medidor = MedidorAbertura('pedidos-havan')
        executor = Mock()
        estado = EstadoInterface(self.pasta / 'historico.sqlite3', executor=executor, medidor_abertura=medidor)
        try:
            self.assertTrue(estado.pronto.wait(3))
            self.assertEqual(estado.fase, 'PRONTO')
            self.assertEqual([linha['etapa'] for linha in self.etapas()], ['historico_iniciado', 'historico_pronto'])
            executor.assert_not_called()
        finally:
            estado.encerrar()
            estado.worker.join(3)
            self.assertFalse(estado.worker.is_alive())

    def test_falha_de_publicacao_preserva_fechamento_e_identifica_etapa(self) -> None:
        servidor, estado, publicacao = Mock(), Mock(), Mock()
        publicacao.publicar.side_effect = OSError('falha-sintetica-privada')
        with patch('src.logs.setup_logging', return_value='sintetica'), patch('src.windows.set_app_id'), \
                patch('src.controlador.EstadoInterface', return_value=estado), \
                patch('src.interface_web.criar_servidor', return_value=(servidor, 'local')), \
                patch('havan.informar_falha'), self.assertLogs('havan', level='ERROR'):
            self.assertEqual(havan.main(publicacao), 1)
        falha = next(linha for linha in self.etapas() if linha['situacao'] == 'falhou')
        self.assertEqual((falha['etapa'], falha['erro']), ('publicacao', 'OSError'))
        self.assertNotIn('falha-sintetica-privada', json.dumps(self.etapas()))
        estado.encerrar.assert_called_once()
        estado.worker.join.assert_called_once()
        servidor.server_close.assert_called_once()
