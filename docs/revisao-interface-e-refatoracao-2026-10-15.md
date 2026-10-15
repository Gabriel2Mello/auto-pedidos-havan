# Revisão completa e possibilidades de refatoração — 15/10/2026

**Atualização após autorização:** os seis achados foram corrigidos e a
refatoração principal foi aplicada. As evidências e a organização atual estão
em [refatoracao-2026-10-15.md](refatoracao-2026-10-15.md). O diagnóstico abaixo
preserva a descrição da versão revisada; suas referências de linha são históricas.

Revisão da pasta de trabalho atual, incluindo a interface web, arquivos novos
e alterações anteriores ainda sem commit. Foram examinados os pontos de entrada,
todos os módulos Python de `src`, HTML/CSS/JavaScript, configuração, abertura por
atalho, dependências, testes e documentação. Esta entrega altera somente a
documentação na etapa de diagnóstico; a implementação posterior está no documento acima.

Os cenários foram reproduzidos com arquivos temporários e integrações simuladas.
Não houve consulta nova ao banco real, login no portal, interação com o Sisplan,
importação, impressão ou envio ao Teams. Não são evidência de falhas ocorridas
com pedidos reais. A decisão de manter “Aviso” como última barreira de
duplicidade foi respeitada e não está sendo reaberta nesta revisão.

## Achados confirmados

### 1. [P2] Encerrar não fecha o servidor depois de uma falha na abertura

Referências: `src/interface_web.py:217–220` e `src/interface_web.py:319–326`.

Se o SQLite estiver corrompido ou a trava estiver ocupada por outra execução,
o executor termina e marca `finalizado`, mantendo a fase `FALHA`. O método
`encerrar()` retorna imediatamente quando encontra esse evento marcado, antes
de definir `encerrando`. Entretanto, o servidor só agenda seu encerramento
quando ambos estão marcados. O botão Encerrar pode responder com sucesso sem
finalizar o servidor; fechar a aba e aguardar o prazo também não resolve essa
combinação de estados.

Reprodução: um SQLite temporário inválido terminou com `fase=FALHA`,
`finalizado=True`, `encerrando=False` e `shutdown_agendado=False`, mesmo após
chamar `encerrar()` e `service_actions()`. Nenhum servidor ficou abandonado
pelo diagnóstico; o socket foi fechado explicitamente ao final.

Correção: registrar a intenção de encerrar mesmo quando o executor já terminou,
e permitir que o ciclo HTTP finalize nessa condição. Acrescentar testes de
encerramento após corrupção, indisponibilidade de pasta e segunda instância,
além do encerramento normal já coberto.

### 2. [P2] O segredo do webhook pode aparecer no log distribuído ao suporte

Referências: `src/utils.py:165–177` e `src/logs.py:66–87`.

A falha de envio ao Teams registra a mensagem completa da exceção. Exceções de
rede de Requests/urllib3 podem carregar o caminho e os parâmetros da URL, que
podem conter o segredo do webhook. O logger raiz também está em DEBUG, permitindo
logs HTTP de bibliotecas que incluem a URL. A proteção aplicada ao driver do
banco não protege esses caminhos. O painel permite baixar esse mesmo log.

Reprodução: uma `ConnectionError` com `MaxRetryError` e uma assinatura fictícia
na URL foi injetada em `requests.post`. O texto `SEGREDO_FICTICIO` apareceu no
log capturado. Não foi feita nenhuma requisição ao Teams e não foram usados
segredos reais. A inclusão de URL nos logs DEBUG do urllib3 também foi
confirmada por leitura do código da dependência disponível no ambiente.

Correção: registrar tipo de erro, etapa e status de forma controlada, sem a
mensagem bruta da URL; reduzir o ruído HTTP das dependências e aplicar redação
de segredos ao texto final dos logs, incluindo exceções. Cobrir respostas de
sucesso e falha com URLs/segredos fictícios. Não basta alterar apenas uma chamada
de `logger.debug`, pois bibliotecas e exceções encadeadas também podem registrar
o endereço. Não foi identificado vazamento real nesta revisão.

### 3. [P2] Algumas asserções do executor não fazem o teste falhar

Referências: `tests/test_interface_web.py:63–71` e
`src/interface_web.py:248–268`.

Há asserções de `unittest` dentro de executores que rodam na thread de trabalho.
Quando falham, o `AssertionError` é capturado pelo tratamento normal de exceções
da aplicação, que pausa para uma decisão. O resultado do teste principal não
recebe essa falha automaticamente. O teste de persistência, por exemplo, não
exige ao final que essas verificações tenham sido concluídas com sucesso.

Reprodução: no teste
`test_lista_e_salva_antes_da_resposta_e_conexao_pertence_ao_executor`, o retorno
de `pendentes()` foi deliberadamente substituído por uma lista vazia. A asserção
na thread falhou, a aplicação capturou `AssertionError`, mas o `TestResult`
continuou informando sucesso, sem falhas ou erros.

Correção: coletar observações/exceções das threads e verificá-las no teste
principal, aguardar explicitamente a conclusão esperada e reprovar se o executor
ficar pausado por uma asserção. Manter separados os erros intencionais de negócio
dos erros do próprio teste. A suíte verde continua útil, mas esse resultado
isoladamente não comprova todas as garantias declaradas pelos testes concorrentes.

### 4. [P2] Corrigir valores do TOML não atualiza a configuração da nova tentativa

Referências: `src/config.py:128–141`, `main.py:148` e `main.py:327`.

Configuração e aliases são carregados uma vez na importação dos módulos.
Quando a validação completa falha dentro de um pedido, o tratamento genérico
oferece tentar novamente. Se o responsável corrigir um valor no TOML, como o
caminho do UnRAR, essa tentativa continua usando o valor antigo. O mesmo ocorre
ao voltar ao painel e iniciar outro lote no processo já aberto. Criar um arquivo
ausente no caminho já configurado pode funcionar; alterar o valor do TOML exige
outra leitura.

Reprodução: uma configuração temporária foi carregada sem impressora; o TOML
foi corrigido. O objeto anterior continuou inválido e um objeto recém-carregado
passou na validação. O código operacional utiliza o objeto anterior e seus aliases.

Correção: explicitar que a alteração exige encerrar e reabrir, ou introduzir
carregamento controlado por execução. A configuração deve permanecer coerente
durante cada operação; não trocar caminhos ou credenciais no meio de uma
gravação/impressão. Este ponto também justifica a refatoração de configuração
antes de implementar sua distribuição central.

### 5. [P3] Os argumentos do console aceitam listas parcialmente inválidas

Referências: `main.py:75–80`, em contraste com a validação integral do menu e
da API web.

`--reimprimir` e `--reiniciar` chamam diretamente o normalizador, que descarta
tokens inválidos. A parte válida é processada sem avisar que outra parte foi
descartada. Isso pode deixar pedidos fora de uma reimpressão solicitada pelo
responsável. O painel e o menu interativo já rejeitam a lista inteira nesse caso.

Reprodução: `--reimprimir "2026-12345,INVALIDO"` encaminhou apenas
`['2026-12345']` ao fluxo simulado, sem erro de entrada. O processamento e o
histórico foram substituídos por doubles/SQLite temporário; nada foi impresso.

Correção: compartilhar o mesmo parser estrito entre API, menu e argumentos,
exibindo todos os tokens inválidos antes de iniciar qualquer ação.

### 6. [P3] Parte dos testes da interface depende do ano de 2026

Referências: `tests/test_interface_web.py:55–56`, `:66` e `:171–173`.

Os testes enviam números sem ano, mas verificam registros com ano fixo de 2026.
Em produção, completar com o ano atual é o comportamento desejado. O relógio
dos testes precisa ser controlado, ou a entrada de teste deve informar o ano.

Reprodução: simulando 01/01/2027 somente no relógio do normalizador, os dez
`InterfaceTests` apresentaram um erro, em
`test_encerrar_nao_abandona_acao_e_preserva_checkpoint`. Algumas asserções em
thread continuam mascaradas pelo achado 3, por isso esse número não representa
todas as verificações afetadas pelo ano.

Correção: fixar o relógio nas fixtures dos testes que exercitam números sem ano
e usar identificadores completos nos demais. Não alterar a regra de ano atual
da aplicação.

## Refatorações recomendadas

São propostas de manutenção, não mudanças já implementadas. Não há necessidade
de trocar de linguagem, criar outro repositório ou adicionar um framework web
para realizá-las.

| Ordem | Refatoração | Benefício e cuidado principal |
| --- | --- | --- |
| 1 | Extrair o serviço de pedidos de `main.py`; deixar ali somente a entrada do console | Console e web passam a chamar o mesmo serviço, sem a web importar o ponto de entrada CLI. Preservar a ordem dos checkpoints e manter temporariamente funções compatíveis para reduzir o risco da migração. |
| 2 | Fornecer configuração e integrações ao serviço por um contexto explícito de execução | Reduz aliases globais, facilita carregar configurações coerentes por lote e simplifica testes. Os recursos reais continuam locais. A leitura central, se aprovada depois, fica concentrada em um lugar. |
| 3 | Separar controlador/executor do adaptador HTTP em `src/interface_web.py` | O arquivo atual reúne fila de comandos, estado de tela, decisões, presença, autenticação e rotas. Separar essas responsabilidades facilita testar falhas de inicialização/encerramento sem subir toda a aplicação. |
| 4 | Centralizar etapas, regras de transição e classificação das quatro filas | Hoje existem `Literal`, `ETAPAS`, consultas SQL e mapas JavaScript com regras relacionadas. Um modelo explícito reduz divergências. Preservar os valores já gravados no SQLite e manter a API como fonte da classificação das filas. |
| 5 | Desmembrar `src/utils.py` por responsabilidade e mover erros/tipos para módulos leves | Arquivos/XML, Teams, interação Win32 e entrada de console estão juntos. A importação de utilidades puxa a automação gráfica mesmo em caminhos de leitura/servidor. Isso dificulta testes e reutilização. |
| 6 | Reutilizar uma representação validada do XML ao longo do fluxo | A retomada confere XML/PDF, a pré-validação relê o XML e a inclusão relê metadados. Um objeto com dados e itens validados reduz repetição e explicita o que foi conferido. O caminho entregue ao Sisplan e a confirmação dos itens continuam obrigatórios. |
| 7 | Organizar JavaScript/CSS em blocos legíveis e testar o contrato HTTP com o fluxo real simulado | Os testes web injetam um executor simplificado. Um teste atravessando API, controlador e serviço, com apenas as integrações externas substituídas, cobre falhas na ligação entre camadas. Não exige uma SPA ou etapa de build. |
| 8 | Publicar alterações de estado por revisão e paginar/filtrar o histórico no servidor | A tabela pagina 50 registros visualmente, mas a API envia todo o histórico a cada segundo e faz cópias desse conteúdo. A melhoria passa a ser útil com o crescimento do histórico; não foi medido um gargalo na instalação atual. |

A extração do serviço pode ser feita mantendo primeiro o comportamento atual,
sem redesenhar todas as regras ao mesmo tempo. Tipos simples e interfaces
pequenas para banco, portal, Sisplan, impressão e histórico são suficientes.

## Melhorias de confiabilidade e entrega

- Backup do SQLite usando mecanismo consistente e restauração testada em pasta
  temporária. Não copiar um arquivo aberto sem considerar a transação. Preservar
  o histórico durante atualizações e nunca retomar uma fila restaurada sem
  reconferir os estados incertos.
- Registro de eventos por pedido: etapa anterior, nova etapa, tentativa, escolha
  do operador e identificador de execução. Hoje o SQLite guarda o último estado
  e os logs rotacionados limitam o histórico detalhado disponível ao suporte.
- Fixar uma combinação validada de dependências e documentar a preparação e
  distribuição em Python 3.13 de 32 bits. O novo atalho depende de `.venv` ou
  `venv32`; a revisão não instalou esse ambiente nem gerou outro executável.
- Conferir a empresa selecionada e a regra para pedidos mistos em homologação
  acompanhada. Hoje a classificação usa o primeiro produto e Matriz é selecionada
  com `{UP}`, sem seleção explícita de Filial nem leitura posterior do campo.
  Isso depende do comportamento do Sisplan ao iniciar a inclusão. É uma
  necessidade de validação já registrada na revisão anterior, não uma gravação
  incorreta comprovada nesta revisão.
- Manter impressão incerta fora de repetição automática, mensagens compreensíveis
  e o significado preciso de “Enviado para impressão”. A conferência física da
  impressão continua manual.

## Ordem de execução sugerida

1. Corrigir a propagação das falhas dos testes concorrentes e acrescentar os
   cenários de regressão do encerramento e dos logs; corrigir esses dois problemas.
2. Uniformizar validação de entrada e orientação sobre alteração de configuração;
   remover a dependência do ano real nos testes.
3. Extrair serviço e contexto de execução em mudanças pequenas, mantendo console
   e web funcionais e as proteções do SQLite.
4. Separar o adaptador HTTP, organizar os arquivos de interface e reforçar os
   testes entre camadas. Depois tratar backup, auditoria e distribuição.

## Validação desta revisão

- **146 testes existentes passaram**, em Python 3.12.14 de 64 bits, com
  dependências de desenvolvimento em pasta temporária. O achado 3 delimita o
  que esse resultado garante nos testes concorrentes.
- **Análise estática de `main.py`, `havan.py` e `src`: zero erros/avisos.**
- **Sintaxe JavaScript válida** pelo Node e **`git diff --check` sem erros de
  whitespace**. O Git informou somente normalização futura de CRLF no
  `requirements.txt` já alterado anteriormente.
- **Seis cenários diagnósticos isolados** reproduziram os achados acima: ciclo
  de encerramento após falha, segredo fictício no log, asserção mascarada,
  configuração em memória, lista parcial por CLI e relógio em 2027.
- Não foi repetida a inspeção visual já registrada da interface nem executada
  qualquer ação operacional real. Esta revisão não homologa temporização de
  janelas, funcionamento físico da impressora ou o executável em 32 bits.

As proteções existentes foram consideradas na avaliação: lista normal salva
antes do processamento, trava da instalação, consultas parametrizadas em leitura,
pré-validação de barras, itens esperados preservados, conferência de quantidades,
decisão explícita após erro e bloqueio de inclusões/impressões incertas. Não foi
comprovado um novo cenário de duplicação de pedidos reais nesta revisão.
