"""Ensaio no WebView2 real, com executor e histórico temporários."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import time
from unittest.mock import patch

from desktop_havan import Janela, executar
from src.controlador import EstadoInterface
from src.interface_web import criar_servidor
from demonstracao import simular


def main():
    resultados, falhas = [], []
    with TemporaryDirectory(prefix='havan-ensaio-') as pasta, patch.dict(os.environ, {'HAVAN_DESKTOP_DADOS': pasta}):
        estado = EstadoInterface(Path(pasta)/'estado.sqlite3', executor=simular)
        estado.pronto.wait(5)
        servidor, _ = criar_servidor(estado, modo_desktop=True)
        servidor.demonstracao = True

        class Ensaio(Janela):
            def executar(self):
                def verificar():
                    try:
                        limite=time.monotonic()+40
                        while self.janela is None or not self.janela.events.loaded.wait(.1):
                            if time.monotonic()>limite: raise RuntimeError('WebView2 não carregou')
                        w=self.janela
                        def aguardar(js):
                            limite=time.monotonic()+10
                            while not w.evaluate_js(js):
                                if time.monotonic()>limite: raise AssertionError(js)
                                time.sleep(.1)
                        aguardar('estado && conectado')
                        for largura in (1180, 760, 480):
                            w.resize(largura,820)
                            time.sleep(.3)
                            assert w.evaluate_js('document.documentElement.scrollWidth<=innerWidth+1')
                            w.evaluate_js("document.querySelector('#demo-configuracoes summary').focus();document.querySelector('#demo-configuracoes summary').click()")
                            assert w.evaluate_js("document.getElementById('demo-configuracoes').open")
                            assert w.evaluate_js("(()=>{const r=document.querySelector('.menu-configuracoes').getBoundingClientRect();return r.left>=0&&r.right<=innerWidth})()")
                            w.evaluate_js("document.getElementById('pedidos').focus()")
                            assert not w.evaluate_js("document.getElementById('demo-configuracoes').open")
                            resultados.append(f'largura {largura}')
                        w.resize(1180,820)
                        w.evaluate_js("document.querySelector('#demo-configuracoes summary').focus();document.querySelector('#demo-configuracoes summary').click()")
                        w.evaluate_js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
                        assert not w.evaluate_js("document.getElementById('demo-configuracoes').open")
                        w.evaluate_js("document.querySelector('#demo-configuracoes summary').focus();document.querySelector('#demo-configuracoes summary').click()")
                        w.evaluate_js("document.getElementById('demo-exemplo').click()")
                        assert not w.evaluate_js("document.getElementById('demo-configuracoes').open")
                        resultados.append('menu demonstração: limites, foco externo, Escape e exemplo')
                        assert w.evaluate_js("document.getElementById('contagem-pedidos').textContent")=='Contagem: 4'
                        w.evaluate_js("document.getElementById('conferir').click()")
                        aguardar('conferencia !== null')
                        assert not estado.situacao()['lote']
                        resultados.append('conferência sem executar')
                        w.evaluate_js("document.getElementById('tema').click()")
                        aguardar("document.documentElement.dataset.tema==='claro'")
                        time.sleep(.3)
                        from desktop_preferencias import ler_tema
                        assert ler_tema()=='claro'
                        resultados.append('tema persistido')
                        w.evaluate_js("document.getElementById('iniciar').click()")
                        aguardar("estado.fase==='PAUSADO'")
                        assert w.evaluate_js("!document.getElementById('aviso-erro').hidden")
                        w.evaluate_js("document.getElementById('pular').click()")
                        aguardar("estado.fase==='CONCLUIDO'")
                        assert w.evaluate_js("document.getElementById('fase').textContent")=='Finalizado com pendências'
                        resultados.append('execução sintética, pausa e finalização com pendências')
                    except Exception as erro:
                        import traceback
                        falhas.append(traceback.format_exc())
                    finally:
                        servidor.encerrar(confirmado=True)
                thread=Thread(target=verificar)
                thread.start()
                try: super().executar()
                finally: thread.join(50)
        try:
            executar(servidor, fabrica=Ensaio)
        finally:
            servidor.server_close()
            estado.worker.join()
    destino=Path('.local/qa-desktop/ensaio.json')
    destino.parent.mkdir(parents=True,exist_ok=True)
    destino.write_text(json.dumps({'aprovados':resultados,'falhas':falhas},ensure_ascii=False,indent=2),encoding='utf-8')
    print(destino.read_text(encoding='utf-8'))
    return int(bool(falhas))


if __name__=='__main__': raise SystemExit(main())
