const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {randomUUID} = require('node:crypto');
const {test} = require('node:test');
const vm = require('node:vm');

function painel() {
  const elementos = new Map(), eventos = new Map();
  class Elemento {
    constructor() { this.texto=''; this.escritas=0; this.value=''; this.checked=false; }
    set textContent(valor) { this.texto=valor; this.escritas++; }
    get textContent() { return this.texto; }
    setAttribute() {}
    addEventListener() {}
    append() {}
    replaceChildren() { this.escritas++; }
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
      querySelectorAll: () => [], documentElement: {dataset:{}},
      createElement: () => new Elemento(), createDocumentFragment: () => new Elemento(),
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
