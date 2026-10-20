const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {randomUUID} = require('node:crypto');
const {test} = require('node:test');
const vm = require('node:vm');

function painel() {
  const elementos = new Map(), eventos = new Map(), criados = [];
  class Elemento {
    constructor() { this.texto=''; this.escritas=0; this.value=''; this.checked=false; this.children=[]; this.atributos={}; }
    set textContent(valor) { this.texto=valor; this.escritas++; }
    get textContent() { return this.texto; }
    setAttribute(nome, valor) { this.atributos[nome]=valor; }
    addEventListener() {}
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
      getElementById: obter, querySelector: () => ({content:'token-local'}),
      querySelectorAll: seletor => seletor==='[data-reimportar]'?criados.filter(e=>'data-reimportar' in e.atributos):[], documentElement: {dataset:{}},
      createElement: () => {const e=new Elemento();criados.push(e);return e;}, createDocumentFragment: () => new Elemento(),
    },
    crypto: {randomUUID}, AbortController,
    localStorage: {getItem: () => 'claro'},
    window: {addEventListener: (nome, executar) => eventos.set(nome, executar)},
    fetch: () => new Promise(() => {}), setTimeout: () => 0,
  });
  vm.runInContext(readFileSync(join(__dirname, '../src/pedidos.js'), 'utf8'), contexto);
  const estado = {
    fase:'PRONTO', mensagem:'Tudo pronto.', ocupada:false, encerrando:false,
    bloqueado:false, execucao:'', indice:0, total:0, pedido:'', pendentes:0,
    filas:{para_baixar:0, baixados:0, importados:0, enviados:0},
    pedidos:[], mensagens:[], resumo:{}, erro:null,
  };
  const renderizar = dados => {
    contexto.dadosTeste=dados;
    vm.runInContext('renderizar(dadosTeste)', contexto);
  };
  return {contexto, elementos, eventos, estado, renderizar, obter};
}

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

test('recuperar conexão com estado idêntico reabilita o início', async () => {
  const p = painel();
  p.renderizar(p.estado);
  p.contexto.fetch=async () => { throw Error('sem conexão'); };
  await vm.runInContext('atualizar()', p.contexto);
  assert.equal(p.obter('iniciar').disabled, true);
  p.contexto.fetch=async () => ({ok:true, json:async () => p.estado});
  await vm.runInContext('atualizar()', p.contexto);
  assert.equal(p.obter('iniciar').disabled, false);
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

test('filtro de produto sem cadastro permite importar novamente apenas o pedido escolhido', async () => {
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
    return {ok:true,json:async()=>url==='/api/estado'?p.estado:{ok:true}};
  };
  await botao.onclick();
  const dados=JSON.parse(chamadas[0].opcoes.body);
  assert.equal(chamadas[0].url,'/api/iniciar');
  assert.equal(dados.modo,'normal');
  assert.equal(dados.pedidos,'2026-12345');
  assert.ok(dados.solicitacao);
  p.renderizar({...p.estado,fase:'EXECUTANDO',ocupada:true});
  assert.equal(botao.disabled,true);
  await botao.onclick();
  assert.equal(chamadas.length,2);
  p.renderizar(p.estado);
  assert.equal(botao.disabled,false);
});
