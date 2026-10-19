# Proveniência dos dados e cálculos

Este é o dicionário operacional do pipeline. Ele descreve a origem de cada grupo de colunas, a chave usada e a fórmula que produz cada resultado. A versão vigente foi revisada em 04/09/2026.

## 1. Chave, território e SISVAN

| Coluna ou grupo | Origem imediata | Tratamento | Uso posterior |
|---|---|---|---|
| `regiao`, `codigo_UF`, `UF`, `codigo_IBGE`, `municipio` | relatório municipal do SISVAN | cabeçalho e linhas de município; `codigo_IBGE` precisa ter seis dígitos e ser único | `codigo_IBGE` é a chave de todas as junções municipais; os demais descrevem o território |
| `total_que_<marcador>` | uma das dez tabelas SISVAN de consumo alimentar | leitura HTML com milhar `.` e decimal `,`; mantém a contagem de respostas afirmativas | numerador de cada prevalência e somas anual, histórica e territorial |
| `total_all_<marcador>` | a mesma tabela SISVAN | mesma leitura; contagem de acompanhados que responderam ao marcador | denominador de cada prevalência e das somas |
| `percentual_que_<marcador>` | derivado, não copiado como texto do portal | `total_que_<marcador> / total_all_<marcador>`; denominador zero vira ausente | indicador exibido, nunca somado ou promediado |

Os dez marcadores são: três refeições principais; refeições assistindo à televisão; feijão; fruta; verduras e legumes; alimentos ultraprocessados; hambúrguer e/ou embutidos; bebidas adoçadas; macarrão instantâneo, salgadinho de pacote ou biscoito salgado; e biscoito recheado, doces ou guloseimas. Cada relatório vem de `dados/sisvan/mensais/{ano}/{mes}/{faixa}/{marcador}.xls`; cada sumário mensal tem as cinco colunas territoriais e três colunas para cada marcador, totalizando 35 colunas.

`criar_sumarios` só produz esse arquivo quando valida os dez relatórios de um mesmo ano, mês e faixa. `sanear_sumarios` remove linha que não é município e trata cópia parcial de cidade pelo máximo de cada contador. Os agregados anual e histórico somam somente contadores por `codigo_IBGE` e reconstroem os percentuais. As séries Brasil, região e UF repetem a mesma razão depois de somar os contadores de cada grupo.

## 2. Rateios demográficos PNAE

| Coluna | Origem | Cálculo ou significado | Entra no resultado final? |
|---|---|---|---|
| `PNACN`, `PNAPN(4)`, `PNAPN(5)`, `PNAFN(6-9)`, `PNAFN(10-15)` | `dados/referencia/quant_idades/quant_idades.xlsx` | razões etárias construídas da composição municipal de 2019; junção um-para-um por `codigo_IBGE` | 2–4 e 5–9: sim; adolescentes: `PNAFN(10-15)` é preservada como informação de rateio, mas não entra no `TOTAL_EF` vigente |

As fórmulas das outras faixas são `TOTAL_2a4 = PNACN × valor_pago_CR + PNAPN(4) × valor_pago_PE` e `TOTAL_5a9 = PNAPN(5) × valor_pago_PN + PNAFN(6-9) × valor_pago_FN`.

## 3. Colunas financeiras do PNAE de adolescentes

| Coluna | Fonte primária | Transformação e chave | Papel no `TOTAL_EF` |
|---|---|---|---|
| `valor_pago_FN` | `dados/pnaes/redes/`, arquivo anual Redes do FNDE, ação `PNAFN` ou `PN+FN` legada | entidade prefeitura é normalizada e mapeada para `codigo_IBGE`; pagamentos municipais são somados por cidade | multiplicado por `percen_MAT_FUND_AF` |
| `valor_pago_secretarias_EM` | `dados/pnaes/redes/`, arquivo anual Redes do FNDE, ações `PNAMN`, `PNAMI` e `PN+MN` | entidades secretaria estadual são somadas por `UF`; o total da UF aparece em cada cidade da mesma UF antes do rateio | multiplicado por `percen_MAT_MED` |
| `valor_pago_prefeituras_EM` | `dados/pnaes/redes/`, arquivo anual Redes do FNDE, mesmas ações de Ensino Médio | entidade prefeitura é mapeada e somada por `codigo_IBGE` | entra diretamente: o repasse já é identificado para o município |
| `tipo_valor_fnde` | coluna de valor do arquivo Redes | `pago` em 2015–2023; `previsto` quando a fonte de 2024 só disponibiliza `VALOR_PREVISTO` | ressalva interpretativa para todo valor financeiro |

Não se deve somar `valor_pago_secretarias_EM` diretamente entre municípios, pois ele é o mesmo total estadual repetido para permitir o rateio. A soma apropriada é a de `componente_EM_secretarias`, já ponderada.

## 4. Matrículas e pesos de adolescentes

| Coluna | Fonte primária | Transformação | Papel no `TOTAL_EF` |
|---|---|---|---|
| `QT_MAT_MED_cidade` | `dados/mec/microdados/microdados_ed_basica_{ano}.csv` | escolas `TP_DEPENDENCIA = 2`, agregadas por `CO_MUNICIPIO` convertido para `codigo_IBGE` | numerador de `percen_MAT_MED` |
| `QT_MAT_FUND_cidade` | mesmo microdado | mesmo filtro e agregação | numerador de `percen_MAT_FUND`; coluna de controle, não entra no total |
| `QT_MAT_FUND_AF_cidade` | mesmo microdado | mesmo filtro e agregação | numerador de `percen_MAT_FUND_AF` |
| `QT_MAT_MED_UF`, `QT_MAT_FUND_UF`, `QT_MAT_FUND_AF_UF` | mesmo microdado | soma, respectivamente, das matrículas estaduais de todas as cidades da UF | denominadores dos três pesos |
| `percen_MAT_MED` | derivada das duas colunas de Ensino Médio | `QT_MAT_MED_cidade / QT_MAT_MED_UF` | rateia o repasse estadual de Ensino Médio |
| `percen_MAT_FUND` | derivada das duas colunas de Fundamental | `QT_MAT_FUND_cidade / QT_MAT_FUND_UF` | controle; não entra na fórmula de referência |
| `percen_MAT_FUND_AF` | derivada das duas colunas de anos finais | `QT_MAT_FUND_AF_cidade / QT_MAT_FUND_AF_UF` | pondera a parcela PNAFN de anos finais |

Quando não há matrícula estadual localizada para uma cidade, o peso correspondente é mantido como ausente na coluna de auditoria e tratado como zero somente no componente financeiro. Assim, ele não inventa matrícula nem apaga a parcela válida do outro componente.

## 5. Resultado final de adolescentes

| Coluna | Fórmula exata | Origem da regra |
|---|---|---|
| `componente_EM_prefeituras` | `valor_pago_prefeituras_EM` | repasse municipal direto do FNDE, identificado por `codigo_IBGE` |
| `componente_EM_secretarias` | `valor_pago_secretarias_EM × percen_MAT_MED` | `_arquivo/v1-2.0/transform/pnaes.py` |
| `componente_EF_anos_finais` | `valor_pago_FN × percen_MAT_FUND_AF` | `_arquivo/v1-2.0/transform/pnaes.py` |
| `TOTAL_EF` | `componente_EM_prefeituras + componente_EM_secretarias + componente_EF_anos_finais` | soma do repasse municipal direto e dos dois componentes ponderados |
| `metodo_calculo_total` | texto da fórmula usada | metadado de reprodutibilidade |
| `filtro_matriculas_mec` | `TP_DEPENDENCIA=2 (estadual)` | metadado de reprodutibilidade |

A versão simplificada `PNAFN(10-15) × valor_pago_FN` existia em uma cópia antiga de notebook e foi retirada dos dez arquivos finais em 03/09/2026. Ela calculava os pesos de matrícula, mas os deixava fora do resultado. A revisão encontrou a fórmula ponderada no script operacional de referência e a tornou verificável por componentes separados.

## 6. Limites declarados

- O rateio demográfico de `quant_idades.xlsx` é fixo em 2019. Essa é a divergência deliberada em relação ao artigo para a faixa de 5–9 anos, que descreve o uso de matrículas do Ensino Fundamental I.
- O `TOTAL_EF` soma o repasse municipal de Ensino Médio diretamente e distribui os valores estaduais pela participação municipal nas matrículas estaduais correspondentes.
- Os arquivos de 2024 registram valor previsto do FNDE, não pagamento executado.
- As tabelas PNAE representam os municípios que constam no respectivo sumário SISVAN; um total estadual financeiro é distribuído apenas entre as cidades presentes nesse recorte analítico.
