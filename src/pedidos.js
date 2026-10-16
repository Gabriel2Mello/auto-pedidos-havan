'use strict';
const el = id => document.getElementById(id);
const token = document.querySelector('meta[name="havan-token"]').content;
const headers = {Authorization: 'Bearer ' + token, 'Content-Type': 'application/json', 'X-Havan-Pagina': crypto.randomUUID()};
const fases = {INICIANDO:'Iniciando',PRONTO:'Pronto',EXECUTANDO:'Em andamento',PAUSADO:'Aguardando sua escolha',PARANDO:'Parando com segurança',CONCLUIDO:'Finalizado',INTERROMPIDO:'Parado',FALHA:'Precisa de atenção',ENCERRANDO:'Encerrando',ENCERRADO:'Encerrado'};
let modo='normal', estado=null, enviando=false, encerrado=false, encerramentoPedido=false, pagina=0, erroVisivel='', tabelaAnterior='', atividadeAnterior='', presenca=null;
let estadoAnterior='', saindo=false;

async function api(caminho, dados) {
  const resposta = await fetch(caminho, {method:dados===undefined?'GET':'POST',headers,body:dados===undefined?undefined:JSON.stringify(dados),cache:'no-store'});
  const conteudo = await resposta.json();
  if (!resposta.ok) throw Error(conteudo.erro || 'Não foi possível concluir a ação.');
  return conteudo;
}
function mensagem(texto) { el('mensagem-acao').textContent=texto; }
function mudarModo(novo) {
  if (enviando || estado?.ocupada) return;
  modo=novo; mensagem(''); el('confirmar-copia').checked=false;
  document.querySelectorAll('[data-modo]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.modo===modo)));
  el('campo-pedidos').hidden=modo==='retomar'; el('pedidos').required=modo!=='retomar';
  el('confirmacao-reimpressao').hidden=modo!=='reimprimir';
  el('ajuda-modo').textContent=modo==='normal'?'Informe os pedidos. Os que já estão no Sisplan serão identificados antes de incluir.':modo==='retomar'?`Existem ${estado?.pendentes??0} pedido(s) pendente(s). Vamos continuar a partir da etapa salva de cada um.`:'Informe os pedidos para enviar outra cópia. Confira a impressão anterior antes de confirmar.';
  el('iniciar').textContent=modo==='normal'?'Inserir e processar':modo==='retomar'?'Retomar pendências':'Reimprimir pedidos';
  atualizarBotoes();
}
function atualizarBotoes() {
  const bloqueado=enviando||!estado||estado.ocupada||estado.bloqueado||encerrado||estado.encerrando;
  document.querySelectorAll('[data-modo]').forEach(b=>b.disabled=bloqueado);
  el('iniciar').disabled=bloqueado||(modo==='retomar'&&!estado?.pendentes);
  el('pedidos').disabled=bloqueado; el('confirmar-copia').disabled=bloqueado;
  el('parar').hidden=!estado?.ocupada||['INICIANDO','ENCERRANDO','PARANDO'].includes(estado?.fase);
  el('parar').disabled=enviando; el('encerrar').disabled=encerrado||enviando||estado?.encerrando;
  ['repetir','pular','parar-erro'].forEach(id=>el(id).disabled=enviando);
}
function renderizarTabela() {
  const filtro=el('filtro').value, busca=el('busca').value.trim().toLowerCase();
  const lista=(estado?.pedidos??[]).filter(p=>(filtro==='todos'||(filtro==='pendentes'?p.pendente:p.fila===filtro))&&(`${p.pedido} ${p.numero}`.toLowerCase().includes(busca)));
  pagina=Math.min(pagina,Math.max(0,Math.ceil(lista.length/50)-1));
  const inicio=pagina*50, visiveis=lista.slice(inicio,inicio+50), chave=JSON.stringify([visiveis,filtro,busca,pagina]);
  if(chave!==tabelaAnterior){
    tabelaAnterior=chave;
    const linhas=document.createDocumentFragment();
    for(const p of visiveis){
      const tr=document.createElement('tr');
      [p.pedido,p.numero||'—',p.rotulo||'Conferir situação',p.erro||'—'].forEach((texto,i)=>{
        const td=document.createElement('td');
        if(i===2){const span=document.createElement('span');span.textContent=texto;span.className='situacao'+(['importacao_iniciada','gravacao_pendente','impressao_incerta'].includes(p.etapa)?' atencao':['impressao_enviada','existente'].includes(p.etapa)?' concluido':'');td.append(span);}else td.textContent=texto;
        tr.append(td);
      });linhas.append(tr);
    }
    if(!visiveis.length){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=4;td.className='vazio';td.textContent=busca?'Nenhum pedido corresponde à busca.':filtro==='pendentes'?'Não há pedidos pendentes.':'Nenhum pedido nesta fila.';tr.append(td);linhas.append(tr);}
    el('linhas').replaceChildren(linhas);
  }
  el('quantidade').textContent=lista.length?`${inicio+1}–${Math.min(inicio+50,lista.length)} de ${lista.length} pedido(s)`:'Nenhum pedido nesta seleção';
  el('anterior').disabled=pagina===0;el('proxima').disabled=inicio+50>=lista.length;
}
function renderizar(s) {
  const chave=JSON.stringify(s);if(chave===estadoAnterior)return;estadoAnterior=chave;
  estado=s; encerrado=s.fase==='ENCERRADO';
  for(const [fila,n] of Object.entries(s.filas))el('n-'+fila).textContent=n;
  el('n-pendentes').textContent=s.pendentes;
  el('fase').textContent=fases[s.fase]||s.fase;el('status').textContent=s.mensagem;
  el('codigo').textContent=s.codigo_execucao||'—';
  el('pedido-atual').textContent=s.pedido?`Pedido ${s.indice} de ${s.total} · ${s.pedido}`:'As etapas concluídas ficam preservadas para retomar.';
  el('progresso').max=Math.max(1,s.total);el('progresso').value=s.fase==='CONCLUIDO'?s.total:Math.max(0,s.indice-(s.ocupada?1:0));
  el('orientacao').textContent=s.ocupada?'Durante a inclusão, aguarde o robô terminar antes de usar o teclado, o mouse ou a tela do Sisplan.':'O Sisplan deve estar aberto na tela 1002 — Pedido por Grade.';
  const resumo=s.resumo??{};el('resumo').hidden=!Object.keys(resumo).length;
  el('resumo').textContent=`Importações confirmadas: ${resumo.importacoes_confirmadas??0} · Já existentes: ${resumo.existente??0}\nImpressões enviadas: ${resumo.impressao_enviada??0} · Não processados: ${resumo.aguardando??0}`;
  el('aviso-erro').hidden=!s.erro;
  if(s.erro){
    el('erro-pedido').textContent='Pedido: '+s.erro.pedido;el('erro-mensagem').textContent=s.erro.mensagem;
    el('repetir').hidden=!s.erro.repetir;el('pular').hidden=!s.erro.pular;
    el('repetir').textContent=s.erro.reconectar?'Reconectar e continuar':'Corrigi o problema · tentar novamente';
    el('erro-seguranca').textContent=s.erro.configuracao?'Pare este processamento. Os ajustes do arquivo serão aplicados no próximo processamento ou em Retomar.':s.erro.repetir?'Nenhuma nova tentativa será feita sem sua escolha.':s.erro.pular?'Confira a impressão antes de usar Reimprimir para enviar outra cópia.':'Solicite ajuda ao responsável para conferir o Sisplan antes de iniciar outra inclusão.';
    if(erroVisivel!==s.erro.id){erroVisivel=s.erro.id;el('titulo-erro').focus();}
  } else erroVisivel='';
  const atividade=JSON.stringify(s.mensagens);
  if(atividade!==atividadeAnterior){atividadeAnterior=atividade;const frag=document.createDocumentFragment();for(const texto of s.mensagens??[]){const li=document.createElement('li');li.textContent=texto;frag.append(li);}el('atividade').replaceChildren(frag);}
  if(modo==='retomar')el('ajuda-modo').textContent=`Existem ${s.pendentes} pedido(s) pendente(s). Vamos continuar a partir da etapa salva de cada um.`;
  atualizarBotoes();renderizarTabela();
}
async function atualizar() {
  if(encerrado||saindo)return;
  try{renderizar(await api('/api/estado'));el('conexao').hidden=true;}
  catch(_){estadoAnterior='';el('conexao').hidden=false;const texto=encerramentoPedido?'Aplicação encerrada. Você pode fechar esta aba.':'Não consegui falar com o programa. Reabra o atalho se ele tiver sido fechado. Confira o andamento antes de reenviar pedidos.';if(el('conexao').textContent!==texto)el('conexao').textContent=texto;if(encerramentoPedido){encerrado=true;pararPresenca();}else{el('iniciar').disabled=true;}}
  if(!encerrado&&!saindo)setTimeout(atualizar,1000);
}
async function acao(caminho,dados){
  if(enviando)return;enviando=true;mensagem('');atualizarBotoes();
  try{await api(caminho,dados);renderizar(await api('/api/estado'));}
  catch(erro){mensagem(erro.message);}
  finally{enviando=false;atualizarBotoes();}
}
el('formulario').addEventListener('submit',async e=>{
  e.preventDefault();
  if(modo==='reimprimir'&&!el('confirmar-copia').checked){mensagem('Confirme que deseja enviar outra cópia.');el('confirmar-copia').focus();return;}
  await acao('/api/iniciar',{modo,pedidos:modo==='retomar'?'':el('pedidos').value,confirmado:el('confirmar-copia').checked,solicitacao:crypto.randomUUID()});
});
document.querySelectorAll('[data-modo]').forEach(b=>b.onclick=()=>mudarModo(b.dataset.modo));
document.querySelectorAll('[data-fila]').forEach(b=>b.onclick=()=>{el('filtro').value=b.dataset.fila;pagina=0;renderizarTabela();el('titulo-historico').scrollIntoView({behavior:'smooth',block:'start'});});
for(const id of ['busca','filtro'])el(id).addEventListener('input',()=>{pagina=0;renderizarTabela();});
el('anterior').onclick=()=>{pagina--;renderizarTabela();};el('proxima').onclick=()=>{pagina++;renderizarTabela();};
for(const [id,decisao] of [['repetir','repetir'],['pular','pular'],['parar-erro','encerrar']])el(id).onclick=()=>{if(estado?.erro)acao('/api/decidir',{execucao:estado.execucao,erro:estado.erro.id,decisao});};
el('parar').onclick=()=>{if(confirm('Parar após concluir a etapa atual com segurança? Os pedidos pendentes serão preservados.'))acao('/api/parar',{execucao:estado.execucao});};
el('encerrar').onclick=async()=>{
  if(!confirm('Encerrar Pedidos Havan? Se houver uma ação em andamento, vamos finalizá-la com segurança e preservar as pendências.'))return;
  encerramentoPedido=true;
  try{await api('/api/encerrar',{});el('status').textContent='Encerrando com segurança. Aguarde a conclusão da etapa atual.';el('encerrar').disabled=true;el('iniciar').disabled=true;}
  catch(erro){encerramentoPedido=false;mensagem(erro.message);}
};
el('baixar-log').onclick=async()=>{
  try{const r=await fetch('/api/log',{headers});if(!r.ok)throw Error('Não consegui abrir o log. Avise o responsável.');const url=URL.createObjectURL(await r.blob());const a=document.createElement('a');a.href=url;a.download='auto-pedidos.log';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  catch(erro){mensagem(erro.message);}
};
el('copiar-suporte').onclick=async()=>{
  if(!estado)return;
  const texto=`Pedidos Havan\nExecução: ${estado.codigo_execucao}\nSituação: ${fases[estado.fase]||estado.fase}\nPedido: ${estado.pedido||'—'}\nMensagem: ${estado.erro?.mensagem||estado.mensagem}`;
  try{await navigator.clipboard.writeText(texto);el('copiar-suporte').textContent='Diagnóstico copiado';setTimeout(()=>el('copiar-suporte').textContent='Copiar diagnóstico',2200);}
  catch(_){mensagem('Não consegui copiar. Informe ao suporte o código de execução exibido abaixo.');}
};
function aplicarTema(tema){document.documentElement.dataset.tema=tema;el('tema').textContent=tema==='escuro'?'Tema claro':'Tema escuro';el('tema').setAttribute('aria-label',tema==='escuro'?'Usar tema claro':'Usar tema escuro');}
try{const salvo=localStorage.getItem('tema-pedidos-havan');aplicarTema(['claro','escuro'].includes(salvo)?salvo:matchMedia('(prefers-color-scheme:dark)').matches?'escuro':'claro');}catch(_){aplicarTema('claro');}
el('tema').onclick=()=>{const tema=document.documentElement.dataset.tema==='escuro'?'claro':'escuro';aplicarTema(tema);try{localStorage.setItem('tema-pedidos-havan',tema);}catch(_){}};
function pararPresenca(){presenca?.abort();}
async function acompanhar(){
  if(encerrado||saindo)return;presenca=new AbortController();
  try{const r=await fetch('/api/presenca',{headers,signal:presenca.signal});if(!r.ok)return;const leitor=r.body.getReader();while(!encerrado){const {done}=await leitor.read();if(done)break;}}
  catch(_){}finally{if(!encerrado&&!encerramentoPedido&&!saindo)setTimeout(acompanhar,1000);}
}
window.addEventListener('beforeunload',e=>{if(!encerrado&&!encerramentoPedido){e.preventDefault();e.returnValue='';}});
window.addEventListener('pagehide',()=>{
  saindo=true;pararPresenca();
  if(!encerrado&&!encerramentoPedido)fetch('/api/fechar',{method:'POST',headers,body:'{}',keepalive:true}).catch(()=>{});
});
window.addEventListener('pageshow',e=>{if(e.persisted)window.location.reload();});
acompanhar();atualizar();
