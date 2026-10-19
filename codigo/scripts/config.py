"""
scripts/config.py — Fonte única de verdade para caminhos e constantes do pipeline.

Todos os módulos (extract, transform, load) importam daqui.
Nunca hardcode caminhos nos scripts — altere apenas este arquivo.
"""
from pathlib import Path
import os

# ── Raiz ──────────────────────────────────────────────────────────────────
# projeto/scripts/config.py → parent = scripts/ → parent = projeto/
PROJETO_DIR = Path(__file__).resolve().parent.parent
RAIZ_DIR = PROJETO_DIR.parent if PROJETO_DIR.name == 'codigo' else PROJETO_DIR
DADOS_DIR = Path(os.environ.get('OBSERVATORIO_DADOS_DIR', RAIZ_DIR / 'dados')).expanduser().resolve()

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

# Séries temporais mensais (saída de SeriesMensaisTransformer)
#   series/serie_mensal_{faixa}.xlsx
SISVAN_SERIES_DIR = DADOS_DIR / "sisvan" / "series"

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


def localizar_microdados(ano: int) -> Path:
    """Aceita o nome do extrator e os nomes históricos, inclusive .CSV."""
    nomes = [f'microdados_ed_basica_{ano}.csv', f'microdados_censo_escolar_{ano}.csv']
    candidatos = {
        p.name.lower(): p for p in MEC_MICRODADOS_DIR.glob('*')
        if p.is_file() and not p.name.startswith('.')
    }
    for nome in nomes:
        if nome in candidatos:
            return candidatos[nome]
    raise FileNotFoundError(f'Microdados MEC de {ano} ausentes em {MEC_MICRODADOS_DIR}')

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

REGIOES = ["CENTRO-OESTE", "NORDESTE", "NORTE", "SUDESTE", "SUL"]

UF_NOMES: dict[str, str] = {
    "AC": "Acre",
    "AL": "Alagoas",
    "AM": "Amazonas",
    "AP": "Amapá",
    "BA": "Bahia",
    "CE": "Ceará",
    "DF": "Distrito Federal",
    "ES": "Espírito Santo",
    "GO": "Goiás",
    "MA": "Maranhão",
    "MG": "Minas Gerais",
    "MS": "Mato Grosso do Sul",
    "MT": "Mato Grosso",
    "PA": "Pará",
    "PB": "Paraíba",
    "PE": "Pernambuco",
    "PI": "Piauí",
    "PR": "Paraná",
    "RJ": "Rio de Janeiro",
    "RN": "Rio Grande do Norte",
    "RO": "Rondônia",
    "RR": "Roraima",
    "RS": "Rio Grande do Sul",
    "SC": "Santa Catarina",
    "SE": "Sergipe",
    "SP": "São Paulo",
    "TO": "Tocantins",
}


# ── Localização dos arquivos Redes do FNDE ────────────────────────────────
def localizar_redes(ano: int) -> list:
    """Arquivos Redes de um ano, do mais provável ao menos.

    O FNDE alterna entre 'REDES' e 'Redes' conforme o ano, e os arquivos podem
    estar em redes/{ano}/ (layout antigo) ou soltos em redes/ (layout gravado
    pelo downloader). Cópias com prefixo '{ano}_' são idênticas; a ordenação por
    tamanho do nome deixa a versão canônica em primeiro lugar.
    """
    achados = []
    for base in (PNAES_REDES_DIR / str(ano), PNAES_REDES_DIR):
        if not base.exists():
            continue
        for p in base.glob('*.xlsx'):
            if p.name.startswith(('.~lock.', '~$')):
                continue
            nome = p.name.lower()
            if str(ano) in nome and 'redes' in nome:
                achados.append(p)
    return sorted(set(achados), key=lambda p: (len(p.name), p.name))
