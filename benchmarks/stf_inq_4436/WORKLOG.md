# Registro do caso de benchmark

## Escopo

Este registro documenta o caminho completo realizado em 29 de julho de 2026: seleção da peça, programação do teste, execução do TCRIA, exame assistido pelo ChatGPT, revisão humana e conversão do aprendizado em regressão permanente.

O objeto é o inteiro teor do acórdão do STF no Inquérito 4.436/DF, julgado em 2022. O documento tem 60 páginas e linguagem intensamente acusatória sobre corrupção e lavagem de dinheiro, embora sua natureza documental seja decisória e jurisprudencial.

## 1. Seleção da peça modelo

O PDF foi escolhido por reunir, em um único artefato:

- ementa, relatório, voto do relator, votos vogais e ata;
- diversos investigados e diferentes papéis processuais;
- alegações de valores elevados e mecanismos de ocultação;
- datas, referências processuais e códigos de autenticação;
- fundamentos judiciais distintos que convergem para o mesmo resultado;
- risco elevado de um classificador superficial confundir alegação reproduzida com fato reconhecido judicialmente.

Antes da auditoria, foram confirmados o total de 60 páginas, a ausência de criptografia e a existência de uma camada textual utilizável. Páginas do início, do corpo e da ata foram renderizadas e verificadas visualmente.

## 2. Programação e execução do teste

O documento original foi mantido intacto. Uma cópia foi colocada em um workspace repetível de caso e processada em modo estrito pelo pipeline oficial.

Fluxo executado:

```text
case init -> case run --strict -> investigate
```

Foram produzidos localmente:

- auditoria oficial JSON e Markdown;
- revisão complementar de itens bloqueados;
- resumo de preparação;
- projeção de cronologia;
- relatório unificado em PDF;
- relatório de investigação em JSON, Markdown e PDF.

Os artefatos de execução permanecem em `cases/` e `output/`, que são diretórios locais ignorados pelo Git. O benchmark versiona a fonte, o contrato e a regressão, sem versionar caminhos locais ou relatórios com metadados do ambiente.

## 3. Resultado determinístico do TCRIA

O TCRIA:

- preservou o SHA-256 da fonte;
- extraiu 263.473 caracteres com qualidade `high`;
- registrou 133 ocorrências de datas e 54 ocorrências monetárias;
- aprovou a verificação de rastreabilidade;
- identificou o documento como decisão ou opinião;
- classificou-o como `CASE_LAW_REFERENCE`;
- selecionou a rota `REFERENCE_CASE_LAW`;
- aplicou o `document intent shield`;
- manteve `raises_accusation=false`;
- preservou o artefato em `non_accusation_set`.

A intensidade do vocabulário acusatório não iludiu a governança. A natureza e a função documental prevaleceram sobre a simples contagem de palavras de acusação.

## 4. Projeção dos portais

O resumo de preparação e a cronologia acusatória apresentaram listas vazias porque essas camadas projetam apenas `accusation_set`. O documento estava preservado em `non_accusation_set` como referência jurisprudencial.

Consequentemente:

- cronologia vazia não significou perda de datas;
- `case_readiness=low` não significou baixa qualidade de extração;
- o resultado indicou ausência de material automaticamente promovível para um workspace acusatório.

Essa semântica foi transformada em teste automatizado para impedir futuras interpretações equivocadas.

## 5. Exame assistido pelo ChatGPT

O ChatGPT utilizou o registro governado para explicar o processo. A leitura identificou corretamente:

- a rejeição unânime da denúncia;
- a diferença entre rejeição na admissibilidade e absolvição de mérito;
- a inépcia da denúncia como fundamento do relator;
- a falta de ligação suficientemente descrita entre vantagem alegada e função pública;
- os fundamentos alternativos de ausência de justa causa e corroboração independente insuficiente;
- a mudança de posição da própria PGR;
- o fato de a discussão sobre prescrição da lavagem não ter sido o fundamento dispositivo;
- a situação processual distinta de Marcelo Odebrecht.

O resultado demonstrou compreensão útil de um caso até então desconhecido pelo leitor humano, sem transformar as alegações do acórdão em fatos provados.

## 6. Revisão humana e correção

Na primeira descrição do resultado, o assistente afirmou que as camadas posteriores haviam "perdido" datas e valores. A revisão humana corrigiu o enquadramento:

> A informação foi preservada; apenas não foi selecionada para portais cuja finalidade não incluía aquela referência jurisprudencial.

A inspeção do JSON e do código confirmou a correção. A extração integral, os sinais e a rastreabilidade permaneciam disponíveis. O filtro ocorria somente na projeção de `accusation_set`.

Essa intervenção exemplifica a arquitetura de responsabilidade do caso:

```text
TCRIA preserva e governa -> ChatGPT interpreta -> humano valida e corrige
```

## 7. Formalização do benchmark

O aprendizado foi convertido nos seguintes artefatos versionados:

- `benchmark.json`: contrato determinístico e resultados observados;
- `CHATGPT_EVALUATION.md`: rubrica de compreensão e falhas críticas;
- `tests/test_benchmark_stf_inq_4436.py`: regressão executável;
- `source/STF_INQ_4436_7c0e2.pdf`: fonte fixada por hash;
- `README.md`: finalidade, reprodução e regra de aceitação.

O teste automatizado verifica tanto a preservação e os gates quanto a distinção entre informação presente e informação não projetada no portal acusatório.

## 8. Validação registrada

Em 29 de julho de 2026:

- os 2 testes específicos do benchmark passaram;
- a suíte completa do repositório passou com 20 testes;
- a leitura assistida, após a correção terminológica humana, atingiu 8 de 8 afirmações exigidas e nenhuma falha crítica.

## Limite da evidência

Este benchmark comprova a execução reproduzível deste caso e protege seu comportamento esperado contra regressões. Ele não substitui uma bateria com outros tribunais, formatos, qualidades de OCR e estruturas processuais, nem transforma a explicação do ChatGPT em decisão oficial do TCRIA.
