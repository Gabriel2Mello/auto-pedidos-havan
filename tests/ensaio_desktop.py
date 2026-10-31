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
                            limite=time.monotonic()+20
                            while not w.evaluate_js(js):
                                if time.monotonic()>limite: raise AssertionError(js)
                                time.sleep(.1)
                        def selecionar(cenario):
                            aguardar('!estado.ocupada && !enviando && conectado')
                            w.evaluate_js("document.getElementById('demo-configuracoes').open=true;"
                                          f"document.getElementById('demo-cenario').value={json.dumps(cenario)};"
                                          "document.getElementById('demo-cenario').dispatchEvent(new Event('change'));"
                                          "document.getElementById('demo-exemplo').click()")

                        def preparar(modo, entrada=''):
                            aguardar('!estado.ocupada && !enviando')
                            w.evaluate_js(f'mudarModo({json.dumps(modo)});'
                                          f"document.getElementById('pedidos').value={json.dumps(entrada)};"
                                          "document.getElementById('pedidos').dispatchEvent(new Event('input'))")

                        def iniciar():
                            anterior = w.evaluate_js('estado.execucao')
                            w.evaluate_js("document.getElementById('conferir').click()")
                            aguardar('conferencia !== null && !enviando')
                            if w.evaluate_js('conferencia.pedidos.length===1'):
                                assert w.evaluate_js("document.querySelector('.rolagem-conferencia').scrollHeight<=document.querySelector('.rolagem-conferencia').clientHeight")
                                assert abs(w.evaluate_js("document.querySelector('.rolagem-conferencia').getBoundingClientRect().width")-largura_conferencia)<1
                            if w.evaluate_js("modo==='reimprimir'"):
                                assert w.evaluate_js("document.getElementById('iniciar').disabled")
                                w.evaluate_js("document.getElementById('confirmar-copia').checked=true;document.getElementById('confirmar-copia').dispatchEvent(new Event('change'))")
                            w.evaluate_js("document.getElementById('iniciar').click()")
                            aguardar(f'estado.execucao !== {json.dumps(anterior)} && !enviando')

                        def responder(botao):
                            anterior = w.evaluate_js('estado.erro.id')
                            w.evaluate_js(f'document.getElementById({json.dumps(botao)}).click()')
                            aguardar(f'!enviando && (!estado.erro || estado.erro.id !== {json.dumps(anterior)})')

                        def terminar():
                            aguardar("['CONCLUIDO','INTERROMPIDO'].includes(estado.fase) && !enviando")

                        aguardar('estado && conectado && cenariosDemo.length>0')
                        assert w.evaluate_js("document.getElementById('demo-roteiro')===null")
                        for largura in (1180, 760, 480):
                            w.resize(largura,820)
                            time.sleep(.3)
                            assert w.evaluate_js('document.documentElement.scrollWidth<=innerWidth+1')
                            w.evaluate_js("document.querySelector('#demo-configuracoes summary').focus();document.querySelector('#demo-configuracoes summary').click()")
                            assert w.evaluate_js("document.getElementById('demo-configuracoes').open")
                            assert w.evaluate_js("(()=>{const r=document.querySelector('.menu-configuracoes').getBoundingClientRect();return r.left>=0&&r.right<=innerWidth})()")
                            w.evaluate_js("document.getElementById('pedidos').focus()")
                            assert not w.evaluate_js("document.getElementById('demo-configuracoes').open")
                            resultados.append(f'janela solicitada {largura}; viewport real {w.evaluate_js("innerWidth")}')
                        w.maximize()
                        time.sleep(.3)
                        assert w.evaluate_js('document.documentElement.scrollWidth<=innerWidth+1 && document.documentElement.clientWidth===innerWidth')
                        resultados.append('janela maximizada sem faixa de rolagem reservada')
                        w.restore()
                        w.resize(1180,820)
                        w.evaluate_js("document.querySelector('#demo-configuracoes summary').focus();document.querySelector('#demo-configuracoes summary').click()")
                        w.evaluate_js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
                        assert not w.evaluate_js("document.getElementById('demo-configuracoes').open")
                        w.evaluate_js("document.querySelector('#demo-configuracoes summary').focus();document.querySelector('#demo-configuracoes summary').click()")
                        w.evaluate_js("document.getElementById('demo-exemplo').click()")
                        assert not w.evaluate_js("document.getElementById('demo-configuracoes').open")
                        resultados.append('menu demonstração: limites, foco externo, Escape e roteiro restrito ao menu')
                        assert w.evaluate_js("document.getElementById('contagem-pedidos').textContent")=='Contagem: 4'
                        w.evaluate_js("document.getElementById('conferir').click()")
                        aguardar('conferencia !== null')
                        largura_conferencia = w.evaluate_js("document.querySelector('.rolagem-conferencia').getBoundingClientRect().width")
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
                        aguardar("estado.fase==='PAUSADO' && estado.pedido.endsWith('999004')")
                        responder('pular')
                        terminar()
                        assert w.evaluate_js("document.getElementById('fase').textContent")=='Finalizado com pendências'
                        resultados.append('execução sintética, pausa e finalização com pendências')
                        preparar('retomar');iniciar();terminar()
                        assert w.evaluate_js('estado.pendentes===0')
                        resultados.append('retomada de cadastro e download após solicitação')

                        selecionar('entrada')
                        assert w.evaluate_js("document.getElementById('conferir').disabled && document.getElementById('contagem-pedidos').textContent==='Contagem: 2'")
                        preparar('normal','999002\n999002\n999015')
                        w.evaluate_js("document.getElementById('conferir').click()")
                        aguardar('conferencia!==null && !enviando')
                        w.evaluate_js("document.getElementById('pedidos').value+=" + json.dumps('\n999016') + ";document.getElementById('pedidos').dispatchEvent(new Event('input'))")
                        assert w.evaluate_js('conferencia===null')
                        resultados.append('entrada inválida, duplicação, conferência e edição')

                        selecionar('existente');iniciar();terminar()
                        assert w.evaluate_js('estado.resumo.importacoes_confirmadas===0 && estado.resumo.existente===1')
                        selecionar('reimprimir');iniciar();terminar()
                        assert w.evaluate_js('estado.resumo.importacoes_confirmadas===0 && estado.resumo.impressao_enviada===1')
                        resultados.append('existente sem envio e reimpressão com confirmação')

                        for cenario in ('portal','banco'):
                            selecionar(cenario);iniciar();aguardar("estado.fase==='PAUSADO'")
                            assert w.evaluate_js("document.getElementById('pular').hidden && !document.getElementById('repetir').hidden")
                            if cenario=='portal':
                                assert w.evaluate_js("document.getElementById('repetir').textContent==='Reconectar e continuar'")
                            responder('repetir');terminar()
                            resultados.append(cenario+': pausa e recuperação autorizada')

                        selecionar('retomada');iniciar();terminar()
                        assert w.evaluate_js("estado.pedidos.find(p=>p.pedido.endsWith('999009')).etapa==='baixado' && estado.pedidos.find(p=>p.pedido.endsWith('999010')).etapa==='importado'")
                        preparar('retomar');iniciar();terminar()
                        assert w.evaluate_js('estado.resumo.importacoes_confirmadas===1 && estado.resumo.impressao_enviada===2')
                        resultados.append('retomada por etapa sem reincluir o importado')

                        selecionar('impressao-pendente');iniciar();aguardar("estado.fase==='PAUSADO'")
                        responder('parar-erro');terminar()
                        preparar('retomar');iniciar();terminar()
                        assert w.evaluate_js('estado.resumo.importacoes_confirmadas===0 && estado.resumo.impressao_enviada===1')
                        resultados.append('impressão pendente retomada sem nova inclusão')

                        selecionar('impressao-incerta');iniciar();aguardar("estado.fase==='PAUSADO'")
                        responder('pular');terminar()
                        preparar('retomar');iniciar();aguardar("estado.fase==='PAUSADO'")
                        assert w.evaluate_js("document.getElementById('repetir').hidden")
                        responder('pular');terminar()
                        preparar('reimprimir','999011');iniciar();terminar()
                        assert w.evaluate_js('estado.resumo.importacoes_confirmadas===0 && estado.resumo.impressao_enviada===1')
                        resultados.append('impressão incerta bloqueada até reimpressão explícita')

                        for cenario in ('gravacao','aviso'):
                            selecionar(cenario);iniciar();aguardar("estado.fase==='PAUSADO'")
                            assert w.evaluate_js("document.getElementById('repetir').hidden && document.getElementById('pular').hidden")
                            responder('parar-erro');terminar()
                            preparar('retomar');iniciar();terminar()
                            assert w.evaluate_js('estado.resumo.importacoes_confirmadas===0')
                            resultados.append(cenario+': bloqueio e conferência posterior sem reinclusão')

                        selecionar('paginacao')
                        w.evaluate_js("document.getElementById('conferir').click()")
                        aguardar('conferencia!==null && !enviando')
                        assert w.evaluate_js("document.querySelector('.rolagem-conferencia').scrollHeight>document.querySelector('.rolagem-conferencia').clientHeight")
                        assert abs(w.evaluate_js("document.querySelector('.rolagem-conferencia').getBoundingClientRect().width")-largura_conferencia)<1
                        iniciar();terminar()
                        w.evaluate_js("document.getElementById('proxima').click()")
                        assert w.evaluate_js("document.getElementById('quantidade').textContent==='51–60 de 60 pedido(s)'")
                        w.evaluate_js("document.getElementById('busca').value='999159';document.getElementById('busca').dispatchEvent(new Event('input'))")
                        assert w.evaluate_js("document.getElementById('quantidade').textContent==='1–1 de 1 pedido(s)'")
                        w.evaluate_js("document.getElementById('busca').value='';document.getElementById('busca').dispatchEvent(new Event('input'))")
                        from System import Action
                        w.native.Invoke(Action(lambda:setattr(w.native.webview,'ZoomFactor',1.25)))
                        w.resize(760,540);time.sleep(.3)
                        assert w.evaluate_js('document.documentElement.scrollWidth<=innerWidth+1 && document.documentElement.clientWidth===innerWidth')
                        w.evaluate_js("document.getElementById('demo-configuracoes').open=true")
                        assert w.evaluate_js("(()=>{const r=document.querySelector('.menu-configuracoes').getBoundingClientRect();return r.left>=0&&r.right<=innerWidth+1&&r.bottom<=innerHeight+1})()")
                        resultados.append('60 pedidos: paginação, busca, rolagem estável e zoom real 125% em janela estreita')
                        w.native.Invoke(Action(lambda:setattr(w.native.webview,'ZoomFactor',1)))
                        w.resize(1180,820)

                        selecionar('parada');iniciar()
                        w.evaluate_js("window.confirm=()=>true;document.getElementById('parar').click()")
                        terminar()
                        assert w.evaluate_js("!estado.pedidos.some(p=>['importacao_iniciada','gravacao_pendente','impressao_iniciada'].includes(p.etapa))")
                        preparar('retomar');iniciar();terminar()
                        resultados.append('parada cooperativa e retomada')

                        selecionar('cancelamento');iniciar();aguardar("estado.fase==='PAUSADO'")
                        assert w.evaluate_js("document.getElementById('repetir').hidden && document.getElementById('pular').hidden")
                        w.evaluate_js("window.confirm=()=>false;document.getElementById('encerrar').click()")
                        assert not estado.encerrando
                        w.evaluate_js("window.confirm=()=>true;document.getElementById('encerrar').click()")
                        assert estado.finalizado.wait(10)
                        resultados.append('cancelamento incerto; cancelar e confirmar encerramento durante pausa')
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
