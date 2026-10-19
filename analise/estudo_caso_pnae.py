"""Estudo de caso ecológico: PNAE e índice de qualidade alimentar.

Constrói uma base município-ano-faixa a partir dos produtos finais do pipeline,
deflaciona os repasses pelo IPCA (média anual; preços de 2024), calcula os
indicadores por matrícula e por residente da faixa etária de referência, e
executa as análises de sensibilidade descritas no manuscrito.

Uso:
    .venv/bin/python analise/estudo_caso_pnae.py --atualizar-ipca

Os dados brutos e os produtos finais do ETL não são alterados. Os resultados
analíticos são gravados em ``analise/estudo_caso_pnae/``.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
from scipy.stats import pearsonr, spearmanr
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


RAIZ = Path(__file__).resolve().parents[1]
DADOS = RAIZ / "dados"
FINAIS = DADOS / "pnaes" / "finais"
MEC = DADOS / "mec" / "microdados"
QUANT_IDADES = DADOS / "referencia" / "quant_idades" / "quant_idades.xlsx"
IPCA_DIR = DADOS / "referencia" / "ipca"
IPCA_MENSAL = IPCA_DIR / "ipca_mensal_2015_2024.csv"
SAIDA = RAIZ / "analise" / "estudo_caso_pnae"

ANOS = list(range(2015, 2025))
FAIXAS = ("2a4", "5a9", "Adolescentes")
ARQUIVO_FINAL = "PNAES_valores_{faixa}_{ano}_ajustado.xlsx"

# Tabela 1737 do SIDRA: IPCA, número-índice mensal para Brasil.
IPCA_URL = (
    "https://apisidra.ibge.gov.br/values/t/1737/n1/1/v/2266/"
    "p/201501-202412"
)

POSITIVOS = {
    "habito de realizar no minimo as tres refeicoes principais do dia",
    "consumo de feijao",
    "consumo de fruta",
    "consumo de verduras e legumes",
}


def normalizar(texto: str) -> str:
    """Normaliza textos de cabeçalho sem depender de acentos ou pontuação."""
    sem_acento = unicodedata.normalize("NFKD", str(texto)).encode(
        "ascii", "ignore"
    ).decode("ascii")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", sem_acento.lower())).strip()


def localizar_microdado(ano: int) -> Path:
    """Localiza o Censo Escolar, tolerando extensão e nome histórico."""
    candidatos = sorted(
        p for p in MEC.iterdir()
        if p.suffix.lower() == ".csv" and str(ano) in p.name
    )
    preferidos = [p for p in candidatos if "ed_basica" in p.name.lower()]
    if preferidos:
        return preferidos[0]
    if candidatos:
        return candidatos[0]
    raise FileNotFoundError(f"Microdado MEC ausente para {ano}")


def obter_ipca(atualizar: bool) -> pd.DataFrame:
    """Lê ou baixa o IPCA mensal e produz a média anual do número-índice."""
    if atualizar or not IPCA_MENSAL.exists():
        resposta = requests.get(IPCA_URL, timeout=60)
        resposta.raise_for_status()
        registros = resposta.json()
        if len(registros) != 121:
            raise ValueError(
                "IPCA incompleto: esperados 120 meses de 2015 a 2024, "
                f"recebidos {len(registros) - 1}"
            )
        mensal = pd.DataFrame(registros[1:])[["D3C", "V"]].rename(
            columns={"D3C": "periodo", "V": "ipca_numero_indice"}
        )
        mensal["ano"] = mensal["periodo"].str[:4].astype(int)
        mensal["mes"] = mensal["periodo"].str[4:].astype(int)
        mensal["ipca_numero_indice"] = pd.to_numeric(
            mensal["ipca_numero_indice"], errors="raise"
        )
        IPCA_DIR.mkdir(parents=True, exist_ok=True)
        mensal.to_csv(IPCA_MENSAL, index=False)
    else:
        mensal = pd.read_csv(IPCA_MENSAL)

    esperado = set(ANOS)
    contagem = mensal.groupby("ano")["mes"].nunique()
    if set(contagem.index) != esperado or not contagem.eq(12).all():
        raise ValueError("Arquivo IPCA não contém doze meses para cada ano de 2015 a 2024")
    anual = (
        mensal.groupby("ano", as_index=False)["ipca_numero_indice"]
        .mean()
        .rename(columns={"ipca_numero_indice": "ipca_media_anual"})
    )
    base_2024 = anual.loc[anual["ano"].eq(2024), "ipca_media_anual"].iloc[0]
    anual["fator_deflacao_base_2024"] = base_2024 / anual["ipca_media_anual"]
    return anual


def carregar_matriculas(ano: int) -> pd.DataFrame:
    """Soma matrículas municipais e estaduais por etapa de ensino.

    A rede federal e a privada não entram no denominador: os repasses tratados
    neste estudo são destinados às prefeituras e às secretarias estaduais.
    """
    caminho = localizar_microdado(ano)
    cabecalho = pd.read_csv(caminho, sep=";", encoding="latin-1", nrows=0).columns
    colunas = [
        "CO_MUNICIPIO", "TP_DEPENDENCIA", "QT_MAT_INF_CRE", "QT_MAT_INF_PRE",
        "QT_MAT_FUND_AI", "QT_MAT_FUND_AF", "QT_MAT_MED",
    ]
    faltantes = [c for c in colunas if c not in cabecalho]
    if faltantes:
        raise ValueError(f"{caminho.name}: campos de matrícula ausentes: {faltantes}")
    micro = pd.read_csv(
        caminho, sep=";", encoding="latin-1", usecols=colunas,
        on_bad_lines="error", low_memory=False,
    )
    micro["TP_DEPENDENCIA"] = pd.to_numeric(micro["TP_DEPENDENCIA"], errors="coerce")
    micro = micro[micro["TP_DEPENDENCIA"].isin([2, 3])].copy()
    for coluna in colunas[2:]:
        micro[coluna] = pd.to_numeric(micro[coluna], errors="coerce").fillna(0)
    micro["codigo_IBGE"] = (
        pd.to_numeric(micro["CO_MUNICIPIO"], errors="coerce") // 10
    ).astype("Int64")
    micro = micro.dropna(subset=["codigo_IBGE"])
    agregado = micro.groupby("codigo_IBGE", as_index=False)[colunas[2:]].sum()
    agregado["matriculas_2a4"] = agregado["QT_MAT_INF_CRE"] + agregado["QT_MAT_INF_PRE"]
    agregado["matriculas_5a9"] = agregado["QT_MAT_FUND_AI"]
    agregado["matriculas_Adolescentes"] = (
        agregado["QT_MAT_FUND_AF"] + agregado["QT_MAT_MED"]
    )
    return agregado[[
        "codigo_IBGE", "matriculas_2a4", "matriculas_5a9", "matriculas_Adolescentes"
    ]]


def carregar_populacao_referencia() -> pd.DataFrame:
    """Obtém contagens etárias municipais da referência demográfica fixa de 2019."""
    quant = pd.read_excel(QUANT_IDADES)
    quant["codigo_IBGE"] = pd.to_numeric(
        quant["Município"].astype(str).str.extract(r"^(\d{6})")[0], errors="coerce"
    ).astype("Int64")
    idades: dict[int, str] = {}
    for coluna in quant.columns:
        encontrado = re.match(r"^\s*(\d{1,2})\s*anos?\s*$", str(coluna))
        if encontrado:
            idades[int(encontrado.group(1))] = coluna
    if set(range(2, 19)) - set(idades):
        raise ValueError("quant_idades não contém todas as idades de 2 a 18")
    resultado = quant[["codigo_IBGE"]].copy()
    resultado["residentes_2a4_ref2019"] = quant[[idades[i] for i in range(2, 5)]].sum(axis=1)
    resultado["residentes_5a9_ref2019"] = quant[[idades[i] for i in range(5, 10)]].sum(axis=1)
    resultado["residentes_Adolescentes_ref2019"] = quant[[idades[i] for i in range(10, 19)]].sum(axis=1)
    return resultado.dropna(subset=["codigo_IBGE"])


def identificar_marcadores(df: pd.DataFrame) -> list[tuple[str, str, bool, str]]:
    """Relaciona cada denominador ao numerador e à direção no índice."""
    marcadores: list[tuple[str, str, bool, str]] = []
    for denominador in df.columns:
        if not denominador.startswith("total_all_"):
            continue
        sufixo = denominador.removeprefix("total_all_")
        numerador = f"total_que_{sufixo}"
        if numerador not in df.columns:
            raise ValueError(f"Numerador ausente para {denominador}")
        marcador = normalizar(sufixo)
        marcadores.append((numerador, denominador, marcador in POSITIVOS, marcador))
    if len(marcadores) != 10 or sum(positivo for _, _, positivo, _ in marcadores) != 4:
        raise ValueError("Esperados dez marcadores, quatro positivos e seis negativos")
    return marcadores


def calcular_indices(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula índice igualitário, equilíbrio entre grupos e versões leave-one-out."""
    marcadores = identificar_marcadores(df)
    escores: dict[str, pd.Series] = {}
    denominadores: list[pd.Series] = []
    for numerador, denominador, positivo, nome in marcadores:
        que = pd.to_numeric(df[numerador], errors="coerce")
        all_ = pd.to_numeric(df[denominador], errors="coerce")
        valido = all_.gt(0) & que.ge(0) & que.le(all_)
        percentual = (100 * que / all_).where(valido)
        escores[nome] = percentual if positivo else 100 - percentual
        denominadores.append(all_.where(valido))
    quadro = pd.DataFrame(escores, index=df.index)
    df = df.copy()
    df["n_componentes_validos"] = quadro.notna().sum(axis=1)
    df["n_respostas_validas_indice"] = pd.concat(denominadores, axis=1).min(axis=1)
    # O índice primário requer os dez componentes previstos no manuscrito.
    completo = df["n_componentes_validos"].eq(10)
    df["indice_qualidade_igual"] = quadro.mean(axis=1).where(completo)
    pos = quadro[[nome for _, _, positivo, nome in marcadores if positivo]].mean(axis=1)
    neg = quadro[[nome for _, _, positivo, nome in marcadores if not positivo]].mean(axis=1)
    df["indice_qualidade_grupos_equilibrados"] = (0.5 * pos + 0.5 * neg).where(completo)
    for _, _, _, nome in marcadores:
        coluna = f"indice_sem_{nome[:28].replace(' ', '_')}"
        df[coluna] = quadro.drop(columns=nome).mean(axis=1).where(completo)
    return df


def carregar_painel(ipca: pd.DataFrame) -> pd.DataFrame:
    """Empilha os produtos finais e integra matrículas, população e IPCA."""
    populacao = carregar_populacao_referencia()
    blocos: list[pd.DataFrame] = []
    for ano in ANOS:
        matriculas = carregar_matriculas(ano)
        for faixa in FAIXAS:
            caminho = FINAIS / faixa / ARQUIVO_FINAL.format(faixa=faixa, ano=ano)
            if not caminho.exists():
                raise FileNotFoundError(caminho)
            df = calcular_indices(pd.read_excel(caminho))
            total_coluna = "TOTAL_EF" if faixa == "Adolescentes" else "TOTAL"
            if total_coluna not in df.columns:
                raise ValueError(f"{caminho.name}: {total_coluna} ausente")
            df["repasse_nominal"] = pd.to_numeric(df[total_coluna], errors="coerce")
            df["ano"] = ano
            df["faixa"] = faixa
            df["codigo_IBGE"] = pd.to_numeric(df["codigo_IBGE"], errors="coerce").astype("Int64")
            df = df.merge(matriculas, on="codigo_IBGE", how="left", validate="many_to_one")
            df = df.merge(populacao, on="codigo_IBGE", how="left", validate="many_to_one")
            df["matriculas_elegiveis"] = df[f"matriculas_{faixa}"]
            df["residentes_faixa_ref2019"] = df[f"residentes_{faixa}_ref2019"]
            blocos.append(df)
    painel = pd.concat(blocos, ignore_index=True)
    painel = painel.merge(ipca, on="ano", how="left", validate="many_to_one")
    painel["repasse_real_base_2024"] = (
        painel["repasse_nominal"] * painel["fator_deflacao_base_2024"]
    )
    painel["repasse_real_por_matricula"] = (
        painel["repasse_real_base_2024"] / painel["matriculas_elegiveis"]
    ).where(painel["matriculas_elegiveis"].gt(0))
    painel["repasse_real_por_residente_ref2019"] = (
        painel["repasse_real_base_2024"] / painel["residentes_faixa_ref2019"]
    ).where(painel["residentes_faixa_ref2019"].gt(0))
    painel["log_repasse_real_por_matricula"] = np.log1p(
        painel["repasse_real_por_matricula"].clip(lower=0)
    )
    painel["log_matriculas_elegiveis"] = np.log1p(painel["matriculas_elegiveis"])
    painel["log_respostas_validas"] = np.log1p(painel["n_respostas_validas_indice"])
    painel["ano_centralizado"] = painel["ano"] - 2019.5
    return painel


def base_elegivel(painel: pd.DataFrame, limiar: int) -> pd.DataFrame:
    """Seleciona a base com desfecho e exposição observáveis."""
    mascara = (
        painel["indice_qualidade_igual"].notna()
        & painel["n_respostas_validas_indice"].ge(limiar)
        & painel["matriculas_elegiveis"].gt(0)
        & painel["repasse_real_base_2024"].notna()
        & np.isfinite(painel["log_repasse_real_por_matricula"])
        & np.isfinite(painel["log_matriculas_elegiveis"])
        & np.isfinite(painel["log_respostas_validas"])
    )
    return painel.loc[mascara].copy()


def fluxo_exclusoes(painel: pd.DataFrame) -> pd.DataFrame:
    """Produz o fluxo da especificação principal e sua sensibilidade estrita."""
    completo = painel["indice_qualidade_igual"].notna()
    seis = completo & painel["n_respostas_validas_indice"].ge(6)
    cem = completo & painel["n_respostas_validas_indice"].ge(100)
    elegivel_seis = (
        seis
        & painel["matriculas_elegiveis"].gt(0)
        & painel["repasse_real_base_2024"].notna()
        & np.isfinite(painel["log_repasse_real_por_matricula"])
    )
    elegivel_cem = (
        cem
        & painel["matriculas_elegiveis"].gt(0)
        & painel["repasse_real_base_2024"].notna()
        & np.isfinite(painel["log_repasse_real_por_matricula"])
    )
    return pd.DataFrame({
        "etapa": [
            "Observações município ano faixa nos arquivos finais",
            "Dez componentes alimentares válidos",
            "Pelo menos 6 respostas válidas por componente",
            "Base final com mínimo de 6 respostas",
            "Base final com mínimo de 100 respostas",
        ],
        "observacoes": [
            len(painel), int(completo.sum()), int(seis.sum()),
            int(elegivel_seis.sum()), int(elegivel_cem.sum()),
        ],
    })


def distribuicao_respostas(painel: pd.DataFrame) -> pd.DataFrame:
    cortes = [-np.inf, 5, 9, 24, 49, 99, 499, np.inf]
    rotulos = ["0-5", "6-9", "10-24", "25-49", "50-99", "100-499", "500 ou mais"]
    faixa = pd.cut(painel["n_respostas_validas_indice"], cortes, labels=rotulos)
    faixa = faixa.cat.add_categories(["Componentes incompletos"]).fillna(
        "Componentes incompletos"
    )
    return (
        faixa.value_counts(sort=False, dropna=False)
        .rename_axis("faixa_respostas").reset_index(name="observacoes")
    )


def criar_pipeline(modelo: object) -> Pipeline:
    numericas = [
        "log_repasse_real_por_matricula", "ano_centralizado",
        "log_matriculas_elegiveis", "log_respostas_validas",
    ]
    categoricas = ["faixa", "UF"]
    pre = ColumnTransformer(
        [
            ("numericas", StandardScaler(), numericas),
            ("categoricas", OneHotEncoder(handle_unknown="ignore", sparse_output=False), categoricas),
        ],
        sparse_threshold=0,
    )
    return Pipeline([("pre", pre), ("model", modelo)])


def modelos() -> dict[str, object]:
    return {
        "Ridge": Ridge(alpha=1.0),
        "Random Forest": RandomForestRegressor(
            n_estimators=200, min_samples_leaf=3, n_jobs=-1, random_state=2026,
        ),
        "Gradient Boosting": GradientBoostingRegressor(
            n_estimators=200, learning_rate=0.05, max_depth=2, subsample=0.8,
            random_state=2026,
        ),
    }


def executar_modelos(
    base: pd.DataFrame, nome: str, ponderar_respostas: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Executa validação cruzada agrupada e importância por permutação."""
    colunas = [
        "log_repasse_real_por_matricula", "ano_centralizado",
        "log_matriculas_elegiveis", "log_respostas_validas", "faixa", "UF",
    ]
    X = base[colunas]
    y = base["indice_qualidade_igual"]
    grupos = base["codigo_IBGE"]
    pesos = base["n_respostas_validas_indice"] if ponderar_respostas else None
    if not np.isfinite(X.select_dtypes(include="number").to_numpy()).all():
        raise ValueError(f"{nome}: preditores numéricos não finitos na base elegível")
    if not np.isfinite(y.to_numpy()).all():
        raise ValueError(f"{nome}: desfecho não finito na base elegível")
    divisao = GroupKFold(n_splits=5)
    resultados: list[dict] = []
    importancias: list[dict] = []
    for modelo_nome, modelo in modelos().items():
        for dobra, (treino, teste) in enumerate(divisao.split(X, y, grupos), start=1):
            pipe = criar_pipeline(modelo)
            # A normalização preserva todas as razões entre pesos e evita que
            # a magnitude absoluta dos contadores altere a estabilidade numérica.
            if pesos is not None:
                peso_treino = pesos.iloc[treino].astype(float)
                kwargs = {"model__sample_weight": peso_treino / peso_treino.mean()}
            else:
                kwargs = {}
            # A instalação local de NumPy/BLAS sinaliza flags espúrias de
            # divisão/overflow em produtos matriciais grandes, mesmo com
            # matrizes finitas. Suprimimos apenas esses avisos no ajuste e
            # testamos explicitamente a finitude das previsões logo abaixo.
            with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
                pipe.fit(X.iloc[treino], y.iloc[treino], **kwargs)
                previsto = pipe.predict(X.iloc[teste])
            if not np.isfinite(previsto).all():
                raise FloatingPointError(
                    f"{nome}, {modelo_nome}, dobra {dobra}: previsão não finita"
                )
            resultados.append({
                "especificacao": nome, "modelo": modelo_nome, "dobra": dobra,
                "n_treino": len(treino), "n_teste": len(teste),
                "R2": r2_score(y.iloc[teste], previsto),
                "MAE": mean_absolute_error(y.iloc[teste], previsto),
                "RMSE": root_mean_squared_error(y.iloc[teste], previsto),
            })
            if modelo_nome == "Gradient Boosting":
                perm = permutation_importance(
                    pipe, X.iloc[teste], y.iloc[teste], n_repeats=10,
                    random_state=2026 + dobra, scoring="r2", n_jobs=-1,
                )
                for variavel, media, desvio in zip(
                    colunas, perm.importances_mean, perm.importances_std, strict=True,
                ):
                    importancias.append({
                        "especificacao": nome, "dobra": dobra, "variavel": variavel,
                        "importancia_permutacao": media, "desvio_repeticoes": desvio,
                    })
    return pd.DataFrame(resultados), pd.DataFrame(importancias)


def validacao_temporal(base: pd.DataFrame) -> pd.DataFrame:
    """Avalia Gradient Boosting em 2024 após treinamento em 2015-2023."""
    colunas = [
        "log_repasse_real_por_matricula", "ano_centralizado",
        "log_matriculas_elegiveis", "log_respostas_validas", "faixa", "UF",
    ]
    treino = base[base["ano"] < 2024]
    teste = base[base["ano"].eq(2024)]
    pipe = criar_pipeline(modelos()["Gradient Boosting"])
    pipe.fit(treino[colunas], treino["indice_qualidade_igual"])
    previsto = pipe.predict(teste[colunas])
    return pd.DataFrame([{
        "modelo": "Gradient Boosting", "treino": "2015-2023", "teste": "2024",
        "n_treino": len(treino), "n_teste": len(teste),
        "R2": r2_score(teste["indice_qualidade_igual"], previsto),
        "MAE": mean_absolute_error(teste["indice_qualidade_igual"], previsto),
        "RMSE": root_mean_squared_error(teste["indice_qualidade_igual"], previsto),
    }])


def correlacoes(base: pd.DataFrame, nome: str) -> pd.DataFrame:
    saida = []
    for indicador in ["repasse_real_por_matricula", "repasse_real_por_residente_ref2019"]:
        x = base[indicador]
        y = base["indice_qualidade_igual"]
        if not np.isfinite(x.to_numpy()).all() or not np.isfinite(y.to_numpy()).all():
            raise ValueError(f"{nome}: correlação com valores não finitos")
        # Ver comentário equivalente no ajuste dos modelos: nesta instalação
        # os flags do BLAS podem gerar aviso espúrio em vetores grandes.
        with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
            pearson = pearsonr(x, y)
            spearman = spearmanr(x, y)
        saida.extend([
            {"especificacao": nome, "indicador": indicador, "metodo": "Pearson", "coeficiente": pearson.statistic, "p_valor": pearson.pvalue},
            {"especificacao": nome, "indicador": indicador, "metodo": "Spearman", "coeficiente": spearman.statistic, "p_valor": spearman.pvalue},
        ])
    return pd.DataFrame(saida)


def sensibilidade_indice(base: pd.DataFrame) -> pd.DataFrame:
    """Compara a versão igualitária, a de grupos e a retirada de um marcador."""
    alvos = [c for c in base.columns if c.startswith("indice_")]
    linhas = []
    referencia = base["indice_qualidade_igual"]
    for coluna in alvos:
        serie = base[coluna]
        if not (
            np.isfinite(referencia.to_numpy()).all()
            and np.isfinite(serie.to_numpy()).all()
            and np.isfinite(base["repasse_real_por_matricula"].to_numpy()).all()
        ):
            raise ValueError(f"Sensibilidade do índice: valores não finitos em {coluna}")
        with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
            corr_indice = pearsonr(referencia, serie).statistic
            corr_financiamento = spearmanr(
                serie, base["repasse_real_por_matricula"], nan_policy="omit"
            ).statistic
        linhas.append({
            "indice": coluna,
            "n": int(serie.notna().sum()),
            "correlacao_com_indice_igual": corr_indice,
            "spearman_financiamento_matricula": corr_financiamento,
            "media": serie.mean(),
            "desvio_padrao": serie.std(),
        })
    return pd.DataFrame(linhas)


def gerar_figuras(fluxo: pd.DataFrame, distribuicao: pd.DataFrame, base100: pd.DataFrame, importancia: pd.DataFrame) -> None:
    plt.rcParams.update({"font.size": 10, "text.color": "black", "axes.labelcolor": "black", "xtick.color": "black", "ytick.color": "black"})
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.barh(fluxo["etapa"], fluxo["observacoes"], color="#4C4C4C")
    ax.invert_yaxis()
    ax.set_xlabel("Observações")
    ax.set_title("Fluxo de inclusão da base analítica")
    for i, valor in enumerate(fluxo["observacoes"]):
        ax.text(valor, i, f" {valor:,}".replace(",", "."), va="center")
    fig.tight_layout()
    fig.savefig(SAIDA / "figura_fluxo_exclusoes.png", dpi=220)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.bar(distribuicao["faixa_respostas"].astype(str), distribuicao["observacoes"], color="#4C4C4C")
    ax.set_xlabel("Respostas válidas por componente")
    ax.set_ylabel("Observações município ano faixa")
    ax.set_title("Distribuição das respostas válidas")
    ax.tick_params(axis="x", rotation=35)
    fig.tight_layout()
    fig.savefig(SAIDA / "figura_distribuicao_respostas.png", dpi=220)
    plt.close(fig)

    amostra = base100.sample(min(5000, len(base100)), random_state=2026)
    fig, ax = plt.subplots(figsize=(6.5, 5))
    ax.scatter(
        np.log1p(amostra["repasse_real_por_residente_ref2019"]),
        np.log1p(amostra["repasse_real_por_matricula"]), s=7, alpha=0.25, color="#4C4C4C",
    )
    ax.set_xlabel("log(1 + repasse real por residente ref. 2019)")
    ax.set_ylabel("log(1 + repasse real por matrícula)")
    ax.set_title("Comparação dos indicadores de financiamento")
    fig.tight_layout()
    fig.savefig(SAIDA / "figura_comparacao_indicadores.png", dpi=220)
    plt.close(fig)

    resumo = (
        importancia[importancia["especificacao"].eq("minimo_100")]
        .groupby("variavel", as_index=False)["importancia_permutacao"].mean()
        .sort_values("importancia_permutacao", ascending=True)
    )
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.barh(resumo["variavel"], resumo["importancia_permutacao"], color="#4C4C4C")
    ax.set_xlabel("Redução média de R² após permutação")
    ax.set_title("Importância por permutação no Gradient Boosting")
    fig.tight_layout()
    fig.savefig(SAIDA / "figura_importancia_permutacao.png", dpi=220)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--atualizar-ipca", action="store_true", help="Baixa novamente a tabela 1737 do SIDRA")
    args = parser.parse_args()
    SAIDA.mkdir(parents=True, exist_ok=True)
    ipca = obter_ipca(args.atualizar_ipca)
    painel = carregar_painel(ipca)
    fluxo = fluxo_exclusoes(painel)
    distribuicao = distribuicao_respostas(painel)
    base6 = base_elegivel(painel, 6)
    base100 = base_elegivel(painel, 100)

    resultados = []
    importancias = []
    correlacoes_todas = []
    for nome, base, ponderar in [
        ("minimo_6", base6, False),
        ("minimo_100", base100, False),
        ("minimo_6_ponderado_respostas", base6, True),
    ]:
        resultado, importancia = executar_modelos(base, nome, ponderar)
        resultados.append(resultado)
        importancias.append(importancia)
        correlacoes_todas.append(correlacoes(base, nome))
    resultados_df = pd.concat(resultados, ignore_index=True)
    importancia_df = pd.concat(importancias, ignore_index=True)
    correlacoes_df = pd.concat(correlacoes_todas, ignore_index=True)
    resumo_modelos = (
        resultados_df.groupby(["especificacao", "modelo"], as_index=False)[["R2", "MAE", "RMSE"]]
        .mean()
    )
    resumo_importancia = (
        importancia_df.groupby(["especificacao", "variavel"], as_index=False)["importancia_permutacao"]
        .agg(["mean", "std"]).reset_index()
    )

    ipca.to_csv(SAIDA / "ipca_anual_base_2024.csv", index=False)
    painel.to_csv(SAIDA / "base_analitica_completa.csv", index=False)
    fluxo.to_csv(SAIDA / "fluxo_exclusoes.csv", index=False)
    distribuicao.to_csv(SAIDA / "distribuicao_respostas_validas.csv", index=False)
    resultados_df.to_csv(SAIDA / "resultados_modelos_por_dobra.csv", index=False)
    resumo_modelos.to_csv(SAIDA / "resultados_modelos_resumo.csv", index=False)
    importancia_df.to_csv(SAIDA / "importancia_permutacao_por_dobra.csv", index=False)
    resumo_importancia.to_csv(SAIDA / "importancia_permutacao_resumo.csv", index=False)
    correlacoes_df.to_csv(SAIDA / "correlacoes_indicadores.csv", index=False)
    sensibilidade_indice(base100).to_csv(SAIDA / "sensibilidade_indice_minimo_100.csv", index=False)
    validacao_temporal(base100).to_csv(SAIDA / "validacao_temporal_2024.csv", index=False)
    gerar_figuras(fluxo, distribuicao, base100, importancia_df)

    resumo = {
        "observacoes_iniciais": int(len(painel)),
        "base_minimo_6": int(len(base6)),
        "base_minimo_100": int(len(base100)),
        "descartadas_adicionais_minimo_100": int(len(base6) - len(base100)),
        "fonte_ipca": "SIDRA/IBGE tabela 1737, variável 2266",
        "base_monetaria": "média anual do IPCA, preços de 2024",
    }
    (SAIDA / "resumo_execucao.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(resumo, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
