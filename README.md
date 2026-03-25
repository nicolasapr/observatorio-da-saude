# Observatório da Saúde — Pipeline ETL

Pipeline de coleta, transformação e visualização de dados de saúde e educação alimentar no Brasil, integrando fontes do SISVAN, PNAES/FNDE, IBGE e MEC/INEP.

---

## Estrutura do Projeto

```
projeto/
├── dados/                          # Dados brutos e processados (ignorados pelo git)
│   ├── sisvan/
│   │   ├── mensais/                # CSVs mensais baixados do SISVAN Web
│   │   ├── anuais/                 # Sumários anuais gerados pelo Transform
│   │   └── historico/             # Série histórica consolidada (todos os anos)
│   ├── pnaes/
│   │   ├── redes/                  # Planilhas PNAES Redes (download manual)
│   │   ├── percen/
│   │   │   ├── 2a4/                # Percentuais calculados — faixa 2 a 4 anos
│   │   │   ├── 5a9/                # Percentuais calculados — faixa 5 a 9 anos
│   │   │   └── Adolescentes/
│   │   ├── valores/
│   │   │   ├── 2a4/                # Valores PNAES tratados — faixa 2 a 4 anos
│   │   │   ├── 5a9/
│   │   │   └── Adolescentes/
│   │   └── finais/
│   │       ├── 2a4/                # Tabelas finais com repasse per capita
│   │       ├── 5a9/
│   │       └── Adolescentes/
│   ├── mec/
│   │   └── microdados/             # Microdados do Censo Escolar (INEP/ZIP)
│   └── referencia/
│       ├── ibge/                   # Estimativas populacionais (SIDRA API)
│       └── quant_idades/           # Quantitativos por faixa etária
│
└── scripts/                        # Código-fonte do pipeline (Python)
    ├── config.py                   # Fonte única de verdade para todos os caminhos
    ├── extract/
    │   ├── base.py                 # Classe abstrata BaseDownloader
    │   ├── sisvan.py               # Scraper Selenium → dados/sisvan/mensais/
    │   ├── ibge.py                 # API SIDRA → dados/referencia/ibge/
    │   ├── mec.py                  # Download ZIP INEP → dados/mec/microdados/
    │   ├── pnaes.py                # Placeholder (download manual obrigatório)
    │   └── run_all.py              # Orquestrador CLI da camada Extract
    ├── transform/
    │   ├── base.py                 # Classe abstrata BaseTransformer
    │   ├── criar_sumarios.py       # Consolida mensais → anuais (SISVAN)
    │   ├── sumarios_anuais.py      # Agrega anuais por faixa etária
    │   ├── sumarios_totais.py      # Série histórica multi-ano
    │   ├── pnaes_redes.py          # Processa planilhas de Redes
    │   ├── pnaes.py                # Calcula percentuais e valores finais PNAES
    │   ├── repair_percentuais.py   # Corrige formatação de números brasileiros
    │   └── run_all.py              # Orquestrador CLI da camada Transform
    └── load/
        ├── app.py                  # Ponto de entrada do Streamlit (run: streamlit run)
        ├── catalog.py              # Página: Catálogo de dados disponíveis
        ├── viz.py                  # Página: Mapa coroplético interativo
        ├── extractor.py            # Página: Extração de dados via interface
        └── utils.py                # Helpers compartilhados (formatação, cache)
```

---

## Como Funciona: Pipeline ETL

O pipeline segue três camadas sequenciais:

```
[Fontes externas]
      │
      ▼
┌─────────────┐
│   EXTRACT   │  Baixa dados brutos → dados/sisvan/mensais/, dados/referencia/ibge/, etc.
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  TRANSFORM  │  Limpa, agrega e calcula indicadores → dados/pnaes/percen/, dados/sisvan/anuais/, etc.
└──────┬──────┘
       │
       ▼
┌─────────────┐
│    LOAD     │  Dashboard Streamlit — visualiza, filtra e exporta os dados processados
└─────────────┘
```

### Fontes de dados

| Fonte | Dado | Método de extração |
|-------|------|--------------------|
| SISVAN Web | Hábitos alimentares mensais por município | Selenium (automático) |
| IBGE SIDRA | Estimativas populacionais por município | API REST (automático) |
| INEP/MEC | Microdados do Censo Escolar | Download ZIP (automático) |
| FNDE/PNAES | Repasse PNAE por rede escolar | **Download manual** (ver abaixo) |

---

## Pré-requisitos

```bash
pip install streamlit pandas selenium requests openpyxl folium streamlit-folium
```

Para o scraper SISVAN, instale também o ChromeDriver compatível com sua versão do Chrome.

---

## Executando o Pipeline

### 1. Extração automática

```bash
# Da raiz do projeto
python -m scripts.extract.run_all
```

Executa em sequência: SISVAN → IBGE → MEC.

Para executar individualmente:

```bash
python -m scripts.extract.sisvan   # Apenas SISVAN
python -m scripts.extract.ibge     # Apenas IBGE
python -m scripts.extract.mec      # Apenas MEC
```

### 2. Download manual do PNAES (obrigatório)

Os arquivos do PNAES/FNDE não têm URL estável. Faça o download manualmente:

1. Acesse o portal do FNDE: https://www.fnde.gov.br/sigefweb/
2. Navegue até **PNAE → Dados Abertos → Recursos Transferidos**
3. Baixe as planilhas de repasse por **Rede Escolar** para cada ano disponível
4. Salve os arquivos `.xlsx` em `dados/pnaes/redes/`

Nomenclatura esperada: `PNAE_Redes_<ANO>.xlsx`

### 3. Transformação

```bash
python -m scripts.transform.run_all
```

Executa na ordem correta de dependências:
1. Reparo de formatação (`repair_percentuais`)
2. Sumários mensais → anuais (`criar_sumarios`)
3. Sumários anuais por faixa (`sumarios_anuais`)
4. Série histórica (`sumarios_totais`)
5. Processamento PNAES Redes (`pnaes_redes`)
6. Cálculo de percentuais e valores finais (`pnaes`)

---

## Camada Load — Dashboard Streamlit

O dashboard é a interface de consulta e extração dos dados processados.

### Iniciando

```bash
# Da pasta projeto/
streamlit run scripts/load/app.py
```

O dashboard abrirá em `http://localhost:8501`.

### Páginas disponíveis

#### Catálogo de Dados
Exibe uma matriz de status mostrando quais arquivos de dados estão disponíveis para cada combinação de (fonte × ano × faixa etária). Útil para verificar se o pipeline rodou com sucesso antes de analisar.

#### Mapa Coroplético
Visualização geográfica dos indicadores por município brasileiro.

- Selecione o **indicador** (hábito alimentar, repasse per capita, etc.)
- Selecione o **ano** e a **faixa etária**
- O mapa exibe as diferenças regionais com escala de cores automática
- Os dados do GeoJSON são buscados da API do IBGE e cacheados localmente

#### Extração de Dados
Interface para exportar os dados processados:

1. Escolha a **fonte** (SISVAN, PNAES, MEC, IBGE)
2. Aplique **filtros** (ano, estado, faixa etária, indicador)
3. Visualize a tabela resultante na tela
4. Clique em **Baixar CSV** para exportar

```
Fluxo de extração no app:
  Usuário seleciona filtros
        │
        ▼
  extractor.py carrega o arquivo CSV/XLSX correspondente de dados/
        │
        ▼
  Filtragem e formatação em memória (pandas)
        │
        ▼
  Exibição em st.dataframe() + botão de download
```

### Configuração de caminhos

Todos os caminhos do pipeline são definidos em `scripts/config.py`. Se você mover a pasta `dados/`, basta atualizar `DADOS_DIR` neste arquivo — todos os módulos herdam automaticamente o novo caminho.

```python
# scripts/config.py
PROJETO_DIR = Path(__file__).parent.parent
DADOS_DIR = PROJETO_DIR / "dados"
SISVAN_MENSAIS_DIR = DADOS_DIR / "sisvan" / "mensais"
# ...
```

---

## Git e Dados

Os arquivos de dados (`.csv`, `.xlsx`, `.xls`, `.zip`) são **ignorados pelo git** (ver `.gitignore`). Apenas a estrutura de diretórios é versionada via arquivos `.gitkeep`.

Para popular os dados em uma nova máquina:
1. Clone o repositório
2. Execute `python -m scripts.extract.run_all`
3. Faça o download manual do PNAES (ver acima)
4. Execute `python -m scripts.transform.run_all`
5. Inicie o dashboard com `streamlit run scripts/load/app.py`
