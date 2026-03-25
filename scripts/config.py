"""
scripts/config.py — Fonte única de verdade para caminhos e constantes do pipeline.

Todos os módulos (extract, transform, load) importam daqui.
Nunca hardcode caminhos nos scripts — altere apenas este arquivo.
"""
from pathlib import Path

# ── Raiz ──────────────────────────────────────────────────────────────────
# projeto/scripts/config.py → parent = scripts/ → parent = projeto/
PROJETO_DIR = Path(__file__).parent.parent
DADOS_DIR   = PROJETO_DIR / "dados"

# ── SISVAN ────────────────────────────────────────────────────────────────
# Arquivos brutos mensais baixados pelo SISVAN scraper
#   mensais/{ano}/{MES}/{faixa}/{habito}.csv
SISVAN_MENSAIS_DIR = DADOS_DIR / "sisvan" / "mensais"

# Sumários mensais consolidados (por mês, saída de CriarSumariosTransformer)
#   mensais/{ano}/{mes}/sumario_habitos_{faixa}.xlsx
# (ficam junto com os brutos, na mesma pasta mensais/)

# Sumários anuais (saída de SumariosAnuaisTransformer)
#   anuais/{ano}/sumario_anual_habitos_{faixa}.xlsx
SISVAN_ANUAIS_DIR = DADOS_DIR / "sisvan" / "anuais"

# Sumário histórico total (saída de SumariosTotaisTransformer)
#   historico/sumario_total_habitos_{faixa}.xlsx
SISVAN_HISTORICO_DIR = DADOS_DIR / "sisvan" / "historico"

# ── PNAES ─────────────────────────────────────────────────────────────────
# Arquivos brutos Redes FNDE: redes/{ano}/{ano}Redes*.xlsx
PNAES_REDES_DIR = DADOS_DIR / "pnaes" / "redes"

# Percentuais SISVAN por faixa (gerados pelo pipeline Percen)
#   percen/{faixa}/PNAES_Percen_{faixa}_{ano}.xlsx
PNAES_PERCEN_DIR = DADOS_DIR / "pnaes" / "percen"

# Valores calculados por faixa (saída de PNAESRedesTransformer)
#   valores/{faixa}/PNAES_valores_{faixa}_{ano}.xlsx
PNAES_VALORES_DIR = DADOS_DIR / "pnaes" / "valores"

# Arquivos finais ajustados (saída de PNAES*Transformer)
#   finais/{faixa}/PNAES_valores_{faixa}_{ano}_ajustado.xlsx
PNAES_FINAIS_DIR = DADOS_DIR / "pnaes" / "finais"

# ── MEC / INEP ────────────────────────────────────────────────────────────
# Microdados Censo Escolar: mec/microdados/microdados_ed_basica_{ano}.csv
MEC_MICRODADOS_DIR = DADOS_DIR / "mec" / "microdados"

# ── Referência ────────────────────────────────────────────────────────────
# Projeções populacionais IBGE
REFERENCIA_IBGE_DIR  = DADOS_DIR / "referencia" / "ibge"
# Quantitativo de crianças/adolescentes por município
REFERENCIA_QUANT_DIR = DADOS_DIR / "referencia" / "quant_idades"

# ── Constantes de domínio ─────────────────────────────────────────────────
ANOS_DISPONIVEIS = list(range(2015, 2026))

FAIXAS = ["2a4", "5a9", "Adolescentes"]

FASES_NOMES = [
    "Crianças de 2 a 4 anos",
    "Crianças de 5 a 9 anos",
    "Adolescentes",
]

FASES_SLUGS = [
    "Crianças_de_2_a_4_anos",
    "Crianças_de_5_a_9_anos",
    "Adolescentes",
]

COLUNAS_CADASTRAIS = ["regiao", "codigo_UF", "UF", "codigo_IBGE", "municipio"]
