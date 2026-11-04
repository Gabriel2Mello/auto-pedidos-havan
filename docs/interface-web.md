# Interface local de Pedidos Havan

Implementada em 15/10/2026, seguindo o modelo de uso local do contas-receber.
O navegador mostra o painel; a automação continua executando no Windows do
operador, com Sisplan, impressora, histórico e configurações dessa instalação.

## Preparação pelo responsável

Use Python 3.13 de 32 bits, compatível com a automação Win32 já utilizada.
Na pasta do projeto, com esse Python instalado e disponível pelo launcher:

```powershell
py -3.13-32 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\"Criar Atalho Pedidos Havan.ps1"
```

Configure `config.toml`, o perfil de banco e as variáveis de ambiente conforme
o README. O painel não cria nem distribui credenciais. Para atualizações,
preserve `config.toml`, `estado-pedidos.sqlite3`, os pedidos e os logs.

O script gera `Abrir Pedidos Havan.lnk` nesta pasta, usando `icons/icone.ico`.
O atalho aponta diretamente para `Pedidos Havan.exe` ou, se ele não existir,
para o `pythonw.exe` de `.venv` ou `venv32`, com `havan.py` como argumento.
Esse formato permite fixar o atalho na barra de tarefas do Windows.
Pode ser copiado para a área de trabalho. Gere novamente se mudar o projeto
de pasta ou alterar o executável/ambiente Python usado. O arquivo `.lnk` é
específico da máquina e não é versionado. Também é possível abrir diretamente
`Abrir Pedidos Havan.cmd`, que procura `Pedidos Havan.exe` na mesma pasta,
depois `.venv` e por último `venv32`. O executável tem prioridade quando presente.
O programa abre tendo esta pasta como diretório de trabalho.

Em 15/10/2026, o `.venv` local foi criado com Python 3.13.13 de 32 bits e as
dependências de `requirements.txt`. Nesse ambiente, `pip check` não encontrou
conflitos, a importação dos módulos passou e os 156 testes automatizados passaram
com integrações simuladas. A validação operacional com Sisplan real
continua pendente. Não foi gerado um executável novo. O comando antigo de
empacotamento de `main.py` gera o modo console; a interface usa `havan.py` e
também precisa dos arquivos HTML/CSS/JS e ícones no pacote de distribuição.

## Uso pelo operador

1. Em **1. Informar pedidos**, digite números separados por vírgula ou linha.
   O contador elimina repetições e entradas inválidas bloqueiam o envio.
2. Clique em **Baixar e conferir**. A aplicação salva a lista, consulta duplicidade
   no banco e separa os já existentes antes do download. Para os novos, confere
   XML/PDF e todos os EANs. Esta etapa não abre a inclusão no Sisplan nem imprime;
   não exige impressora ou Sumatra configurados.
3. No **Sumário dos pedidos**, abaixo dos cartões, confira pedido Havan,
   número Sisplan, situação e ações. A orientação fica junto da situação; a coluna
   **Ações** contém somente o comando disponível, sem repetir instruções.
   As ações de preparação, conferência
   e recuperação também ficam nessa tabela compacta. Use **2. Conferir resultados**
   para consultar observações, erros, buscar e filtrar a lista pelos grupos:
   **Prontos para importar**, **Produtos sem cadastro**, **Outras pendências**,
   **Já existentes** e **Importados**. EAN ausente ou ambíguo bloqueia o pedido
   inteiro; os outros pedidos continuam sendo conferidos. Falha de banco, sessão
   ou configuração exige decisão e não é tratada como cadastro ausente.
4. Abra o Sisplan na tela 1002 — Pedido por Grade e clique em **Importar N pedidos
   aptos**. O botão inclui todos os aptos do escopo escolhido (lote em conferência
   ou histórico completo); busca e filtros só alteram a visualização. A aplicação
   revalida arquivos/EANs e consulta duplicidade novamente antes de incluir.
5. Durante a importação, deixe o Sisplan em primeiro plano e aguarde sem usar
   mouse ou teclado. Depois, confira os estados e os números internos na lista.
   Importação confirmada e impressão pendente são estados distintos.

Na tabela, **Situação** resume a condição atual; **Observação** explica a pendência
e a próxima providência. As etapas internas de recuperação continuam preservadas.
Pedidos ausentes no portal aparecem como **Não disponível**, sem ação. Pedidos
já existentes aparecem como **Sem ação necessária**, com o motivo na observação.
Erros posteriores continuam visíveis, inclusive em etapas anteriormente concluídas.
Arquivos baixados ainda exigem conferência; importação confirmada e PDF pronto
aparecem como **Impressão pendente**. Envio iniciado sem confirmação fica como
**Impressão a conferir**, sem presumir que a impressão continua em andamento.

Na tabela detalhada, os botões da coluna Ação usam **Preparar**, **Conferir** e **Imprimir**,
com descrição completa para leitores de tela. Não há função de reimpressão.

As próximas ações ficam na linha do pedido (as descrições abaixo explicam os botões):

| Situação | Ação |
| --- | --- |
| Produto sem cadastro | Corrija os EANs indicados e use **Conferir cadastro novamente**. Os arquivos são reaproveitados; depois, solicite a importação dos aptos. |
| Arquivos baixados a conferir | **Conferir arquivos e produtos** revalida sem download nem inclusão. |
| Download ausente ou inválido | **Baixar e conferir** obtém os arquivos novamente. |
| Inclusão incerta | **Conferir gravação no Sisplan** reconcilia a gravação; não abre nova inclusão. Enquanto houver inclusão incerta, a importação de novos pedidos fica bloqueada. |
| Importado, impressão pendente | **Retomar impressão**, sem reincluir o pedido. |
| Impressão incerta | Confira a fila de impressão com o responsável. Não há ação de reenvio. |

A faixa de importação fica na coluna esquerda, abaixo de **Baixar e conferir** e
**Limpar**, com a quantidade de pedidos prontos e a orientação para abrir a tela
1002 do Sisplan. **Detalhes do processamento** fica logo abaixo dessa faixa.
Ambos ficam fora da entrada recolhível, mantendo a importação acessível quando
**1. Informar pedidos** é recolhido. À direita, o sumário vem diretamente abaixo
dos cartões. No sumário, os botões são **Baixar e conferir**, **Conferir novamente**,
**Conferir gravação** ou **Retomar impressão**, conforme a etapa. **Ver detalhes**
localiza o pedido na conferência completa quando não há ação de recuperação.
Pedidos aptos, já existentes e enviados para impressão exibem apenas um traço
na coluna de ações. Nas impressões incertas, a orientação permanece junto da
situação e não há botão de reenvio. A coluna de ações fica alinhada à direita;
em áreas estreitas, os campos continuam empilhados com seus rótulos.
No sumário, as situações usam texto colorido com marcador circular, sem fundo de
etiqueta. **Cadastro pendente** traz a orientação curta **Cadastro precisa de
revisão.**; os EANs, produtos e a mensagem completa continuam na tabela detalhada
de **2. Conferir resultados**. As orientações de inclusão ou impressão incerta
continuam visíveis no próprio sumário.
Após iniciar a importação, a página sobe suavemente até o topo, preservando a entrada expandida ou
recolhida, para acompanhar o pedido. O botão informa quantos pedidos estão aptos e fica desabilitado com o texto
**Nenhum pedido apto** quando não há aptos no escopo. Observações que apenas
repetem a situação salva são omitidas; erros e resultados diferentes permanecem.

A entrada permanece à esquerda durante a execução e pode ser recolhida pelo título.
Os quatro cartões **Importar**, **Importados**, **Pendências** e **Já existentes**
aparecem uma única vez, abaixo da faixa do pedido, seguidos pelo sumário compacto,
e continuam filtrando a tabela detalhada no escopo
selecionado. O sumário e a importação usam todos os pedidos desse escopo (lote em
conferência ou histórico completo), independentemente da busca, filtro e página
dos detalhes. O cabeçalho do sumário identifica esse alcance. Pedidos ainda sem
registro local também aparecem durante a conferência. Listas longas têm rolagem
sobreposta, sem reservar faixa; em colunas estreitas, os campos se empilham com
rótulos. Inclusões e impressões incertas preservam suas orientações e bloqueios.
Ao navegar para os detalhes de um pedido ou grupo, o foco acompanha o título.
O cartão **Pendências** soma os grupos **Produtos sem cadastro** e **Outras
pendências**, que continuam disponíveis separadamente no filtro detalhado.
Os cartões ficam em uma linha quando há espaço e em duas colunas nas áreas estreitas.
O mostrador exibe o pedido atual e a última etapa salva. Ao terminar, mantém o
último pedido processado nesta execução, inclusive quando ficou pendente,
identificado pelo estado salvo. Os detalhes ficam expansíveis após o término; decisões de segurança permanecem visíveis.
Durante a execução, o botão de parada e a orientação ficam na mesma linha
quando há espaço, com quebra em janelas menores. Ao recolher a entrada, a faixa do último pedido permanece visível após o término.
O acompanhamento só fica oculto quando ainda não há pedido para exibir. Nesse caso,
os quatro cartões passam para a conferência, acima da busca. Com pedidos no escopo,
os cartões e o sumário permanecem no acompanhamento; a importação continua
acessível na área de comandos mesmo com a entrada recolhida.
Durante execução, pausa por erro ou
falha, o acompanhamento continua acessível. A seleção de escopo fica junto aos
filtros, alinhada à direita quando há espaço. **Limpar filtros** limpa a busca,
seleciona todos os grupos e retorna à primeira página, preservando o escopo.
Clicar em um cartão de estado recolhe a entrada e aplica o grupo na conferência.
Os cartões ficam desabilitados durante a execução, inclusive nas pausas por erro,
e são liberados após concluir ou interromper o processamento com segurança.
A seção “Resumo da execução” foi removida. Os pedidos
separados no preparo continuam no escopo de conferência após importar os aptos.
Ao reabrir a aplicação, os estados persistidos aparecem em **Todos os pedidos
salvos**, inclusive os prontos para importar; o escopo do lote é da sessão.

Use **Parar após a etapa atual** para preservar as pendências, ou **Encerrar**
para sair. Em **Configurações**, abaixo dos controles da impressora,
**Atividade e diagnóstico** reúne o código de execução, cópia do
resumo de suporte e acesso ao log. “Enviado para impressão” confirma apenas
retorno de sucesso do SumatraPDF, sem comprovar a saída física do papel.

### Contrato do fluxo em etapas

`preparar` baixa e valida; `revalidar` só confere arquivos locais e cadastro;
`importar` aceita apenas pedidos `pronto_importar` sem erro; `recuperar` aceita
somente etapas pós-inclusão/incertas. Solicitações de reimpressão são recusadas.
Todas as ações passam por `/api/conferir` (snapshot local) e `/api/iniciar`, com
revisão e identificador de solicitação. A consulta local não substitui a validação
real no serviço. Os modos HTTP antigos `normal` e `retomar` ficam limitados à
preparação, evitando importação implícita por uma página antiga.

`pronto_importar` é persistido no histórico existente, sem apagar ou converter
pedidos antigos automaticamente. “Baixado” não significa apto: é preciso conferir
os produtos. A nova versão precisa ser usada para ler esse estado; executáveis
antigos devem ser reconstruídos. O console mantém seu fluxo legado, com validação
imediatamente antes de incluir; a separação em três etapas é do painel desktop/web.

## Persistência e encerramento

A lista de Baixar e conferir é salva antes de confirmar o recebimento na página. Um único
executor possui o SQLite e executa o lote; outras abas acompanham a mesma
operação. Cliques simultâneos, solicitações repetidas e respostas a avisos
antigos são recusados. A trava existente impede outra execução na mesma pasta,
inclusive pelo console. A tela pode ser recarregada sem reenviar o lote.

Ao tentar fechar sem usar Encerrar, a página solicita a confirmação nativa
do navegador, inclusive quando não há processamento. O navegador só permite
esse aviso após alguma interação com a página, como um clique.
Ao confirmar o fechamento da última aba ou janela, a página avisa o programa para encerrar
automaticamente. Há uma tolerância de cerca de um segundo para permitir
recarregamentos. Se o aviso falhar, a desconexão da página é detectada e há
uma tolerância de cinco segundos, permitindo reconexões transitórias.
Se estiver incluindo um pedido,
termina a confirmação da gravação antes de parar, preservando a impressão
pendente. Não força o encerramento de uma ação em andamento. Ao reabrir, use
Retomar. Se o navegador não chegar a conectar, o prazo inicial é de dois minutos.
O encerramento pode demorar enquanto uma integração termina sua etapa atual.
Se o atalho for reaberto durante a liberação do histórico, a nova execução
aguarda até dez segundos. Caso outra execução continue aberta ou terminando
uma etapa, o painel informa essa situação sem confundi-la com falha de gravação.
O painel só redesenha o andamento quando os dados mudam.

A pré-validação no banco, conferência de barras/itens e o tratamento de “Aviso”
como última barreira de duplicidade foram preservados. Inclusões incertas
continuam bloqueadas; a liberação especializada por `--reiniciar` permanece no
console, após a conferência prevista no README.

## Contrato HTTP de recusa — E8

O adaptador mantém a exigência de Host local, token e Origin nas ações. Se o
cliente receber a resposta, falha de autorização é **403**; enquadramento,
JSON/tipo ou corpo inválido é **400**. Conflitos de execução continuam em 409.
Não se inicia uma ação antes dessas verificações. O corpo precisa ter o número
exato de bytes de `Content-Length`; mesmo um JSON válido é recusado se o envio
terminar antes do tamanho declarado. O limite continua em 16.384 bytes e o
timeout de leitura em cinco segundos. `Transfer-Encoding`, tamanho duplicado,
ausente ou inválido são recusados antes da leitura.

Recusas antecipadas fecham a conexão, sem consumir um upload não autorizado
ou acima do limite. No Windows, dados ainda em envio podem provocar reset,
aborto ou fechamento TCP antes da entrega do JSON de erro. Esse resultado é
admitido para essas recusas de transporte: o teste também exige zero execução,
fase PRONTO e resposta normal de uma nova consulta. Não se exige que o servidor
consuma um upload arbitrário para garantir a entrega de uma mensagem de erro.
Quando a resposta chega, seu status e JSON são conferidos exatamente. Respostas
com conexão destinada ao fechamento incluem `Connection: close`.

Uma queda após uma solicitação válida pode ocorrer depois de a ação ter sido
aceita. Consulte o estado/histórico antes de decidir repetir; reset não é uma
confirmação geral de que uma ação válida deixou de ocorrer. A E8 não implementa
repetição automática nem altera as regras de inclusão/retomada/impressão.

**193 testes Python e seis JavaScript aprovados**, incluindo três testes novos:
40 uploads recusados seguidos de uma solicitação válida sintética, cabeçalhos
inválidos sem envio do corpo e corpo truncado com JSON válido. Este último
recebia 200 antes da correção e agora recebe 400, sem iniciar o executor.
JSON malformado/tipo inválido com corpo completo continuam exigindo 400; o
tratamento de reset não foi aplicado genericamente às falhas de testes.
Tipagem estrita de `src/interface_web.py`: zero erros/avisos. A validação usou
HTTP local e executor fictício, em cópia sem configuração operacional, com
rede externa/aplicativos bloqueados. Nenhum pedido real foi consultado, inserido
ou impresso. Reabrir o Havan para carregar a atualização; executáveis antigos
precisam ser reconstruídos.

## Implementação e identidade

`havan.py` abre o navegador e o servidor em `127.0.0.1`, numa porta livre.
`src/interface_web.py` controla HTTP/API e presença das páginas;
`src/controlador.py` possui o estado e o executor único, que chama
`src/servico_pedidos.py`, compartilhado com o console.
HTML/CSS/JavaScript locais não requerem Node ou acesso à internet para carregar
o painel. As APIs exigem token da execução, Host local e Origin nas ações.
Os recursos servidos são uma lista fixa; a API não permite consultar arquivos
arbitrários. Esse servidor não foi preparado para acesso pela rede.

A assinatura segue `estrutura-nunes/identidade-visual/marca-pessoal/README.md`,
com link para o GitHub e dois traços separados sob os dois “l”. Os ícones em
`icons/` foram gerados pelo script oficial da identidade Nunes, usando o símbolo
aprovado e a cor já atribuída ao projeto, **#6D28D9**. Incluem SVG, ICO e PNG
192/512. O `icone.ico` antigo da raiz foi preservado.

## Validação em 15/10/2026

- 156 testes automatizados aprovados, com integrações externas simuladas,
  incluindo download sem console ao iniciar por `pythonw.exe`.
- Testes de API e executor cobrem persistência, concorrência, decisões seguras,
  reconexão explícita, autenticação local, recursos, log e encerramento.
- Testes de fluxo verificam parada após download e após inclusão confirmada,
  preservando a impressão pendente.
- Inspeção no navegador usa SQLite temporário e pedidos fictícios. Não acessa
  o histórico operacional, banco, portal, Sisplan, impressora ou Teams.
- Conferidos os temas claro/escuro, layout estreito sem transbordamento da
  página, assinatura, pausa com decisão manual e bloqueio de reenvio de impressão incerta.
- Análise estática de `main.py`, `havan.py` e `src/`: zero erros e avisos.
  Sintaxe JavaScript e `git diff --check` aprovados.

O painel não centraliza configurações nem permite compartilhar a fila entre
computadores. A proposta correspondente continua em
[analise-centralizacao-vm.md](analise-centralizacao-vm.md).

As correções posteriores e a leitura de configuração por lote estão descritas
em [refatoracao-2026-10-15.md](refatoracao-2026-10-15.md). Um erro de configuração
oferece parar e orienta aplicar os ajustes em outro lote ou Retomar.

## Integração com o Hub Nunes

O contrato local `integracao_hub.py`, mantido no Hub Nunes e copiado para esta
aplicação, publica endereço, saúde e estado da interface e permite solicitar
a parada segura pelo monitor. O atalho próprio e o console usam a mesma trava
Sisplan por usuário e sessão: encerre Havan antes de abrir outra ferramenta
que use o ERP. A trava permanece enquanto o encerramento aguarda o executor.
Outra aba conectada mantém o servidor aberto; fechar a última segue a parada
segura já descrita. Executáveis antigos precisam ser reconstruídos para
incorporar essa integração; os atalhos Python usam os fontes atualizados.

## Adaptação de layout e conferência — 31/10/2026

O painel mantém sua identidade violeta, com cabeçalho compacto, preparação à
esquerda, acompanhamento à direita e histórico em largura completa. Em telas
estreitas, as áreas são empilhadas e cada pedido conserva seus rótulos. O rodapé
tem divisória em toda a largura, assinatura alinhada ao conteúdo e Encerrar.
Página, campo de pedidos, sumário, histórico e menu usam rolagem sobreposta,
sem reservar espaço. A roda movimenta cada região enquanto há conteúdo naquela
direção; sobre o puxador no limite, o evento fica livre para continuar na página.
O menu mantém a rolagem contida, sem mover o conteúdo atrás dele. Ctrl+roda
conserva o zoom e o arraste dos puxadores continua disponível.
As barras são medidas em uma única fase e desenhadas depois por transformações,
sem alternar mudanças de estilo e leituras de posição entre as regiões. A pintura
dos indicadores fica isolada e estilos idênticos não são reescritos durante o scroll.
`src/rolagem.js` é uma adaptação local da Impressão de OPs;
os ícones `tema-lua.svg` e `tema-lua-sol.svg` foram copiados daquela referência,
com hashes conferidos. A aplicação continua independente e no navegador.

### Preparar, conferir e executar

1. Informe os pedidos para baixar e conferir. Cole os pedidos separados por vírgula
   ou linha. O contador mostra pedidos válidos únicos, completando o ano conforme
   o servidor. Repetições e inválidos são informados separadamente; nenhum item
   inválido é descartado silenciosamente para permitir execução parcial.
2. Use **Conferir pedidos**. A aba Conferência mostra o número normalizado,
   a situação no histórico local e a próxima ação prevista. Não consulta banco,
   portal ou arquivos de negócio, não cadastra pedidos e não autoriza inclusão
   incerta. “Não consta no histórico local” não significa ausência no Sisplan.
3. Revise os resultados e use Importar pedidos ou as ações de conferência na lista. Importar novamente
   prepara e confere apenas aquele pedido, sem iniciar automaticamente.
4. Alterar entrada/modo, mudar o histórico ou iniciar outra execução invalida a
   conferência. Uma execução nova sempre exige uma revisão nova. A consulta ao
   Sisplan e todas as proteções do executor continuam ocorrendo no processamento.

A API autenticada acrescenta `POST /api/conferir` (`modo`, `pedidos`) e retorna
`id`, `revisao`, `modo` e a lista normalizada com o snapshot `salvo` de cada pedido.
`POST /api/iniciar` agora exige `conferencia` com esse identificador, além dos
campos anteriores. O servidor compara modo, pedidos e revisão sob a mesma trava
do início; rejeita revisões ausentes, alteradas, antigas e consumidas com 409.
Conferências ficam somente em memória, limitadas às 20 mais recentes. Não se
reutilizam após reiniciar a aplicação. Host, token, Origin, limite do corpo,
solicitações idempotentes e regras de encerramento foram preservados.

### Andamento e histórico

A tela distingue o estado da execução e o último estado salvo do pedido. Cada
salvamento confirmado atualiza o snapshot do painel na thread dona do SQLite;
o observador não altera a ordem nem o significado das operações de negócio.
A barra indica avanço pelo lote, não quantidade de inclusões ou impressões
bem-sucedidas. Finalização com pendências tem rótulo próprio e resumo por resultado.
Durante pausa ou interrupção, a posição conhecida é preservada.

**Lote atual** contém os pedidos da última execução desta sessão, inclusive
pedidos ainda sem registro local. **Todos os pedidos salvos** conserva o
histórico persistido. Filas e filtro Exigem atenção usam o escopo selecionado;
atenção é uma visão sobreposta, não uma quinta etapa somável às outras. No lote,
a observação também informa o resultado desta execução, distinguindo-o da etapa
salva anteriormente. A composição e os resultados do último lote são mantidos
no processo, disponíveis após recarregar a página, mas não são um novo histórico
persistente de execuções. As etapas dos pedidos continuam no SQLite existente.

Perda de conexão conserva campos e últimos dados, mostra atualização interrompida,
bloqueia novos inícios e invalida a conferência. Resposta de início perdida não
provoca reenvio automático; a tela precisa recuperar o estado antes de permitir
nova conferência. Nenhum teste visual deve usar pedidos ou integrações reais.

### Prévia isolada

`python -B -m tests.preview_pedidos` abre somente um servidor local com SQLite
em diretório temporário e executor sintético, sem portal, Sisplan, banco externo,
impressora ou publicação no Hub. O endereço é escrito no terminal. Números
terminados em 003 simulam produto sem cadastro e 004 simulam uma pausa; os demais
percorrem etapas fictícias. Use Encerrar para finalizar e remover os dados
temporários. Esse utilitário não faz parte da abertura operacional.

Validação desta adaptação: suíte Python de 226 casos executada; o único teste
que ainda iniciava sem conferência foi adaptado ao novo contrato e passou na
reexecução dirigida de 45 casos (incluindo uma nova regressão HTTP). Foram
aprovados os 15 testes JavaScript e a regressão específica de retomada após o
ajuste do total inicial. Sintaxe de JavaScript e revisão de whitespace aprovadas.
Na prévia isolada Chromium, foram conferidos os dois temas, conferência de 65
pedidos, pausa com decisão, finalização com pendências, abas e rolagem por teclado,
limites de 320, 352, 1280 e 1920 px e estabilidade do campo com/sem excedente
(602 px nos dois casos). Sem transbordamento horizontal nas larguras verificadas.
Zoom nativo de 200%, escala Windows de 125%, toque e alto contraste ainda precisam
de homologação no posto; o controle de zoom do navegador de teste não aplicou a
mudança. Nenhum pedido real foi consultado, incluído ou impresso. Executável não
foi gerado; reabra a aplicação pelos fontes para carregar a atualização.


A tipografia distingue o rótulo auxiliar da etapa em seminegrito na faixa do
pedido. Etiquetas usam 13 px; cartões bloqueados preservam o contraste dos
contadores. Busca e filtros usam peso normal, com seminegrito no escopo
selecionado. Observações separam resultados e pendências em linhas; o título
da pausa e a mensagem do problema recebem destaque sobre a orientação auxiliar.
