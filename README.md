# 🤖 RPA - Automação de Pedidos Havan (Portal do Fornecedor ➔ Sisplan ERP)

Este é um robô de automação de processos (RPA) desenvolvido em Python para otimizar o fluxo de inclusão de pedidos. O sistema realiza o download de documentos digitais do portal de fornecedores da Havan, processa metadados e arquivos binários, injeta as informações no ERP Sisplan via automação de interface gráfica (GUI) e gerencia a impressão física dos documentos modificados.

---

## ⚙️ Tecnologias e Bibliotecas Utilizadas

* **Orquestração e Core:** Python 3.13-32
* **Web Scraping & Bypass:** `cloudscraper` (com emulação dinâmica de Client Hints do Chrome no Windows) e `BeautifulSoup4` (LXML parsing).
* **Automação de Interface (GUI Automation):** `pywinauto` (Win32 backend para interação com componentes Delphi/VCL do Sisplan).
* **Manipulação de Arquivos:** `pypdf` (leitura, escrita e merge de PDFs), `reportlab` (geração de overlays em tempo real) e `rarfile` (extração de buffers XML comprimidos).
* **Interface de Console:** `tqdm` (barras de progresso concorrentes) e `logging` customizado com suporte a encoding UTF-8 nativo no Windows.

---

## 🚀 Fluxo Operacional do Robô
[Usuário insere os IDs] ➔ [Login & Scraping Havan] ➔ [Extração XML/PDF]
│
[Impressão Silenciosa] 🖨️ [Marca D'água PDF] 🔑 [Captura ID Interno] ◀─ [GUI Sisplan]

1.  **Entrada de Dados:** O robô solicita as chaves dos pedidos. Entradas parciais são automaticamente expandidas usando o ano vigente (ex: `12345` vira `2026-12345`).
2.  **Fase Web (Concorrente):** Realiza o bypass de segurança e autenticação no Portal Havan. Localiza os cards dos pedidos via seletores CSS, captura os links e efetua o download simultâneo do PDF (Ordem de Compra) e do RAR (Arquivo de Integração).
3.  **Processamento de Dados:** Descompacta o XML diretamente em memória, extrai metadados logísticos (Datas, Itens, Operação) e verifica se o pedido contém itens de campanhas promocionais ou regras de faturamento por Filial/Matriz (`PRODUTOS_GOVERNADOR`).
4.  **Automação do ERP (Sisplan):** Vincula-se à instância aberta do Sisplan, inicia o modo de inclusão na tela *1002 - Pedido por Grade*, preenche campos de cadastro, dispara a janela nativa de busca do Windows (`#32770`) para carregar o XML e captura o **Número Interno** gerado pelo banco de dados do ERP.
5.  **Geração e Impressão de Documentos:** Utiliza coordenadas para renderizar uma marca d'água rotacionada em 90° com o Número Interno no PDF original. O arquivo finalizado é enviado de forma assíncrona e silenciosa (sem abrir janelas) para o spooler da impressora local ou de rede.

---

## 📋 Pré-requisitos de Infraestrutura

O ambiente de execução precisa das seguintes ferramentas instaladas no Windows:

1.  **ERP Sisplan** aberto e posicionado na tela `1002 - Pedido Por Grade`.
2.  **UnRAR Tool executable:** Utilitário de linha de comando para descompactar arquivos `.rar`. (Incluso nativamente em instalações do WinRAR).
3.  **SumatraPDF:** Leitor leve de PDF utilizado para o gerenciamento de impressões em lote via CLI de forma oculta.

---

## 🔧 Configuração do Ambiente (Variáveis de Ambiente)

O projeto adota o padrão de doze fatores para configurações, isolando credenciais e caminhos locais através de variáveis de ambiente do sistema operacional. Certifique-se de definir as variáveis abaixo:

| Variável | Tipo | Descrição | Exemplo de Valor |
| :--- | :--- | :--- | :--- |
| `CNPJ_MATRIZ` | `String` | CNPJ de autenticação no portal Havan. | `00000000000100` |
| `SENHA_PORTAL` | `String` | Senha de acesso em texto plano. | `MinhaSenhaHavan123` |
| `UNRAR_TOOL` | `Path` | Caminho completo para o executável do UnRAR. | `C:\Program Files\WinRAR\UnRAR.exe` |
| `SUMATRA` | `Path` | Caminho para o executável do SumatraPDF. | `C:\LocalApps\SumatraPDF.exe` |
| `HAVAN_PEDIDOS` | `Path` | Diretório raiz para armazenamento dos arquivos baixados. | `D:\Automacao\ArquivoPedidos` |
| `IMPRESSORA_PEDIDO` | `String` | Nome exato do dispositivo de impressão no Windows. | `HP LaserJet M402 - Almoxarifado` |

---

## 📦 Instalação e Execução

1. Clone o repositório para a máquina de operação:
   ```bash
   git clone https://github.com/Gabriel2Mello/auto-pedidos-havan.git
   cd auto-pedidos-havan
   ```

2. Instale as dependências do projeto:
   ```bash
   pip install -r requirements.txt
   ```

3. Execute o robô com o comando:
   ```bash
   python main.py
   ```

---

## 🪵 Gerenciamento de Logs e Arquivos de Saída

O robô gera saídas persistentes em tempo de execução localizados na pasta raiz do script:

* **`auto-pedidos.log`:** Arquivo contendo o rastreamento completo em nível `DEBUG` para auditorias técnicas, estruturado em codificação UTF-8. O console exibe simultaneamente mensagens simplificadas em nível `INFO`.
* **`pedidos_com_erro.txt`:** Gerado de forma automatizada ao final da execução listando os pedidos que falharam na fase de download/extração para reprocessamento posterior.
* **`PROMOCIONAL.txt`:** Identifica e cataloga pedidos classificados no XML como `ITENS PROMOCIONAIS PARA COMERCIALIZACAO`, para apuração sobre tratativas fiscais especiais.

