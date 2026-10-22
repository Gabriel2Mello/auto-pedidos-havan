# 🤖 RPA - Automação de Pedidos Havan (Portal do Fornecedor ➔ Sisplan ERP)

Este é um robô de automação de processos (RPA) desenvolvido em Python para otimizar o fluxo de inclusão de pedidos. O sistema realiza o download de documentos digitais do portal de fornecedores da Havan, processa metadados e arquivos binários, injeta as informações no ERP Sisplan via automação de interface gráfica (GUI) e gerencia a impressão física dos documentos modificados.

---

## Interface no navegador

O operador pode usar **Abrir Pedidos Havan.cmd**, ou o atalho com o mesmo nome,
para abrir o painel local. Ele oferece Inserir, Retomar e Reimprimir, as quatro
filas, busca por pedido/número interno, andamento, decisões após erro e acesso
ao diagnóstico. Tem temas claro/escuro, assinatura g2mello e ícone Nunes violeta.

A instalação pelo código precisa de Python **3.13 de 32 bits** com as dependências
em `.venv` ou `venv32`. O atalho procura primeiro `Pedidos Havan.exe` na mesma
pasta; se não existir, usa `.venv` e depois `venv32`. Ele não instala dependências
sozinho. O executável da nova interface ainda precisa ser gerado com os recursos
do painel incluídos. O [guia da interface](docs/interface-web.md)
explica a preparação, abertura, encerramento e os limites da validação.

O painel roda no computador do operador, junto ao Sisplan. Configurações,
arquivos, fila e logs continuam locais. O modo console em `main.py` permanece
disponível. A centralização das configurações é uma entrega futura.

---

## ⚙️ Tecnologias e Bibliotecas Utilizadas

* **Orquestração e Core:** Python 3.13-32
* **Web Scraping & Bypass:** `cloudscraper` e `BeautifulSoup4` (LXML parsing).
* **Automação de Interface (GUI Automation):** `pywinauto` (Win32 backend para interação com componentes Delphi/VCL do Sisplan).
* **Manipulação de Arquivos:** `pypdf` (leitura, escrita e merge de PDFs), `reportlab` (geração de overlays em tempo real) e `rarfile` (extração de buffers XML comprimidos).
* **Pré-validação no banco:** `pg8000`, driver PostgreSQL em Python, usado somente para consultas de pedidos e códigos de barras.
* **Interface de Console:** `tqdm` (barras de progresso concorrentes) e `logging` customizado com suporte nativo no Windows.

---

## 🚀 Fluxo Operacional do Robô
```
[Usuário insere os IDs] ➔ [Login & Scraping Havan] ➔ [Extração XML/PDF]
│
[Impressão Silenciosa] 🖨️ [Marca D'água PDF] 🔑 [Captura ID Interno] ◀─ [GUI Sisplan]
```
1.  **Entrada de Dados e duplicidade:** O menu oferece Inserir, Retomar e Reimprimir. Ao inserir, o robô salva a lista completa antes de acessar portal ou Sisplan. Entradas parciais são expandidas usando o ano vigente (ex: `12345` vira `2026-12345`). Remove repetições; se houver números inválidos no menu, pede a correção da lista. Antes do download, consulta os pedidos Havan existentes no Sisplan, considerando matriz e filial, informa seus números internos e os ignora.
2.  **Fase Web (Concorrente):** Realiza o bypass de segurança e autenticação no Portal Havan. Localiza os cards dos pedidos via seletores CSS, captura os links e efetua o download simultâneo do PDF (Ordem de Compra) e do RAR (Arquivo de Integração).
3.  **Processamento de Dados:** Descompacta o XML diretamente em memória, confere o número do pedido, os campos e datas e todos os códigos de barras de todas as variações. Pedido com XML inválido, barra ausente ou cadastro ambíguo é ignorado por inteiro antes da inclusão. Extrai metadados logísticos (Datas, Itens, Operação) e aplica as regras de campanhas promocionais e de Filial/Matriz (`PRODUTOS_GOVERNADOR`).
4.  **Automação do ERP (Sisplan):** Vincula-se à instância aberta do Sisplan, inicia o modo de inclusão na tela *1002 - Pedido por Grade*, preenche campos de cadastro, dispara a janela nativa de busca do Windows (`#32770`) para carregar o XML e captura o **Número Interno**. Após gravar, aguarda até dez segundos para conferir no banco o número Havan, o número interno e a presença de itens vinculados por `ID_PED`. Somente depois confirma a importação e envia os avisos promocionais. Falha ao interagir com uma janela encontrada interrompe o lote; ausência esperada de aviso permite continuar.
5.  **Geração e Impressão de Documentos:** Gera um PDF numerado, preservando o original, no padrão `<numero interno> <pedido Havan>.pdf`. Por exemplo, `11250 2026-109335.pdf` usa o número interno Sisplan `11250`. O envio silencioso aguarda o retorno do SumatraPDF e registra a etapa concluída ou pendente. Retorno zero do programa confirma o envio, sem comprovar a saída física do papel.

---

## 📋 Pré-requisitos de Infraestrutura

O ambiente de execução precisa das seguintes ferramentas instaladas no Windows:

1.  **ERP Sisplan** aberto e posicionado na tela `1002 - Pedido Por Grade`.
2.  **UnRAR Tool executable:** Utilitário de linha de comando para descompactar arquivos `.rar`. (Incluso em instalações do WinRAR).
3.  **SumatraPDF:** Leitor leve de PDF utilizado para o gerenciamento de impressões em lote via CLI de forma oculta.

---

## 🔧 Configuração

As opções operacionais ficam no arquivo `config.toml`, ao lado do executável.
Copie `config.example.toml`, renomeie a cópia para `config.toml` e ajuste:

```toml
unrar_tool = 'C:\Program Files\WinRAR\UnRAR.exe'
sumatra = 'C:\LocalApps\SumatraPDF.exe'
pasta_pedidos = 'D:\Automacao\ArquivoPedidos'
impressora = "HP LaserJet M402 - Almoxarifado"
banco_config = 'C:\Configuracao\banco-sisplan.json'
banco_perfil = "principal"
tolerancia_numero_interno = 100
```

O arquivo local `config.toml` é ignorado pelo Git para que configurações de uma
máquina não sejam enviadas ao repositório. O `config.example.toml` serve como
modelo versionado. Se `config.toml` não existir ao iniciar o robô, esse arquivo
de exemplo será criado automaticamente na mesma pasta, sem substituir um modelo
existente.

O arquivo é relido ao iniciar cada lote. Durante o lote, a configuração fica
preservada, inclusive nas threads de download. Se precisar corrigir o TOML,
pare o processamento e inicie outro lote ou use Retomar para aplicar os valores.
Alterações de variáveis de ambiente do Windows exigem reabrir o programa.

A possibilidade de centralizar configuração e distribuição, mantendo o robô
na sessão do Sisplan, está analisada em
[Centralização e VM](docs/analise-centralizacao-vm.md). É uma proposta baseada
no estrutura-nunes; o carregamento central e o serviço em VM ainda não foram implementados.

`banco_config` aponta para o JSON privado documentado no estrutura-nunes; o
arquivo precisa estar acessível na máquina que executa o robô. Caminhos relativos
são resolvidos a partir da pasta do `config.toml`. O perfil selecionado deve
conter `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER` e `PGPASSWORD` como texto em
`perfis.<banco_perfil>`. As senhas continuam nesse arquivo privado e não devem
ser copiadas para o TOML, código ou repositório. O perfil padrão é `principal`.

A pré-validação consulta `sisplan.pedido_001` por cliente e `PED_CLI` e
`sisplan.pa_iten_001` pelo campo `BARRA`, vinculado a `produto_001` por `CODIGO`.
As barras são tratadas como texto e, no formato atual da integração, devem ter
13 dígitos. Múltiplas linhas de estoque com o mesmo produto/cor/tamanho são
aceitas; uma barra com combinações diferentes bloqueia o pedido. Não foi
acrescentado filtro por atividade do produto.

Todas as consultas usam parâmetros e transações de leitura, com limite de oito
segundos por consulta. Falha de conexão ou consulta interrompe a importação antes
do próximo pedido. O robô reconsulta a duplicidade imediatamente antes de cada
inclusão e preserva os avisos da interface, pois alterações por outros operadores
podem acontecer entre a consulta e a importação. Se não houver pedidos aptos,
não inicia a interação com o Sisplan.

Ao atualizar uma instalação, instale as dependências de `requirements.txt` no
Python usado pelo robô. Executáveis distribuídos precisam ser recompilados nesse
ambiente para incluir `pg8000` e suas dependências.

Credenciais e integrações sensíveis continuam em variáveis de ambiente:

| Variável | Obrigatória | Descrição |
| :--- | :---: | :--- |
| `CNPJ_MATRIZ` | Ao baixar | CNPJ usado na autenticação do portal. |
| `SENHA_PORTAL` | Ao baixar | Senha de acesso ao portal. |
| `TEAMS_WEBHOOK_URL` | Não | Webhook para envio dos alertas ao Teams. |

---

## Retomada e reimpressão

Ao abrir sem argumentos de terminal, o operador recebe o menu:

```text
1 - Inserir pedidos
2 - Retomar (quantidade de pendentes)
3 - Reimprimir pedidos
0 - Sair
```

Se houver pendências, o programa informa a quantidade e oferece Enter para
retomar. O menu volta a aparecer após o processamento, sem exigir que o usuário
saiba usar comandos de terminal. Em Reimprimir, os números são digitados
manualmente e a existência no Sisplan é conferida antes do envio.

As etapas de cada pedido são salvas em `estado-pedidos.sqlite3`, na pasta da
aplicação, com número interno, empresa, PDF gerado, erro e data da atualização.
A lista inteira é salva numa única transação assim que o usuário a informa;
falha no portal, configuração ou banco não descarta os pedidos ainda não iniciados.
Esse arquivo deve ser preservado ao atualizar a instalação. Não contém as
credenciais do banco. A trava local `estado-pedidos.lock` impede duas execuções
simultâneas dessa instalação e é liberada pelo sistema ao fechar o processo.

As quatro filas são visões do mesmo histórico, sem copiar ou apagar registros
entre arquivos:

| Fila | Como avança |
| --- | --- |
| A baixar | Os arquivos ainda precisam ser obtidos; falhas ficam pendentes. |
| Baixados | XML e PDF já foram salvos; serão conferidos antes da importação. Inclusões ainda não confirmadas permanecem nessa fase, com bloqueio próprio. |
| No Sisplan | Importação confirmada, etapas de preparação/envio de impressão ou pedido já existente identificado. |
| Enviados para impressão | SumatraPDF retornou sucesso. É a etapa final automática, sem afirmar saída física do papel. |

Retomar percorre a fila na ordem de entrada. Arquivos de pedidos baixados são
conferidos e reaproveitados; credenciais do portal e UnRAR só são exigidos se
for necessário baixar. Pedidos importados seguem apenas para a impressão,
após reconferir a gravação no banco. Pedidos existentes identificados e envios
concluídos saem das pendências, permanecendo no histórico. A fila pendente se
esvazia; o arquivo de histórico é preservado para auditoria.

Pedidos antigos que não têm histórico local continuam sendo ignorados como
existentes. Ter um PDF na pasta não comprova que já foi impresso. Uma impressão
incerta não será repetida automaticamente. Se arquivos marcados como baixados
estiverem ausentes ou inválidos, o programa pausa antes de tentar baixá-los de novo.

O fluxo processa um pedido por vez, com reaproveitamento da sessão autenticada
e dos controles do Sisplan enquanto não houver erro. A consulta inicial de
duplicidade é feita em lote; antes de cada inclusão há nova conferência.

### Quando acontece um erro

O processamento pausa antes de iniciar o próximo pedido. O usuário recebe uma
mensagem curta e opções conforme a etapa:

- **Tentar novamente:** somente após o usuário escolher e quando a etapa puder
  ser repetida com segurança, como consulta, download ou produto sem cadastro.
- **Deixar pendente e continuar:** somente quando avançar para outro pedido for
  seguro; o pedido com erro permanece salvo para uma retomada posterior.
- **Parar e voltar ao menu:** preserva todos os pedidos ainda pendentes.

Se a inclusão no Sisplan ficou incerta ou o histórico não pôde ser salvo,
repetir e continuar ficam bloqueados. O operador deve solicitar ajuda ao
responsável. Outra inclusão não começa enquanto houver uma inclusão anterior
sem conferência. Uma impressão incerta exige conferência e uso manual de Reimprimir.

Os detalhes técnicos ficam em `auto-pedidos.log`, com código de execução,
pedido, etapa, dados do ambiente e pilha da exceção. A tela não exibe a pilha
técnica. Para atendimento, o operador envia o log e informa o código exibido ao
abrir. As senhas do banco e parâmetros secretos não são reproduzidos no log.

Quando o portal volta a exigir autenticação durante o lote, o programa pausa e
oferece **Reconectar ao Portal Havan** ou **Parar**. A reconexão faz novo login
somente depois da escolha do operador; parar preserva todos os pedidos pendentes.
Falhas de banco também descartam a conexão indisponível: quando for seguro
repetir e o operador autorizar, uma nova conexão é aberta e o pedido é reconferido.
Inclusões que ficaram incertas continuam exigindo conferência antes de outra inclusão.

Antes de incluir um pedido novo, o robô preserva no histórico os produtos,
cores, tamanhos e quantidades esperados a partir do XML e do cadastro de barras.
Depois de gravar, compara os totais dessas combinações com os itens do Sisplan.
Itens ausentes, excedentes ou quantidades diferentes bloqueiam a impressão e
ficam detalhados no log. A retomada de uma inclusão incerta usa os itens
preservados, mesmo que o XML ou o cadastro de barras tenham mudado. Pendências
de versões anteriores sem esses itens precisam do XML válido e do cadastro
correspondente para reconstruir a conferência. Pedidos já confirmados e
reimpressões de pedidos antigos mantêm a conferência de existência e número
interno, sem exigir que o saldo atual corresponda ao XML original.

O histórico recebe uma tabela adicional de itens esperados automaticamente,
preservando a fila existente. Erros do histórico registram a causa original,
o caminho e os códigos SQLite disponíveis. Se o arquivo de log não puder ser
aberto na inicialização, o programa orienta o operador e aguarda Enter antes
de fechar, sem iniciar o processamento.
O console retorna código 1 nessa falha, em erros de histórico ou quando um
lote termina com pedidos rejeitados, falhos ou pendentes. O código é acumulado
na sessão: 0 indica todos os lotes sem falhas ou pendências, com pedidos
existentes ou impressão enviada (ou nenhum trabalho); interrupção capturada retorna 130. O código não
confirma impressão física e não autoriza repetir inclusões ou envios incertos.

As buscas por diálogos são restritas ao processo do Sisplan. O tratamento de
“Aviso” conserva a barreira de cancelamento. Desde a E9, a retirada da fila
exige correspondência única no banco, conforme a seção de recuperação abaixo.

Os argumentos anteriores continuam disponíveis para o responsável. Para
retomar todas as etapas pendentes registradas por esta versão:

```powershell
python main.py --retomar
```

Para reimprimir explicitamente um pedido, inclusive anterior ao histórico local:

```powershell
python main.py --reimprimir "2026-109335"
```

O robô confere o número interno no banco e pode reutilizar o PDF numerado já
existente quando seu título corresponde ao número confirmado. Se necessário,
gera esse PDF a partir da ordem de compra original. Reimprimir não acessa o
portal nem inicia a interface do Sisplan e não exige UnRAR ou credenciais do
portal. Retomar usa apenas as dependências das etapas pendentes. Vários números
podem ser separados por vírgula. No executável, passe os mesmos argumentos ao
arquivo `.exe` atualizado.

Timeout, retorno de erro do Sumatra ou interrupção durante o envio deixam a
impressão **incerta**. Ela não será reenviada automaticamente: confira a fila e
use `--reimprimir` se precisar enviá-la novamente. Falha antes de iniciar o
programa, como executável ausente, deixa a impressão pendente e permite retomada.

Antes de cada nova inclusão, o robô consulta os cinco pedidos com número interno
numérico mais recentemente incluídos no Sisplan (todos os clientes e empresas)
e usa a mediana como referência. Isso evita que um registro isolado errado, como
`1`, determine a faixa aceita. São necessários pelo menos três números recentes.
A distância máxima permitida é `tolerancia_numero_interno`, por padrão **100**,
para cima ou para baixo da referência; não é exigida sequência exata. Por exemplo,
com referência `11250`, aceita de `11150` a `11350`, mas rejeita `1` e `999999`.

O número é conferido ao iniciar a inclusão e novamente antes de gravar. Um
número vazio, inválido ou fora da faixa cancela a inclusão e permite **uma única
nova tentativa automática do mesmo pedido**. Antes de repetir, o robô aguarda a
tela restaurar o número exibido antes de Incluir. Se o cancelamento falhar, o
lote para e mantém a inclusão como incerta para conferência manual. Se a segunda
tentativa também gerar um número suspeito, ela é cancelada e o lote pausa para
o operador corrigir o Sisplan e escolher tentar novamente ou parar. O pedido
permanece baixado, sem gravação nem impressão; os próximos pedidos aguardam.

Se houve interrupção na gravação, o robô tenta confirmar o número esperado no
banco antes de imprimir. Caso o pedido continue ausente, a inclusão permanece
bloqueada. Depois de conferir e **cancelar a inclusão anterior no Sisplan**, é
possível liberar uma nova tentativa:

```powershell
python main.py --reiniciar "2026-109335"
```

Esse comando só libera o registro local de gravação pendente quando o pedido
não existe no banco. Não exclui nem altera pedidos no ERP. Pendências já
importadas seguem para a retomada da impressão.

---

### Pedidos com produto sem cadastro

Pedidos bloqueados por falta de cadastro ficam salvos como **Produto sem cadastro**,
com os códigos de barras e descrições encontrados na pré-validação. No histórico,
use o filtro **Produto sem cadastro** para localizá-los. Após cadastrar os produtos
no Sisplan, clique em **Importar novamente** no pedido desejado ou use **Retomar**
para processar todas as pendências. No console, utilize **Retomar** ou informe os
pedidos em **Inserir**.

A nova tentativa confere o cadastro e a existência do pedido no Sisplan novamente,
reaproveitando os arquivos locais válidos. Se ainda faltar cadastro, o pedido
continua pendente. A situação é preservada ao fechar o programa; pendências antigas
salvas como Baixado com motivo de produto sem cadastro também são identificadas
ao reabrir. A tentativa começa apenas quando o operador a solicita.

## 🪵 Gerenciamento de Logs e Arquivos de Saída

O robô gera saídas em tempo de execução localizados na pasta raiz do script:

* **`auto-pedidos.log`:** Preserva as execuções anteriores e registra um identificador para cada execução, em nível `DEBUG`. Rotaciona ao atingir 5 MiB e mantém cinco arquivos anteriores (`.log.1` até `.log.5`). O console exibe mensagens em nível `INFO`.
* **`estado-pedidos.sqlite3`:** Fila completa desde a entrada e histórico operacional das etapas de download, gravação, PDF e envio da impressão. É local à instalação e ignorado pelo Git.
* **`pedidos_com_erro.txt`:** Registra falhas de download/extração, importação e pré-validação, incluindo os códigos de barras pendentes e suas descrições. Pedidos já existentes são informados no console e log, sem serem registrados como erro.
* **`PROMOCIONAL.txt`:** Identifica e cataloga pedidos classificados no XML como `ITENS PROMOCIONAIS PARA COMERCIALIZACAO`, para apuração sobre tratativas fiscais especiais.

O resumo final distingue pedidos existentes, importações confirmadas, retomadas,
rejeições, falhas, impressões enviadas, pendentes e incertas e pedidos não
processados. Também é exibido quando uma falha interrompe o lote.

---

## 🧪 Desenvolvimento e testes

**E8, 20/10/2026:** passaram 193 testes Python e seis JavaScript, sem operação
real. A API rejeita corpo truncado antes de iniciar uma ação; o contrato de
recusa distingue respostas 400/403 de reset TCP durante uploads recusados.
Os testes verificam também ausência de execução e continuidade do servidor.
Uso, evidências e limites no [guia HTTP](docs/interface-web.md#contrato-http-de-recusa--e8).
Tipagem estrita do adaptador HTTP sem erros/avisos. Reabrir a ferramenta para
carregar a atualização; executáveis antigos precisam de reconstrução.

As regras puras de entrada, datas, XML e seleção da empresa ficam em
`src/pedidos.py`. Esse módulo não depende do portal nem da interface do Sisplan,
o que permite testar as regras sem executar a automação.

Execute a suíte com o próprio `unittest` da biblioteca padrão:

```powershell
python -m unittest discover -v
```

Antes de alterar uma regra de negócio, adicione ou ajuste um teste em `tests/`.
Assim, mudanças estruturais podem ser feitas com segurança sem alterar o
resultado esperado pelo processo operacional.

Os testes de banco usam conexões simuladas, e os testes do fluxo substituem
portal, banco, impressão e interação com o ERP. A suíte não importa pedidos reais.
As evidências da análise e da validação em leitura ficam em
[`docs/analise-prevalidacao-sisplan.md`](docs/analise-prevalidacao-sisplan.md).

A revisão posterior da interface e as propostas de refatoração estão em
[`docs/revisao-interface-e-refatoracao-2026-10-15.md`](docs/revisao-interface-e-refatoracao-2026-10-15.md).
Os seis achados foram corrigidos após autorização. A nova organização do código,
o contexto por lote e as evidências de 156 testes estão em
[`docs/refatoracao-2026-10-15.md`](docs/refatoracao-2026-10-15.md).


## Estatísticas no Hub Nunes

As inclusões são registradas após a confirmação no Sisplan; retomadas de inclusão incerta só contam após confirmação e sem duplicar. Já existentes e pedidos com falha são contados por pedido em cada lote. Retomar impressão ou reimprimir não cria outra inclusão.

O registro funciona na interface web e no console, mesmo com o hub fechado. O módulo `metricas_nunes.py` é distribuído a partir do Hub Nunes; seu README documenta armazenamento, recuperação, filtros e exportação. Feche e reabra esta ferramenta após atualizar. O histórico começa com esta versão e não importa operações anteriores. Falhas na estatística não repetem nem interrompem operações concluídas; uma fila local recupera gravações transitórias e falhas de persistência são registradas no log. Antes de rodar a suíte completa, use um terminal exclusivo de testes e configure NUNES_METRICAS_DADOS para uma pasta temporária; o README do Hub Nunes contém o comando de isolamento.


## Recuperação de avisos — E9, 21/10/2026

Por decisão do responsável em 21/10, o aviso genérico continua cancelando a
inclusão, mas deixa de comprovar duplicidade sozinho. A automação aguarda o
aviso desaparecer e a tela restaurar o número anterior antes de prosseguir.
Se o cancelamento não for confirmado, mantém a inclusão incerta e interrompe.

Depois do cancelamento confirmado, grava `aviso_pendente` antes da consulta.
Só uma correspondência única pelo cliente/pedido Havan no banco permite
concluir como `existente`, guardando número interno e empresa. Ausência,
ambiguidade ou indisponibilidade do banco preservam a pendência e bloqueiam
outras inclusões. O painel identifica **Aviso: conferir existência no banco**.
Ao abrir o histórico, registros antigos `existente` sem número interno voltam
a `aviso_pendente`, preservando os dados e eventual diagnóstico anterior.

Use **Retomar** para consultar novamente. Se encontrar uma correspondência
única, a pendência termina sem inclusão, impressão ou métrica de nova inclusão.
Sem confirmação, continua bloqueada para análise com o responsável. Nem
Retomar nem `--reiniciar` reincluem automaticamente um `aviso_pendente`.
O comando especializado `--reiniciar` conserva sua regra anterior apenas
para as outras etapas de inclusão incerta. Não altere o SQLite para liberar
uma pendência sem esclarecer o que aconteceu no Sisplan.

Esta decisão substitui o desfecho aprovado em 15/10 descrito em
[revisão anterior](docs/revisao-projeto-2026-10-15.md), preservando o cancelamento.
Não foi inventado reconhecimento de texto do aviso: mensagens desconhecidas
também cancelam e exigem comprovação no banco. A checagem não transforma
ausência de gravação em autorização para repetir o efeito.

Validação: 198 testes Python e seis JavaScript aprovados; tipagem estrita dos
módulos alterados sem erros/avisos. Inclui cancelamento incompleto, ausência,
ambiguidade, indisponibilidade, migração conservadora e retomada somente por
consulta. O histórico também foi reaberto por outro processo depois de saída
abrupta, preservando a pendência. Somente dados sintéticos, sem portal, banco
real ou interação real com o Sisplan. Reabra a ferramenta; executáveis antigos
precisam ser reconstruídos. O retorno real da tela após cancelar ainda precisa
de homologação acompanhada; divergência bloqueia a operação.
