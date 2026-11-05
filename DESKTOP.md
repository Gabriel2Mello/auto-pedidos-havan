# Pedidos Havan desktop

A abertura padrão de `havan.py` usa pywebview/WinForms e WebView2, mantendo o
servidor local autenticado e o executor único. `havan.py --web` conserva o modo
navegador. `main.py` continua sendo a entrada de console.

## Abrir e testar

- **Abrir Pedidos Havan.cmd** abre a automação operacional.
- **testar interface.cmd** abre **Pedidos Havan · Demonstração**, com histórico,
  log, tema e geometria temporários. Pode ser usada junto da aplicação normal.
- Na demonstração, abra o ícone **Configurações**, ao lado do tema,
  escolha um dos 15 cenários e clique em **Preparar cenário**. Isso apenas preenche
  a lista e seleciona a operação; **Baixar e conferir** e **Importar aptos**
  são ações separadas. O painel não oferece reimpressão. O roteiro e o resultado esperado ficam apenas no menu de
  configurações, junto do cenário selecionado.

A demonstração não cria `IntegracaoLocal`, não reserva Sisplan, não inicia
sincronização e não consulta portal, banco externo ou impressoras. Os dados são
removidos após a saída. O executor operacional não é chamado nesse modo.
O seletor de impressora usa duas filas fictícias na demonstração e não altera
a preferência operacional. No uso normal, o mesmo menu permite escolher e
salvar uma fila instalada no Windows para os próximos lotes.

## Roteiros da demonstração

Os cenários exercitam o fluxo **preparar → conferir estados → importar aptos**
com SQLite temporário. Preparar cenário no menu só preenche a lista. Baixar e
conferir não importa; só o botão Importar aptos faz a inclusão sintética.

- **Lote misto:** separa dois aptos, um EAN sem cadastro e um download falho.
  Importe os aptos e confira que as pendências permanecem na lista.
- **Cadastro/download:** use a ação na linha para corrigir a pendência; a
  revalidação de cadastro não baixa nem importa. Importe após a liberação.
- **Existente/lista longa:** existentes não são baixados nem importados. Os 60
  pedidos permitem conferir paginação, filtros, busca e rolagem.
- **Banco/portal:** a consulta interrompida pede decisão e não vira “sem cadastro”.
- **Impressão pendente:** prepare e importe primeiro; depois recupere a impressão
  pela linha sem nova inclusão. Impressão incerta exige conferência da fila com o responsável; não há reenvio pela automação.
- **Gravação/aviso incerto:** prepare e importe primeiro. Pare na pausa e use
  Conferir gravação no Sisplan; a ação não reinclui o pedido.
- **Cancelamento incerto:** permanece bloqueado mesmo após conferir gravação.
  Teste por último e reabra a demonstração para limpar o bloqueio sintético.
- **Entrada/parada:** confira repetição, inválidos, parada segura e preservação
  das etapas. Não há reimpressão.

Os cenários compartilham o histórico da janela. Reabrir **testar interface.cmd**
começa uma demonstração vazia de execuções anteriores. Os testes também verificam
teclado, menu por Escape/foco externo, temas, janela normal/maximizada/estreita,
listas curtas/longas e zoom. A rolagem deve sobrepor a borda sem reservar espaço.
Nenhum cenário valida temporização do Sisplan real nem saída física do papel.

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

## Renderização da janela

A abertura desktop configura `--disable-gpu` antes de criar o WebView2.
Essa mitigação evita a piscada durante a rolagem da página inteira que foi
eliminada no teste manual com a GPU desativada no posto Windows. Vale para
a abertura pelo Hub, atalho próprio e demonstração; dispensa lançador especial.
O CSS e o processamento dos pedidos permanecem iguais.

O argumento é acrescentado a `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS` apenas
no processo da aplicação e seus filhos, preservando argumentos existentes e
sem gravar configuração no Windows. Uma instância já aberta conserva sua
renderização: use **Encerrar**, aguarde o término completo no Hub e reabra
pelo atalho habitual. Executáveis precisam ser reconstruídos para incorporar
a alteração; a abertura pelos fontes já usa o comportamento atualizado.

A renderização por software pode aumentar o uso de CPU. A validação manual
isola o caminho acelerado como fator do sintoma, sem identificar sozinho
o driver ou componente responsável. A Microsoft documenta o argumento em
[WebView2 browser flags](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/webview-features-flags)
e recomenda aceleração gráfica quando compatível em
[Performance best practices](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/performance).

## Verificações

```powershell
.\.venv-desktop\Scripts\python.exe -B -m unittest discover -s tests -q
node --test tests/test_pedidos_ui.cjs
.\.venv-desktop\Scripts\python.exe -B -m tests.ensaio_desktop
```

Validação dos cenários em 31/10/2026: **259 testes Python e 18 testes JavaScript
aprovados**, incluindo proteção contra chamadas às integrações operacionais.
O ensaio WebView2 real aprovou **21 verificações**: menu, entrada e conferência,
decisões, retomadas, barreiras de operações incertas, paginação,
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
