# Validação operacional em 18 de outubro de 2026

O teste separou reprodução do snapshot histórico e disponibilidade atual das
fontes oficiais. Não foram sobrescritos dados usados nos artigos. As fórmulas
financeiras aprovadas foram preservadas.

## Resultados

| Verificação | Escopo | Resultado |
|---|---|---|
| Testes automatizados | Regressões, incluindo CLI completa das três faixas e restauração do pacote com dados artificiais | Aprovados |
| Verificação dos dados preservados | 102 checagens de comportamento e invariantes | Zero falhas |
| Regeneração histórica isolada | 360 mensais, 30 anuais, 3 históricos, 9 séries e 90 produtos PNAE | 492 produtos numericamente equivalentes |
| Proteção do snapshot original | Tamanho e data de modificação dos arquivos de origem | Nenhum original alterado |
| Extração FNDE ao vivo | Dez arquivos Redes, 2015–2024 | XLSX baixados, abertos e cabeçalhos validados |
| Extração INEP ao vivo | Censo Escolar 2024 | ZIP baixado, CSV identificado, extraído e validado |
| Extração IBGE ao vivo | Estimativas municipais de 2016 e 2024 | 5.571 localidades em cada resposta; uma sem valor numérico |
| SISVAN preservado | 397 relatórios brutos, sumários mensais e séries derivados | Conferência com o acervo já baixado |

Uma comparação literal encontrou nomes legados de colunas e percentuais
textuais no sumário de março de 2016, crianças de 5 a 9 anos. Seus contadores
coincidiram com a regeneração. A equivalência acima normaliza os nomes conforme
o pipeline e deriva percentuais textuais reconhecidos dos respectivos contadores.
O arquivo original permaneceu intacto; os produtos anuais e financeiros também
coincidiram numericamente.

## Correções operacionais

- O FNDE devolvia página HTML com HTTP 200; o coletor a salvava como `.xlsx`.
  Agora segue somente um link oficial de download no mesmo domínio, valida a
  planilha e grava o arquivo atomicamente. Cache inválido é rejeitado.
- O INEP salvava `microdados_censo_escolar_ANO.csv`, mas a transformação procurava
  `microdados_ed_basica_ANO.csv`. Extrator, transformação e catálogo agora aceitam
  os nomes históricos e `.CSV`, e novas coletas usam o nome canônico.
- A conexão INEP por Python falhava na verificação da cadeia de certificados
  neste ambiente, embora a conexão nativa do sistema funcionasse. A sessão usa
  `truststore` com verificação TLS habilitada, sem `verify=False`.
- Downloads INEP são transmitidos a arquivo temporário e validados antes da
  substituição atômica. A escolha ambígua de CSV dentro do ZIP é rejeitada.
- Respostas SIDRA vazias ou de outro ano falham explicitamente. Valores não
  numéricos permanecem ausentes e conservam o texto em `populacao_fonte`.
- Falhas de coleta não são mais escondidas como execução bem-sucedida. A
  transformação interrompe a cadeia na primeira exceção; entradas financeiras
  obrigatórias ausentes geram erro. Linhas malformadas do Censo não são puladas
  silenciosamente pelos leitores usados na transformação e no estudo de caso.
- O verificador financeiro foi atualizado para conferir o Ensino Médio
  municipal direto, além dos dois componentes ponderados por matrículas estaduais.
- `OBSERVATORIO_DADOS_DIR` permite trabalhar em área separada. O caminho padrão
  de dados não depende mais do link simbólico `codigo/dados`.

## Limites da aprovação

Os testes automatizados usam dados artificiais para validar o encadeamento. A
regeneração histórica usa relatórios e sumários preservados; não substitui uma
nova coleta dos 3.600 relatórios SISVAN. Apenas 397 brutos estão arquivados.

A validação do SISVAN nesta etapa usa os dados já baixados. Uma nova coleta
não integra o escopo desta aprovação e fica para outra etapa.

Os downloads de teste de FNDE, IBGE e INEP ficaram em área isolada. Sua validação
não implica substituição das fontes históricas nem atualização dos resultados
dos artigos. O FNDE 2024 ao vivo confirmou `VALOR_PREVISTO`; 2015–2023 confirmaram
`VALOR_PAGO`, com notas nos cabeçalhos de 2020 e 2021.

## Como repetir

Consulte `EXECUCAO-DO-PIPELINE.md`. O script
`analise/validar_transformacao.py` cria logs por etapa e `resultado.json` numa
pasta independente. A integração contínua executa os testes sem acesso às bases
grandes e sem depender dos serviços públicos.
