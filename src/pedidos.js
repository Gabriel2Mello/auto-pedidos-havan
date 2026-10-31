'use strict';
const el = id => document.getElementById(id);
const token = document.querySelector('meta[name="havan-token"]').content;
const desktop=document.querySelector('meta[name="havan-desktop"]').content==='1';
const demonstracao=document.querySelector('meta[name="havan-demo"]').content==='1';
let salvamentoTema=Promise.resolve(true);
const headers = {Authorization: 'Bearer ' + token, 'Content-Type': 'application/json', 'X-Havan-Pagina': crypto.randomUUID()};
const fases = {INICIANDO:'Iniciando',PRONTO:'Pronto',EXECUTANDO:'Em andamento',PAUSADO:'Aguardando sua escolha',PARANDO:'Parando com segurança',CONCLUIDO:'Finalizado',INTERROMPIDO:'Parado',FALHA:'Precisa de atenção',ENCERRANDO:'Encerrando',ENCERRADO:'Encerrado'};
let modo='normal', estado=null, enviando=false, encerrado=false, encerramentoPedido=false, pagina=0, erroVisivel='', tabelaAnterior='', atividadeAnterior='', presenca=null;
let estadoAnterior='', saindo=false;
let conferencia=null, escopo='todos', conectado=false, inicioIncerto=false, ultimoLote='';
let cenariosDemo=[];
const etapasAtencao=['sem_cadastro','importacao_iniciada','gravacao_pendente','aviso_pendente','impressao_incerta'];
const exigeAtencao=p=>Boolean(p.erro)||etapasAtencao.includes(p.etapa)||['falhou','rejeitado','gravacao_pendente','impressao_incerta','impressao_pendente','sem_cadastro'].includes(p.resultado);
function rotuloResultado(valor){
  return ({aguardando:'Não processado',existente:'Já existente, sem novo envio',impressao_enviada:'Enviado para impressão',sem_cadastro:'Produto sem cadastro',falhou:'Falha no processamento',rejeitado:'Pedido rejeitado',gravacao_pendente:'Gravação não confirmada',impressao_incerta:'Conferir impressão',impressao_pendente:'Impressão pendente'})[valor]||'Pendente — conferir situação';
}

function analisarEntrada(texto, ano=estado?.ano??new Date().getFullYear()) {
  const pedidos=[], invalidos=[]; let repetidos=0;
  for(const parte of texto.replace(/\r/g,'\n').split(/[\n,]/)){
    let pedido=parte.trim();if(!pedido)continue;
    if(/^[0-9]{4,}$/.test(pedido))pedido=ano+'-'+pedido;
    if(!/^[0-9]{4}-[0-9]{4,}$/.test(pedido)||pedido.length>50){invalidos.push(parte.trim());continue;}
    if(pedidos.includes(pedido))repetidos++;else pedidos.push(pedido);
  }
  return {pedidos,invalidos,repetidos};
}
function contarPedidos(){
  const a=analisarEntrada(el('pedidos').value);
  el('contagem-pedidos').textContent='Contagem: '+a.pedidos.length;
  el('validacao-pedidos').textContent=[a.repetidos?`${a.repetidos} repetição(ões), contadas uma única vez.`:'',a.invalidos.length?`${a.invalidos.length} entrada(s) inválida(s): ${a.invalidos.join(', ').slice(0,250)}`:''].filter(Boolean).join(' ');
  el('pedidos').setAttribute('aria-invalid',String(a.invalidos.length>0));
  return a;
}
function abrirAba(nome, foco=false){
  for(const aba of ['pedidos','conferencia']){
    const ativa=aba===nome;
    el('aba-'+aba).setAttribute('aria-selected',String(ativa));
    el('aba-'+aba).setAttribute('tabindex',ativa?'0':'-1');
    el('painel-'+aba).hidden=!ativa;
  }
  if(foco)el('aba-'+nome).focus();
}
function invalidarConferencia(texto='Confira os pedidos para revisar o lote antes de iniciar.', preservar=false){
  conferencia=null;el('confirmar-copia').checked=false;
  el('conferencia-conteudo').hidden=!preservar;el('conferencia-vazia').hidden=false;el('conferencia-vazia').textContent=texto;
}
function proximaAcao(p){
  if(modo==='reimprimir')return 'Verificar gravação no Sisplan e enviar outra cópia.';
  if(!p)return 'Verificar existência no Sisplan antes de incluir.';
  if(['impressao_enviada','existente'].includes(p.etapa))return 'Conferir correspondência no Sisplan; não reincluir nem reimprimir.';
  if(p.etapa==='sem_cadastro')return 'Após corrigir o cadastro, validar os produtos novamente.';
  if(etapasAtencao.includes(p.etapa))return 'Conferir a situação; nenhuma repetição automática de ação incerta.';
  return 'Continuar a partir da etapa salva, após as verificações de segurança.';
}
async function conferirPedidos(){
  if(inicioBloqueado())return;
  const entrada=el('pedidos').value, operacao=modo;
  invalidarConferencia();enviando=true;mensagem('');atualizarBotoes();
  try{
    const c=await api('/api/conferir',{modo:operacao,pedidos:operacao==='retomar'?'':entrada});
    if(modo!==operacao||el('pedidos').value!==entrada)return;
    conferencia=c;
    const frag=document.createDocumentFragment();
    for(const item of c.pedidos){
      const tr=document.createElement('tr'),numero=document.createElement('td'),detalhe=document.createElement('td'),acao=document.createElement('small');
      numero.textContent=item.pedido;detalhe.textContent=item.salvo?item.salvo.rotulo+(item.salvo.numero?' · Sisplan '+item.salvo.numero:''):'Não consta no histórico local';
      acao.textContent=proximaAcao(item.salvo);detalhe.append(acao);tr.append(numero,detalhe);frag.append(tr);
    }
    el('itens-conferencia').replaceChildren(frag);
    el('resumo-conferencia').textContent=`${c.pedidos.length} pedido(s) para ${modo==='retomar'?'retomar':modo==='reimprimir'?'reimprimir':'processar'}`;
    el('conferencia-vazia').hidden=true;el('conferencia-conteudo').hidden=false;
    el('confirmacao-reimpressao').hidden=modo!=='reimprimir';abrirAba('conferencia',true);
  }catch(erro){mensagem(erro.message);}finally{enviando=false;atualizarBotoes();}
}

async function api(caminho, dados) {
  const resposta = await fetch(caminho, {method:dados===undefined?'GET':'POST',headers,body:dados===undefined?undefined:JSON.stringify(dados),cache:'no-store'});
  const conteudo = await resposta.json();
  if (!resposta.ok) {const erro=Error(conteudo.erro || 'Não foi possível concluir a ação.');erro.status=resposta.status;throw erro;}
  return conteudo;
}
function mensagem(texto) { el('mensagem-acao').textContent=texto; }
function mudarModo(novo) {
  if (enviando || estado?.ocupada) return;
  modo=novo; mensagem(''); el('confirmar-copia').checked=false;
  invalidarConferencia();abrirAba('pedidos');
  document.querySelectorAll('[data-modo]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.modo===modo)));
  el('campo-pedidos').hidden=modo==='retomar'; el('pedidos').required=modo!=='retomar';
  el('retomada').hidden=modo!=='retomar';el('limpar').hidden=modo==='retomar';
  el('confirmacao-reimpressao').hidden=modo!=='reimprimir';
  el('ajuda-modo').textContent=modo==='normal'?'Informe os pedidos. Os que já estão no Sisplan serão identificados antes de incluir.':modo==='retomar'?`Existem ${estado?.pendentes??0} pedido(s) pendente(s). Vamos continuar a partir da etapa salva de cada um.`:'Informe os pedidos para enviar outra cópia. Confira a impressão anterior antes de confirmar.';
  el('iniciar').textContent=modo==='normal'?'Inserir e processar':modo==='retomar'?'Retomar pendências':'Reimprimir pedidos';
  atualizarBotoes();
}
function inicioBloqueado() { return enviando||!conectado||inicioIncerto||!estado||estado.ocupada||estado.bloqueado||encerrado||estado.encerrando; }
function atualizarBotoes() {
  const bloqueado=inicioBloqueado();
  document.querySelectorAll('[data-modo]').forEach(b=>b.disabled=bloqueado);
  document.querySelectorAll('[data-reimportar]').forEach(b=>b.disabled=bloqueado);
  const entrada=analisarEntrada(el('pedidos').value);
  el('conferir').disabled=bloqueado||(modo==='retomar'?!estado?.pendentes:!entrada.pedidos.length||entrada.invalidos.length>0);
  el('iniciar').disabled=bloqueado||!conferencia||(modo==='reimprimir'&&!el('confirmar-copia').checked);
  el('limpar').disabled=bloqueado||!el('pedidos').value;
  el('pedidos').disabled=bloqueado; el('confirmar-copia').disabled=bloqueado;
  el('parar').hidden=!estado?.ocupada||['INICIANDO','ENCERRANDO','PARANDO'].includes(estado?.fase);
  el('parar').disabled=enviando||!conectado; el('encerrar').disabled=encerrado||enviando||estado?.encerrando;
  ['repetir','pular','parar-erro'].forEach(id=>el(id).disabled=enviando||!conectado);
  if(demonstracao){el('demo-cenario').disabled=bloqueado||!cenariosDemo.length;el('demo-exemplo').disabled=bloqueado||!cenariosDemo.length;}
}
function pedidosDoEscopo(){
  const lista=estado?.pedidos??[];
  if(escopo==='todos')return lista;
  const mapa=new Map(lista.map(p=>[p.pedido,p]));
  return (estado?.lote??[]).map(p=>{
    const salvo=mapa.get(p)||{pedido:p,numero:'',etapa:'',fila:'',pendente:true,rotulo:'Sem registro local',erro:''};
    const resultado=estado?.resultados_lote?.[p];
    return {...salvo,resultado:estado?.ocupada?'':resultado};
  });
}
function renderizarTabela() {
  const filtro=el('filtro').value, busca=el('busca').value.trim().toLowerCase();
  const base=pedidosDoEscopo();
  for(const fila of ['para_baixar','baixados','importados','enviados','atencao'])el('n-'+fila).textContent=estado?.fase==='INICIANDO'||estado?.bloqueado&&!base.length?'—':base.filter(p=>fila==='atencao'?exigeAtencao(p):p.fila===fila).length;
  document.querySelectorAll('[data-fila]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.fila===filtro)));
  el('alcance').textContent=escopo==='todos'?'Filas do histórico completo.':'Filas dos pedidos deste lote; situações salvas no histórico.';
  const lista=base.filter(p=>(filtro==='todos'||(filtro==='pendentes'?p.pendente:filtro==='atencao'?exigeAtencao(p):filtro==='sem_cadastro'?p.etapa==='sem_cadastro':p.fila===filtro))&&(`${p.pedido} ${p.numero}`.toLowerCase().includes(busca)));
  pagina=Math.min(pagina,Math.max(0,Math.ceil(lista.length/50)-1));
  const inicio=pagina*50, visiveis=lista.slice(inicio,inicio+50), chave=JSON.stringify([visiveis,filtro,busca,pagina,escopo,estado?.fase]);
  if(chave!==tabelaAnterior){
    tabelaAnterior=chave;
    const linhas=document.createDocumentFragment();
    for(const p of visiveis){
      const tr=document.createElement('tr');
      const resultado=p.resultado?rotuloResultado(p.resultado):'';
      [p.pedido,p.numero||'—',p.rotulo||'Conferir situação',[resultado?'Nesta execução: '+resultado:'',p.erro].filter(Boolean).join(' · ')||'—'].forEach((texto,i)=>{
        const td=document.createElement('td');
        td.setAttribute('data-rotulo',['Pedido Havan','Nº Sisplan','Situação salva','Observação / ação'][i]);
        if(i===2){const span=document.createElement('span');span.textContent=texto;span.className='situacao'+(['sem_cadastro','importacao_iniciada','gravacao_pendente','aviso_pendente','impressao_incerta'].includes(p.etapa)?' atencao':['impressao_enviada','existente'].includes(p.etapa)?' concluido':'');td.append(span);}else td.textContent=texto;
        if(i===3&&p.etapa==='sem_cadastro'){
          const botao=document.createElement('button');botao.type='button';botao.textContent='Importar novamente';
          botao.setAttribute('data-reimportar',p.pedido);botao.setAttribute('aria-label','Importar novamente o pedido '+p.pedido);
          botao.disabled=inicioBloqueado();botao.onclick=()=>importarNovamente(p.pedido);td.append(botao);
        }
        tr.append(td);
      });linhas.append(tr);
    }
    if(!visiveis.length){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=4;td.className='vazio';td.textContent=estado?.fase==='INICIANDO'?'Carregando o histórico…':estado?.bloqueado?'Histórico indisponível. Confira o aviso de andamento.':busca?'Nenhum pedido corresponde à busca.':escopo==='lote'&&!estado?.lote?.length?'Nenhum lote iniciado nesta sessão.':!base.length?'Nenhum pedido salvo. Prepare o primeiro lote.':'Nenhum pedido nesta seleção.';tr.append(td);linhas.append(tr);}
    el('linhas').replaceChildren(linhas);
  }
  el('quantidade').textContent=lista.length?`${inicio+1}–${Math.min(inicio+50,lista.length)} de ${lista.length} pedido(s)`:'Nenhum pedido nesta seleção';
  el('anterior').disabled=pagina===0;el('proxima').disabled=inicio+50>=lista.length;
}
function renderizar(s) {
  const chave=JSON.stringify(s);if(chave===estadoAnterior)return;estadoAnterior=chave;
  const anoAnterior=estado?.ano;
  estado=s; encerrado=s.fase==='ENCERRADO';
  if(anoAnterior!==s.ano){contarPedidos();el('dica-pedidos').textContent=`Separe por vírgula ou linha. Sem o ano, será utilizado ${s.ano}.`;}
  if(conferencia&&(s.revisao!==conferencia.revisao||s.ocupada))invalidarConferencia('A situação mudou. Confira novamente os pedidos antes de iniciar.');
  if(s.execucao&&s.execucao!==ultimoLote){ultimoLote=s.execucao;escopo='lote';pagina=0;el('filtro').value='todos';}
  el('escopo-lote').setAttribute('aria-pressed',String(escopo==='lote'));el('escopo-todos').setAttribute('aria-pressed',String(escopo==='todos'));
  el('n-pendentes').textContent=s.fase==='INICIANDO'||s.bloqueado&&!s.pedidos.length?'—':s.pendentes;
  el('titulo-andamento').textContent=!s.ocupada&&s.execucao?'Último lote':'Andamento do lote';
  el('fase').textContent=fases[s.fase]||s.fase;el('status').textContent=s.mensagem;
  el('codigo').textContent=s.codigo_execucao||'—';
  el('pedido-atual').textContent=s.pedido?`Pedido ${s.indice} de ${s.total}`:'As etapas concluídas ficam preservadas para retomar.';
  el('numero-atual').textContent=s.pedido||'Aguardando lote';
  const atual=s.pedidos.find(p=>p.pedido===s.pedido);
  el('etapa-atual').textContent=atual?'Último estado salvo: '+atual.rotulo:'';
  const mapa=new Map(s.pedidos.map(p=>[p.pedido,p])), lote=(s.lote??[]).map(p=>({...mapa.get(p),pendente:mapa.get(p)?.pendente??true,resultado:s.ocupada?'':s.resultados_lote?.[p]}));
  el('indicadores').hidden=!lote.length;el('total-lote').textContent=lote.length;el('pendentes-lote').textContent=lote.filter(p=>p.pendente).length;el('atencao-lote').textContent=lote.filter(exigeAtencao).length;
  el('area-progresso').hidden=!s.total;
  const resultadosConhecidos=Object.values(s.resultados_lote??{}).filter(v=>v!=='aguardando').length;
  el('posicao').textContent=s.ocupada?`Pedido ${s.indice} de ${s.total}. Etapas e pendências ficam salvas.`:`${resultadosConhecidos} de ${s.total} pedido(s) com resultado nesta execução; confira as pendências.`;
  el('progresso').max=Math.max(1,s.total);el('progresso').value=s.ocupada?Math.max(0,s.indice-1):resultadosConhecidos;
  el('orientacao').textContent=s.ocupada?'Durante a inclusão, aguarde o robô terminar antes de usar o teclado, o mouse ou a tela do Sisplan.':'O Sisplan deve estar aberto na tela 1002 — Pedido por Grade.';
  const resumo=s.resumo??{};el('resumo').hidden=!Object.keys(resumo).length;
  const pendenciasResultado=Object.entries(s.resultados_lote??{}).filter(([,v])=>!['existente','impressao_enviada'].includes(v)).length;
  if(s.fase==='CONCLUIDO'&&pendenciasResultado){el('fase').textContent='Finalizado com pendências';el('status').textContent='Processamento finalizado com pendências. Confira o resultado de cada pedido.';}
  el('fase').className='etiqueta'+(s.erro||['FALHA','INTERROMPIDO'].includes(s.fase)||pendenciasResultado&&s.fase==='CONCLUIDO'?' atencao':'');
  el('resumo').textContent=`Resultado desta execução\nImportações confirmadas: ${resumo.importacoes_confirmadas??0} · Já existentes: ${resumo.existente??0}\nImpressões enviadas: ${resumo.impressao_enviada??0} · Não processados: ${resumo.aguardando??0}\nAguardando cadastro de produto: ${resumo.sem_cadastro??0} · Outras pendências: ${Math.max(0,pendenciasResultado-(resumo.aguardando??0)-(resumo.sem_cadastro??0))}`;
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
  try{const s=await api('/api/estado');conectado=true;inicioIncerto=false;renderizar(s);atualizarBotoes();el('conexao').hidden=true;}
  catch(_){conectado=false;estadoAnterior='';invalidarConferencia('A conexão foi interrompida. Reconecte e confira novamente o lote.');el('conexao').hidden=false;const texto=encerramentoPedido?'Aplicação encerrada. Você pode fechar esta aba.':'Atualização interrompida. Os últimos dados permanecem visíveis. Aguarde a reconexão e confira o andamento antes de reenviar pedidos.';if(el('conexao').textContent!==texto)el('conexao').textContent=texto;if(encerramentoPedido){encerrado=true;pararPresenca();}atualizarBotoes();}
  if(!encerrado&&!saindo)setTimeout(atualizar,1000);
}
async function acao(caminho,dados){
  if(enviando)return;enviando=true;mensagem('');atualizarBotoes();
  try{await api(caminho,dados);renderizar(await api('/api/estado'));}
  catch(erro){mensagem(erro.message);if(caminho==='/api/iniciar'){invalidarConferencia('Confira o andamento e revise novamente o lote antes de iniciar.');if(!erro.status){inicioIncerto=true;invalidarConferencia('Envio sem confirmação. Aguarde a atualização do andamento antes de conferir outro lote.');}}}
  finally{enviando=false;atualizarBotoes();}
}
async function importarNovamente(pedido){
  if(inicioBloqueado())return;
  mudarModo('normal');el('pedidos').value=pedido;contarPedidos();await conferirPedidos();el('titulo-entrada').scrollIntoView?.({behavior:'smooth',block:'start'});
}
el('formulario').addEventListener('submit',async e=>{
  e.preventDefault();
  await conferirPedidos();
});
el('iniciar').onclick=async()=>{
  if(inicioBloqueado()||!conferencia)return;
  if(modo==='reimprimir'&&!el('confirmar-copia').checked){mensagem('Confirme que deseja enviar outra cópia.');el('confirmar-copia').focus();return;}
  const id=conferencia.id,confirmado=el('confirmar-copia').checked;
  invalidarConferencia('Última conferência enviada. Acompanhe o resultado ao lado. Uma nova execução exige nova conferência.',true);
  await acao('/api/iniciar',{modo,pedidos:modo==='retomar'?'':el('pedidos').value,confirmado,conferencia:id,solicitacao:crypto.randomUUID()});
};
el('pedidos').addEventListener('input',()=>{invalidarConferencia();contarPedidos();atualizarBotoes();});
el('confirmar-copia').addEventListener('change',atualizarBotoes);
el('limpar').onclick=()=>{if(inicioBloqueado())return;el('pedidos').value='';invalidarConferencia();contarPedidos();mensagem('');atualizarBotoes();el('pedidos').focus();};
el('editar').onclick=()=>abrirAba('pedidos',true);
for(const nome of ['pedidos','conferencia']){
  el('aba-'+nome).onclick=()=>abrirAba(nome);
  el('aba-'+nome).addEventListener('keydown',e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();abrirAba(e.key==='Home'?'pedidos':e.key==='End'?'conferencia':nome==='pedidos'?'conferencia':'pedidos',true);}});
}
for(const nome of ['lote','todos'])el('escopo-'+nome).onclick=()=>{escopo=nome;pagina=0;el('escopo-lote').setAttribute('aria-pressed',String(nome==='lote'));el('escopo-todos').setAttribute('aria-pressed',String(nome==='todos'));renderizarTabela();};
document.querySelectorAll('[data-modo]').forEach(b=>b.onclick=()=>mudarModo(b.dataset.modo));
document.querySelectorAll('[data-fila]').forEach(b=>b.onclick=()=>{el('filtro').value=b.dataset.fila;pagina=0;renderizarTabela();el('titulo-historico').scrollIntoView({behavior:'smooth',block:'start'});});
for(const id of ['busca','filtro'])el(id).addEventListener('input',()=>{pagina=0;renderizarTabela();});
el('anterior').onclick=()=>{pagina--;renderizarTabela();};el('proxima').onclick=()=>{pagina++;renderizarTabela();};
for(const [id,decisao] of [['repetir','repetir'],['pular','pular'],['parar-erro','encerrar']])el(id).onclick=()=>{if(estado?.erro)acao('/api/decidir',{execucao:estado.execucao,erro:estado.erro.id,decisao});};
el('parar').onclick=()=>{if(confirm('Parar após concluir a etapa atual com segurança? Os pedidos pendentes serão preservados.'))acao('/api/parar',{execucao:estado.execucao});};
el('encerrar').onclick=async()=>{
  if(!confirm('Encerrar Pedidos Havan? Se houver uma ação em andamento, vamos finalizá-la com segurança e preservar as pendências.'))return;
  encerramentoPedido=true;
  if(desktop&&!await salvamentoTema){encerramentoPedido=false;mensagem('Não foi possível salvar o tema. Tente alternar o tema novamente antes de encerrar.');return;}
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
const tema=window.NunesTema.iniciar({controle:el('tema'),chave:'tema-pedidos-havan',cookie:true});
if(desktop){
  tema.aplicar(document.querySelector('meta[name="havan-tema"]').content);
  el('tema').addEventListener('click',()=>{
    const valor=document.documentElement.dataset.tema;
    salvamentoTema=salvamentoTema.then(async()=>{try{await api('/api/tema',{tema:valor});mensagem('');return true;}catch(erro){mensagem('Não foi possível salvar o tema: '+erro.message);return false;}});
  });
  el('baixar-log').hidden=true;
}
if(demonstracao){
  const menu=el('demo-configuracoes');
  menu.hidden=false;
  document.addEventListener('pointerdown',e=>{if(!menu.contains(e.target))menu.open=false;});
  document.addEventListener('focusin',e=>{if(!menu.contains(e.target))menu.open=false;});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&menu.open){menu.open=false;menu.querySelector('summary').focus();}});
  const descrever=()=>{const c=cenariosDemo.find(c=>c.id===el('demo-cenario').value);if(c)el('demo-descricao').textContent=c.orientacao;};
  el('demo-cenario').addEventListener('change',descrever);
  el('demo-exemplo').onclick=()=>{
    if(inicioBloqueado())return;
    const c=cenariosDemo.find(c=>c.id===el('demo-cenario').value);if(!c)return;
    mudarModo(c.modo);el('pedidos').value=c.entrada;contarPedidos();atualizarBotoes();
    menu.open=false;el('pedidos').focus();
  };
  (async()=>{
    try{
      cenariosDemo=await api('/api/demo/cenarios');
      const opcoes=cenariosDemo.map(c=>{const o=document.createElement('option');o.value=c.id;o.textContent=c.nome;return o;});
      el('demo-cenario').replaceChildren(...opcoes);el('demo-cenario').value='geral';descrever();atualizarBotoes();
    }catch(_){el('demo-descricao').textContent='Não foi possível carregar os cenários. Reabra a demonstração.';}
  })();
}
el('tema').addEventListener('click',()=>{document.documentElement.dataset.temaAnimado='1';});
function pararPresenca(){presenca?.abort();}
async function acompanhar(){
  if(encerrado||saindo)return;presenca=new AbortController();
  try{const r=await fetch('/api/presenca',{headers,signal:presenca.signal});if(!r.ok)return;const leitor=r.body.getReader();while(!encerrado){const {done}=await leitor.read();if(done)break;}}
  catch(_){}finally{if(!encerrado&&!encerramentoPedido&&!saindo)setTimeout(acompanhar,1000);}
}
window.addEventListener('beforeunload',e=>{if(!desktop&&!encerrado&&!encerramentoPedido){e.preventDefault();e.returnValue='';}});
window.addEventListener('pagehide',()=>{
  saindo=true;pararPresenca();
  if(!desktop&&!encerrado&&!encerramentoPedido)fetch('/api/fechar',{method:'POST',headers,body:'{}',keepalive:true}).catch(()=>{});
});
window.addEventListener('pageshow',e=>{if(e.persisted)window.location.reload();});
acompanhar();atualizar();
