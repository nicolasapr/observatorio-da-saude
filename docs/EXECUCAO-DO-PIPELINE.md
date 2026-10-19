# Execução e validação do pipeline

O código vigente está em `codigo/scripts/`. A referência territorial é o código
IBGE municipal de seis dígitos. As fórmulas financeiras aprovadas estão em
`PROVENIENCIA-DOS-DADOS-E-CALCULOS.md`; alterações operacionais não mudam essas fórmulas.

## Ambiente

Na raiz do projeto:

```sh
uv sync --frozen
uv run python -B -m unittest discover -s tests -v
```

Python 3.12 e dependências são fixados em `.python-version`, `pyproject.toml` e
`uv.lock`. Os testes geram registros artificiais em pastas temporárias. Eles não
exigem as bases do estudo e não comprovam disponibilidade dos serviços externos.

## Dados e área de trabalho

O local padrão é `dados/` na raiz. É possível usar uma pasta independente sem
alterar o código:

```sh
export OBSERVATORIO_DADOS_DIR=/caminho/absoluto/dados-da-validacao
```

Não execute uma nova coleta sobre o snapshot usado nos artigos. Serviços oficiais
podem revisar dados históricos. Uma validação ao vivo e uma reprodução do snapshot
respondem a perguntas diferentes e devem ter resultados registrados separadamente.

## Extração

```sh
cd codigo
uv run --project .. python -m scripts.extract.run_all --ano 2024 --only ibge mec pnaes
uv run --project .. python -m scripts.extract.run_all --ano 2024 --only sisvan --meses JANEIRO --fases Adolescentes --habitos 'Consumo de fruta'
```

Sem seletores SISVAN, a coleta percorre os doze meses, três faixas e dez
marcadores do ano. O extrator confirma ano, mês, faixa e marcador no conteúdo.
Falhas são reportadas como erro; não se grava um relatório inválido como resultado.

O FNDE pode devolver uma página HTML com HTTP 200. O coletor segue o link oficial
`@@download`, valida o XLSX e o grava atomicamente. O INEP usa certificados nativos
do sistema com verificação TLS habilitada, extrai somente o CSV escolar identificado
e salva `microdados_ed_basica_ANO.csv`. Os nomes históricos e a extensão `.CSV`
também são aceitos pela transformação e pelo catálogo.

Valores não numéricos do SIDRA permanecem ausentes na coluna numérica e são
preservados literalmente em `populacao_fonte`. Não são substituídos por zero.

## Transformação

```sh
uv run --project .. python -m scripts.transform.run_all --ano 2024
```

A ordem é: sumários mensais, saneamento, anuais, histórico, séries, rateios,
valores FNDE e totais finais das três faixas. A execução para na primeira exceção
para evitar o uso de uma saída antiga por uma etapa dependente.

O acervo histórico contém 397 relatórios brutos e 360 sumários canônicos. Quando
os dez brutos de um mês/faixa não estão preservados, `criar_sumarios` mantém o
sumário existente. Portanto, esse snapshot permite reproduzir as etapas
posteriores, mas não permite reconstruir todos os meses exclusivamente dos brutos.

## Reprodução isolada do histórico

Com o snapshot completo em `dados/`, execute da raiz:

```sh
uv run python -B analise/validar_transformacao.py --destino /tmp/observatorio-validacao-historica
uv run python -B analise/verificar_comportamento.py
uv run python -B analise/auditar_pipeline.py
uv run python -B analise/conferir_mk.py
```

O destino deve ser novo ou vazio. O primeiro comando copia os insumos para uma
área separada, usa os microdados do INEP somente para leitura, regenera 2015–2024 e
compara os produtos numéricos com o snapshot. Logs e `resultado.json` ficam no
destino; os dados canônicos não são substituídos.

## Estudos

`analise/estudo_series_temporais.py` reproduz o recorte Norte/adolescentes e
`analise/estudo_caso_pnae.py` reproduz o painel ecológico PNAE. Esses comandos
gravam resultados em `analise/`; não fazem parte da validação operacional acima.
O rateio demográfico permanece fixo em 2019 e os valores FNDE de 2024 são previstos.

O dashboard Streamlit é iniciado com:

```sh
cd codigo
uv run --project .. streamlit run scripts/load/app.py
```

O dashboard estático possui repositório separado: `nicolasapr/obs_saude`.
