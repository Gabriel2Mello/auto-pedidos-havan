"""A API só autoriza uma importação explícita de aptos conferidos."""
from dataclasses import replace
from tests.test_interface_web import BaseInterface
from src.controlador import EstadoInterface, ConflitoInterface
from src.estado import EstadoPedido, EstadoPedidos
from src.config import CONFIG

class ContratoEtapasTests(BaseInterface):
    def semear(self, *registros):
        self.estado.encerrar(); self.estado.worker.join(3)
        with EstadoPedidos(self.caminho) as h:
            for registro in registros: h.salvar(registro)
        self.estado=EstadoInterface(self.caminho,executor=self.despachar)
        self.assertTrue(self.estado.pronto.wait(3))

    def test_importacao_recusa_nao_conferidos_sem_cadastro_e_mistura_com_aptos(self):
        self.semear(EstadoPedido('2026-12345','','pronto_importar'),EstadoPedido('2026-67890','','sem_cadastro'))
        for entrada in ('99999','67890','12345,67890'):
            with self.subTest(entrada=entrada), self.assertRaises(ConflitoInterface):
                self.estado.conferir({'modo':'importar','pedidos':entrada})
        self.assertEqual(self.chamadas,[])
        self.iniciar(modo='importar',pedidos='12345')
        self.aguardar(lambda:self.estado.fase=='CONCLUIDO')
        self.assertEqual(self.chamadas[0][0],(['2026-12345'],'importar'))

    def test_importacao_recusa_conferencia_de_preparo_e_confirmacao_antiga(self):
        self.semear(EstadoPedido('2026-12345','','pronto_importar'))
        c=self.estado.conferir({'modo':'preparar','pedidos':'12345'})
        with self.assertRaises(ConflitoInterface):
            self.estado.iniciar({'modo':'importar','pedidos':'12345','conferencia':c['id'],'solicitacao':'x'})
        c=self.estado.conferir({'modo':'importar','pedidos':'12345'})
        with self.estado.trava: self.estado.revisao+=1
        with self.assertRaises(ConflitoInterface):
            self.estado.iniciar({'modo':'importar','pedidos':'12345','conferencia':c['id'],'solicitacao':'y'})
        self.assertEqual(self.chamadas,[])

    def test_aptos_persistidos_sao_reconhecidos_e_incerta_bloqueia_nova_inclusao(self):
        self.semear(EstadoPedido('2026-12345','','pronto_importar'),EstadoPedido('2026-67890','','gravacao_pendente'))
        self.assertEqual(next(p for p in self.estado.situacao()['pedidos'] if p['pedido']=='2026-12345')['rotulo'],'Pronto para importar')
        with self.assertRaises(ConflitoInterface): self.estado.conferir({'modo':'importar','pedidos':'12345'})
        c=self.estado.conferir({'modo':'recuperar','pedidos':'67890'})
        self.assertEqual(c['modo'],'recuperar')
        with self.assertRaises(ConflitoInterface): self.estado.conferir({'modo':'recuperar','pedidos':'12345'})

    def test_cliente_antigo_normal_e_retomar_so_preparam_iniciais(self):
        self.semear(EstadoPedido('2026-12345','','baixado'),EstadoPedido('2026-67890','100','impressao_pendente'))
        self.iniciar(modo='retomar',pedidos='')
        self.aguardar(lambda:self.estado.fase=='CONCLUIDO')
        self.assertEqual(self.chamadas[-1][0],(['2026-12345'],'preparar'))
        self.iniciar(modo='normal',pedidos='99999',solicitacao='nova')
        self.aguardar(lambda:self.estado.fase=='CONCLUIDO')
        self.assertEqual(self.chamadas[-1][0],(['2026-99999'],'preparar'))

    def test_preparacao_nao_exige_impressora_ou_sumatra(self):
        banco=self.raiz/'banco.json';banco.touch()
        config=replace(CONFIG,erro_leitura='',banco_config=banco,pasta_pedidos=self.raiz,impressora='',sumatra=self.raiz/'ausente.exe')
        config.validar(apenas_impressao=True,somente_preparacao=True)
        with self.assertRaises(ValueError): config.validar(apenas_impressao=True)
