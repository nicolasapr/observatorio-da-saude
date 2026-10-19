# Fluxo das transformações e salvaguardas

Revisão de 04/09/2026 do fluxo atual, confrontado com os scripts e notebooks legados em `_arquivo/` e com os produtos existentes em `dados/`.

## Regra comum

A unidade territorial é o município e a chave de todas as junções é `codigo_IBGE` de seis dígitos. Nome, UF e região são atributos descritivos. Contagens não são estimadas, e percentuais nunca são somados: são sempre recalculados como `total_que / total_all`.

## 1. Relatórios brutos do SISVAN

Cada relatório representa ano, mês, faixa etária e um dos dez marcadores alimentares. A extensão é `.xls`, mas o portal entrega tabela HTML. A leitura declara `.` como separador de milhar e `,` como decimal, para que `5.028` signifique cinco mil e vinte e oito respostas, não 5,028.

Antes de usar um arquivo, o script confirma no próprio cabeçalho ano, mês, faixa e marcador. Nas faixas infantis, a legenda "Total de Crianças de 2 a 4" ou "5 a 9 anos" resolve o cabeçalho genérico. O nome do arquivo local só o localiza: não prova sua identidade.

## 2. Sumário mensal (`criar_sumarios`)

Os dez relatórios validados da mesma combinação ano, mês e faixa são unidos por `codigo_IBGE`. Cada marcador gera três campos: `total_que_*`, `percentual_que_*` e `total_all_*`.

O script exige código IBGE válido e único em cada relatório. Também interrompe a gravação se uma cidade tiver cadastro textual conflitante entre marcadores: ele não escolhe uma grafia arbitrariamente e preserva o sumário existente para inspeção. Uma cidade presente em apenas um marcador é mantida, com os demais campos ausentes, nunca preenchidos artificialmente com zero.

Há uma salvaguarda adicional porque apenas 397 dos 3.600 relatórios brutos possíveis estão arquivados localmente. `criar_sumarios` só grava se encontrar e validar exatamente os dez marcadores. Com conjunto incompleto, não escreve nada. Um relatório recuperado isoladamente é aplicado por `aplicar_recuperado`, que atualiza somente as três colunas daquele marcador no sumário mensal já completo.

## 3. Higienização mensal (`sanear_sumarios`)

São removidas linhas sem código IBGE válido, que são sobras de totais estaduais e não municípios. Se uma cidade aparece duas vezes no mesmo mês, o script toma o máximo de cada contador e recalcula o percentual. A auditoria direta mostrou que esses casos eram cópias parciais da mesma cidade; somar duplicaria a contagem. As escritas são atômicas, evitando `.xlsx` parcial se o processo cair.

## 4. Agregações SISVAN

`sumarios_anuais` empilha os meses de uma faixa, soma `total_que_*` e `total_all_*` por código IBGE e só então recalcula cada percentual. `sumarios_totais` faz a mesma operação entre anos. A versão antiga agrupava também por textos cadastrais, o que podia dividir uma cidade quando o portal alterava grafia ou acento.

`series_mensais` agrega os sumários por Brasil, região e UF. Antes de ordenar, normaliza a codificação de nomes de meses; assim `MARÇO` não é perdido por diferença no acento. O resultado são nove séries, cada uma com 120 meses entre janeiro de 2015 e dezembro de 2024, sem interpolação ou imputação.

## 5. Rateio e PNAE

`percen` une cada sumário anual à planilha `quant_idades.xlsx` por código IBGE, um a um. Os pesos são `PNACN` e `PNAPN(4)` (2 a 4 anos), `PNAPN(5)` e `PNAFN(6-9)` (5 a 9 anos), e `PNAFN(10-15)` (adolescentes). Eles reproduzem o rateio manual confirmado no projeto original. São uma distribuição fixa de 2019, e não uma composição demográfica anual.

`pnaes_redes` lê os arquivos Redes do FNDE, interpreta valores brasileiros, mapeia prefeitura para código IBGE e interrompe caso uma entidade com valor diferente de zero não tenha mapeamento. As exceções históricas de grafia são explícitas. Os valores de 2015 a 2023 são pagos; 2024 é valor previsto, marcado como tal.

As fórmulas finais verificadas são:

- 2 a 4: `TOTAL = PNACN × valor_pago_CR + PNAPN(4) × valor_pago_PE`;
- 5 a 9: `TOTAL = PNAPN(5) × valor_pago_PN + PNAFN(6-9) × valor_pago_FN`;
- adolescentes: `TOTAL_EF = valor_pago_prefeituras_EM + valor_pago_secretarias_EM × percen_MAT_MED + valor_pago_FN × percen_MAT_FUND_AF`.

No arquivo de adolescentes, o Censo Escolar é filtrado para rede estadual (`TP_DEPENDENCIA = 2`) e agregado por código municipal. As razões cidade/UF entram nas parcelas que precisam ser rateadas: o valor estadual de Ensino Médio é rateado pela participação municipal em matrículas de Ensino Médio, e o valor de Fundamental usa a participação municipal nos anos finais. O repasse municipal de Ensino Médio já vem identificado para a cidade no arquivo Redes do FNDE e, por isso, entra integralmente, sem novo peso. A cópia mais antiga de notebook que deixava os pesos fora do total está superada.

## 6. Verificação e limites

`repair_percentuais` é somente leitura por padrão. Ele aponta percentuais que não batem com os contadores e contagens não inteiras, mas não tenta multiplicar valores por mil: `2,5` é ambíguo sem consultar a fonte. A opção explícita `--aplicar-percentuais` recalcula apenas os campos percentuais; contadores só podem ser corrigidos a partir do relatório SISVAN ou FNDE de origem.

As verificações registradas em `analise/` confirmaram 360 sumários mensais sem problemas estruturais, 397 relatórios brutos comparados diretamente e 180 testes de tendência reproduzidos independentemente. Os 3.203 relatórios brutos que não estão neste acervo não foram considerados errados: eles apenas limitam a auditoria documental direta e exigiriam nova consulta ao SISVAN ou ao acervo antigo para serem revisados.

O dicionário completo de proveniência, incluindo cada coluna final do PNAE de adolescentes e seu uso ou não uso na fórmula, está em `docs/PROVENIENCIA-DOS-DADOS-E-CALCULOS.md`.
