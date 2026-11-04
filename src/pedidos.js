'use strict';
const el = id => document.getElementById(id);
const token = document.querySelector('meta[name="havan-token"]').content;
const desktop=document.querySelector('meta[name="havan-desktop"]').content==='1';
const demonstracao=document.querySelector('meta[name="havan-demo"]').content==='1';
let salvamentoTema=Promise.resolve(true);
const headers = {Authorization: 'Bearer ' + token, 'Content-Type': 'application/json', 'X-Havan-Pagina': crypto.randomUUID()};
const fases = {INICIANDO:'Iniciando',PRONTO:'Pronto',EXECUTANDO:'Em andamento',PAUSADO:'Aguardando sua escolha',PARANDO:'Parando com segurança',CONCLUIDO:'Finalizado',INTERROMPIDO:'Parado',FALHA:'Precisa de atenção',ENCERRANDO:'Encerrando',ENCERRADO:'Encerrado'};
let estado=null, enviando=false, encerrado=false, encerramentoPedido=false, pagina=0, erroVisivel='', tabelaAnterior='', atividadeAnterior='', presenca=null;
let estadoAnterior='', saindo=false, sumarioAnterior='';
const tamanhoPagina=50;
let escopo='todos', conectado=false, inicioIncerto=false, ultimoLote='';
let cenariosDemo=[];
let consultandoImpressoras=false;
const etapasImportadas=['importado','pdf_pronto','impressao_pendente','impressao_iniciada','impressao_incerta','impressao_enviada'];
const apto=p=>p.etapa==='pronto_importar'&&!p.erro;
const iniciais=['para_baixar','baixado','sem_cadastro','pronto_importar'];
function grupoPedido(p){return apto(p)?'prontos':p.etapa==='sem_cadastro'?'sem_cadastro':p.etapa==='existente'?'existentes':etapasImportadas.includes(p.etapa)?'importados':'outras';}
const etapasAtencao=['sem_cadastro','importacao_iniciada','gravacao_pendente','aviso_pendente','impressao_incerta'];
const exigeAtencao=p=>Boolean(p.erro)||etapasAtencao.includes(p.etapa)||['falhou','rejeitado','gravacao_pendente','impressao_incerta','impressao_pendente','sem_cadastro'].includes(p.resultado);
function rotuloResultado(valor){
  return ({pronto_importar:'Pronto para importar',aguardando:'Não processado',existente:'Já existente, sem novo envio',impressao_enviada:'Enviado para impressão',sem_cadastro:'Produto sem cadastro',falhou:'Falha no processamento',rejeitado:'Pedido rejeitado',gravacao_pendente:'Gravação não confirmada',impressao_incerta:'Conferir impressão',impressao_pendente:'Impressão pendente'})[valor]||'Pendente — conferir situação';
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
async function api(caminho, dados) {
  const resposta = await fetch(caminho, {method:dados===undefined?'GET':'POST',headers,body:dados===undefined?undefined:JSON.stringify(dados),cache:'no-store'});
  const conteudo = await resposta.json();
  if (!resposta.ok) {const erro=Error(conteudo.erro || 'Não foi possível concluir a ação.');erro.status=resposta.status;throw erro;}
  return conteudo;
}
function mensagem(texto) { el('mensagem-acao').textContent=texto; }
function inicioBloqueado() { return enviando||!conectado||inicioIncerto||!estado||estado.ocupada||estado.bloqueado||encerrado||estado.encerrando; }
function atualizarBotoes() {
  const bloqueado=inicioBloqueado();
  for(const id of ['lista-impressoras','atualizar-impressoras'])el(id).disabled=bloqueado||consultandoImpressoras;
  el('confirmar-impressora').disabled=bloqueado||consultandoImpressoras||!el('lista-impressoras').value;
  document.querySelectorAll('[data-fila]').forEach(b=>b.disabled=!estado||estado.ocupada||estado.encerrando||encerrado||estado.fase==='INICIANDO');
  document.querySelectorAll('[data-acao-pedido]').forEach(b=>b.disabled=bloqueado);
  const entrada=analisarEntrada(el('pedidos').value);
  el('conferir').disabled=bloqueado||!entrada.pedidos.length||entrada.invalidos.length>0;
  atualizarImportacao();
  el('limpar').disabled=bloqueado||!el('pedidos').value;
  el('pedidos').disabled=bloqueado;
  el('parar').hidden=!estado?.ocupada||['INICIANDO','ENCERRANDO','PARANDO'].includes(estado?.fase);
  el('parar').disabled=enviando||!conectado; el('encerrar').disabled=encerrado||enviando||estado?.encerrando;
  ['repetir','pular','parar-erro'].forEach(id=>el(id).disabled=enviando||!conectado);
  if(demonstracao){el('demo-cenario').disabled=bloqueado||!cenariosDemo.length;el('demo-exemplo').disabled=bloqueado||!cenariosDemo.length;}
}
function pedidosDoEscopo(){
  const lista=estado?.pedidos??[];
  if(escopo==='todos')return lista;
  const mapa=new Map(lista.map(p=>[p.pedido,p]));
  return ((estado?.lote_preparacao?.length?estado.lote_preparacao:estado?.lote)??[]).map(p=>{
    const salvo=mapa.get(p)||{pedido:p,numero:'',etapa:'',fila:'',pendente:true,rotulo:'Sem registro local',erro:''};
    const resultado=estado?.resultados_lote?.[p];
    return {...salvo,resultado:estado?.ocupada?'':resultado};
  });
}
function atualizarImportacao(){
  const quantidade=pedidosDoEscopo().filter(apto).length;
  const rotulo=quantidade?`Importar ${quantidade} ${quantidade===1?'pedido':'pedidos'}`:'Nenhum pedido apto';
  if(el('importar-aptos').textContent!==rotulo)el('importar-aptos').textContent=rotulo;
  el('importar-aptos').disabled=inicioBloqueado()||!quantidade;
  const titulo=quantidade?`${quantidade} ${quantidade===1?'pedido pronto':'pedidos prontos'} para importar`:'Nenhum pedido pronto para importar';
  if(el('titulo-importacao').textContent!==titulo)el('titulo-importacao').textContent=titulo;
  const aviso='Antes de importar, abra o Sisplan na tela 1002 — Pedido por Grade.';
  if(el('alcance-importacao').textContent!==aviso)el('alcance-importacao').textContent=aviso;
}
function correspondeFiltro(p,filtro){
  if(filtro==='todos')return true;
  if(filtro==='pendentes')return p.pendente;
  if(filtro==='pendencias')return ['sem_cadastro','outras'].includes(grupoPedido(p));
  if(filtro==='atencao')return exigeAtencao(p);
  if(['prontos','sem_cadastro','outras','existentes','importados'].includes(filtro))return grupoPedido(p)===filtro;
  return p.fila===filtro;
}
function acaoDoPedido(p){
  if(p.etapa==='sem_cadastro')return ['revalidar','Conferir cadastro novamente'];
  if(p.etapa==='baixado'||p.etapa==='pronto_importar'&&p.erro)return ['revalidar','Conferir arquivos e produtos'];
  if(p.etapa==='para_baixar')return p.erro==='Pedido não encontrado no Portal Havan.'?null:['preparar','Baixar e conferir'];
  if(['importacao_iniciada','gravacao_pendente','aviso_pendente'].includes(p.etapa))return ['recuperar','Conferir gravação no Sisplan'];
  if(['importado','pdf_pronto','impressao_pendente'].includes(p.etapa))return ['recuperar','Retomar impressão'];
  return null;
}
function apresentacaoPedido(p){
  const motivos={existente:'Já existe no Sisplan.',baixado:'Confira os arquivos e produtos.',sem_cadastro:'Confira novamente.',importacao_iniciada:'Inclusão iniciada. Confira no Sisplan.',gravacao_pendente:'Gravação não confirmada no Sisplan.',aviso_pendente:'Duplicidade não confirmada. Confira no Sisplan.',importado:'Importação confirmada. Retome a impressão.',pdf_pronto:'PDF pronto. Retome a impressão.',impressao_pendente:'Retome a impressão.',impressao_iniciada:'Confira a fila de impressão com o responsável.',impressao_incerta:'Confira a fila de impressão com o responsável.'};
  const rotulos={para_baixar:'Aguardando preparação',baixado:'Conferência pendente',sem_cadastro:'Cadastro pendente',pronto_importar:'Pronto para importar',importacao_iniciada:'Inclusão a conferir',gravacao_pendente:'Inclusão a conferir',aviso_pendente:'Existência a conferir',importado:'Impressão pendente',pdf_pronto:'Impressão pendente',impressao_pendente:'Impressão pendente',impressao_iniciada:'Impressão a conferir',impressao_incerta:'Impressão a conferir',impressao_enviada:'Enviado para impressão',existente:'Sem ação necessária'};
  let situacao=rotulos[p.etapa]||p.rotulo||'Conferir situação';
  if(p.erro){
    if(p.etapa==='para_baixar')situacao=p.erro==='Pedido não encontrado no Portal Havan.'?'Não disponível':'Preparação pendente';
    if(['pronto_importar','existente','impressao_enviada'].includes(p.etapa))situacao='Conferência pendente';
  }
  const falhaResultado=['falhou','rejeitado'].includes(p.resultado);
  if(falhaResultado&&!p.erro)situacao='Conferência pendente';
  const resultado=p.resultado&&rotuloResultado(p.resultado)!==p.rotulo?rotuloResultado(p.resultado):'';
  let motivo=motivos[p.etapa]||'';
  if(p.erro){
    // O erro específico prevalece sobre informações genéricas de arquivos ou existência.
    // Nas etapas incertas, a orientação só sai se já estiver na mensagem.
    if(['baixado','existente'].includes(p.etapa)||p.erro.includes(motivo))motivo='';
    if(['importado','pdf_pronto','impressao_pendente','impressao_iniciada','impressao_incerta'].includes(p.etapa)&&p.erro.includes('Confira a fila de impressão com o responsável.'))motivo='';
  }
  const observacao=[p.erro||'',motivo,!p.erro&&(falhaResultado||!rotulos[p.etapa])?resultado:''].filter(Boolean).join('\n');
  return {situacao,observacao:observacao.replace(/;\s+/g,';\n').replace(/\. (?=Pedido salvo\.|Após cadastrar)/g,'.\n')||'—'};
}
function criarAcaoPedido(p,acao,rotuloVisivel){
  const [operacao,rotulo]=acao,botao=document.createElement('button');
  botao.type='button';botao.textContent=rotuloVisivel||(operacao==='preparar'?'Preparar':rotulo==='Retomar impressão'?'Imprimir':'Conferir');
  botao.setAttribute('data-acao-pedido',p.pedido);botao.setAttribute('aria-label',botao.textContent+' — '+rotulo+' — pedido '+p.pedido);
  botao.disabled=inicioBloqueado();botao.onclick=()=>executarEtapa(operacao,[p.pedido]);
  return botao;
}
function renderizarSumario(base){
  el('sumario-pedidos').hidden=!base.length;
  el('importacao-lote').hidden=!base.length;
  const chave=JSON.stringify([base,escopo,estado?.ocupada]);
  if(chave===sumarioAnterior)return;
  sumarioAnterior=chave;
  el('alcance-sumario').textContent=`${escopo==='lote'?'Lote em conferência':'Todos os pedidos salvos'} · ${base.length} ${base.length===1?'pedido':'pedidos'}${estado?.ocupada?' · em andamento':''}`;
  const linhas=document.createDocumentFragment();
  for(const p of base){
    const tr=document.createElement('tr'),pedido=document.createElement('td'),situacao=document.createElement('td'),acoes=document.createElement('td');
    const numero=document.createElement('strong'),sisplan=document.createElement('span'),etiqueta=document.createElement('span');
    numero.textContent=p.pedido;sisplan.textContent='Sisplan: '+(p.numero||'—');sisplan.className='dica';pedido.append(numero,sisplan);
    const apresentacao=apresentacaoPedido(p),atencao=exigeAtencao(p)||['falhou','rejeitado'].includes(p.resultado);
    etiqueta.textContent=p.etapa==='existente'&&!atencao?'Já existe no Sisplan':apresentacao.situacao;
    etiqueta.className='situacao'+(atencao?' atencao':['existente','impressao_enviada'].includes(p.etapa)?' concluido':'');situacao.append(etiqueta);
    let observacao=apresentacao.observacao;
    if(!atencao&&['existente','impressao_enviada','pronto_importar'].includes(p.etapa))observacao='';
    else if(p.etapa==='sem_cadastro')observacao='Cadastro precisa de revisão.';
    if(observacao&&observacao!=='—'){
      const orientacao=document.createElement('p');orientacao.className='dica orientacao-sumario';orientacao.textContent=observacao;situacao.append(orientacao);
    }
    const acao=acaoDoPedido(p);
    if(acao){
      const rotulo=acao[0]==='preparar'?'Baixar e conferir':acao[0]==='revalidar'?'Conferir novamente':acao[1]==='Retomar impressão'?'Retomar impressão':'Conferir gravação';
      acoes.append(criarAcaoPedido(p,acao,rotulo));
    }else if((!atencao&&(apto(p)||['existente','impressao_enviada'].includes(p.etapa)))||['impressao_iniciada','impressao_incerta'].includes(p.etapa)){
      const vazio=document.createElement('span');vazio.className='acao-ausente';vazio.textContent='—';vazio.setAttribute('aria-label','Nenhuma ação disponível para este pedido');acoes.append(vazio);
    }else{
      const detalhe=document.createElement('button');detalhe.type='button';detalhe.textContent='Ver detalhes';
      detalhe.setAttribute('aria-label','Ver detalhes do pedido '+p.pedido);
      detalhe.onclick=()=>{el('busca').value=p.pedido;el('filtro').value='todos';pagina=0;renderizarTabela();abrirResultados();};
      acoes.append(detalhe);
    }
    [pedido,situacao,acoes].forEach((td,i)=>td.setAttribute('data-rotulo',['Pedido / Sisplan','Situação','Ações'][i]));
    tr.append(pedido,situacao,acoes);linhas.append(tr);
  }
  el('linhas-sumario').replaceChildren(linhas);
}
function renderizarTabela() {
  const filtro=el('filtro').value, busca=el('busca').value.trim().toLowerCase();
  const semFiltros=filtro==='todos'&&!busca;
  if(semFiltros&&document.activeElement===el('limpar-filtros'))el('busca').focus();
  el('limpar-filtros').hidden=semFiltros;
  const base=pedidosDoEscopo();
  renderizarSumario(base);
  for(const grupo of ['prontos','importados','pendencias','existentes'])el('n-'+grupo).textContent=estado?.fase==='INICIANDO'||estado?.bloqueado&&!base.length?'—':base.filter(p=>correspondeFiltro(p,grupo)).length;
  atualizarImportacao();
  document.querySelectorAll('[data-fila]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.fila===filtro)));
  el('alcance').textContent=escopo==='todos'?'Estados salvos de todos os pedidos.':'Lote em conferência: inclui os pedidos separados durante o preparo.';
  const lista=base.filter(p=>correspondeFiltro(p,filtro)&&(`${p.pedido} ${p.numero}`.toLowerCase().includes(busca)));
  pagina=Math.min(pagina,Math.max(0,Math.ceil(lista.length/tamanhoPagina)-1));
  const inicio=pagina*tamanhoPagina, visiveis=lista.slice(inicio,inicio+tamanhoPagina), chave=JSON.stringify([visiveis,filtro,busca,pagina,escopo,estado?.fase]);
  if(chave!==tabelaAnterior){
    tabelaAnterior=chave;
    const linhas=document.createDocumentFragment();
    for(const p of visiveis){
      const tr=document.createElement('tr');
      const apresentacao=apresentacaoPedido(p);
      [p.pedido,p.numero||'—',apresentacao.situacao,'',apresentacao.observacao].forEach((texto,i)=>{
        const td=document.createElement('td');
        td.setAttribute('data-rotulo',['Pedido Havan','Nº Sisplan','Situação','Ação','Observação'][i]);
        if(i===2){const span=document.createElement('span');span.textContent=texto;span.className='situacao'+(['sem_cadastro','importacao_iniciada','gravacao_pendente','aviso_pendente','impressao_incerta'].includes(p.etapa)?' atencao':['impressao_enviada','existente'].includes(p.etapa)?' concluido':'');td.append(span);}else td.textContent=texto;
        const acao=acaoDoPedido(p);
        if(i===3&&acao){
          td.append(criarAcaoPedido(p,acao));
        }
        tr.append(td);
      });linhas.append(tr);
    }
    if(!visiveis.length){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=5;td.className='vazio';td.textContent=estado?.fase==='INICIANDO'?'Carregando o histórico…':estado?.bloqueado?'Histórico indisponível. Confira o aviso de andamento.':busca?'Nenhum pedido corresponde à busca.':escopo==='lote'&&!estado?.lote?.length?'Nenhum lote iniciado nesta sessão.':!base.length?'Nenhum pedido salvo. Prepare o primeiro lote.':'Nenhum pedido nesta seleção.';tr.append(td);linhas.append(tr);}
    el('linhas').replaceChildren(linhas);
  }
  el('quantidade').textContent=lista.length>tamanhoPagina?`${inicio+1}–${Math.min(inicio+tamanhoPagina,lista.length)} de ${lista.length} pedidos`:lista.length?`${lista.length} ${lista.length===1?'pedido':'pedidos'}`:'Nenhum pedido nesta seleção';
  if(lista.length<=tamanhoPagina&&[el('anterior'),el('proxima')].includes(document.activeElement))el('busca').focus();
  el('paginacao-controles').hidden=lista.length<=tamanhoPagina;
  el('anterior').disabled=pagina===0;el('proxima').disabled=inicio+tamanhoPagina>=lista.length;
  atualizarLayout();
}
function atualizarLayout(){
  const recolhida=!el('preparacao').open;
  const comSumario=!el('sumario-pedidos').hidden;
  const destino=el(recolhida&&!comSumario?'grupos-resultados':'grupos-acompanhamento');
  const grupos=el('grupos-estados');
  if(grupos.parentElement!==destino)destino.append(grupos);
  el('acompanhamento').hidden=recolhida&&!comSumario&&el('identificacao').hidden&&!estado?.ocupada&&!estado?.erro&&!estado?.bloqueado&&!['FALHA','ENCERRANDO'].includes(estado?.fase);
}
el('preparacao').addEventListener('toggle',atualizarLayout);
function renderizar(s) {
  const chave=JSON.stringify(s);if(chave===estadoAnterior)return;estadoAnterior=chave;
  const anoAnterior=estado?.ano;
  const impressoraAnterior=estado?.impressora;
  estado=s; encerrado=s.fase==='ENCERRADO';
  el('grupos-estados').setAttribute('data-finalizado',String(!s.ocupada&&Boolean(s.lote?.length)));
  el('impressora-atual').textContent=s.impressora||'Nenhuma impressora selecionada.';
  if(anoAnterior!==s.ano){contarPedidos();el('dica-pedidos').textContent=`Separe por vírgula ou linha. Sem o ano, será utilizado ${s.ano}.`;}
  if(s.execucao&&s.execucao!==ultimoLote){
    ultimoLote=s.execucao;escopo='lote';pagina=0;el('filtro').value='todos';
    const preparacao=el('preparacao');
    if(document.activeElement&&preparacao.contains(document.activeElement))el('titulo-entrada').focus();
    el('detalhes-processamento').open=false;
  }
  el('escopo-lote').setAttribute('aria-pressed',String(escopo==='lote'));el('escopo-todos').setAttribute('aria-pressed',String(escopo==='todos'));

  const preparando=['preparar','revalidar','normal','retomar'].includes(s.modo);
  el('titulo-andamento').textContent=s.ocupada?(preparando?'Conferindo pedidos':'Importação e impressão'):s.execucao?(preparando?'Resultado da conferência':'Resultado da execução'):'Etapas do lote';
  el('fase').textContent=fases[s.fase]||s.fase;
  el('status').textContent=s.fase==='EXECUTANDO'?(preparando?'Conferindo duplicidade, arquivos e cadastro dos produtos.':'Processamento em curso. As etapas ficam salvas para conferência.'):s.mensagem;
  const ultimoProcessado=s.pedido||(s.lote??[]).slice().reverse().find(p=>s.resultados_lote?.[p]&&s.resultados_lote[p]!=='aguardando');
  const pedidoExibido=s.ocupada?s.pedido:ultimoProcessado;
  el('detalhes-processamento').hidden=s.ocupada||!pedidoExibido||Boolean(s.erro);
  el('identificacao').hidden=!pedidoExibido;
  el('codigo').textContent=s.codigo_execucao||'—';
  el('pedido-atual').textContent=s.ocupada?`Pedido ${s.indice} de ${s.total}`:'Último pedido processado';
  el('numero-atual').textContent=pedidoExibido||'Aguardando lote';
  const atual=s.pedidos.find(p=>p.pedido===pedidoExibido);
  el('estado-atual').hidden=!atual;
  el('etapa-atual').textContent=atual?.rotulo||'';
  const mapa=new Map(s.pedidos.map(p=>[p.pedido,p])), lote=(s.lote??[]).map(p=>({...mapa.get(p),pendente:mapa.get(p)?.pendente??true,resultado:s.ocupada?'':s.resultados_lote?.[p]}));
  el('indicadores').hidden=!lote.length;el('total-lote').textContent=lote.length;el('pendentes-lote').textContent=lote.filter(p=>p.pendente).length;el('atencao-lote').textContent=lote.filter(exigeAtencao).length;
  el('area-progresso').hidden=!s.total;
  const resultadosConhecidos=Object.values(s.resultados_lote??{}).filter(v=>v!=='aguardando').length;
  el('posicao').textContent=s.ocupada?`Pedido ${s.indice} de ${s.total}. Etapas e pendências ficam salvas.`:`${resultadosConhecidos} de ${s.total} pedido(s) com resultado nesta execução; confira as pendências.`;
  el('progresso').max=Math.max(1,s.total);el('progresso').value=s.ocupada?Math.max(0,s.indice-1):resultadosConhecidos;
  el('orientacao').textContent=s.ocupada?'Durante a inclusão, aguarde o robô terminar antes de usar o teclado, o mouse ou a tela do Sisplan.':'O Sisplan deve estar aberto na tela 1002 — Pedido por Grade.';
  el('orientacao').hidden=preparando||!s.ocupada;
  const pendenciasResultado=Object.entries(s.resultados_lote??{}).filter(([,v])=>!['pronto_importar','existente','impressao_enviada'].includes(v)).length;
  if(s.fase==='CONCLUIDO'&&pendenciasResultado){el('fase').textContent='Finalizado com pendências';el('status').textContent='Processamento finalizado com pendências. Confira o resultado de cada pedido.';}
  if(s.fase==='CONCLUIDO'&&!pendenciasResultado)el('status').textContent='Processamento finalizado. Confira abaixo os estados salvos e os resultados por pedido.';
  if(s.fase==='CONCLUIDO'&&preparando){el('status').textContent='Conferência concluída. Revise os grupos abaixo e importe os pedidos aptos quando estiver pronto.';el('fase').textContent=pendenciasResultado?'Conferido com pendências':'Conferido';}
  el('fase').className='etiqueta'+(s.erro||['FALHA','INTERROMPIDO'].includes(s.fase)||pendenciasResultado&&s.fase==='CONCLUIDO'?' atencao':'');
  el('aviso-erro').hidden=!s.erro;
  if(s.erro){
    el('erro-pedido').textContent='Pedido: '+s.erro.pedido;el('erro-mensagem').textContent=s.erro.mensagem;
    el('repetir').hidden=!s.erro.repetir;el('pular').hidden=!s.erro.pular;
    el('repetir').textContent=s.erro.reconectar?'Reconectar e continuar':'Corrigi o problema · tentar novamente';
    el('erro-seguranca').textContent=s.erro.configuracao?'Pare este processamento. Os ajustes do arquivo serão aplicados na próxima solicitação desta etapa.':s.erro.repetir?'Nenhuma nova tentativa será feita sem sua escolha.':s.erro.pular?'Confira a fila de impressão com o responsável.':'Solicite ajuda ao responsável para conferir o Sisplan antes de iniciar outra inclusão.';
    if(erroVisivel!==s.erro.id){erroVisivel=s.erro.id;el('titulo-erro').focus();}
  } else erroVisivel='';
  const atividade=JSON.stringify(s.mensagens);
  if(atividade!==atividadeAnterior){atividadeAnterior=atividade;const frag=document.createDocumentFragment();for(const texto of s.mensagens??[]){const li=document.createElement('li');li.textContent=texto;frag.append(li);}el('atividade').replaceChildren(frag);}
  atualizarBotoes();renderizarTabela();
}
async function atualizar() {
  if(encerrado||saindo)return;
  try{const s=await api('/api/estado');conectado=true;inicioIncerto=false;renderizar(s);atualizarBotoes();el('conexao').hidden=true;}
  catch(_){conectado=false;estadoAnterior='';mensagem('A conexão foi interrompida. Reconecte e confira novamente o lote.');el('conexao').hidden=false;const texto=encerramentoPedido?'Aplicação encerrada. Você pode fechar esta aba.':'Atualização interrompida. Os últimos dados permanecem visíveis. Aguarde a reconexão e confira o andamento antes de reenviar pedidos.';if(el('conexao').textContent!==texto)el('conexao').textContent=texto;if(encerramentoPedido){encerrado=true;pararPresenca();}atualizarBotoes();}
  if(!encerrado&&!saindo)setTimeout(atualizar,1000);
}
async function acao(caminho,dados){
  if(enviando)return;enviando=true;mensagem('');atualizarBotoes();
  try{await api(caminho,dados);renderizar(await api('/api/estado'));}
  catch(erro){mensagem(erro.message);if(caminho==='/api/iniciar'){mensagem('Confira o andamento e revise novamente o lote antes de iniciar.');if(!erro.status){inicioIncerto=true;mensagem('Envio sem confirmação. Aguarde a atualização do andamento antes de conferir outro lote.');}}}
  finally{enviando=false;atualizarBotoes();}
}
async function executarEtapa(operacao,pedidos){
  if(inicioBloqueado()||!pedidos.length)return;
  const lista=[...new Set(pedidos)].join('\n');
  enviando=true;mensagem('');atualizarBotoes();
  let iniciando=false;
  try{
    const c=await api('/api/conferir',{modo:operacao,pedidos:lista});
    if(!conectado||estado?.ocupada||estado?.encerrando||saindo)throw Error('A situação mudou. Aguarde a atualização e solicite a ação novamente.');
    iniciando=true;
    await api('/api/iniciar',{modo:operacao,pedidos:lista,conferencia:c.id,solicitacao:crypto.randomUUID(),impressora:estado?.impressora});
    renderizar(await api('/api/estado'));
    if(operacao==='importar')window.scrollTo({top:0,behavior:'smooth'});
  }catch(erro){
    mensagem(erro.message);
    if(iniciando&&!erro.status){inicioIncerto=true;mensagem('Envio sem confirmação. Aguarde a atualização dos estados antes de tentar novamente.');}
  }finally{enviando=false;atualizarBotoes();}
}
el('formulario').addEventListener('submit',async e=>{
  e.preventDefault();
  const entrada=contarPedidos();if(entrada.invalidos.length)return;
  await executarEtapa('preparar',entrada.pedidos);
});
el('importar-aptos').onclick=()=>executarEtapa('importar',pedidosDoEscopo().filter(apto).map(p=>p.pedido));
const contemLetras=texto=>/[\p{L}\p{M}]/u.test(texto);
let entradaAnterior={valor:'',inicio:0,fim:0};
el('pedidos').addEventListener('beforeinput',e=>{
  const campo=el('pedidos');
  entradaAnterior={valor:campo.value,inicio:campo.selectionStart,fim:campo.selectionEnd};
  if(contemLetras(e.data||''))e.preventDefault();
});
el('pedidos').addEventListener('paste',e=>{
  if(contemLetras(e.clipboardData?.getData('text')||''))e.preventDefault();
});
el('pedidos').addEventListener('input',()=>{
  const campo=el('pedidos');
  if(contemLetras(campo.value)){
    campo.value=entradaAnterior.valor;campo.setSelectionRange(entradaAnterior.inicio,entradaAnterior.fim);return;
  }
  entradaAnterior={valor:campo.value,inicio:campo.selectionStart,fim:campo.selectionEnd};
  contarPedidos();atualizarBotoes();
});
el('limpar').onclick=()=>{if(inicioBloqueado())return;el('pedidos').value='';contarPedidos();mensagem('');atualizarBotoes();el('pedidos').focus();};
function abrirResultados(){el('titulo-historico').focus();el('titulo-historico').scrollIntoView({behavior:'smooth',block:'start'});}
for(const nome of ['lote','todos'])el('escopo-'+nome).onclick=()=>{escopo=nome;pagina=0;el('escopo-lote').setAttribute('aria-pressed',String(nome==='lote'));el('escopo-todos').setAttribute('aria-pressed',String(nome==='todos'));renderizarTabela();};
document.querySelectorAll('[data-fila]').forEach(b=>b.onclick=()=>{if(b.disabled)return;el('preparacao').open=false;atualizarLayout();el('filtro').value=el('filtro').value===b.dataset.fila?'todos':b.dataset.fila;pagina=0;renderizarTabela();abrirResultados();});
el('limpar-filtros').onclick=()=>{el('busca').value='';el('filtro').value='todos';pagina=0;renderizarTabela();};
for(const id of ['busca','filtro'])el(id).addEventListener('input',()=>{pagina=0;renderizarTabela();});
el('anterior').onclick=()=>{pagina--;renderizarTabela();};el('proxima').onclick=()=>{pagina++;renderizarTabela();};
for(const [id,decisao] of [['repetir','repetir'],['pular','pular'],['parar-erro','encerrar']])el(id).onclick=()=>{if(estado?.erro)acao('/api/decidir',{execucao:estado.execucao,erro:estado.erro.id,decisao});};
el('parar').onclick=()=>{if(confirm('Parar após concluir a etapa atual com segurança? Os pedidos pendentes serão preservados.'))acao('/api/parar',{execucao:estado.execucao});};
el('encerrar').onclick=async()=>{
  if(!confirm('Encerrar Pedidos Havan? Se houver uma ação em andamento, vamos finalizá-la com segurança e preservar as pendências.'))return;
  encerramentoPedido=true;
  if(desktop&&!await salvamentoTema){encerramentoPedido=false;mensagem('Não foi possível salvar o tema. Tente alternar o tema novamente antes de encerrar.');return;}
  try{await api('/api/encerrar',{});el('status').textContent='Encerrando com segurança. Aguarde a conclusão da etapa atual.';el('encerrar').disabled=true;}
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
  catch(_){mensagem('Não consegui copiar. Informe ao suporte o código de execução em Configurações → Atividade e diagnóstico.');}
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
const menu=el('demo-configuracoes');
document.addEventListener('pointerdown',e=>{if(!menu.contains(e.target))menu.open=false;});
document.addEventListener('focusin',e=>{if(!menu.contains(e.target))menu.open=false;});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&menu.open){menu.open=false;menu.querySelector('summary').focus();}});
async function carregarImpressoras(){
  if(inicioBloqueado()||consultandoImpressoras)return;
  const anterior=el('lista-impressoras').value;
  consultandoImpressoras=true;atualizarBotoes();el('erro-impressora').textContent='';
  el('aviso-impressora').textContent='Consultando as impressoras…';
  el('lista-impressoras').replaceChildren();
  try{
    const r=await api('/api/impressoras');
    for(const nome of r.impressoras){const o=document.createElement('option');o.value=nome;o.textContent=nome;el('lista-impressoras').append(o);}
    el('lista-impressoras').value=r.impressoras.includes(anterior)?anterior:r.impressoras.includes(r.impressora)?r.impressora:'';
    el('aviso-impressora').textContent=r.aviso_impressora||'';
  }catch(erro){el('erro-impressora').textContent=erro.message;el('aviso-impressora').textContent='Use Atualizar lista para tentar novamente.';}
  finally{consultandoImpressoras=false;atualizarBotoes();}
}
menu.addEventListener('toggle',()=>{if(menu.open)carregarImpressoras();});
el('atualizar-impressoras').onclick=carregarImpressoras;
el('lista-impressoras').addEventListener('change',atualizarBotoes);
el('confirmar-impressora').onclick=async()=>{
  if(inicioBloqueado()||consultandoImpressoras||!el('lista-impressoras').value)return;
  enviando=true;atualizarBotoes();el('erro-impressora').textContent='';
  try{
    await api('/api/impressora',{impressora:el('lista-impressoras').value});
    renderizar(await api('/api/estado'));
    el('aviso-impressora').textContent='Impressora selecionada.';
  }catch(erro){el('erro-impressora').textContent=erro.message;}
  finally{enviando=false;atualizarBotoes();}
};
if(demonstracao){
  el('demo-opcoes').hidden=false;
  const descrever=()=>{const c=cenariosDemo.find(c=>c.id===el('demo-cenario').value);if(c)el('demo-descricao').textContent=c.orientacao;};
  el('demo-cenario').addEventListener('change',descrever);
  el('demo-exemplo').onclick=()=>{
    if(inicioBloqueado())return;
    const c=cenariosDemo.find(c=>c.id===el('demo-cenario').value);if(!c)return;
    el('preparacao').open=true;mensagem('');el('pedidos').value=c.entrada;contarPedidos();atualizarBotoes();
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
