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

1. Abra o Sisplan na tela 1002 — Pedido por Grade e abra o atalho.
2. Escolha **Inserir**, **Retomar** ou **Reimprimir**. Em Inserir/Reimprimir,
   digite números separados por vírgula ou por linha. Reimprimir exige confirmar
   o envio de outra cópia.
3. Acompanhe o pedido atual e as quatro filas. Durante a inclusão, aguarde o
   robô terminar antes de usar mouse, teclado ou a tela do Sisplan.
4. Em caso de erro, o robô pausa. A página apresenta somente as escolhas
   permitidas pela etapa. Reconexão de sessão exige uma escolha explícita.
5. Para suporte, use **Copiar diagnóstico** e **Baixar log**. Informe o código
   da execução. O botão baixa o log atual; os arquivos rotacionados permanecem
   na pasta da aplicação quando for necessário consultar execuções anteriores.
6. Use **Parar processamento** para preservar as pendências e continuar no
   painel, ou **Encerrar** para finalizar o aplicativo.

Os cartões filtram o histórico; a busca aceita número Havan ou número interno.
O histórico permanece salvo depois que as pendências terminam. “Enviado para
impressão” mantém o significado existente: retorno de sucesso do SumatraPDF,
sem comprovar a saída física do papel.

## Persistência e encerramento

A lista de Inserir é salva antes de confirmar o recebimento na página. Um único
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
  página, assinatura, pausa com decisão manual e confirmação de reimpressão.
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
As regiões de lista, conferência, histórico e atividade usam rolagem sobreposta,
sem reservar espaço. `src/rolagem.js` é uma adaptação local da Impressão de OPs;
os ícones `tema-lua.svg` e `tema-lua-sol.svg` foram copiados daquela referência,
com hashes conferidos. A aplicação continua independente e no navegador.

### Preparar, conferir e executar

1. Escolha Inserir, Retomar ou Reimprimir. Cole os pedidos separados por vírgula
   ou linha. O contador mostra pedidos válidos únicos, completando o ano conforme
   o servidor. Repetições e inválidos são informados separadamente; nenhum item
   inválido é descartado silenciosamente para permitir execução parcial.
2. Use **Conferir pedidos**. A aba Conferência mostra o número normalizado,
   a situação no histórico local e a próxima ação prevista. Não consulta banco,
   portal ou arquivos de negócio, não cadastra pedidos e não autoriza inclusão
   incerta. “Não consta no histórico local” não significa ausência no Sisplan.
3. Revise e use Inserir e processar, Retomar pendências ou Reimprimir pedidos.
   Reimpressão continua exigindo a confirmação de outra cópia. Importar novamente
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
reimpressões ainda sem registro local. **Todos os pedidos salvos** conserva o
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
