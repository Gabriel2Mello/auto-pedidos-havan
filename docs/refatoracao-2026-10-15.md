# Correções e refatoração — 15/10/2026

Implementação autorizada após a revisão da interface e do código. As seis
correções do relatório foram aplicadas, junto da separação do serviço, contexto
de execução, adaptador HTTP e utilidades. As alterações anteriores da pasta de
trabalho foram preservadas.

## Comportamento corrigido

1. Encerrar funciona mesmo se o executor já terminou por falha ao abrir o SQLite.
   Corrupção, trava ocupada e pasta ausente têm regressões específicas; o servidor
   termina sem precisar matar o processo.
2. Logs da aplicação passam por redação após a formatação, incluindo traceback
   e exceções encadeadas. A URL do Teams e seus parâmetros conhecidos são
   registrados para redação, sem registrar resposta ou mensagem bruta de falha
   dessa integração. Logs HTTP de dependências têm menos ruído e também passam
   pelo formatador. O download do log aplica redação novamente. Arquivos antigos
   em disco são preservados; não foi feita uma limpeza retroativa deles.
3. Os testes da interface coletam falhas de asserção do executor e as propagam
   para o teste principal. Um metateste contraria deliberadamente uma verificação
   na thread e exige que o teste interno reprove.
4. Cada lote carrega uma configuração própria e coerente. Corrigir o TOML passa
   a valer no próximo lote ou em Retomar, sem trocar configurações durante uma
   inclusão ou impressão. Um erro de configuração oferece parar, com orientação
   para corrigir e iniciar outro processamento. Alterações nas variáveis de
   ambiente externas ao processo ainda exigem reabrir o programa.
5. Console, menu e API usam o mesmo parser estrito: uma lista com token inválido
   é recusada por inteiro. Argumentos inválidos não abrem o histórico nem iniciam
   processamento. Entradas por linha, vírgula e remoção de duplicados continuam
   disponíveis.
6. Testes com expectativas de 2026 usam entradas completas ou relógio controlado.
   A regra da aplicação continua completando números sem ano com o ano atual.

## Organização atual

| Módulo | Responsabilidade |
| --- | --- |
| `main.py` | Entrada de console, argumentos e menu. Reexporta `processar_pedidos` para compatibilidade. |
| `havan.py` | Abertura do navegador e ciclo de vida da aplicação local. |
| `src/servico_pedidos.py` | Processamento compartilhado; `ContextoExecucao` reúne configuração e `Integracoes`. Mantém a sequência de checkpoints. |
| `src/controlador.py` | Executor único, comandos, progresso, decisões do operador e representação do estado para a página. |
| `src/interface_web.py` | HTTP local, autenticação, recursos fixos, presença e encerramento do servidor. Reexporta o controlador para compatibilidade. |
| `src/etapas.py` | Etapas persistidas, situações finais, classificação das filas e rótulos apresentados na página. |
| `src/contratos.py`, `src/erros.py`, `src/mensagens.py` | Contratos, exceções e mensagens comuns, sem dependência da interface gráfica. |
| `src/arquivos.py` | Caminhos, XML e registros TXT. |
| `src/notificacoes.py` | Integração opcional com Teams e diagnóstico controlado. |
| `src/windows.py` | Identidade da aplicação, teclas e espera de controles Win32. O envio de teclas importa pywinauto somente quando necessário. |
| `src/seguranca.py` | Registro e redação de segredos para diagnóstico. |
| `src/utils.py` | Compatibilidade para importações anteriores; os módulos internos usam suas dependências específicas. |

O contexto da configuração usa `ContextVar` para que módulos de arquivos,
login e impressão consultem a configuração do lote, em vez de aliases de uma
leitura antiga. O download propaga esse contexto para sua thread de trabalho.
Conexões SQLite continuam pertencendo ao executor, sem serem compartilhadas
com as threads HTTP. `Integracoes` permite fornecer as implementações de banco,
portal, Sisplan, impressão e notificações ao serviço.

A página recebe do servidor a fila, o rótulo e a indicação de pendência de cada
registro. A classificação não é recalculada em JavaScript. Nenhum valor das
etapas salvas foi renomeado; não há migração destrutiva nem limpeza de filas.

## Validação

- **156 testes aprovados**, incluindo dez testes adicionais de regressão e
  integração. Os testes internos deliberadamente inválidos do metateste são
  capturados para provar a reprovação; não são falhas ignoradas da suíte.
- Integração API → controlador → serviço → SQLite/PDF verificada com arquivos
  temporários, banco e Sisplan simulados e envio de impressão substituído.
  A gravação dos itens esperados e a etapa final são conferidas fora da thread.
- Encerramento após falha, redação em logs/download, parser CLI, leitura de TOML
  corrigido e propagação de contexto ao download têm verificações específicas.
- O teste de ano futuro confirma normalização para 2027 e executa os dez testes
  da interface sob esse relógio.
- A suíte completa de **156 testes também passou simulando 01/01/2027** no
  relógio do normalizador, além da execução com a data corrente.
- Análise estática de `main.py`, `havan.py` e `src`: zero erros/avisos. Sintaxe
  JavaScript e verificação de whitespace aprovadas.
- Inspeção no navegador com SQLite temporário: rótulos, filtro de enviados,
  retomada, pausa por configuração e parada que preserva a pendência.

Testes executados no runtime de desenvolvimento Python 3.12.14 de 64 bits.
Não foram executados login real, consultas novas ao banco real, interações com
o Sisplan, importações, impressões ou envios ao Teams. Não foi gerado outro
executável nem preparado o ambiente operacional Python 3.13 de 32 bits.

O tratamento de “Aviso” permanece como última barreira de duplicidade, conforme
decisão do responsável. Inclusões incertas continuam bloqueadas e impressão
incerta continua exigindo conferência e reimpressão explícita.

## Evoluções posteriores

Backup automático, auditoria persistente de eventos, paginação no servidor,
representação única do XML validado e distribuição central de configuração
continuam como evoluções registradas na revisão. Esta refatoração prepara a
separação necessária para elas; não implanta VM, fila compartilhada ou portal
acessível pela rede. A homologação de empresa selecionada, temporização das
janelas e impressora real continua dependente de acompanhamento operacional.
