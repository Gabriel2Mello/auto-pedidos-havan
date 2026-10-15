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

O script gera `Abrir Pedidos Havan.lnk` nesta pasta, apontando para a instalação
atual e usando `icons/icone.ico`. Pode ser copiado para a área de trabalho.
Gere novamente se mudar o projeto de pasta. O arquivo `.lnk` é específico da
máquina e não é versionado. Também é possível abrir diretamente
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

Ao fechar a última aba, o programa aguarda cerca de cinco segundos para permitir
recarregamentos e solicita parada segura. Se estiver incluindo um pedido,
termina a confirmação da gravação antes de parar, preservando a impressão
pendente. Não força o encerramento de uma ação em andamento. Ao reabrir, use
Retomar. Se o navegador não chegar a conectar, o prazo inicial é de dois minutos.
O encerramento pode demorar enquanto uma integração termina sua etapa atual.

A pré-validação no banco, conferência de barras/itens e o tratamento de “Aviso”
como última barreira de duplicidade foram preservados. Inclusões incertas
continuam bloqueadas; a liberação especializada por `--reiniciar` permanece no
console, após a conferência prevista no README.

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
