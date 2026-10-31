# Pedidos Havan desktop

A abertura padrão de `havan.py` usa pywebview/WinForms e WebView2, mantendo o
servidor local autenticado e o executor único. `havan.py --web` conserva o modo
navegador. `main.py` continua sendo a entrada de console.

## Abrir e testar

- **Abrir Pedidos Havan.cmd** abre a automação operacional.
- **testar interface.cmd** abre **Pedidos Havan · Demonstração**, com histórico,
  log, tema e geometria temporários. Pode ser usada junto da aplicação normal.
- Na demonstração, abra o ícone **Configurações da demonstração**, ao lado do tema,
  para acessar o aviso de dados temporários e **Preencher exemplo**. Use **Conferir pedidos** e
  **Inserir e processar**. Pedidos terminados em 003 simulam falta de cadastro;
  004 pausam para testar as decisões. As demais etapas são fictícias.

A demonstração não cria `IntegracaoLocal`, não reserva Sisplan, não inicia
sincronização e não consulta portal, banco externo ou impressoras. Os dados são
removidos após a saída. O executor operacional não é chamado nesse modo.

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

A suíte de 232 testes Python e os 15 testes JavaScript passaram no ambiente
novo. O ensaio WebView2 real aprovou larguras 1180/760/480, tema persistido,
conferência sem executar, processamento sintético, pausa e finalização com
pendências. Evidência local: `.local/qa-desktop/ensaio.json`.
A regressão adicional HTTP verifica ativação e preferência com tokens e dados
sintéticos. Homologação de pedidos/impressão reais, dois monitores físicos em
100%/125%, pacote distribuído e toque permanece separada.

A regressão HTTP/desktop adicional passou na execução direcionada de seis casos.
Os 40 testes do Hub e da manutenção passaram após atualizar catálogo e manifesto.
O atalho local foi recriado e aponta para pythonw de `.venv-desktop`, com a
entrada `havan.py`. As cópias compartilhadas coincidem por SHA-256.
