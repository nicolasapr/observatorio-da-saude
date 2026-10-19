# Estado do projeto

Este repositório contém o pipeline e os estudos reproduzíveis do Observatório da
Saúde, desenvolvido na iniciação científica Aplicação de técnicas de ciência de
dados à área da Saúde, UFPR, Jandaia do Sul, edital de 2025.

Há dois repositórios distintos:

- `nicolasapr/observatorio-da-saude`: extração, transformação e análises em Python;
- `nicolasapr/obs_saude`: dashboard estático publicado no GitHub Pages.

A organização local também conserva manuscritos e versões antigas. Eles não
devem ser confundidos com fontes numéricas nem ser usados como insumos do ETL.

## Trabalhos derivados

O estudo temporal analisa os marcadores SISVAN de adolescentes da região Norte
entre 2015 e 2024, com Mann-Kendall, Sen e SARIMA. Seu ponto de entrada é
`analise/estudo_series_temporais.py`.

O estudo ecológico de financiamento integra os produtos municipais do SISVAN e
do PNAE, deflaciona valores pelo IPCA para 2024 e compara repasse por matrícula e
por residente de referência. Seu ponto de entrada é `analise/estudo_caso_pnae.py`.

A sensibilidade descritiva do índice equilibrado está implementada. O comando
principal de modelagem ainda usa o índice original; os ajustes preditivos com o
índice alternativo exigem incorporação explícita ao fluxo antes de serem
considerados integralmente reproduzíveis por esse comando.

## Limites do snapshot

O recorte histórico possui 360 sumários mensais de 2015–2024 e preserva 397 dos
3.600 relatórios brutos SISVAN possíveis. A consistência dos agregados não prova
auditoria documental dos relatórios que não estão arquivados.

As proporções demográficas financeiras são fixas em 2019. Os valores do FNDE
de 2024 são previstos, enquanto 2015–2023 registram pagamentos. As fórmulas
aprovadas, incluindo o Ensino Médio municipal, estão na documentação de
proveniência. A versão legada em `_arquivo/` é referência histórica, não um
ponto de entrada operacional.

O marcador de três refeições apresenta descontinuidade de registro. Os estudos
trabalham com dados agregados e não permitem inferências individuais ou causais.
