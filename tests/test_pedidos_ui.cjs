const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {randomUUID} = require('node:crypto');
const {test} = require('node:test');
const vm = require('node:vm');

function painel({temaSalvo=null, cookie='', falhaStorage=false, falhaCookie=false, demonstracao=false, cenarios=null}={}) {
  const elementos = new Map(), eventos = new Map(), criados = [];
  class Elemento {
    constructor() { this.texto=''; this.escritas=0; this.value=''; this.checked=false; this.children=[]; this.atributos={}; }
    set textContent(valor) { this.texto=valor; this.escritas++; }
    get textContent() { return this.texto; }
    setAttribute(nome, valor) { this.atributos[nome]=valor; }
    addEventListener(nome,acao) { this.listeners??={}; (this.listeners[nome]??=[]).push(acao); if(nome==='click')this.onclick=(...args)=>this.listeners.click.forEach(fn=>fn(...args)); }
    append(...filhos) { this.children.push(...filhos); }
    replaceChildren(...filhos) { this.children=filhos; this.escritas++; }
    focus() {}
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
      querySelectorAll: seletor => seletor==='[data-reimportar]'?criados.filter(e=>'data-reimportar' in e.atributos):[], documentElement: {dataset:{},setAttribute(nome,valor){this.dataset.tema=valor;}},
      createElement: () => {const e=new Elemento();criados.push(e);return e;}, createDocumentFragment: () => new Elemento(),
    },
    crypto: {randomUUID}, AbortController,
    localStorage: {
      getItem: () => {if(falhaStorage)throw Error('Storage indisponível');return temaSalvo;},
      setItem: (_chave, valor) => {if(falhaStorage)throw Error('Storage indisponível');temaSalvo=valor;},
    },
    matchMedia: () => {throw Error('O tema não depende do sistema operacional');},
    window: {addEventListener: (nome, executar) => eventos.set(nome, executar)},
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
  return {contexto, elementos, eventos, estado, renderizar, obter};
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

test('importar novamente confere somente o pedido escolhido antes de permitir execução', async () => {
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
  assert.equal(botao.textContent,'Importar novamente');
  assert.equal(botao.disabled,false);
  p.contexto.fetch=async (url,opcoes)=>{
    chamadas.push({url,opcoes});
    return {ok:true,json:async()=>url==='/api/estado'?p.estado:url==='/api/conferir'?{id:'conferencia-1',revisao:0,pedidos:[{pedido:'2026-12345',salvo:p.estado.pedidos[0]}]}:{ok:true}};
  };
  await botao.onclick();
  const dados=JSON.parse(chamadas[0].opcoes.body);
  assert.equal(chamadas[0].url,'/api/conferir');
  assert.equal(dados.modo,'normal');
  assert.equal(dados.pedidos,'2026-12345');
  assert.equal(chamadas.length,1);
  assert.equal(p.obter('iniciar').disabled,false);
  await p.obter('iniciar').onclick();
  assert.equal(chamadas[1].url,'/api/iniciar');
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
  assert.equal(p.obter('n-enviados').textContent,0);
  assert.equal(p.obter('n-atencao').textContent,1);
  assert.equal(p.obter('fase').textContent,'Finalizado com pendências');
  p.obter('escopo-todos').onclick();
  assert.equal(p.obter('n-enviados').textContent,1);
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
