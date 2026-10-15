# Análise da pré-validação de pedidos Havan

Verificação realizada em 15/10/2026, a pedido do responsável. Escopo: leitura dos
logs enviados, dos XMLs locais, do código da automação e consultas ao banco.
Nenhuma importação, impressão ou alteração no banco foi executada. O código da
automação permaneceu inalterado durante a análise inicial. A implementação
posteriormente solicitada está registrada ao final deste documento.

## Fontes e método

- XMLs em `C:\Users\ADM07\Desktop\Mello\python\Havan Pedidos`, incluindo `Feitos`.
- Logs anexados das telas de produtos e pedidos, além do trecho da tela de barras.
- Guia de acesso em `estrutura-nunes/area-nunes/banco-sisplan.md`.
- Perfil `principal` carregado do JSON privado indicado pelo guia, sem copiar ou
  registrar credenciais neste projeto.
- Conexões com transação explicitamente `READ ONLY`, confirmada como `on`,
  limite de oito segundos por consulta e encerramento com rollback.
- Consulta de metadados, índices e correspondências limitadas aos pedidos e
  códigos de barras presentes nos XMLs. O esquema confirmado é `sisplan`.

Os logs mostram a inicialização das telas, mas não contêm o SELECT específico
executado durante a importação Havan para procurar uma barra nem a consulta do
aviso de duplicidade. As correspondências abaixo foram verificadas diretamente
nos dados; a equivalência integral com as regras internas do importador ainda
precisa de seu log durante uma importação.

## Resultados da conferência

| Medida | Resultado |
| --- | ---: |
| XMLs lidos sem erro de parsing | 689 |
| Arquivos na pasta principal | 226 |
| Arquivos em `Feitos` | 463 |
| Pedidos distintos no conteúdo dos XMLs | 678 |
| Pedidos distintos encontrados no banco | 677 |
| Itens nos XMLs | 751 |
| Variações nos XMLs | 1.630 |
| XMLs com mais de um item | 8 |
| Códigos de barras distintos | 277 |
| Barras encontradas em `PA_ITEN_001.BARRA` | 262 |
| Barras não encontradas nesse campo | 15 |

Existem onze números de pedido com dois arquivos cada. Todos os 226 arquivos
da pasta principal correspondem a pedidos existentes no momento da consulta.
Os 677 pedidos encontrados têm `CODCLI = '00022'`; 676 têm `EMP_ID = 2` e um
tem `EMP_ID = 1`. Não houve mais de um registro em `PEDIDO_001` por número
Havan consultado.

O único número sem correspondência foi `2026-99999`, contido em
`Feitos\2026-29276 esse\Arq de integracao 2026-29276.xml`. Nesse arquivo, o
número interno do XML diverge da pasta e do nome do arquivo. Também há uma barra
com dezesseis dígitos, `7899357644233333`, ausente no cadastro. A origem dessa
inconsistência não foi determinada; o arquivo não deve ser considerado apto
apenas porque seu número não existe no banco.

## Identificação de pedido existente

O número Havan completo está em `PEDIDO_001.PED_CLI`. O campo `NUMERO` é o
número interno do Sisplan. Exemplos confirmados:

| Número Havan | Número interno | Cliente |
| --- | --- | --- |
| 2026-109020 | 11116 | 00022 |
| 2026-109160 | 11221 | 00022 |
| 2026-75450 | 10273 | 00022 |

Consulta proposta, com parâmetros vinculados pelo driver:

```sql
SELECT numero, ped_cli, codcli, emp_id
FROM sisplan.pedido_001
WHERE codcli = %s
  AND ped_cli = %s;
```

Parâmetros: cliente `00022` e número Havan completo, preservando o ano.
Existe índice em `PED_CLI`. Para vários pedidos, é possível consultar
`ped_cli = ANY(%s)` com a lista de números normalizados.

A consulta inicial deve considerar ambas as empresas: `2026-109127` já existe
com número interno `11289` e `EMP_ID = 1`. Filtrar somente a empresa 2 deixaria
esse pedido passar. Não se propõe excluir pedidos por situação ou status:
qualquer registro existente deve ser identificado e informado, salvo regra de
negócio expressamente definida para reimportação.

## Identificação de produtos por código de barras

O caminho XML é:

```text
ItensOrdemCompra/ItemOrdemCompra/
  DetalhamentoVariacoesItem/VariacaoItem/CodigoBarrasVariacao
```

É necessário percorrer todos os itens e suas variações. `CodigoProduto` é o
código do catálogo Havan; não é o código interno do produto no Sisplan. As barras
devem permanecer como texto, com remoção apenas dos espaços externos.

A correspondência confirmada é com `PA_ITEN_001.BARRA`, retornando produto,
cor e tamanho. Para `2026-109020`, por exemplo:

| Barra do XML | Produto Sisplan | Cor | Tamanho |
| --- | --- | --- | --- |
| 7899357654812 | 5132020 | 170409 | 40X120 |
| 7899357654713 | 5132022 | 171060 | 40X120 |
| 7899357654720 | 5132023 | 171061 | 40X120 |

Essas três combinações também foram encontradas nos itens do pedido interno
`11116`. Consulta proposta para o conjunto de barras de pedidos novos:

```sql
SELECT DISTINCT
    pa.barra, pa.codigo, pa.cor, pa.tam,
    pa.ativo AS variacao_ativa,
    p.ativo AS produto_ativo
FROM sisplan.pa_iten_001 AS pa
JOIN sisplan.produto_001 AS p ON p.codigo = pa.codigo
WHERE pa.barra = ANY(%s);
```

Existe índice em `BARRA`. A mesma combinação pode aparecer em várias linhas
de estoque por depósito ou lote; isso não significa produto ambíguo. A
ambiguidade relevante é uma mesma barra corresponder a combinações diferentes
de produto/cor/tamanho. Não foi encontrada nas 262 barras localizadas.

Nos registros analisados, `PA_ITEN_001.ID_PRO` está nulo; ligar por esse campo
eliminaria correspondências válidas. O vínculo por `CODIGO` acima encontrou o
cadastro principal de todos os produtos associados às barras localizadas.

As 262 variações distintas localizadas estão ativas. Contudo, dois produtos
principais estão inativos: `0128002` e `3038065`. Suas barras aparecem em onze
pedidos históricos. Existência e situação de atividade são verificações
distintas; não acrescentar bloqueio por inatividade sem confirmar a regra do
importador ou a decisão operacional correspondente.

## Barras ausentes e contexto histórico

As quinze barras ausentes de `BARRA` também não foram localizadas em `BARRACLI`
ou `BARRA28`:

```text
7899357644233333
7899357647814  7899357647821  7899357647852  7899357647869
7899357647890  7899357647906  7899357650906  7899357650920
7899357650937  7899357651064  7899357651071  7899357651095
7899357651101  7899357651118
```

Quatorze dessas barras aparecem em quatorze pedidos já existentes, relacionados
a trocadores. Em `2026-101488`, o Sisplan contém os produtos `2747001`,
`2747002`, `2747005` e `2747006`, mas hoje suas barras são, respectivamente,
`7899357654843`, `7899357654850`, `7899357652801` e `7899357652818`.

Isso demonstra diferença entre os XMLs históricos e o cadastro atual. Não
comprova quando nem por que a diferença surgiu. Não se deve marcar um pedido
já existente como falha de importação apenas porque sua barra histórica não
está mais cadastrada. Tampouco se propõe substituir automaticamente uma barra.

## Fluxo proposto para implementação

1. Normalizar a entrada, validar o formato e eliminar números repetidos.
2. Consultar pedidos existentes pelo cliente e número Havan completo; informar
   o número interno e ignorar esses pedidos antes de iniciar uma inclusão.
   Antecipar essa consulta ao download também evita transferências desnecessárias.
3. Para os pedidos restantes, obter e validar o XML: número correspondente ao
   solicitado, itens presentes e barras preenchidas e compatíveis com o formato
   confirmado para a integração.
4. Consultar todas as barras distintas e associar as pendências às respectivas
   descrições de produto e variação. Se houver ausência ou ambiguidade, ignorar
   o pedido inteiro antes de enviar o atalho de inclusão, registrando o motivo.
5. Iniciar a interação com o Sisplan somente se houver pedidos aptos. Manter a
   gravação pela interface já utilizada pela automação.
6. Preservar o tratamento de duplicidade e de produto sem cadastro na interface:
   outro operador pode gravar um pedido ou alterar um cadastro entre a consulta
   e a importação. A pré-validação não é uma trava transacional.

Falha de conexão ou consulta não significa pedido ou produto inexistente. Na
indisponibilidade do banco, interromper a etapa antes de incluir pedidos e
informar o motivo, sem liberar a importação com resultado inconclusivo.

A menor alteração necessária é um módulo de consulta de leitura, extração das
variações em `src/pedidos.py` e integração dessa conferência antes da inclusão.
O caminho do JSON privado e o perfil devem ser configuráveis, sem copiar senhas
para o código, TOML versionado ou logs. Usar parâmetros SQL e transações de
leitura. Não são necessários ORM, criação de tabelas ou novos índices para a
conferência proposta, conforme os índices encontrados.

## Validação necessária ao implementar

- Testar pedido existente em cada empresa, pedido ausente e consulta indisponível.
- Testar XML com vários itens, barra ausente, número divergente e entrada repetida.
- Testar repetição de estoque para a mesma combinação e barra com combinações
  diferentes, distinguindo duplicidade de linha e ambiguidade de cadastro.
- Garantir que nenhum atalho de inclusão seja enviado para pedidos não aptos.
- Confirmar no log da ação de importar Havan os filtros adicionais do importador,
  especialmente atividade, depósito, qualidade ou outras condições de cadastro.
- Validar a dependência de banco no Python de 32 bits e no executável distribuído.

Esta análise confirma a viabilidade das consultas e suas correspondências nos
dados observados. Não equivale a validação de uma implementação, que ainda não
havia sido feita nessa etapa, nem comprova todas as regras internas do importador Sisplan.

## Implementação e verificação em 15/10/2026

Implementados `src/banco.py` e `src/prevalidacao.py`, integrados ao fluxo em
`main.py`. Pedidos existentes são ignorados antes do download; XMLs e barras
dos pedidos restantes são conferidos antes de iniciar a interface. A duplicidade
é consultada novamente antes de cada inclusão, mantendo os avisos originais do
ERP. Dados fixos e consulta compartilham o mesmo código de cliente Havan.

O TOML agora recebe `banco_config` e `banco_perfil`. A configuração local desta
máquina aponta para o JSON privado do estrutura-nunes, sem copiar credenciais.
O driver `pg8000` foi incluído em `requirements.txt`. A regra de barras aceita
13 dígitos, preserva zeros à esquerda e não acrescenta filtro por atividade.

Verificações concluídas:

- 42 testes automatizados aprovados, incluindo indisponibilidade do banco,
  duplicidade nas duas empresas, XML inválido, todas as variações, barras ausentes
  e ambíguas, interrupção entre pedidos e bloqueio de ações na interface.
- Consultas do novo módulo executadas no banco real, com confirmação de
  `transaction_read_only = on`, correspondências das duas empresas e 262 barras
  cadastradas entre as 276 barras dos XMLs estruturalmente válidos.
- Nova validação aplicada aos 689 XMLs: 688 aceitos na validação estrutural e um
  rejeitado por identificação divergente. Aceitação estrutural não significa
  que as barras estejam cadastradas nem autoriza reimportação de pedidos existentes.
- Fluxo principal executado com o banco real para os 226 arquivos da pasta
  principal, com portal e ações de interface substituídos por bloqueios de teste:
  todos ignorados como existentes, sem acessar portal ou interface.

Os testes foram executados no Python 3.12 de 64 bits disponível nesta sessão,
com dependências em diretório temporário. Não houve inclusão ou impressão real,
recompilação do executável nem validação do pacote distribuído em Python de 32 bits.
O SELECT interno específico do importador Havan continua fora dos logs recebidos.

## Confirmação, avisos, retomada e logs

Por solicitação posterior do responsável, implementados os itens 2, 3, 4 e 5
da lista de próximas melhorias:

- Confirmação da gravação por cliente, número Havan, número interno e presença
  de itens. A relação conferida no banco é `PED_ITEN_001.ID_PED = PEDIDO_001.ID`.
  `EMP_ID` dos itens está vazio nos exemplos consultados e não foi usado no vínculo.
- Apenas ausência de janela na busca é opcional. Timeout sem causa conhecida,
  falha de acesso ou erro ao aguardar/clicar/fechar uma janela encontrada são
  fatais. A busca considera somente janelas visíveis para não confundir formulários
  ocultos do Delphi com um aviso exibido.
- SQLite local e trava de execução, sem dependência adicional. Estado salvo
  antes do comando de gravação e antes do envio ao Sumatra, permitindo recuperar
  gravação confirmada, PDF pronto e impressão pendente sem importar novamente.
- Interrupção ou falha de retorno durante o envio ao Sumatra resulta em etapa
  incerta, sem repetição automática. Reimpressão é explícita. PDF final é gravado
  por substituição de arquivo temporário, preservando o anterior em caso de erro.
- Log em modo de acréscimo, rotação de 5 MiB com cinco arquivos anteriores,
  identificador de execução e resumo final inclusive em caso de interrupção.

Disponíveis `--retomar`, `--reimprimir` e `--reiniciar`, com comportamento e
condições documentados no README. Uma pendência sem correspondência no banco
impede novas inclusões até ser resolvida. Nenhum pedido é excluído ou alterado
no banco pelas consultas ou pelo histórico local.

O responsável esclareceu o padrão do arquivo
`2026-109335/11250 2026-109335.pdf`: o prefixo `11250` é o número interno do
Sisplan. Confirmados o título `Pedido 11250`, duas páginas e o vínculo no banco,
incluindo a presença de itens. O nome e esse padrão foram preservados.

Verificação desta etapa:

- 81 testes automatizados aprovados, incluindo falhas de gravação, persistência,
  janelas, geração de PDF, envio e interrupção durante impressão, além da retomada.
- Verificação estrita com basedpyright sem erros ou avisos em `main.py` e nos
  módulos `banco`, `estado`, `imprimir`, `handle_app`, `importar`, `resumo` e `logs`.
- Confirmação de gravação executada em leitura no banco real para o exemplo
  informado pelo responsável.
- Reimpressão simulada com uma cópia temporária do PDF informado, sem o original
  da ordem de compra: o PDF numerado foi reutilizado e o estado final persistido.
  O subprocesso de impressão foi substituído por um retorno simulado; não houve
  impressão real. SHA-256 do PDF original permaneceu igual.
- Novo fluxo com banco real e histórico temporário: os 226 pedidos existentes
  foram ignorados, com portal, interface e impressão bloqueados no teste.

Permanecem sem execução a importação e a impressão reais, a recompilação e a
validação do executável em Python de 32 bits. As verificações em leitura não
substituem essas etapas operacionais.

## Filas completas e operação por usuário leigo

O responsável solicitou fila desde a digitação, menu Inserir/Retomar/Reimprimir,
reimpressão com números digitados e pausa em erros para escolha do operador.

A solução adotada mantém um único SQLite. As quatro filas são visões por etapa:
a baixar, baixados, no Sisplan e enviados para impressão. Não se criaram arquivos
separados nem um serviço de filas. Isso evita que uma interrupção entre retirar
de uma lista e acrescentar em outra perca ou duplique o pedido. A transação de
entrada salva o lote completo; os registros concluídos continuam no histórico.
O esquema anterior permanece compatível, sem apagar etapas já registradas.

Retomar agora inclui o download e a pré-validação, além da impressão. Arquivos
locais são conferidos antes do reaproveitamento. Inclusão iniciada é registrada
antes da primeira ação de inclusão; interrupções nesse ponto exigem conferência
e não permitem outra inclusão, inclusive de outro pedido. Cancelamentos
conhecidos de produto sem cadastro devolvem o pedido à fase baixado para correção.

O fluxo segue sequencial, reutilizando sessão do portal e controles de interface
nos caminhos normais. Assim pode pausar exatamente no pedido com falha, sem
continuar executando ações nos seguintes. A consulta inicial de duplicidade
continua em lote; tentativas após uma pausa reconferem os dados, e a inclusão
sempre tem uma nova consulta imediatamente antes de começar.

Nenhum pedido é repetido por decisão automática da aplicação. O menu de erro
oferece repetir somente em etapas seguras e avançar somente quando não houver
risco de continuar sobre uma inclusão incerta. Problemas de persistência ou
inclusão em andamento exigem atendimento do responsável. Envios de impressão
incertos permanecem sem reenvio automático; a opção Reimprimir é manual.

O console mostra mensagens curtas e as opções disponíveis. O arquivo de log
mantém identificação da execução, lista dos pedidos, transições, ambiente e
exceções completas. Falhas de banco registram tipo, SQLSTATE/errno quando
disponíveis, sem reproduzir parâmetros secretos de conexão. Falhas de leitura
do JSON informam arquivo, perfil e posição do erro de sintaxe, sem seu conteúdo.

Essa organização é benéfica para a rotina atual: melhora recuperação e
rastreabilidade com a biblioteca padrão, sem manter quatro arquivos em
sincronia ou introduzir serviço externo. Uma fila distribuída aumentaria custo
de operação sem benefício comprovado para um único robô de interface, que já
precisa executar as inclusões sequencialmente. Monitoramento do spooler foi
adiado conforme a orientação do responsável; a última fila usa o nome
"enviados para impressão", pois o retorno do Sumatra não comprova papel impresso.

Verificação final desta entrega:

- 102 testes automatizados aprovados, incluindo menu, lista inválida, persistência
  atômica da entrada, falha antes do primeiro download, reaproveitamento de
  arquivos, pausa antes de avançar ao próximo pedido, repetição somente após
  decisão do operador e bloqueio de repetição de inclusão incerta.
- Verificação estrita dos módulos do fluxo sem erros ou avisos.
- Fluxo com banco real em leitura e histórico temporário: 226 pedidos recebidos,
  uma consulta inicial em lote, 226 registros identificados como existentes,
  zero pendências finais e os 226 registros preservados na visão "no Sisplan".
  Portal, interface do ERP e impressão ficaram bloqueados por substitutos de teste.
- Os testes confirmam que a pilha técnica fica no arquivo de log e não aparece
  no console apresentado ao operador.

Não houve nova inclusão, impressão real ou recompilação do executável. A
validação operacional em Python de 32 bits continua necessária antes de
substituir a instalação em uso.

## Ajustes aprovados após a revisão completa de 15/10/2026

O responsável optou por manter o tratamento de “Aviso” como última barreira de
duplicidade. Foram aplicados os demais ajustes da revisão:

- Conexão de banco com falha é descartada. Uma nova conexão só é aberta quando
  o operador escolhe tentar novamente e essa repetição é segura.
- Sessão do portal expirada interrompe o lote e oferece reconectar ou parar.
  A reconexão faz novo login após a escolha; parar mantém as pendências.
- Diálogos são localizados dentro do processo do Sisplan, antes de conectar
  pelo handle. Isso evita a busca global e respeita o comportamento da
  biblioteca, na qual `Application.connect(process=...)` ignora título/classe.
- Falhas do histórico preservam a exceção original, caminho e códigos SQLite
  no log técnico. Falha ao abrir o log na inicialização orienta e aguarda o usuário.
- A pré-validação agrega as quantidades por produto/cor/tamanho e preserva esses
  itens numa tabela adicional do histórico antes da primeira ação de inclusão.
  A confirmação de pedido novo compara os totais com `SUM(ped_iten_001.qtde)`
  pela relação `id_ped = pedido_001.id`. Divergência bloqueia impressão.
- Retomadas de inclusão incerta utilizam os itens preservados. Pendências antigas
  sem esse registro precisam reconstruí-lo pelo XML e cadastro válido. Etapas já
  confirmadas e reimpressões antigas mantêm a conferência de cabeçalho, evitando
  comparar o saldo atual após faturamento/cancelamento com o pedido original.

Validação da entrega: 127 testes aprovados e análise estática de todo `src` e
`main.py` sem erros ou avisos. Foi verificada a presença de quantidade positiva
nas 1.630 variações dos XMLs locais. A conferência nova foi executada em leitura
para `2026-109335`, interno `11250`: três combinações e 282 peças correspondentes.
O armazenamento e a reabertura desses itens foram verificados em SQLite temporário.
Não houve inclusão, impressão, envio ao Teams ou login real no portal. O executável
distribuído e o ambiente operacional de 32 bits não foram recompilados/homologados.

## Interface local autorizada — 15/10/2026

Após a análise de viabilidade, foi implementado o painel no navegador com
Inserir/Retomar/Reimprimir, filas persistidas, decisões seguras após erro,
diagnóstico, assinatura g2mello e ícone Nunes. O guia e a preparação do ambiente
estão em [interface-web.md](interface-web.md).

Validação desta entrega: **146 testes aprovados**, análise estática sem erros
ou avisos, sintaxe JavaScript válida e inspeção visual com dados fictícios.
Não foram executados login, inclusão, impressão ou envio ao Teams. O tratamento
de “Aviso” permanece como última barreira de duplicidade. O ambiente operacional
de Python 32 bits ainda precisa ser preparado para o novo atalho nesta máquina.

## Correções da revisão e refatoração — 15/10/2026

Após nova autorização, os seis achados da revisão da interface foram corrigidos.
O fluxo compartilhado foi extraído para `src/servico_pedidos.py`, com contexto
de configuração por lote e integrações explícitas. Controlador e HTTP foram
separados; etapas, contratos, erros e utilidades passaram a ter módulos próprios.
As etapas salvas, os checkpoints e o tratamento de “Aviso” foram preservados.

**156 testes passaram com a data corrente e simulando 01/01/2027**, incluindo
regressões e integração entre API, controlador, serviço, SQLite e geração de
PDF com integrações externas substituídas. A análise estática e a sintaxe
JavaScript foram aprovadas. Uma prévia isolada no navegador conferiu filtros,
retomada, erro de configuração e parada preservando pendência fictícia.

Não houve operação real no portal, banco, Sisplan, impressora ou Teams.
Os detalhes estão em [refatoracao-2026-10-15.md](refatoracao-2026-10-15.md).
