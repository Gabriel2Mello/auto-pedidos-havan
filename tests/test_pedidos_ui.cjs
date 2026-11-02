const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {randomUUID} = require('node:crypto');
const {test} = require('node:test');
const vm = require('node:vm');

function painel({temaSalvo=null, cookie='', falhaStorage=false, falhaCookie=false, demonstracao=false, cenarios=null}={}) {
  const elementos = new Map(), eventos = new Map(), criados = [], rolagens = [];
  class Elemento {
    constructor() { this.texto=''; this.escritas=0; this.value=''; this.checked=false; this.children=[]; this.atributos={}; }
    set textContent(valor) { this.texto=valor; this.escritas++; }
    get textContent() { return this.texto; }
    setAttribute(nome, valor) { this.atributos[nome]=valor; }
    addEventListener(nome,acao) { this.listeners??={}; (this.listeners[nome]??=[]).push(acao); if(nome==='click')this.onclick=(...args)=>this.listeners.click.forEach(fn=>fn(...args)); }
    append(...filhos) { this.children.push(...filhos); }
    replaceChildren(...filhos) { this.children=filhos; this.escritas++; }
    focus() {}
    scrollIntoView() {}
  }
  const obter = id => {
    if (!elementos.has(id)) elementos.set(id, new Elemento());
    return elementos.get(id);
  };
  obter('filtro').value='todos';
  const contexto = vm.createContext({
    document: {
      get cookie() { if(falhaCookie)throw Error('Cookies indisponíveis');return cookie; },
      set cookie(valor) { if(falhaCookie)throw Error('Cookies indisponíveis');cookie=valor; },
      getElementById: obter, querySelector: seletor => ({content:seletor==='meta[name="havan-demo"]'&&demonstracao?'1':'token-local'}),
      addEventListener: () => {},
      querySelectorAll: seletor => seletor==='[data-fila]'?['prontos','sem_cadastro','outras','existentes','importados'].map(nome=>{const b=obter('fila-'+nome);b.dataset={fila:nome};return b;}):seletor==='[data-acao-pedido]'?criados.filter(e=>'data-acao-pedido' in e.atributos):[], documentElement: {dataset:{},setAttribute(nome,valor){this.dataset.tema=valor;}},
      createElement: () => {const e=new Elemento();criados.push(e);return e;}, createDocumentFragment: () => new Elemento(),
    },
    crypto: {randomUUID}, AbortController,
    localStorage: {
      getItem: () => {if(falhaStorage)throw Error('Storage indisponível');return temaSalvo;},
      setItem: (_chave, valor) => {if(falhaStorage)throw Error('Storage indisponível');temaSalvo=valor;},
    },
    matchMedia: () => {throw Error('O tema não depende do sistema operacional');},
    window: {addEventListener: (nome, executar) => eventos.set(nome, executar), scrollTo: opcoes=>rolagens.push(opcoes)},
    fetch: url => url==='/api/demo/cenarios'&&cenarios?Promise.resolve({ok:true,json:async()=>cenarios}):new Promise(() => {}), setTimeout: () => 0,
  });
  obter('tema').tagName='BUTTON';
  vm.runInContext(readFileSync(join(__dirname, '../src/nunes-tema.js'), 'utf8'), contexto);
  vm.runInContext(readFileSync(join(__dirname, '../src/pedidos.js'), 'utf8'), contexto);
  const estado = {
    fase:'PRONTO', mensagem:'Tudo pronto.', ocupada:false, encerrando:false,
    bloqueado:false, execucao:'', indice:0, total:0, pedido:'', pendentes:0,
    filas:{para_baixar:0, baixados:0, importados:0, enviados:0},
    pedidos:[], mensagens:[], resumo:{}, erro:null,
    lote:[], resultados_lote:{}, revisao:0, ano:2026,
  };
  const renderizar = dados => {
    contexto.dadosTeste=dados;
    vm.runInContext('conectado=true; renderizar(dadosTeste)', contexto);
  };
  return {contexto, elementos, eventos, estado, renderizar, obter, rolagens};
}

test('preparar cenário mantém roteiro no menu e preenche lista sem conferir nem executar', async () => {
  const c={id:'geral',nome:'Lote misto',modo:'normal',entrada:'999002\n999003',orientacao:'Deixe o cadastro pendente.'};
  const p=painel({demonstracao:true,cenarios:[c]});
  p.renderizar(p.estado);
  await new Promise(setImmediate);
  const chamadas=[];
  p.contexto.fetch=(...args)=>{chamadas.push(args);throw Error('Preparar não deve acessar a API');};
  p.obter('demo-exemplo').onclick();
  assert.equal(p.obter('demo-cenario').disabled,false);
  assert.equal(p.obter('pedidos').value,c.entrada);
  assert.equal(p.obter('contagem-pedidos').textContent,'Contagem: 2');
  assert.equal(p.obter('demo-descricao').textContent,c.orientacao);
  assert.equal(p.elementos.has('demo-roteiro'),false);
  assert.equal(p.obter('demo-configuracoes').open,false);
  assert.equal(p.obter('iniciar').disabled,true);
  assert.equal(vm.runInContext('conferencia',p.contexto),null);
  assert.equal(chamadas.length,0);
});

test('cenários de entrada e reimpressão preservam validação e confirmação obrigatórias', async () => {
  const cenarios=[{id:'geral',nome:'Entrada',modo:'normal',entrada:'999002\n999002\nINVALIDO',orientacao:'Corrija a entrada.'},
    {id:'reimprimir',nome:'Reimpressão',modo:'reimprimir',entrada:'999001',orientacao:'Confirme outra cópia.'}];
  const p=painel({demonstracao:true,cenarios});p.renderizar(p.estado);await new Promise(setImmediate);
  p.obter('demo-exemplo').onclick();
  assert.equal(p.obter('conferir').disabled,true);
  assert.match(p.obter('validacao-pedidos').textContent,/repetição/);
  assert.match(p.obter('validacao-pedidos').textContent,/INV[AÁ]LIDO|INVALIDO/);
  p.obter('confirmar-copia').checked=true;
  p.obter('demo-cenario').value='reimprimir';p.obter('demo-exemplo').onclick();
  assert.equal(vm.runInContext('modo',p.contexto),'reimprimir');
  assert.equal(p.obter('confirmar-copia').checked,false);
  assert.equal(p.obter('iniciar').disabled,true);
  assert.equal(p.obter('conferir').disabled,false);
});

test('cenários não substituem a lista durante execução ou perda de conexão', async () => {
  const p=painel({demonstracao:true,cenarios:[{id:'geral',nome:'Geral',modo:'normal',entrada:'999002',orientacao:'Execute.'}]});
  p.renderizar(p.estado);await new Promise(setImmediate);
  p.obter('pedidos').value='12345';
  p.renderizar({...p.estado,fase:'EXECUTANDO',ocupada:true});
  p.obter('demo-exemplo').onclick();
  assert.equal(p.obter('pedidos').value,'12345');assert.equal(p.obter('demo-exemplo').disabled,true);
  p.renderizar(p.estado);
  vm.runInContext('conectado=false;atualizarBotoes()',p.contexto);p.obter('demo-exemplo').onclick();
  assert.equal(p.obter('pedidos').value,'12345');assert.equal(p.obter('demo-cenario').disabled,true);
});

test('andamento ocioso ou em falha não redesenha mensagens idênticas', () => {
  const p = painel();
  for (const fase of ['PRONTO', 'FALHA']) {
    p.estado.fase=fase;
    p.estado.mensagem=fase==='PRONTO'?'Tudo pronto.':'Falha de leitura.';
    p.renderizar(p.estado);
    const escritas = [...p.elementos.values()].map(e => e.escritas);
    p.renderizar(JSON.parse(JSON.stringify(p.estado)));
    assert.deepEqual([...p.elementos.values()].map(e => e.escritas), escritas);
  }
  p.estado.mensagem='Situação alterada.';
  p.renderizar(p.estado);
  assert.equal(p.obter('status').textContent, 'Situação alterada.');
});

test('tema escuro padrão e preferências válidas são recuperados sem consultar o sistema', () => {
  for(const [salvo, esperado] of [[null,'escuro'],['invalido','escuro'],['claro','claro'],['escuro','escuro']]){
    const p=painel({temaSalvo:salvo});
    assert.equal(p.contexto.document.documentElement.dataset.tema, esperado);
    assert.equal(p.obter('tema').textContent, esperado==='escuro'?'Tema claro':'Tema escuro');
    if(salvo===esperado)assert.match(p.contexto.document.cookie, new RegExp(`^tema-pedidos-havan=${esperado};`));
  }
});

test('alternância salva a preferência e cookie restaura o tema com storage de outra porta', () => {
  const p=painel();
  p.obter('tema').onclick();
  assert.equal(p.contexto.document.documentElement.dataset.tema, 'claro');
  assert.equal(p.contexto.localStorage.getItem('tema-pedidos-havan'), 'claro');
  assert.equal(p.contexto.document.cookie, 'tema-pedidos-havan=claro; Path=/; Max-Age=31536000; SameSite=Strict');
  const reaberto=painel({cookie:p.contexto.document.cookie});
  assert.equal(reaberto.contexto.document.documentElement.dataset.tema, 'claro');
  assert.equal(painel({cookie:p.contexto.document.cookie, temaSalvo:'escuro'}).contexto.document.documentElement.dataset.tema, 'claro');
  assert.equal(painel({cookie:'tema-pedidos-havan=claro=invalido', temaSalvo:'escuro'}).contexto.document.documentElement.dataset.tema, 'escuro');
  reaberto.obter('tema').onclick();
  assert.equal(reaberto.contexto.localStorage.getItem('tema-pedidos-havan'), 'escuro');
});

test('armazenamentos indisponíveis mantêm tema escuro inicial e alternância funcional', () => {
  const p=painel({falhaStorage:true, falhaCookie:true});
  assert.equal(p.contexto.document.documentElement.dataset.tema, 'escuro');
  p.obter('tema').onclick();
  assert.equal(p.contexto.document.documentElement.dataset.tema, 'claro');
  assert.equal(p.obter('tema').atributos['aria-label'], 'Ativar tema escuro');
});

test('recuperar conexão com estado idêntico reabilita o início', async () => {
  const p = painel();
  p.obter('pedidos').value='12345';
  p.renderizar(p.estado);
  p.contexto.fetch=async () => { throw Error('sem conexão'); };
  await vm.runInContext('atualizar()', p.contexto);
  assert.equal(p.obter('iniciar').disabled, true);
  p.contexto.fetch=async () => ({ok:true, json:async () => p.estado});
  await vm.runInContext('atualizar()', p.contexto);
  assert.equal(p.obter('iniciar').disabled, true);
  assert.equal(p.obter('conferir').disabled, false);
  assert.equal(p.obter('conexao').hidden, true);
});

test('fechar avisa o servidor e impede novas consultas e reconexões', async () => {
  const p = painel(), chamadas=[];
  p.contexto.fetch=async (url, opcoes) => { chamadas.push({url, opcoes}); return {ok:true}; };
  p.eventos.get('pagehide')();
  assert.equal(chamadas.length, 1);
  assert.equal(chamadas[0].url, '/api/fechar');
  assert.equal(chamadas[0].opcoes.keepalive, true);
  assert.equal(chamadas[0].opcoes.headers.Authorization, 'Bearer token-local');
  assert.ok(chamadas[0].opcoes.headers['X-Havan-Pagina']);
  assert.equal(vm.runInContext('presenca.signal.aborted', p.contexto), true);
  await vm.runInContext('atualizar(); acompanhar();', p.contexto);
  assert.equal(chamadas.length, 1);
});

test('fechar pede confirmação mesmo ocioso e só avisa o servidor após sair', () => {
  const p = painel();
  let avisos=0;
  const evento={preventDefault: () => avisos++};
  p.renderizar(p.estado);
  p.eventos.get('beforeunload')(evento);
  assert.equal(avisos, 1);
  assert.equal(vm.runInContext('saindo', p.contexto), false);
  assert.equal(vm.runInContext('presenca.signal.aborted', p.contexto), false);
  p.renderizar({...p.estado, fase:'EXECUTANDO', ocupada:true, execucao:'lote'});
  p.eventos.get('beforeunload')(evento);
  assert.equal(avisos, 2);
  p.renderizar({...p.estado, fase:'ENCERRADO'});
  p.eventos.get('beforeunload')(evento);
  assert.equal(avisos, 2);
});

test('Encerrar já confirmado dispensa uma segunda confirmação ao fechar a aba', async () => {
  const p = painel();
  p.contexto.confirm=() => true;
  p.contexto.fetch=async () => ({ok:true, json:async () => ({ok:true})});
  await p.obter('encerrar').onclick();
  let avisos=0;
  p.eventos.get('beforeunload')({preventDefault: () => avisos++});
  assert.equal(avisos, 0);
});

test('conferir cadastro novamente revalida somente o pedido escolhido sem solicitar importação', async () => {
  const p=painel(), chamadas=[];
  p.estado.pedidos=[
    {pedido:'2026-12345',numero:'',etapa:'sem_cadastro',fila:'baixados',rotulo:'Produto sem cadastro',erro:'Barra 0123456789012',pendente:true},
    {pedido:'2026-67890',numero:'',etapa:'baixado',fila:'baixados',rotulo:'Baixado',erro:'',pendente:true},
  ];
  p.estado.pendentes=2;
  p.obter('filtro').value='sem_cadastro';
  p.renderizar(p.estado);
  const linhas=p.obter('linhas').children[0].children;
  assert.equal(linhas.length,1);
  assert.equal(linhas[0].children[0].textContent,'2026-12345');
  const botao=linhas[0].children[3].children[0];
  assert.equal(botao.textContent,'Conferir cadastro novamente');
  assert.equal(botao.disabled,false);
  p.contexto.fetch=async (url,opcoes)=>{
    chamadas.push({url,opcoes});
    return {ok:true,json:async()=>url==='/api/estado'?p.estado:url==='/api/conferir'?{id:'conferencia-1',revisao:0,pedidos:[{pedido:'2026-12345',salvo:p.estado.pedidos[0]}]}:{ok:true}};
  };
  await botao.onclick();
  const dados=JSON.parse(chamadas[0].opcoes.body);
  assert.equal(chamadas[0].url,'/api/conferir');
  assert.equal(dados.modo,'revalidar');
  assert.equal(dados.pedidos,'2026-12345');
  assert.equal(chamadas.length,3);
  assert.equal(p.obter('iniciar').disabled,true);
  assert.equal(chamadas[1].url,'/api/iniciar');
  assert.equal(JSON.parse(chamadas[1].opcoes.body).modo,'revalidar');
  assert.equal(JSON.parse(chamadas[1].opcoes.body).conferencia,'conferencia-1');
  p.renderizar({...p.estado,fase:'EXECUTANDO',ocupada:true});
  assert.equal(botao.disabled,true);
  await botao.onclick();
  assert.equal(chamadas.length,3);
  p.renderizar(p.estado);
  assert.equal(botao.disabled,false);
});

test('contador normaliza ano, elimina repetições e informa inválidos sem aceitar separadores diferentes',()=>{
  const p=painel();p.renderizar(p.estado);
  p.obter('pedidos').value='12345,2026-12345\n2025-12345\r\nerrado,12345 67890;99999';
  const a=vm.runInContext('contarPedidos()',p.contexto);
  assert.deepEqual(Array.from(a.pedidos),['2026-12345','2025-12345']);
  assert.equal(a.repetidos,1);assert.equal(a.invalidos.length,2);
  assert.equal(p.obter('contagem-pedidos').textContent,'Contagem: 2');
  assert.equal(p.obter('pedidos').atributos['aria-invalid'],'true');
});

test('editar a entrada invalida a conferência e mantém o conteúdo',async()=>{
  const p=painel();p.renderizar(p.estado);p.obter('pedidos').value='12345';
  p.contexto.fetch=async()=>({ok:true,json:async()=>({id:'c',revisao:0,pedidos:[{pedido:'2026-12345',salvo:null}]})});
  await vm.runInContext('conferirPedidos()',p.contexto);
  assert.equal(p.obter('iniciar').disabled,false);
  p.obter('pedidos').value='12345,67890';
  p.obter('pedidos').listeners.input[0]();
  assert.equal(p.obter('iniciar').disabled,true);
  assert.equal(p.obter('contagem-pedidos').textContent,'Contagem: 2');
  assert.equal(vm.runInContext('conferencia',p.contexto),null);
});

test('reimpressão exige conferência e confirmação de outra cópia',async()=>{
  const p=painel();p.renderizar(p.estado);p.obter('pedidos').value='12345';
  vm.runInContext("mudarModo('reimprimir')",p.contexto);
  p.contexto.fetch=async()=>({ok:true,json:async()=>({id:'c',revisao:0,pedidos:[{pedido:'2026-12345',salvo:null}]})});
  await vm.runInContext('conferirPedidos()',p.contexto);
  assert.equal(p.obter('iniciar').disabled,true);
  p.obter('confirmar-copia').checked=true;p.obter('confirmar-copia').listeners.change[0]();
  assert.equal(p.obter('iniciar').disabled,false);
  vm.runInContext("mudarModo('normal')",p.contexto);
  assert.equal(p.obter('confirmar-copia').checked,false);
  assert.equal(p.obter('iniciar').disabled,true);
});

test('lote e histórico possuem contagens separadas e finalização não esconde pendências',()=>{
  const p=painel();
  p.estado.pedidos=[{pedido:'2026-12345',numero:'',etapa:'sem_cadastro',rotulo:'Produto sem cadastro',pendente:true,fila:'baixados',erro:'Corrigir cadastro'},
    {pedido:'2026-67890',numero:'123',etapa:'impressao_enviada',rotulo:'Enviado',pendente:false,fila:'enviados',erro:''}];
  Object.assign(p.estado,{execucao:'lote',lote:['2026-12345'],fase:'CONCLUIDO',resultados_lote:{'2026-12345':'sem_cadastro'}});
  p.renderizar(p.estado);
  assert.equal(p.obter('n-importados').textContent,0);
  assert.equal(p.obter('n-sem_cadastro').textContent,1);
  assert.equal(p.obter('fase').textContent,'Finalizado com pendências');
  p.obter('escopo-todos').onclick();
  assert.equal(p.obter('n-importados').textContent,1);
});

test('perda de conexão conserva dados, bloqueia ações e invalida a revisão anterior',async()=>{
  const p=painel();p.renderizar(p.estado);p.obter('pedidos').value='12345';
  p.contexto.fetch=async()=>({ok:true,json:async()=>({id:'c',revisao:0,pedidos:[{pedido:'2026-12345',salvo:null}]})});
  await vm.runInContext('conferirPedidos()',p.contexto);
  p.contexto.fetch=async()=>{throw Error('rede');};
  await vm.runInContext('atualizar()',p.contexto);
  assert.equal(p.obter('pedidos').value,'12345');assert.equal(p.obter('conferir').disabled,true);
  assert.equal(p.obter('iniciar').disabled,true);assert.match(p.obter('conexao').textContent,/últimos dados/);
  assert.equal(vm.runInContext('conferencia',p.contexto),null);
});

test('falha de transporte no início não permite reenvio até obter o estado',async()=>{
  const p=painel();p.renderizar(p.estado);p.obter('pedidos').value='12345';
  p.contexto.fetch=async()=>({ok:true,json:async()=>({id:'c',revisao:0,pedidos:[{pedido:'2026-12345',salvo:null}]})});
  await vm.runInContext('conferirPedidos()',p.contexto);
  p.contexto.fetch=async()=>{throw Error('resposta perdida');};
  await p.obter('iniciar').onclick();
  assert.equal(vm.runInContext('inicioIncerto',p.contexto),true);
  assert.equal(p.obter('conferir').disabled,true);assert.equal(p.obter('iniciar').disabled,true);
});

test('novo lote preserva entrada aberta e permite recolher manualmente',()=>{
  const p=painel();p.renderizar(p.estado);
  p.obter('preparacao').open=true;
  p.obter('pedidos').value='12345';
  const s={...p.estado,execucao:'lote-1',fase:'EXECUTANDO',ocupada:true,total:1,indice:1,pedido:'2026-12345',lote:['2026-12345'],mensagem:'Processando pedido 1 de 1: 2026-12345.'};
  p.renderizar(s);
  assert.equal(p.obter('preparacao').open,true);
  assert.equal(p.obter('pedidos').value,'12345');
  assert.equal(p.obter('detalhes-processamento').hidden,true);
  assert.equal(p.obter('detalhes-processamento').open,false);
  assert.doesNotMatch(p.obter('status').textContent,/2026-12345/);
  p.obter('preparacao').open=true;
  p.renderizar({...s,mensagem:'Nova etapa'});
  assert.equal(p.obter('preparacao').open,true);
  p.obter('preparacao').open=false;
  p.renderizar({...s,ocupada:false,fase:'CONCLUIDO',resumo:{importacoes_confirmadas:1},resultados_lote:{'2026-12345':'impressao_enviada'}});
  assert.equal(p.obter('preparacao').open,false);
  assert.equal(p.obter('detalhes-processamento').hidden,false);

  assert.equal(p.obter('orientacao').hidden,true);
  assert.equal(p.obter('titulo-andamento').textContent,'Resultado da execução');
  vm.runInContext("mudarModo('retomar')",p.contexto);
  assert.equal(p.obter('preparacao').open,true);
});

test('pausa conserva decisão visível e falhas conservam mensagem sem depender dos detalhes',()=>{
  const p=painel();
  p.renderizar({...p.estado,execucao:'lote',fase:'PAUSADO',ocupada:true,total:1,erro:{id:'erro',pedido:'2026-12345',mensagem:'Gravação incerta',repetir:false,pular:false}});
  assert.equal(p.obter('aviso-erro').hidden,false);
  assert.equal(p.obter('detalhes-processamento').hidden,true);
  assert.equal(p.obter('repetir').hidden,true);
  assert.equal(p.obter('pular').hidden,true);
  assert.equal(p.obter('erro-mensagem').textContent,'Gravação incerta');
  p.renderizar({...p.estado,fase:'FALHA',mensagem:'Histórico indisponível'});
  assert.equal(p.obter('status').textContent,'Histórico indisponível');
  assert.equal(p.obter('detalhes-processamento').hidden,true);
});


test('mostrador mantém último processado ao finalizar e durante decisão',()=>{
  const p=painel();p.renderizar(p.estado);
  assert.equal(p.obter('identificacao').hidden,true);
  const s={...p.estado,execucao:'lote',fase:'EXECUTANDO',ocupada:true,total:2,indice:1,pedido:'2026-12345',pedidos:[{pedido:'2026-12345',rotulo:'Baixado'}]};
  p.renderizar(s);
  assert.equal(p.obter('identificacao').hidden,false);
  assert.equal(p.obter('numero-atual').textContent,'2026-12345');
  assert.equal(p.obter('pedido-atual').textContent,'Pedido 1 de 2');
  assert.equal(p.obter('etapa-atual').textContent,'Baixado');
  assert.equal(p.obter('detalhes-processamento').open,false);
  const html=readFileSync(join(__dirname,'../src/pedidos.html'),'utf8');
  assert.match(html, /id="identificacao"[^>]*role="status"/);
  assert.ok(html.indexOf('id="identificacao"')<html.indexOf('id="detalhes-processamento"'));
  p.renderizar({...s,fase:'PAUSADO',erro:{id:'e',pedido:s.pedido,mensagem:'Conferir impressão',repetir:false,pular:true}});
  assert.equal(p.obter('identificacao').hidden,false);
  assert.equal(p.obter('aviso-erro').hidden,false);
  p.renderizar({...s,fase:'CONCLUIDO',ocupada:false,lote:[s.pedido],resultados_lote:{[s.pedido]:'impressao_enviada'},pedidos:[{pedido:s.pedido,rotulo:'Enviado para impressão'}]});
  assert.equal(p.obter('identificacao').hidden,false);
  assert.equal(p.obter('pedido-atual').textContent,'Último pedido processado');
  assert.equal(p.obter('numero-atual').textContent,s.pedido);
  assert.equal(p.obter('etapa-atual').textContent,'Enviado para impressão');
});


test('baixar e conferir envia somente preparação e mantém importação como ação explícita',async()=>{
  const p=painel(), chamadas=[];
  p.renderizar(p.estado);p.obter('pedidos').value='12345,12345';
  const pronto={pedido:'2026-12345',etapa:'pronto_importar',rotulo:'Pronto para importar',numero:'',erro:'',pendente:true};
  const final={...p.estado,modo:'preparar',execucao:'preparo',fase:'CONCLUIDO',pedidos:[pronto],lote:['2026-12345'],lote_preparacao:['2026-12345'],resultados_lote:{'2026-12345':'pronto_importar'}};
  p.contexto.fetch=async(url,opcoes)=>{chamadas.push({url,body:opcoes.body&&JSON.parse(opcoes.body)});return {ok:true,json:async()=>url==='/api/conferir'?{id:'c'}:url==='/api/estado'?final:{ok:true}};};
  await p.obter('formulario').listeners.submit[0]({preventDefault(){}});
  assert.deepEqual(chamadas.map(c=>c.url),['/api/conferir','/api/iniciar','/api/estado']);
  assert.equal(chamadas[0].body.modo,'preparar');assert.equal(chamadas[1].body.modo,'preparar');
  assert.equal(chamadas[1].body.pedidos,'2026-12345');
  assert.equal(p.obter('importar-aptos').disabled,false);
  assert.equal(p.obter('importar-aptos').textContent,'Importar 1 pedido apto');
  assert.equal(p.obter('fase').textContent,'Conferido');
  assert.equal(p.obter('orientacao').hidden,true);
});

test('importação usa aptos do lote em conferência e preserva escopo apesar de filtros e nova execução',async()=>{
  const p=painel(), chamadas=[];
  const criar=(pedido,etapa,erro='')=>({pedido,etapa,erro,numero:'',pendente:true,rotulo:etapa});
  p.renderizar({...p.estado,execucao:'importacao-anterior',modo:'importar',lote:['2026-10000'],lote_preparacao:['2026-10000','2026-20000','2026-30000'],pedidos:[criar('2026-10000','pronto_importar'),criar('2026-20000','sem_cadastro'),criar('2026-30000','pronto_importar','Consulta falhou'),criar('2026-40000','pronto_importar')]});
  p.obter('filtro').value='sem_cadastro';p.obter('busca').value='20000';vm.runInContext('renderizarTabela()',p.contexto);
  assert.equal(p.obter('linhas').children[0].children.length,1);
  assert.equal(p.obter('n-sem_cadastro').textContent,1);
  assert.equal(p.obter('importar-aptos').textContent,'Importar 1 pedido apto');
  assert.equal(p.obter('alcance-importacao').textContent,'Antes de importar, abra o Sisplan na tela 1002 — Pedido por Grade.');
  p.contexto.fetch=async(url,opcoes)=>{chamadas.push({url,body:opcoes.body&&JSON.parse(opcoes.body)});return {ok:true,json:async()=>url==='/api/conferir'?{id:'importar-revisao'}:url==='/api/estado'?p.estado:{ok:true}};};
  await p.obter('importar-aptos').onclick();
  assert.equal(chamadas[0].body.modo,'importar');assert.equal(chamadas[0].body.pedidos,'2026-10000');
  assert.equal(chamadas[1].body.conferencia,'importar-revisao');
  assert.equal(chamadas[1].body.pedidos,'2026-10000');
});

test('reabertura encontra aptos persistidos e importação fica bloqueada durante envio ou desconexão',async()=>{
  const p=painel();p.estado.pedidos=[{pedido:'2026-12345',etapa:'pronto_importar',rotulo:'Pronto para importar',erro:'',numero:''}];p.renderizar(p.estado);
  assert.equal(p.obter('importar-aptos').disabled,false);
  let resolver;const chamadas=[];
  p.contexto.fetch=(url,opcoes)=>{chamadas.push(url);return new Promise(r=>{resolver=r;});};
  const primeira=p.obter('importar-aptos').onclick();
  await p.obter('importar-aptos').onclick();
  assert.equal(chamadas.length,1);assert.equal(p.obter('importar-aptos').disabled,true);
  resolver({ok:false,status:409,json:async()=>({erro:'Confira novamente'})});await primeira;
  assert.deepEqual(chamadas,['/api/conferir']);
  vm.runInContext('conectado=false;atualizarBotoes()',p.contexto);
  await p.obter('importar-aptos').onclick();assert.equal(chamadas.length,1);
});

test('resposta perdida ao iniciar preparação bloqueia reenvio até atualização',async()=>{
  const p=painel();p.renderizar(p.estado);p.obter('pedidos').value='12345';const chamadas=[];
  p.contexto.fetch=async(url)=>{chamadas.push(url);if(url==='/api/conferir')return {ok:true,json:async()=>({id:'c'})};throw Error('rede');};
  await p.obter('formulario').listeners.submit[0]({preventDefault(){}});
  assert.equal(vm.runInContext('inicioIncerto',p.contexto),true);
  assert.equal(p.obter('conferir').disabled,true);assert.equal(p.obter('importar-aptos').disabled,true);
  await p.obter('formulario').listeners.submit[0]({preventDefault(){}});
  assert.deepEqual(chamadas,['/api/conferir','/api/iniciar']);
});

test('ações por estado distinguem recuperação pós-inclusão e outra cópia',()=>{
  const p=painel();
  for(const [etapa,modo] of [['para_baixar','preparar'],['baixado','revalidar'],['sem_cadastro','revalidar'],['importacao_iniciada','recuperar'],['gravacao_pendente','recuperar'],['aviso_pendente','recuperar'],['importado','recuperar'],['impressao_pendente','recuperar'],['impressao_incerta','reimprimir']]){
    p.contexto.etapaTeste=etapa;assert.equal(vm.runInContext('acaoDoPedido({etapa:etapaTeste})[0]',p.contexto),modo);
  }
  assert.equal(vm.runInContext("acaoDoPedido({etapa:'pronto_importar',erro:''})",p.contexto),null);
  assert.equal(vm.runInContext("acaoDoPedido({etapa:'existente',erro:''})",p.contexto),null);
});


test('último processado mantém pendência final e ignora outras execuções',()=>{
  const p=painel(), a='2026-11111', b='2026-22222', c='2026-33333';
  const s={...p.estado,execucao:'misto',fase:'INTERROMPIDO',ocupada:false,pedido:b,lote:[a,b],
    pedidos:[{pedido:a,rotulo:'Pronto para importar'},{pedido:b,rotulo:'Produto sem cadastro'}],
    resultados_lote:{[a]:'pronto_importar',[b]:'sem_cadastro',[c]:'impressao_enviada'}};
  p.renderizar(s);
  assert.equal(p.obter('identificacao').hidden,false);
  assert.equal(p.obter('numero-atual').textContent,b);
  p.renderizar({...s,resultados_lote:{[a]:'aguardando',[b]:'sem_cadastro',[c]:'impressao_enviada'}});
  assert.equal(p.obter('identificacao').hidden,false);
  p.renderizar({...s,pedido:'',resultados_lote:{[a]:'aguardando',[c]:'impressao_enviada'}});
  assert.equal(p.obter('identificacao').hidden,true);
  p.renderizar({...s,execucao:'novo',fase:'EXECUTANDO',ocupada:true,pedido:b,indice:1,total:1});
  assert.equal(p.obter('numero-atual').textContent,b);
  assert.equal(p.obter('pedido-atual').textContent,'Pedido 1 de 1');
});

test('grupos de estados aparecem uma vez no acompanhamento, fora da entrada',()=>{
  const html=readFileSync(join(__dirname,'../src/pedidos.html'),'utf8');
  const aside=html.slice(html.indexOf('<aside'),html.indexOf('</aside>'));
  for(const grupo of ['prontos','sem_cadastro','outras','existentes','importados']){
    assert.equal(html.split(`id="n-${grupo}"`).length-1,1);
    assert.ok(aside.includes(`id="n-${grupo}"`));
  }
});


test('importação informa zero, singular e plural de aptos e antecede resultados',()=>{
  const p=painel();p.renderizar(p.estado);
  assert.equal(p.obter('importar-aptos').textContent,'Nenhum pedido apto');
  assert.equal(p.obter('importar-aptos').disabled,true);
  p.renderizar({...p.estado,pedidos:['2026-11111','2026-22222'].map(pedido=>({pedido,etapa:'pronto_importar',erro:''}))});
  assert.equal(p.obter('importar-aptos').textContent,'Importar 2 pedidos aptos');
  assert.equal(p.obter('importar-aptos').disabled,false);
  const html=readFileSync(join(__dirname,'../src/pedidos.html'),'utf8');
  assert.ok(html.indexOf('id="titulo-importacao"')<html.indexOf('id="titulo-historico"'));
  assert.ok(!html.includes('3. Importar'));
});

test('observação omite estado repetido e preserva erro e resultado diferente',()=>{
  const p=painel(),pedido='2026-11111';
  const s={...p.estado,execucao:'lote',lote:[pedido],pedidos:[{pedido,etapa:'impressao_enviada',rotulo:'Enviado para impressão',erro:''}],resultados_lote:{[pedido]:'impressao_enviada'}};
  p.renderizar(s);
  const observacao=()=>p.obter('linhas').children[0].children[0].children[3].textContent;
  assert.equal(observacao(),'—');
  p.renderizar({...s,pedidos:[{...s.pedidos[0],erro:'Conferir documento'}]});
  assert.equal(observacao(),'Conferir documento');
  p.renderizar({...s,resultados_lote:{[pedido]:'falhou'}});
  assert.match(observacao(),/Nesta execução:/);
});


test('entrada recolhida move grupos sem duplicar e preserva decisões e execução',()=>{
  const p=painel();p.obter('preparacao').open=false;p.renderizar(p.estado);
  assert.equal(p.obter('acompanhamento').hidden,true);
  assert.ok(p.obter('grupos-resultados').children.includes(p.obter('grupos-estados')));
  p.obter('preparacao').open=true;
  vm.runInContext('atualizarLayout()',p.contexto);
  assert.equal(p.obter('acompanhamento').hidden,false);
  assert.ok(p.obter('grupos-acompanhamento').children.includes(p.obter('grupos-estados')));
  p.obter('preparacao').open=false;
  for(const dados of [{ocupada:true,fase:'EXECUTANDO'},{fase:'PAUSADO',erro:{id:'e',mensagem:'Conferir'}},{fase:'FALHA'},{bloqueado:true}]){
    p.renderizar({...p.estado,...dados});
    assert.equal(p.obter('acompanhamento').hidden,false);
  }
  const html=readFileSync(join(__dirname,'../src/pedidos.html'),'utf8');
  assert.ok(!html.includes('Resumo da execução'));
  assert.ok(!html.includes('id="detalhes-resultado"'));
});


test('cartão recolhe entrada e filtra; limpar filtros conserva escopo e reinicia página',()=>{
  const p=painel(),pedido='2026-11111';p.obter('preparacao').open=true;
  p.renderizar({...p.estado,execucao:'lote',lote:[pedido],pedidos:[{pedido,etapa:'pronto_importar',erro:''}]});
  p.obter('fila-sem_cadastro').onclick();
  assert.equal(p.obter('preparacao').open,false);
  assert.equal(p.obter('filtro').value,'sem_cadastro');
  assert.equal(p.obter('fila-sem_cadastro').atributos['aria-pressed'],'true');
  assert.ok(p.obter('grupos-resultados').children.includes(p.obter('grupos-estados')));
  p.obter('busca').value='inexistente';
  vm.runInContext('pagina=2',p.contexto);
  p.obter('limpar-filtros').onclick();
  assert.equal(p.obter('busca').value,'');
  assert.equal(p.obter('filtro').value,'todos');
  assert.equal(vm.runInContext('pagina',p.contexto),0);
  assert.equal(vm.runInContext('escopo',p.contexto),'lote');
  assert.equal(p.obter('fila-sem_cadastro').atributos['aria-pressed'],'false');
  p.obter('escopo-todos').onclick();p.obter('limpar-filtros').onclick();
  assert.equal(vm.runInContext('escopo',p.contexto),'todos');
});


test('cartões ficam bloqueados durante execução e pausa e liberam ao terminar',()=>{
  const p=painel();p.obter('preparacao').open=true;
  for(const fase of ['EXECUTANDO','PAUSADO','PARANDO']){
    p.renderizar({...p.estado,fase,ocupada:true});
    assert.equal(p.obter('fila-prontos').disabled,true);
    p.obter('fila-prontos').onclick();
    assert.equal(p.obter('preparacao').open,true);
    assert.equal(p.obter('filtro').value,'todos');
  }
  for(const fase of ['CONCLUIDO','INTERROMPIDO']){
    p.renderizar({...p.estado,fase,ocupada:false});
    assert.equal(p.obter('fila-prontos').disabled,false);
  }
});


test('faixa permanece após terminar com entrada recolhida ou expandida',()=>{
  const p=painel(),pedido='2026-11111';
  for(const fase of ['CONCLUIDO','INTERROMPIDO']){
    p.obter('preparacao').open=false;
    p.renderizar({...p.estado,execucao:'lote',fase,pedido,total:1,indice:1,lote:[pedido],pedidos:[{pedido,rotulo:'Produto sem cadastro'}],resultados_lote:{[pedido]:'sem_cadastro'}});
    assert.equal(p.obter('identificacao').hidden,false);
    assert.equal(p.obter('acompanhamento').hidden,false);
    assert.equal(p.obter('numero-atual').textContent,pedido);
    assert.equal(p.obter('detalhes-processamento').hidden,false);
    p.obter('preparacao').open=true;vm.runInContext('atualizarLayout()',p.contexto);
    assert.equal(p.obter('acompanhamento').hidden,false);
    p.obter('preparacao').open=false;vm.runInContext('atualizarLayout()',p.contexto);
    assert.equal(p.obter('acompanhamento').hidden,false);
  }
});


test('importar sobe suavemente após iniciar com entrada aberta ou recolhida',async()=>{
  for(const aberta of [true,false]){
    const p=painel(),pedido='2026-11111';p.obter('preparacao').open=aberta;
    const s={...p.estado,pedidos:[{pedido,etapa:'pronto_importar',erro:''}]};
    p.renderizar(s);
    p.contexto.fetch=async url=>({ok:true,json:async()=>url==='/api/conferir'?{id:'c'}:url==='/api/estado'?{...s,ocupada:true,execucao:'importacao',pedido,fase:'EXECUTANDO'}:{ok:true}});
    await p.obter('importar-aptos').onclick();
    assert.equal(p.rolagens.length,1);
    assert.equal(p.rolagens[0].top,0);
    assert.equal(p.rolagens[0].behavior,'smooth');
    assert.equal(p.obter('preparacao').open,aberta);
    await p.obter('importar-aptos').onclick();
    assert.equal(p.rolagens.length,1);
  }
});
