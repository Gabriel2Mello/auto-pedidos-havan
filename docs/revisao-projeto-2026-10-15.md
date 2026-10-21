# Revisão do projeto — 15/10/2026

> Atualização de 21/10/2026, E9: o responsável aprovou manter o cancelamento
> e exigir correspondência única no banco para retirar o pedido da fila.
> Ausência/ambiguidade/falha deixam `aviso_pendente`, sem reinclusão automática.
> Essa decisão substitui o desfecho anterior do item 1. Uso e limites no
> [README](../README.md#recuperação-de-avisos--e9-21102026).

Atualização após a revisão: por orientação do responsável, o item 1 permanece
como última barreira de duplicidade. Os itens 2 a 6 foram corrigidos, com a
opção de reconectar ou parar explicitamente no caso do portal (item 3).
A conferência de produtos e quantidades do item 7 foi implementada para novas
inclusões e retomadas de inclusão incerta. As descrições abaixo preservam o
diagnóstico da versão examinada; as linhas citadas correspondem àquela versão.

Revisão da versão presente na pasta de trabalho, incluindo arquivos novos e alterações ainda sem commit. Foram examinados o programa principal, todos os módulos de `src`, a configuração, as dependências, os testes e a documentação. O código operacional não foi alterado nesta revisão.

Foram identificados sete achados: um de prioridade alta (P1), cinco de prioridade média (P2) e uma melhoria de integridade a implementar antes de afirmar que a importação foi conferida integralmente. Os cenários abaixo são riscos reproduzidos com simulações; não são evidência de pedidos reais perdidos ou gravados incorretamente.

1. **[P1] Um aviso genérico pode retirar um pedido da fila sem comprovar sua existência.**

   Referências: `src/handle_app.py:200–209` e `main.py:311–314`.

   `handle_aviso_duplicado` interpreta qualquer janela visível com título `Aviso` e classe `TfmAviso` como duplicidade. Não lê a mensagem. Em seguida envia Não/Desistir/Sim. O programa principal aceita esse resultado e grava `existente` sem uma consulta posterior ao banco. Esse estado deixa de aparecer em Retomar.

   Reprodução isolada: uma janela simulada com mensagem “Prazo de entrega inválido” retornou `True` e provocou três envios de teclas. A rota seguinte, com lista de registros encontrados vazia, deixou o pedido sem pendências. O teste comprova a interpretação genérica; não comprova quais outras mensagens o Sisplan usa nessa classe de janela.

   Correção recomendada: reconhecer a mensagem específica de duplicidade, vinculada ao pedido e processo corretos; mensagens desconhecidas devem interromper o processamento. Depois do cancelamento, conferir novamente o banco e somente concluir como `existente` quando houver correspondência confirmada. Conferir também a saída efetiva do modo de inclusão antes de liberar outro pedido. Aplicar reconhecimento de conteúdo ao tratamento de `Bloqueio`, que hoje também presume produto sem cadastro apenas pelo título/classe.

2. **[P2] Tentar novamente não reconecta uma conexão de banco perdida.**

   Referências: `src/banco.py:123–145` e `main.py:151–174`.

   O banco é aberto uma vez por processamento. Após falha na consulta, a conexão permanece armazenada, e a escolha do operador por repetir volta a usá-la. Se houve queda do socket, a restauração da rede não recupera essa conexão. Voltar ao menu e iniciar outro processamento cria uma conexão nova, mas a opção oferecida para tentar o pedido novamente não faz isso.

   Reprodução isolada: com uma conexão encerrada e uma segunda conexão saudável disponível no conector simulado, duas tentativas falharam e houve apenas uma chamada para conectar.

   Correção recomendada: invalidar conexões quebradas e abri-las novamente somente após a escolha explícita do operador. Manter a reconferência do pedido e os bloqueios de inclusão incerta; não transformar reconexão em repetição automática de ações na interface.

3. **[P2] Uma sessão expirada do portal é reutilizada na nova tentativa.**

   Referências: `main.py:167`, `main.py:281–294` e `src/baixar.py:127–144`.

   A sessão autenticada fica em cache. Se expirar durante o lote ou enquanto o operador resolve um problema, o download pode receber uma página de login com HTTP 200. O processamento informa falha, mas tentar novamente reutiliza a mesma sessão e não realiza novo login. Somente o recurso do Sisplan é descartado no tratamento comum de erro.

   Reprodução isolada: duas falhas consecutivas de download, com repetição solicitada pelo operador, usaram a mesma sessão; houve apenas um login. A resposta real do portal após expiração não foi provocada nesta revisão.

   Correção recomendada: identificar redirecionamento/resposta de autenticação e invalidar a sessão nesse caso. Após autorização para repetir, criar uma sessão nova e autenticar novamente. Preservar mensagens distintas para sessão expirada, pedido inexistente e falha de comunicação.

4. **[P2] A busca por diálogos não está limitada ao processo do Sisplan.**

   Referências: `src/handle_app.py:131–148` e `src/handle_app.py:165–179`.

   A conexão com a janela principal identifica o Sisplan, mas as buscas posteriores por `Abrir`, `Aviso` e `Bloqueio` usam novas buscas globais por título e classe. Outro aplicativo com uma caixa `Abrir` pode causar ambiguidade e parar a automação. Se for o único diálogo correspondente no instante da busca, pode receber o caminho XML e Enter destinados ao Sisplan.

   Reprodução isolada: a chamada usada para selecionar `Abrir` contém título/classe/timeout, sem processo ou handle associado ao ERP. Não houve interação real com outras janelas.

   Correção recomendada: carregar o identificador do processo obtido na conexão inicial e restringir os diálogos a esse processo. Quando aplicável, verificar também a janela proprietária e focar o diálogo esperado antes de enviar teclas.

5. **[P2] Falhas do histórico perdem o diagnóstico original no log.**

   Referências: `src/estado.py:78–80`, `src/estado.py:112–113` e `src/estado.py:129–130`; o padrão se repete nas consultas das filas e inclusão da lista.

   Os tratamentos capturam erros do SQLite e lançam uma mensagem genérica com `from None`, sem registrar antes a exceção original. Assim, mesmo que o chamador use `logger.exception`, o arquivo não informa se a causa foi corrupção, falta de espaço, somente leitura ou outra falha. Isso prejudica diretamente o suporte ao usuário leigo.

   Reprodução com arquivo temporário corrompido: a causa original era `file is not a database`; essa informação não apareceu no traceback formatado da exceção propagada.

   Correção recomendada: registrar a causa original no log técnico antes de converter para `EstadoError`, incluindo operação, caminho do histórico e código/nome do erro SQLite quando disponíveis. A mensagem de tela pode continuar simples. Preservar o bloqueio de ações quando não for possível salvar o estado.

6. **[P2] Falha ao abrir o log escapa do tratamento amigável de erros.**

   Referências: `main.py:48–49`, `main.py:68` e `src/logs.py:74–77`.

   `setup_logging()` roda antes do bloco de tratamento de erros. Sem permissão para abrir `auto-pedidos.log`, por exemplo, o programa termina com exceção sem chegar ao menu de erro nem manter a tela para orientação. Ao abrir o executável por duplo clique, o operador pode perder a mensagem junto com o fechamento do console.

   Reprodução isolada: uma falha `PermissionError` em `setup_logging` propagou para fora de `main`; nenhuma pergunta ao operador foi chamada.

   Correção recomendada: tratar explicitamente a inicialização dos logs, informar o caminho e a falha, manter a tela aberta e encerrar antes de iniciar operações. Se houver log alternativo em pasta gravável do usuário, informar sua localização ao suporte.

7. **Melhoria de integridade: a confirmação de gravação aceita qualquer item.**

   Referências: `src/banco.py:183–206` e `main.py:318–323`.

   A consulta confirma número interno, unicidade do pedido e a existência de pelo menos uma linha em `ped_iten_001`. Não compara os produtos, cores, tamanhos e quantidades gravados com os esperados no XML. A pré-validação das barras confirma cadastro, não a importação completa. Portanto, se o ERP salvar um pedido parcialmente importado, essa verificação ainda o aprovará e liberará a impressão.

   Reprodução da condição atual: o retorno `[numero, empresa, True]` encerra a confirmação com sucesso; a função não recebe os itens esperados. Não foi simulada nem identificada uma gravação parcial real no ERP.

   Evolução recomendada: preservar os itens esperados a partir do XML e comparar seus totais por produto/cor/tamanho com o banco antes de liberar impressão. A comparação deve respeitar como o Sisplan agrega linhas, trata quantidades e aplica conversões; comparar apenas a quantidade de linhas seria insuficiente. Uma divergência deve manter a inclusão pendente de conferência, sem reimportar automaticamente.

A validação executada nesta revisão teve os seguintes resultados:

- **102 testes existentes passaram**, em Python 3.12 de 64 bits, com dependências de teste em pasta temporária.
- **Análise estática de `main.py` e de todos os módulos de `src`: zero erros e zero avisos.**
- **`git diff --check`: sem erros de whitespace.** O Git informou apenas normalização futura de CRLF em `requirements.txt`.
- **Sete verificações adicionais isoladas** confirmaram as condições descritas acima, usando mocks e arquivos temporários. Elas foram executadas para diagnóstico, sem adicionar testes que cristalizem os comportamentos incorretos como comportamento esperado.
- Não foram realizados novos acessos ao banco real, login no portal, importações, envios ao Teams ou impressões. A revisão não homologa o executável distribuído nem a operação real em Python de 32 bits.

A arquitetura atual já oferece proteções úteis: lista inicial persistida em uma transação, trava contra duas execuções da mesma instalação, consultas parametrizadas em transações de leitura, checkpoints antes de ações irreversíveis, bloqueio de inclusões incertas e proteção contra reenvio automático de impressão incerta. O nome “Enviados para impressão” é coerente com a evidência obtida do Sumatra; não comprova a saída física do papel.

Depois dos achados, as melhorias recomendadas são:

- Backup automático do histórico e procedimento de restauração testado, preservando o estado também nas atualizações da aplicação.
- Histórico de eventos por pedido, além do último estado atual: decisão do operador, tentativa, etapa anterior, etapa seguinte e identificador da execução. A rotação dos logs limita a auditoria disponível hoje.
- Conferência explícita da empresa selecionada antes de gravar. Atualmente somente a seleção de Matriz é comandada, por uma tecla relativa, e a classificação usa o primeiro produto do XML (`src/importar.py:77–78` e `src/pedidos.py:65`). A regra para pedidos com produtos de classificações diferentes e o comportamento de reinicialização do campo pelo ERP precisam ser validados antes de alterar essa lógica.
- Versões reproduzíveis das dependências e rotina documentada de empacotamento, com teste do executável no ambiente de destino.
- Homologação acompanhada de um pedido novo, de uma interrupção antes/depois da gravação e de uma impressão incerta, depois das correções. Os testes atuais do fluxo simulam interface, banco e impressão e não confirmam a temporização real das janelas.

A primeira correção deve ser a identificação e confirmação de duplicidade, pois hoje ela pode encerrar uma pendência incorretamente. Em seguida, priorizar diagnóstico dos erros e recuperação de conexões, conforme a necessidade de suporte ao operador.
