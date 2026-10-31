# Pedidos Havan desktop

A abertura padrão de `havan.py` usa pywebview/WinForms e WebView2, mantendo o
servidor local autenticado e o executor único. `havan.py --web` conserva o modo
navegador. `main.py` continua sendo a entrada de console.

## Abrir e testar

- **Abrir Pedidos Havan.cmd** abre a automação operacional.
- **testar interface.cmd** abre **Pedidos Havan · Demonstração**, com histórico,
  log, tema e geometria temporários. Pode ser usada junto da aplicação normal.
- Na demonstração, abra o ícone **Configurações da demonstração**, ao lado do tema,
  escolha um dos 16 cenários e clique em **Preparar cenário**. Isso apenas preenche
  a lista e seleciona a operação; **Conferir pedidos** e **Iniciar** continuam
  obrigatórios. O roteiro e o resultado esperado ficam apenas no menu de
  configurações, junto do cenário selecionado.

A demonstração não cria `IntegracaoLocal`, não reserva Sisplan, não inicia
sincronização e não consulta portal, banco externo ou impressoras. Os dados são
removidos após a saída. O executor operacional não é chamado nesse modo.

## Roteiros da demonstração

Os cenários exercitam entrada, decisão, recuperação e segurança das filas. As
etapas são persistidas no SQLite temporário; Inserir, Retomar e Reimprimir têm
comportamentos diferentes. A contagem de importações no resumo também é simulada,
sem registrar métricas operacionais. Os pedidos sem ano usam o ano vigente.

| Cenário | O que conferir |
| --- | --- |
| Lote com sucesso e pendências | Deixe cadastro e download pendentes, confira o resumo e retome depois. |
| Entrada inválida e repetida | A contagem remove repetições; uma entrada inválida bloqueia Conferir. Editar a lista invalida uma conferência anterior. |
| Pedido já existente | Inserir identifica o existente sem outra inclusão ou impressão. |
| Produto sem cadastro | Deixe pendente e continue; filtre Produto sem cadastro e use Importar novamente para simular o cadastro corrigido. |
| Falha de download | Teste repetir, deixar pendente e parar. A próxima tentativa solicitada simula a recuperação. |
| Sessão expirada do portal | Reconectar e continuar ou parar; pular fica bloqueado. |
| Banco indisponível | Falha antes da inclusão; tentar novamente simula a rede recuperada, sem liberar o próximo pedido durante a pausa. |
| Retomar de etapas diferentes | A primeira execução prepara um Baixado e um No Sisplan. Retomar inclui apenas o primeiro e imprime os dois. |
| Reimpressão com confirmação | A conferência não envia nada. Outra cópia exige confirmação e não aumenta importações. |
| Impressão pendente recuperável | Falha antes do envio; repetir ou retomar imprime sem incluir novamente. |
| Impressão incerta | Retomar conserva o bloqueio. Só Reimprimir, com confirmação explícita, envia outra cópia. |
| Gravação incerta | Repetir e pular ficam bloqueados. Pare e retome para simular a confirmação, sem reinclusão. |
| Aviso pendente | Retomar confirma existência e não imprime. Reimprimir continua sendo uma operação explícita, sem nova inclusão. |
| Cancelamento não confirmado | A inclusão fica incerta e bloqueia novas inclusões, mesmo após Retomar. |
| Lista longa, filtros e paginação | Confira 60 pedidos, execute e teste duas páginas, busca, filtros, escopos e rolagem. |
| Parar e encerrar durante o lote | Pare durante uma etapa, confira o ponto seguro e retome. Teste cancelar e confirmar a saída, inclusive numa pausa. |

Os roteiros compartilham o histórico da janela aberta. Depois que um pedido
terminou, Inserir reconhece o resultado anterior; selecionar novamente o cenário
não apaga a fila. **Feche e reabra `testar interface.cmd` para começar do zero.**
Teste o cancelamento não confirmado por último, pois ele preserva um bloqueio
intencional até o fechamento da demonstração.

Temas, foco por teclado, menu fechado por Escape/foco externo, janela normal e
maximizada, largura estreita e zoom também fazem parte da conferência visual.
Compare a conferência curta com a lista longa: a barra deve sobrepor a borda sem
alterar a largura do conteúdo ou criar faixa vazia. Nenhum desses roteiros
comprova a temporização das janelas do Sisplan nem impressão física.

## Ambiente

Python 3.13 de **32 bits**, .NET Framework 4.8 e WebView2 Evergreen. O ambiente
separado `.venv-desktop` mantém a arquitetura do Sisplan e não altera `.venv`:

```powershell
.\.venv\Scripts\python.exe -m venv .venv-desktop
.\.venv-desktop\Scripts\python.exe -m pip install -r requirements-desktop.txt
.\"Criar Atalho Pedidos Havan.ps1"
```

O ambiente local foi preparado e `pip check` passou. Os atalhos e o Hub preferem
`.venv-desktop`. O executável, quando existir, tem prioridade no atalho operacional.
Nenhum executável foi gerado nesta entrega. Uma instalação com executável antigo
precisa atualizá-lo para incorporar o desktop.

## Janela, identidade e encerramento

A janela usa identidade própria, ícone Nunes violeta e reativação autenticada da
mesma instância, sem recarregar os campos. Uma instância antiga no navegador
precisa ser encerrada antes de abrir a versão desktop. A ativação exige Host
local, token da instância, ausência de Origin e corpo exato; não usa o token da página.

X e Encerrar pedem confirmação. O tema pendente é salvo antes da solicitação de
saída; uma falha de preferência conserva a janela e informa o problema. O executor
termina sua etapa e preserva o histórico antes de liberar a janela. A sincronização
auxiliar termina no processo, mantendo a exclusividade até a saída. Parada pelo
Hub segue a mesma coordenação. Fechar a janela não comprova término do processo.
Perder presença da página não encerra o desktop. O modo web mantém suas regras.

A espera pelo callback de confirmação do tema tem limite de dez segundos.
Sem retorno, a falha aparece no título e no log, a janela permanece aberta e
uma nova tentativa de encerrar fica disponível. Um callback tardio da tentativa
anterior não encerra a aplicação.

Tema e geometria ficam em `%LOCALAPPDATA%\Nunes\PedidosHavan`. O override
`HAVAN_DESKTOP_DADOS` é usado pela demonstração e pelos testes. Os dados operacionais
permanecem nos destinos anteriores. O log pode ser acessado na pasta da aplicação;
o download de arquivo pela página fica oculto no desktop.

`desktop_windows.py`, `dpi_windows.py` e `desktop-winforms.config` são cópias
locais da fonte no Hub, com hashes conferidos e destinos declarados no manifesto.
Não há importação de repositórios irmãos durante a execução. A janela conserva
geometria e aplica o bootstrap Per-Monitor V2 antes do CLR/WinForms.

## Verificações

```powershell
.\.venv-desktop\Scripts\python.exe -B -m unittest discover -s tests -q
node --test tests/test_pedidos_ui.cjs
.\.venv-desktop\Scripts\python.exe -B -m tests.ensaio_desktop
```

Validação dos cenários em 31/10/2026: **259 testes Python e 18 testes JavaScript
aprovados**, incluindo proteção contra chamadas às integrações operacionais.
O ensaio WebView2 real aprovou **21 verificações**: menu, entrada e conferência,
decisões, retomadas, reimpressão, barreiras de operações incertas, paginação,
tema e encerramento. A rolagem foi conferida em janela normal, maximizada e
estreita, com lista curta/longa e zoom real de 125%, sem deslocamento horizontal
ou espaço reservado. O ensaio registra a largura efetiva do viewport e respeita
o mínimo nativo da janela. Evidência local: `.local/qa-desktop/ensaio.json`.
A regressão adicional HTTP verifica ativação e preferência com tokens e dados
sintéticos. Homologação de pedidos/impressão reais, dois monitores físicos em
100%/125%, pacote distribuído e toque permanece separada.

A regressão HTTP/desktop adicional passou na execução direcionada de seis casos.
Os 40 testes do Hub e da manutenção passaram após atualizar catálogo e manifesto.
O atalho local foi recriado e aponta para pythonw de `.venv-desktop`, com a
entrada `havan.py`. As cópias compartilhadas coincidem por SHA-256.
