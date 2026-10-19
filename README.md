# Observatório da Saúde

Projeto de iniciação científica Aplicação de técnicas de ciência de dados à área
da Saúde, UFPR, Jandaia do Sul, edital de 2025. O pipeline integra SISVAN,
PNAE/FNDE, IBGE e INEP/MEC para estudos de saúde alimentar.

Este repositório contém o código de extração, transformação, dashboard Streamlit
e estudos analíticos. O dashboard estático publicado no GitHub Pages pertence ao
repositório separado [obs_saude](https://github.com/nicolasapr/obs_saude).

## Organização

- `codigo/scripts/extract/`: coleta e validação das respostas oficiais.
- `codigo/scripts/transform/`: sumários, séries, rateios e valores finais.
- `codigo/scripts/load/`: catálogo, séries e mapas no Streamlit.
- `analise/`: auditorias e pontos de entrada dos dois estudos.
- `tests/`: regressões e integração da CLI com dados artificiais.
- `docs/`: execução, proveniência, limites e validação.
- `dados/`: dados locais; os arquivos grandes não são gravados no histórico Git.
- `_arquivo/`: referência histórica explicitamente separada do código vigente.

Os manuscritos e materiais editoriais da pasta de trabalho não são insumos do
pipeline e não integram esta publicação do código.

## Instalação e testes

Requer Python 3.12 e [uv](https://docs.astral.sh/uv/).

```sh
uv sync --frozen
uv run python -B -m unittest discover -s tests -v
```

As dependências estão registradas em `uv.lock`. Os testes automatizados não
dependem das bases grandes nem fazem consultas de rede. A execução completa do
estudo exige os insumos oficiais e as referências etárias documentadas.

## Extração e transformação

```sh
cd codigo
uv run --project .. python -m scripts.extract.run_all --ano 2024 --only ibge mec pnaes
uv run --project .. python -m scripts.extract.run_all --ano 2024 --only sisvan --meses JANEIRO --fases Adolescentes --habitos 'Consumo de fruta'
uv run --project .. python -m scripts.transform.run_all --ano 2024
uv run --project .. streamlit run scripts/load/app.py
```

O comando SISVAN acima testa um marcador; sem os seletores, a coleta inclui os
doze meses, três faixas e dez marcadores do ano. Uma coleta parcial sem sumário
prévio não é suficiente para executar toda a transformação.

Para trabalhar em outra área, defina `OBSERVATORIO_DADOS_DIR` como o caminho
absoluto da pasta de dados. Isso permite validar novas coletas sem substituir o
snapshot dos artigos.

O procedimento completo e os limites estão em
[Execução do pipeline](docs/EXECUCAO-DO-PIPELINE.md).

## Regras de processamento

Os municípios são unidos pelo código IBGE de seis dígitos. Percentuais SISVAN
resultam da soma das respostas positivas dividida pela soma das respostas
válidas. Não são somados nem calculados pela média simples dos percentuais
municipais.

O financiamento adolescente inclui Ensino Médio municipal direto e os dois
componentes ponderados pelas matrículas estaduais, conforme a regra aprovada.
Os rateios demográficos permanecem fixos em 2019. O FNDE de 2024 registra valores
previstos; os anos de 2015 a 2023 registram pagamentos.

Consulte [Proveniência e fórmulas](docs/PROVENIENCIA-DOS-DADOS-E-CALCULOS.md) e
[Fluxo das transformações](docs/FLUXO-DE-TRANSFORMACOES.md).

## Estudos derivados

- `analise/estudo_series_temporais.py`: adolescentes da região Norte, Mann-Kendall,
  Sen e SARIMA, de janeiro de 2015 a dezembro de 2024.
- `analise/estudo_caso_pnae.py`: painel ecológico municipal, IPCA com base 2024,
  repasse por matrícula, limites de respostas e sensibilidade do índice.

Esses scripts gravam produtos analíticos em `analise/`. Eles não alteram os
insumos brutos do ETL. As associações ecológicas não demonstram efeitos
individuais ou causais do financiamento.

## Dados completos e reprodução do snapshot

Todos os 986 arquivos da pasta de dados preservada estão disponíveis na
[Release dos dados](https://github.com/nicolasapr/observatorio-da-saude/releases/tag/dados-2015-2024-20261018).
O pacote tem aproximadamente 572 MB (3,06 GB descompactados), com manifesto e
SHA-256 por arquivo. Ele não ocupa o histórico Git do código.

Depois de instalar as dependências, baixe e confira os dados:

```sh
uv run python analise/baixar_snapshot.py
uv run python analise/baixar_snapshot.py --verificar
```

O instalador exige uma pasta de destino vazia e não sobrescreve dados existentes.
Use `--destino /caminho/alternativo/dados` para instalar em outra pasta e defina
`OBSERVATORIO_DADOS_DIR` ao executar o pipeline nessa área.

```sh
uv run python -B analise/validar_transformacao.py --destino /tmp/observatorio-validacao-historica
uv run python -B analise/verificar_comportamento.py
uv run python -B analise/auditar_pipeline.py
uv run python -B analise/conferir_mk.py
```

O primeiro comando regenera e compara os produtos numa pasta separada. Requer o
snapshot histórico local. Ele não comprova a disponibilidade atual das fontes.

O acervo preserva 397 dos 3.600 relatórios brutos SISVAN possíveis, junto de 360
sumários mensais canônicos. Os sumários existentes são preservados quando faltam
brutos; não se inventam registros para completar relatórios. Uma reconstrução
integral a partir do zero exige recuperar o restante do acervo bruto.

O estado operacional da revisão de outubro de 2026 está documentado em
[Validação do pipeline](docs/VALIDACAO-2026-10-18.md). A validação do SISVAN nesta
etapa utiliza o acervo já baixado; uma nova coleta fica para outra etapa.
