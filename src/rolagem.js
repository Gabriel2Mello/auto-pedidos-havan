'use strict';
// Adaptação local da rolagem da Impressão de OPs para as regiões da Havan.
(() => {
  if (!window.ResizeObserver || !window.PointerEvent) return;
  const alvos = [document.documentElement, ...document.querySelectorAll('#pedidos,.rolagem-conferencia,#atividade,.menu-configuracoes')];
  let quadro = 0;
  const barras = alvos.map(alvo => {
    const trilho = document.createElement('div'), polegar = document.createElement('div');
    trilho.className = 'barra-rolagem';
    trilho.setAttribute('aria-hidden', 'true');
    polegar.className = 'barra-rolagem-polegar';
    trilho.append(polegar);
    // Mantém o indicador na camada do diálogo e dentro do menu, para que
    // arrastá-lo não seja interpretado como um clique fora das configurações.
    (alvo.matches('dialog,.menu-configuracoes') ? alvo : document.body).append(trilho);
    alvo.classList.add('rolagem-sobreposta');
    const pagina = alvo === document.documentElement;
    if (pagina) trilho.classList.add('barra-rolagem-pagina');
    if (alvo.matches('.rolagem-sumario')) trilho.classList.add('barra-rolagem-sumario');
    let percurso = 0, maximo = 0, arraste = null;
    let ocultacao = 0, sobrePolegar = false;
    function mostrar() {
      if (!pagina) return;
      trilho.classList.add('ativa');
      clearTimeout(ocultacao);
      if (!arraste && !sobrePolegar) {
        ocultacao = setTimeout(() => trilho.classList.remove('ativa'), 1200);
      }
    }
    if (pagina) {
      polegar.addEventListener('pointerenter', () => {sobrePolegar = true; mostrar();});
      polegar.addEventListener('pointerleave', () => {sobrePolegar = false; mostrar();});
      mostrar();
    }
    function medir() {
      const rect = alvo.getBoundingClientRect();
      const altura = pagina ? innerHeight : alvo.clientHeight;
      const topoReal = pagina ? 0 : rect.top + alvo.clientTop;
      const topo = Math.max(0, topoReal);
      const fim = pagina ? innerHeight : Math.min(innerHeight, rect.top + alvo.clientTop + altura);
      const visivel = Math.max(0, fim - topo);
      maximo = Math.max(0, alvo.scrollHeight - altura);
      const detalhes = alvo.closest('details'), dialogo = alvo.closest('dialog');
      const oculta = !maximo || !visivel || (!pagina && getComputedStyle(alvo).overflowY === 'visible')
        || (!pagina && detalhes && !detalhes.open) || (!pagina && dialogo && !dialogo.open);
      if (oculta) return {oculta:true};
      // A geometria acompanha a região inteira; só a pintura é recortada pela janela.
      const tamanho = Math.min(altura, Math.max(32, altura * altura / alvo.scrollHeight));
      percurso = altura - tamanho;
      // A largura CSS também está disponível quando o trilho está oculto.
      const larguraBarra = parseFloat(getComputedStyle(trilho).width) || 10;
      const limiteDireito = document.documentElement.clientWidth - larguraBarra;
      let esquerda = pagina ? limiteDireito : rect.right - alvo.clientLeft - larguraBarra;
      if (alvo.matches('.rolagem-sumario')) {
        // O afastamento de 4 px segue a referência e é medido até o traço visível.
        const estiloPolegar = getComputedStyle(polegar);
        const larguraPolegar = parseFloat(estiloPolegar.width);
        const inicioPolegar = larguraBarra - larguraPolegar - parseFloat(estiloPolegar.right);
        esquerda = Math.min(rect.right - alvo.clientLeft + 4 - inicioPolegar, limiteDireito - inicioPolegar - larguraPolegar);
      }
      return {oculta:false,topo,esquerda,
        altura:visivel,tamanho,posicao:topoReal-topo+percurso*alvo.scrollTop/maximo};
    }
    function desenhar(medida) {
      if (trilho.hidden !== medida.oculta) trilho.hidden = medida.oculta;
      if (medida.oculta) return;
      const definir = (estilo, propriedade, valor) => {if(estilo[propriedade]!==valor)estilo[propriedade]=valor;};
      definir(trilho.style,'transform',`translate(${medida.esquerda}px, ${medida.topo}px)`);
      definir(trilho.style,'height',medida.altura+'px');
      definir(polegar.style,'height',medida.tamanho+'px');
      definir(polegar.style,'transform',`translateY(${medida.posicao}px)`);
    }
    polegar.addEventListener('pointerdown', evento => {
      if (evento.button !== 0 || !evento.isPrimary) return;
      evento.preventDefault();
      arraste = {y:evento.clientY, topo:alvo.scrollTop};
      mostrar();
      polegar.setPointerCapture(evento.pointerId);
    });
    polegar.addEventListener('pointermove', evento => {
      if (!arraste || !percurso) return;
      alvo.scrollTop = arraste.topo + (evento.clientY - arraste.y) * maximo / percurso;
      agendar();
    });
    for (const nome of ['pointerup', 'pointercancel', 'lostpointercapture']) {
      polegar.addEventListener(nome, () => { arraste = null; mostrar(); });
    }
    polegar.addEventListener('wheel', evento => {
      if (evento.ctrlKey || !evento.cancelable) return;
      const fator = evento.deltaMode === 1 ? 20 : evento.deltaMode === 2 ? (pagina ? innerHeight : alvo.clientHeight) : 1;
      const y=evento.deltaY*fator,x=evento.deltaX*fator;
      const podeRolar=(delta,posicao,maximo)=>delta<0?posicao>1:delta>0&&posicao<maximo-1;
      // No limite, deixa o navegador continuar a página. O menu preserva
      // sua contenção nativa; Ctrl+roda continua disponível para zoom.
      if(!podeRolar(y,alvo.scrollTop,alvo.scrollHeight-alvo.clientHeight)&&!podeRolar(x,alvo.scrollLeft,alvo.scrollWidth-alvo.clientWidth))return;
      evento.preventDefault();
      alvo.scrollBy({top:y,left:x});
    }, {passive:false});
    return {alvo, medir, desenhar, mostrar};
  });
  function agendar() {
    if (quadro) return;
    quadro = requestAnimationFrame(() => {
      quadro = 0;
      // Todas as leituras precedem as escritas, evitando recálculos entre barras.
      const medidas = barras.map(barra => barra.medir());
      barras.forEach((barra, indice) => barra.desenhar(medidas[indice]));
    });
  }
  const tamanhos = new ResizeObserver(agendar);
  barras.forEach(barra => tamanhos.observe(barra.alvo));
  const conteudo = new MutationObserver(mudancas => {
    if (mudancas.some(mudanca => !mudanca.target.closest?.('.barra-rolagem'))) agendar();
  });
  // Os trilhos ficam fora das regiões observadas, exceto no diálogo;
  // ali ignoramos as alterações de posição do próprio indicador.
  for (const regiao of document.querySelectorAll('main,header,dialog')) {
    conteudo.observe(regiao, {subtree:true, childList:true, characterData:true, attributes:true, attributeFilter:['hidden','class','open']});
  }
  document.addEventListener('toggle', agendar, true);
  document.addEventListener('close', agendar, true);
  document.addEventListener('scroll', evento => {
    if (evento?.target === document || evento?.target === document.documentElement) barras[0].mostrar();
    agendar();
  }, true);
  document.addEventListener('pointermove', evento => {
    if (evento.clientX >= document.documentElement.clientWidth - 10) barras[0].mostrar();
  }, {passive:true});
  document.addEventListener('input', agendar);
  window.addEventListener('resize', agendar);
  document.fonts.ready.then(agendar);
  agendar();
})();
