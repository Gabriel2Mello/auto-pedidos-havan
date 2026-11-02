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

                        def clicar_iniciar(id_):
                            anterior = w.evaluate_js('estado.execucao')
                            assert not w.evaluate_js(f"document.getElementById({json.dumps(id_)}).disabled")
                            w.evaluate_js(f"document.getElementById({json.dumps(id_)}).click()")
                            aguardar(f'estado.execucao !== {json.dumps(anterior)} && !enviando')

                        def baixar():
                            clicar_iniciar('conferir')
                            assert w.evaluate_js("!estado.ocupada || [...document.querySelectorAll('[data-fila]')].every(b=>b.disabled)")

                        def importar():
                            aberta=w.evaluate_js("document.getElementById('preparacao').open")
                            w.evaluate_js("window.scrollTo({top:document.documentElement.scrollHeight,behavior:'instant'})")
                            assert w.evaluate_js('scrollY>0')
                            clicar_iniciar('importar-aptos')
                            aguardar('scrollY===0')
                            assert w.evaluate_js("document.getElementById('preparacao').open")==aberta

                        def acao_pedido(sufixo):
                            anterior = w.evaluate_js('estado.execucao')
                            seletor = f'[data-acao-pedido$="-{sufixo}"]'
                            assert w.evaluate_js(f'document.querySelector({json.dumps(seletor)}) !== null')
                            w.evaluate_js(f'document.querySelector({json.dumps(seletor)}).click()')
                            aguardar(f'estado.execucao !== {json.dumps(anterior)} && !enviando')

                        def reimprimir(entrada):
                            preparar('reimprimir',entrada)
                            w.evaluate_js("document.getElementById('conferir').click()")
                            aguardar('conferencia !== null && !enviando')
                            assert w.evaluate_js("document.getElementById('iniciar').disabled")
                            w.evaluate_js("document.getElementById('confirmar-copia').checked=true;document.getElementById('confirmar-copia').dispatchEvent(new Event('change'))")
                            clicar_iniciar('iniciar')

                        def sem_recorte():
                            assert w.evaluate_js('document.documentElement.scrollWidth<=innerWidth+1 && document.documentElement.clientWidth===innerWidth')

                        def limpar_filtros():
                            w.evaluate_js("document.getElementById('busca').value='';document.getElementById('filtro').value='todos';document.getElementById('busca').dispatchEvent(new Event('input'))")

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
                            w.evaluate_js("document.getElementById('preparacao').open=false")
                            aguardar("document.getElementById('grupos-estados').parentElement.id==='grupos-resultados'")
                            assert w.evaluate_js("document.getElementById('acompanhamento').hidden && document.querySelectorAll('#grupos-estados').length===1 && document.getElementById('detalhes-resultado')===null")
                            sem_recorte()
                            w.evaluate_js("document.getElementById('preparacao').open=true")
                            aguardar("document.getElementById('grupos-estados').parentElement.id==='grupos-acompanhamento'")
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
                        assert not estado.situacao()['lote']
                        assert w.evaluate_js("document.getElementById('importar-aptos').disabled")
                        resultados.append('informar pedidos não inicia preparo nem importação')
                        w.evaluate_js("document.getElementById('tema').click()")
                        aguardar("document.documentElement.dataset.tema==='claro'")
                        time.sleep(.3)
                        from desktop_preferencias import ler_tema
                        assert ler_tema()=='claro'
                        resultados.append('tema persistido')

                        baixar();terminar()
                        assert w.evaluate_js("!document.getElementById('identificacao').hidden && document.getElementById('numero-atual').textContent.endsWith('999015') && document.getElementById('pedido-atual').textContent==='Último pedido processado'")
                        assert w.evaluate_js("document.querySelectorAll('.filas').length===1 && document.querySelector('.acompanhamento .filas')!==null")
                        resultados.append('resumo único no acompanhamento e último pedido concluído preservado')
                        assert w.evaluate_js("!document.getElementById('acompanhamento').hidden && !document.getElementById('detalhes-processamento').hidden && document.getElementById('identificacao').getBoundingClientRect().height>0")
                        resultados.append('execução finalizada mantém faixa do último processado e detalhes com entrada expandida')
                        assert w.evaluate_js("document.querySelector('.importacao-lote').getBoundingClientRect().bottom <= document.getElementById('titulo-historico').getBoundingClientRect().top")
                        assert w.evaluate_js("document.getElementById('importar-aptos').textContent==='Importar 2 pedidos aptos'")
                        resultados.append('faixa de importação acima dos resultados com contagem natural dos aptos')
                        assert w.evaluate_js("estado.modo==='preparar' && estado.resumo.importacoes_confirmadas===0")
                        assert w.evaluate_js("estado.pedidos.filter(p=>p.etapa==='pronto_importar').length===2 && estado.pedidos.find(p=>p.pedido.endsWith('999003')).etapa==='sem_cadastro' && estado.resultados_lote[estado.lote.find(p=>p.endsWith('999004'))]==='falhou'")
                        assert w.evaluate_js("document.getElementById('n-prontos').textContent==='2' && document.getElementById('n-sem_cadastro').textContent==='1' && document.getElementById('n-outras').textContent==='1'")
                        assert w.evaluate_js("document.getElementById('preparacao').open && !document.getElementById('aviso-erro').hidden===false")
                        resultados.append('preparo separa aptos, EAN ausente e download falho sem importar nem pausar por pedido')
                        w.evaluate_js("document.querySelector('[data-fila=sem_cadastro]').click()")
                        aguardar("!document.getElementById('preparacao').open && document.getElementById('grupos-estados').parentElement.id==='grupos-resultados'")
                        assert w.evaluate_js("document.getElementById('filtro').value==='sem_cadastro' && document.activeElement.dataset.fila==='sem_cadastro'")
                        w.evaluate_js("document.getElementById('busca').value='inexistente';document.getElementById('busca').dispatchEvent(new Event('input'));document.getElementById('limpar-filtros').click()")
                        assert w.evaluate_js("document.getElementById('busca').value==='' && document.getElementById('filtro').value==='todos' && escopo==='lote' && pagina===0")
                        resultados.append('cartão recolhe entrada com foco preservado; limpar filtros mantém escopo e mostra todos os grupos')
                        assert w.evaluate_js("[...document.querySelectorAll('[data-fila]')].every(b=>!b.disabled)")
                        w.evaluate_js("document.getElementById('preparacao').open=false")
                        aguardar("!document.getElementById('acompanhamento').hidden && document.getElementById('grupos-estados').parentElement.id==='grupos-resultados'")
                        assert w.evaluate_js("document.querySelector('.filas').getBoundingClientRect().bottom <= document.querySelector('.filtros').getBoundingClientRect().top")
                        assert w.evaluate_js("document.getElementById('identificacao').getBoundingClientRect().height>0 && document.getElementById('numero-atual').textContent.endsWith('999015')")
                        resultados.append('entrada recolhida após término mantém faixa do último pedido e grupos acima da busca')
                        importar();terminar()
                        w.evaluate_js("document.getElementById('preparacao').open=true")
                        aguardar("document.getElementById('grupos-estados').parentElement.id==='grupos-acompanhamento'")
                        assert w.evaluate_js("estado.resumo.importacoes_confirmadas===2 && estado.resumo.impressao_enviada===2")
                        assert w.evaluate_js("pedidosDoEscopo().length===4 && document.getElementById('n-sem_cadastro').textContent==='1' && document.getElementById('n-outras').textContent==='1' && document.getElementById('n-importados').textContent==='2'")
                        resultados.append('importação explícita só dos aptos e pendências preservadas no escopo de conferência')
                        acao_pedido('999003');terminar()
                        assert w.evaluate_js("estado.modo==='revalidar' && estado.resumo.importacoes_confirmadas===0 && estado.pedidos.find(p=>p.pedido.endsWith('999003')).etapa==='pronto_importar'")
                        importar();terminar()
                        assert w.evaluate_js('estado.resumo.importacoes_confirmadas===1')
                        resultados.append('cadastro corrigido revalidado pela linha e importado só após nova ação')
                        acao_pedido('999004');terminar();importar();terminar()
                        assert w.evaluate_js('estado.resumo.importacoes_confirmadas===1')
                        resultados.append('download pendente preparado novamente antes de importar')

                        selecionar('entrada')
                        assert w.evaluate_js("document.getElementById('conferir').disabled && document.getElementById('contagem-pedidos').textContent==='Contagem: 2'")
                        preparar('preparar','999002,999002,999015')
                        assert w.evaluate_js("document.getElementById('contagem-pedidos').textContent==='Contagem: 2' && !document.getElementById('conferir').disabled")
                        resultados.append('entrada inválida bloqueia preparo e repetição é contada uma vez')
                        selecionar('existente');baixar();terminar()
                        assert w.evaluate_js('estado.resumo.importacoes_confirmadas===0 && estado.resumo.existente===1')
                        assert w.evaluate_js("document.getElementById('importar-aptos').disabled")
                        reimprimir('999001');terminar()
                        assert w.evaluate_js('estado.resumo.importacoes_confirmadas===0 && estado.resumo.impressao_enviada===1')
                        resultados.append('existente separado sem importação e reimpressão exige confirmação')

                        for cenario in ('portal','banco'):
                            selecionar(cenario);baixar();aguardar("estado.fase==='PAUSADO'")
                            assert w.evaluate_js("[...document.querySelectorAll('[data-fila]')].every(b=>b.disabled)")
                            w.evaluate_js("document.getElementById('preparacao').open=false")
                            aguardar("document.getElementById('grupos-estados').parentElement.id==='grupos-resultados'")
                            assert w.evaluate_js("!document.getElementById('acompanhamento').hidden && !document.getElementById('aviso-erro').hidden")
                            assert w.evaluate_js("document.getElementById('pular').hidden && !document.getElementById('repetir').hidden")
                            if cenario=='portal':
                                assert w.evaluate_js("document.getElementById('repetir').textContent==='Reconectar e continuar'")
                            responder('repetir');terminar()
                            assert w.evaluate_js('estado.resumo.importacoes_confirmadas===0')
                            assert w.evaluate_js("!document.getElementById('importar-aptos').disabled")
                            resultados.append(cenario+': preparo pausa e repetição apenas libera aptos')

                        selecionar('impressao-pendente');baixar();terminar();importar();aguardar("estado.fase==='PAUSADO'")
                        responder('parar-erro');terminar()
                        acao_pedido('999012');terminar()
                        assert w.evaluate_js("estado.modo==='recuperar' && estado.resumo.importacoes_confirmadas===0 && estado.resumo.impressao_enviada===1")
                        resultados.append('impressão pendente recuperada pela linha sem nova inclusão')

                        selecionar('impressao-incerta');baixar();terminar();importar();aguardar("estado.fase==='PAUSADO'")
                        assert w.evaluate_js("document.getElementById('repetir').hidden")
                        responder('pular');terminar()
                        w.evaluate_js("document.querySelector('[data-acao-pedido$=\"-999011\"]').click()")
                        aguardar('conferencia!==null && !enviando')
                        assert w.evaluate_js("modo==='reimprimir' && document.getElementById('iniciar').disabled")
                        assert w.evaluate_js("estado.pedidos.find(p=>p.pedido.endsWith('999011')).etapa==='impressao_incerta'")
                        w.evaluate_js("document.getElementById('confirmar-copia').checked=true;document.getElementById('confirmar-copia').dispatchEvent(new Event('change'))")
                        clicar_iniciar('iniciar');terminar()
                        assert w.evaluate_js('estado.resumo.importacoes_confirmadas===0 && estado.resumo.impressao_enviada===1')
                        resultados.append('impressão incerta abre revisão e exige confirmação explícita da outra cópia')

                        for cenario,sufixo in (('gravacao','999007'),('aviso','999008')):
                            selecionar(cenario);baixar();terminar();importar();aguardar("estado.fase==='PAUSADO'")
                            assert w.evaluate_js("document.getElementById('repetir').hidden && document.getElementById('pular').hidden")
                            responder('parar-erro');terminar()
                            acao_pedido(sufixo);terminar()
                            assert w.evaluate_js("estado.modo==='recuperar' && estado.resumo.importacoes_confirmadas===0")
                            resultados.append(cenario+': conferência pós-inclusão pela linha sem reincluir')

                        selecionar('paginacao');baixar();terminar()
                        assert w.evaluate_js("estado.resumo.existente===60 && estado.resumo.importacoes_confirmadas===0")
                        assert w.evaluate_js("document.querySelector('.rolagem-historico').scrollHeight>document.querySelector('.rolagem-historico').clientHeight")
                        largura_historico=w.evaluate_js("document.querySelector('.rolagem-historico').getBoundingClientRect().width")
                        w.evaluate_js("document.getElementById('proxima').click()")
                        assert w.evaluate_js("document.getElementById('quantidade').textContent==='51–60 de 60 pedido(s)'")
                        w.evaluate_js("document.getElementById('busca').value='999159';document.getElementById('busca').dispatchEvent(new Event('input'))")
                        assert w.evaluate_js("document.getElementById('quantidade').textContent==='1–1 de 1 pedido(s)'")
                        assert w.evaluate_js("document.querySelector('.rolagem-historico').scrollHeight<=document.querySelector('.rolagem-historico').clientHeight")
                        assert abs(w.evaluate_js("document.querySelector('.rolagem-historico').getBoundingClientRect().width")-largura_historico)<1
                        limpar_filtros()
                        w.evaluate_js("document.querySelector('[data-fila=prontos]').click()")
                        assert w.evaluate_js("document.getElementById('quantidade').textContent==='Nenhum pedido nesta seleção'")
                        limpar_filtros()
                        resultados.append('60 existentes: paginação, busca, grupos e rolagem curta/longa sem deslocar largura')

                        preparar('reimprimir','999001')
                        w.evaluate_js("document.getElementById('conferir').click()")
                        aguardar('conferencia!==null && !enviando')
                        largura_conferencia=w.evaluate_js("document.querySelector('.rolagem-conferencia').getBoundingClientRect().width")
                        assert w.evaluate_js("document.querySelector('.rolagem-conferencia').scrollHeight<=document.querySelector('.rolagem-conferencia').clientHeight")
                        preparar('reimprimir','\n'.join(str(n) for n in range(999100,999160)))
                        w.evaluate_js("document.getElementById('conferir').click()")
                        aguardar('conferencia!==null && !enviando')
                        assert w.evaluate_js("document.querySelector('.rolagem-conferencia').scrollHeight>document.querySelector('.rolagem-conferencia').clientHeight")
                        assert abs(w.evaluate_js("document.querySelector('.rolagem-conferencia').getBoundingClientRect().width")-largura_conferencia)<1
                        assert w.evaluate_js("document.getElementById('iniciar').disabled")
                        w.evaluate_js("document.getElementById('pedidos').value+='\\n999016';document.getElementById('pedidos').dispatchEvent(new Event('input'))")
                        assert w.evaluate_js('conferencia===null')
                        resultados.append('revisão curta/longa de reimpressão estável; edição invalida autorização')

                        from System import Action
                        w.native.Invoke(Action(lambda:setattr(w.native.webview,'ZoomFactor',1.25)))
                        w.resize(760,540);time.sleep(.3);sem_recorte()
                        w.evaluate_js("document.getElementById('demo-configuracoes').open=true")
                        assert w.evaluate_js("(()=>{const r=document.querySelector('.menu-configuracoes').getBoundingClientRect();return r.left>=0&&r.right<=innerWidth+1&&r.bottom<=innerHeight+1})()")
                        resultados.append('zoom real 125% em janela estreita sem recorte ou faixa reservada')
                        w.native.Invoke(Action(lambda:setattr(w.native.webview,'ZoomFactor',1)))
                        w.resize(1180,820)

                        selecionar('parada');baixar()
                        w.evaluate_js("window.confirm=()=>true;document.getElementById('parar').click()")
                        terminar()
                        assert w.evaluate_js("estado.modo==='preparar' && !estado.pedidos.some(p=>['importacao_iniciada','gravacao_pendente','impressao_iniciada'].includes(p.etapa))")
                        selecionar('parada');baixar();terminar();importar();terminar()
                        assert w.evaluate_js('estado.resumo.importacoes_confirmadas===3')
                        resultados.append('parada segura no preparo, novo preparo e importação explícita posterior')

                        selecionar('cancelamento');baixar();terminar();importar();aguardar("estado.fase==='PAUSADO'")
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
