# Gravação e recuperação dos downloads

PDF e XML continuam com seus nomes anteriores na pasta do pedido. A publicação
usa somente arquivos locais e a biblioteca padrão, sem banco ou serviço novo.

## Caminho normal

1. Validar o número, os campos, as datas e os itens do XML e conferir se o PDF
   pode ser aberto e possui páginas. É a mesma validação usada na retomada.
2. Preparar os dois arquivos numa subpasta exclusiva `.nunes-download-*`, dentro
   da pasta do pedido, sincronizar e conferir os bytes gravados.
3. Copiar e sincronizar os arquivos anteriores existentes para `anteriores/`.
   Os arquivos preparados ficam em `novos/`, com os mesmos nomes finais.
4. Substituir cada destino com `os.replace`, com os arquivos fechados.
5. Remover a preparação e só então informar que o download foi concluído.

Uma falha de preparação preserva os destinos. Se uma substituição falhar, a
rotina tenta restaurar os dois anteriores. Destinos que não existiam antes
voltam a ficar ausentes. Quando a restauração termina, a preparação é removida
e a tentativa continua sendo informada como falha, sem confirmar o download.
As etapas posteriores de inclusão, confirmação e impressão mantêm suas regras.

## Recuperação pendente

Duas substituições não são uma transação. Queda do processo entre elas pode
deixar um arquivo novo e um antigo. Se a restauração ou a limpeza falhar, ou
o processo for interrompido, a subpasta permanece. Ela bloqueia a leitura do
par como pronto e a tentativa de um novo download. O serviço interrompe antes
de login, download ou inclusão daquele pedido; a interface permite deixá-lo
pendente ou parar, sem oferecer repetição como solução.

A mensagem informa o caminho. Não apague essa pasta para liberar o robô e não
promova arquivos de `novos/` automaticamente. O responsável deve:

1. Encerrar normalmente a ferramenta e fazer uma cópia da pasta inteira do
   pedido, incluindo a preparação, antes de tentar qualquer restauração.
2. Conferir o log e os arquivos finais, `anteriores/` e `novos/`. Uma queda
   durante preparação/cópia pode deixar temporários incompletos; a ausência
   de um arquivo em `anteriores/` não prova que ele não existia anteriormente.
3. Restaurar somente um par cujo estado e origem tenham sido confirmados.
   Na dúvida, manter o bloqueio e obter nova cópia dos documentos sem executar
   inclusão ou impressão. Não repetir uma operação de negócio para recuperar
   o download.
4. Depois de conferir os destinos finais e o histórico do pedido, remover a
   preparação interrompida e reabrir a ferramenta. A validação normal continua
   obrigatória antes da inclusão.

Não há recuperação automática de uma pasta deixada por queda de processo;
essa escolha evita supor qual versão deve prevalecer. Uma preparação órfã
antes da primeira substituição também bloqueia conservadoramente o pedido.

## Limites e atualização

A validação do PDF comprova abertura e páginas; a identidade do pedido dentro
do conteúdo do PDF continua sem verificação. Também não há garantia de
durabilidade após falta de energia ou comportamento de armazenamento em rede.
Não edite manualmente os arquivos nem execute outra versão do robô sobre a
mesma pasta durante o processamento. Versões anteriores não reconhecem o
bloqueio; resolva qualquer pendência antes de voltar a uma versão anterior.

Feche e reabra os processos para carregar o código. Executáveis precisam ser
reconstruídos, incluindo o novo módulo `src/gravacao_download.py`.

Os testes usam PDFs/XMLs sintéticos, diretórios temporários, falhas de escrita,
sincronização, publicação e restauração e uma queda de subprocesso entre as
substituições. Não acessam portal, banco, Sisplan ou impressoras reais.
