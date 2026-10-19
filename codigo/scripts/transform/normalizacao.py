"""
Normalização dos nomes de coluna dos marcadores do SISVAN.

O nome da coluna vem do nome do arquivo bruto, e a convenção do portal mudou ao
longo dos anos: 'e/ou' virou 'e_ou' e depois 'eou', vírgulas foram removidas e
nomes longos foram truncados em 60 caracteres. Sem normalizar, o mesmo marcador
vira duas colunas distintas e os totais anuais ficam partidos ao meio.
"""
import unicodedata

_PREFIXOS = ('total_que_', 'percentual_que_', 'total_all_')

_SUFIXO_EXPANDIR = {
    'Consumo de macarrão instantâneo salgadinho de pacote ou bis':
        'Consumo de macarrão instantâneo salgadinho de pacote ou biscoito salgado',
    'Hábito de realizar no mínimo as três refeições principais do':
        'Hábito de realizar no mínimo as três refeições principais do dia',
}


def normalizar_col(nome: str) -> str:
    """Reduz as variantes de um mesmo marcador a uma forma única."""
    # 'e/ou' vem do texto canônico do marcador; 'e_ou' vem do nome de arquivo
    # (a barra é sanitizada para underscore ao salvar). As duas formas têm de
    # convergir, senão aplicar_recuperado cria uma coluna paralela em vez de
    # preencher a existente.
    nome = unicodedata.normalize('NFC', str(nome))
    nome = nome.replace('e/ou', 'eou').replace('e_ou', 'eou').replace(', ', ' ')
    for pref in _PREFIXOS:
        if nome.startswith(pref):
            sufixo = nome[len(pref):]
            if sufixo in _SUFIXO_EXPANDIR:
                return pref + _SUFIXO_EXPANDIR[sufixo]
            break
    return nome


def normalizar_df(df):
    """Renomeia e FUNDE colunas que colidem após a normalização.

    Colunas de contagem são somadas; percentuais são descartados e recalculados
    depois a partir dos contadores.
    """
    import pandas as pd
    novo = [normalizar_col(c) for c in df.columns]
    if len(set(novo)) == len(novo):
        df.columns = novo
        return df
    df = df.copy()
    df.columns = novo
    saida = {}
    for col in dict.fromkeys(novo):
        bloco = df.loc[:, [c == col for c in novo]]
        if bloco.shape[1] == 1:
            saida[col] = bloco.iloc[:, 0]
        elif col.startswith(('total_que_', 'total_all_')):
            saida[col] = bloco.apply(pd.to_numeric, errors='coerce').sum(axis=1, min_count=1)
        else:
            saida[col] = bloco.iloc[:, 0]
    return pd.DataFrame(saida)
