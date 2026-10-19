# extract/sisvan.py
"""
SISVANDownloader — baixa hábitos alimentares via POST direto (sem Selenium).

Saída: dados/sisvan/mensais/{ano}/{MES}/{faixa}/{habito}.xls

O servidor retorna um arquivo .xls no formato "Excel HTML" (HTML com
Content-Type: application/force-download). Excel e pandas leem normalmente.

Fluxo:
  1. GET /sisvan/relatoriopublico/index → obtém PHPSESSID via cookie
  2. POST /sisvan/relatoriopublico/consumoalimentar com o payload do formulário

Payload mapeado diretamente do DOM em 2026-03-26:
  nuAno           → Ano de Referência (ex: 2016)
  nuMes[]         → Mês (01–12)
  tpFiltro (M)    → Agrupar por Município
  coUfIbge (99)   → Estado = TODOS
  coMunicipioIbge → Município = TODOS
  TP_RELATORIO5   → Faixa etária = 3 ("2 anos ou mais")
  MAIOR_2_ANOS5   → Fase de vida (1=2-4, 2=5-9, 3=Adolescentes)
  OPCOES_MAIOR_2_ANOS5 → Hábito (1–10)
"""
import html
import os
import re
import time
import unicodedata

import requests

from .base import BaseDownloader
from scripts.config import SISVAN_MENSAIS_DIR

_BASE_URL = 'https://sisaps.saude.gov.br/sisvan/relatoriopublico'
_INDEX_URL  = _BASE_URL + '/index'
_SUBMIT_URL = _BASE_URL + '/consumoalimentar'

MESES = [
    'JANEIRO', 'FEVEREIRO', 'MARÇO', 'ABRIL', 'MAIO', 'JUNHO',
    'JULHO', 'AGOSTO', 'SETEMBRO', 'OUTUBRO', 'NOVEMBRO', 'DEZEMBRO',
]
FASES = ['Crianças de 2 a 4 anos', 'Crianças de 5 a 9 anos', 'Adolescentes']
HABITOS = [
    'Hábito de realizar no mínimo as três refeições principais do dia',
    'Hábito de realizar as refeições assistindo à televisão',
    'Consumo de feijão',
    'Consumo de fruta',
    'Consumo de verduras e legumes',
    'Consumo de Alimentos Ultraprocessados',
    'Consumo de hambúrguer e/ou embutidos',
    'Consumo de bebidas adoçadas',
    'Consumo de macarrão instantâneo, salgadinho de pacote ou biscoito salgado',
    'Consumo de biscoito recheado, doces ou guloseimas',
]

# ── Mapeamento texto → valor dos selects ──────────────────────────────────────
# Verificado diretamente no DOM em 2026-03-26
_FASE_VALOR = {
    'Crianças de 2 a 4 anos':  '1',
    'Crianças de 5 a 9 anos':  '2',
    'Adolescentes':             '3',
}
_HABITO_VALOR = {
    'Hábito de realizar no mínimo as três refeições principais do dia':          '1',
    'Hábito de realizar as refeições assistindo à televisão':                    '2',
    'Consumo de feijão':                                                         '3',
    'Consumo de fruta':                                                          '4',
    'Consumo de verduras e legumes':                                             '5',
    'Consumo de Alimentos Ultraprocessados':                                     '10',
    'Consumo de hambúrguer e/ou embutidos':                                      '6',
    'Consumo de bebidas adoçadas':                                               '7',
    'Consumo de macarrão instantâneo, salgadinho de pacote ou biscoito salgado': '8',
    'Consumo de biscoito recheado, doces ou guloseimas':                         '9',
}
# Valores numéricos do select nuMes[] — verificado no DOM em 2026-03-26
_MES_VALOR = {
    'JANEIRO': '01', 'FEVEREIRO': '02', 'MARÇO':    '03', 'ABRIL':    '04',
    'MAIO':    '05', 'JUNHO':     '06', 'JULHO':    '07', 'AGOSTO':   '08',
    'SETEMBRO':'09', 'OUTUBRO':   '10', 'NOVEMBRO': '11', 'DEZEMBRO': '12',
}

# Campos fixos do formulário (constantes independentes da combinação baixada)
_PAYLOAD_FIXO = {
    # 1 = 'Ver em tela' (o servidor renderiza o relatório inteiro em HTML)
    # 2 = 'Salvar em Excel' (é o que o botão de download da interface envia)
    # Verificado no DOM em 21/08/2026: este é o ÚNICO campo que difere entre
    # os dois botões do formConsumo. O scraper pedia a renderização em tela,
    # não o download — provável causa da lentidão. Ganho não medido.
    'coVisualizacao':       '2',
    'tpRelatorio':          '',
    'nuAno2014':            '',
    'nuAno2015':            '',
    'tpFiltro':             'M',    # Agrupar por Município
    'coRegiao':             '',
    'coUfIbge':             '99',   # TODOS
    'coMunicipioIbge':      '99',   # TODOS
    'noRegional':           '',
    'TP_RELATORIO':         '',
    'MENOR_6_MESES':        '',
    'ENTRE_6_2_ANOS':       '',
    'ENTRE_2_5_ANOS':       '',
    'NU_QUESTAO':           '17',
    'MAIOR_5_ANOS':         'T',
    'OPCOES_MAIOR_5_ANOS[]': '1',
    'ds_sexo3':             'T',
    'ds_raca_cor3':         '99',
    'CO_POVO_COMUNIDADE3':  'TODOS',
    'CO_ESCOLARIDADE3':     'TODOS',
    'TP_RELATORIO5':        '3',    # "2 anos ou mais"
    'MENOR_6_MESES5':       '1',
    'ENTRE_6_2_ANOS5':      '',
    'ENTRE_6_9_MESES5':     '1',
    'OPCAO_ENTRE_6_2_ANOS5':'1',
    'ds_sexo5':             'T',
    'ds_raca_cor5':         '99',
    'co_sistema_origem4':   '0',
    'CO_POVO_COMUNIDADE5':  'TODOS',
    'CO_ESCOLARIDADE5':     'TODOS',
}

_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/122.0.0.0 Safari/537.36'
    ),
    'Referer': _INDEX_URL,
}

REQUEST_TIMEOUT = 900  # segundos por download.
# Medição de 21/08/2026: o servidor leva ~480 s para gerar um relatório e tem
# teto próprio de 600 s (acima disso devolve página de erro de ~578 bytes).
# O valor anterior, 180 s, abortava requisições legítimas antes da resposta e
# foi a causa das lacunas nas séries.
REQUEST_DELAY   = 1.0  # pausa entre downloads (não sobrecarregar o servidor)
REQUEST_RETRIES = 3    # tentativas por combinação antes de desistir


def _texto_relatorio(conteudo: bytes) -> str:
    """Extrai texto normalizado do HTML entregue pelo SISVAN."""
    bruto = conteudo.decode('utf-8', errors='replace')
    texto = html.unescape(re.sub(r'<[^>]+>', ' ', bruto))
    return ' '.join(texto.split())


def _sem_acentos(valor: str) -> str:
    return ''.join(
        c for c in unicodedata.normalize('NFKD', valor.upper())
        if not unicodedata.combining(c)
    )


def identificar_relatorio(conteudo: bytes) -> dict:
    """Lê ano, mês, faixa e marcador do conteúdo — nunca do nome do arquivo.

    O cabeçalho informa apenas ``CRIANÇA`` para as duas faixas infantis. A
    distinção 2–4/5–9 é feita obrigatoriamente pela legenda ``Total de ...``.
    """
    texto = _texto_relatorio(conteudo)
    cab = re.search(
        r'Ano:\s*(\d{4})\s*-\s*M[êe]s:\s*([A-ZÇÃÉÍÓÚ]+)\s+'
        r'Fase da Vida:\s*(.+?)\s+Sexo:',
        texto,
    )
    if not cab:
        raise ValueError('cabeçalho Ano/Mês/Fase não encontrado')

    trecho = texto[cab.end():cab.end() + 5000]
    legenda = re.search(
        r'Total de (Crian[çc]as de (?:2 a 4|5 a 9) anos|Adolescentes)\s+acompanhad',
        trecho,
        flags=re.IGNORECASE,
    )
    if not legenda:
        raise ValueError('legenda da faixa etária não encontrada')

    faixa_legenda = _sem_acentos(legenda.group(1))
    if '2 A 4' in faixa_legenda:
        fase = 'Crianças de 2 a 4 anos'
    elif '5 A 9' in faixa_legenda:
        fase = 'Crianças de 5 a 9 anos'
    elif 'ADOLESCENTE' in faixa_legenda:
        fase = 'Adolescentes'
    else:  # pragma: no cover - protegido pela expressão regular acima
        raise ValueError(f'faixa etária não reconhecida: {legenda.group(1)!r}')

    trecho_norm = _sem_acentos(trecho).replace('E/OU', 'EOU')
    habito = next(
        (h for h in HABITOS
         if _sem_acentos(h).replace('E/OU', 'EOU') in trecho_norm),
        None,
    )
    if habito is None:
        raise ValueError('marcador de consumo não identificado')

    return {
        'ano': int(cab.group(1)),
        'mes': unicodedata.normalize('NFC', cab.group(2).upper()),
        'fase': fase,
        'habito': habito,
    }


def validar_relatorio(
    conteudo: bytes,
    *,
    ano: int,
    mes: str,
    fase: str,
    habito: str,
) -> dict:
    """Confirma que a resposta contém exatamente as dimensões solicitadas."""
    obtido = identificar_relatorio(conteudo)
    esperado = {
        'ano': int(ano),
        'mes': unicodedata.normalize('NFC', mes.upper()),
        'fase': fase.replace('_', ' '),
        'habito': habito,
    }
    divergencias = []
    for campo, valor in esperado.items():
        recebido_norm = (_sem_acentos(str(obtido[campo]))
                          .replace('E/OU', 'EOU').replace('E_OU', 'EOU'))
        esperado_norm = (_sem_acentos(str(valor))
                          .replace('E/OU', 'EOU').replace('E_OU', 'EOU'))
        # Nomes de arquivos são truncados a 60 caracteres; nesse único campo,
        # um prefixo inequívoco é aceitável. As demais dimensões são exatas.
        confere = (
            recebido_norm == esperado_norm
            or (
                campo == 'habito'
                and min(len(recebido_norm), len(esperado_norm)) >= 30
                and (recebido_norm.startswith(esperado_norm)
                     or esperado_norm.startswith(recebido_norm))
            )
        )
        if not confere:
            divergencias.append(
                f'{campo}: recebido {obtido[campo]!r}, esperado {valor!r}'
            )
    if divergencias:
        raise ValueError('relatório divergente — ' + '; '.join(divergencias))
    return obtido


class SISVANDownloader(BaseDownloader):
    """
    Baixa dados de hábitos alimentares do SISVAN via POST direto.

    Não usa Selenium — apenas requests com gestão de sessão PHP.
    Aceita escopo reduzido (meses/fases/habitos) para testes rápidos.

    output_dir padrão: dados/sisvan/mensais/
    """

    def __init__(self, output_dir=None, meses=None, fases=None, habitos=None):
        super().__init__(output_dir or SISVAN_MENSAIS_DIR)
        self.meses   = meses   or MESES
        self.fases   = fases   or FASES
        self.habitos = habitos or HABITOS

    def download(self, ano: int) -> None:
        """Baixa output_dir/{ano}/{MES}/{fase}/{habito}.xls para o ano dado."""
        session = requests.Session()
        session.headers.update(_HEADERS)

        # Obtém PHPSESSID visitando a página inicial
        self._info('Iniciando sessão em %s', _INDEX_URL)
        session.get(_INDEX_URL, timeout=30).raise_for_status()

        falhas = []
        try:
            for mes in self.meses:
                for fase in self.fases:
                    for habito in self.habitos:
                        try:
                            self._baixar_habito(session, ano, mes, fase, habito)
                        except Exception as exc:
                            falhas.append(f'{mes}/{fase}/{habito}: {exc}')
                        time.sleep(REQUEST_DELAY)
        finally:
            session.close()
        if falhas:
            raise RuntimeError('Coleta SISVAN incompleta: ' + '; '.join(falhas))

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _baixar_habito(self, session, ano, mes, fase, habito):
        destino = (
            self.output_dir
            / str(ano)
            / mes
            / fase.replace(' ', '_').replace('/', '_')
            / f"{habito[:60].replace('/', '_')}.xls"
        )
        if destino.exists():
            validar_relatorio(destino.read_bytes(), ano=ano, mes=mes, fase=fase, habito=habito)
            self._info('Já existe: %s/%s/%s — pulando.', mes, fase, habito[:40])
            return

        destino.parent.mkdir(parents=True, exist_ok=True)

        fase_val   = _FASE_VALOR.get(fase)
        habito_val = _HABITO_VALOR.get(habito)
        mes_val    = _MES_VALOR.get(mes)
        if fase_val is None or habito_val is None or mes_val is None:
            raise ValueError(f'Fase, hábito ou mês sem mapeamento: {mes}/{fase}/{habito}')

        payload = {
            **_PAYLOAD_FIXO,
            'nuAno':              str(ano),
            'nuMes[]':            mes_val,
            'MAIOR_2_ANOS5':      fase_val,
            'OPCOES_MAIOR_2_ANOS5': habito_val,
        }

        for tentativa in range(1, REQUEST_RETRIES + 1):
            try:
                resp = session.post(_SUBMIT_URL, data=payload, timeout=REQUEST_TIMEOUT)
                resp.raise_for_status()

                content_type = resp.headers.get('content-type', '')
                if 'html' in content_type and len(resp.content) < 10_000:
                    # Resposta muito pequena com HTML = erro/sessão expirada
                    self._warn('Resposta inesperada (%d bytes) — renovando sessão (tentativa %d)',
                               len(resp.content), tentativa)
                    self._renovar_sessao(session)
                    continue

                # O servidor pode devolver um relatório antigo com HTTP 200.
                # Validar as quatro dimensões antes de persistir evita misturar
                # faixas etárias, meses ou marcadores silenciosamente.
                validar_relatorio(
                    resp.content, ano=ano, mes=mes, fase=fase, habito=habito,
                )

                temporario = destino.with_name(destino.name + '.parcial')
                temporario.write_bytes(resp.content)
                os.replace(temporario, destino)
                self._info('Salvo: %s (%d KB)', destino.relative_to(self.output_dir),
                           len(resp.content) // 1024)
                return

            except requests.Timeout:
                espera = tentativa * 15
                self._warn('Timeout (tentativa %d/%d) em %s/%s/%s — aguardando %ds',
                           tentativa, REQUEST_RETRIES, mes, fase, habito[:30], espera)
                if tentativa < REQUEST_RETRIES:
                    time.sleep(espera)
            except Exception as e:
                raise RuntimeError(f'Erro em {mes}/{fase}/{habito}: {e}') from e

        raise RuntimeError(f'Falhou após {REQUEST_RETRIES} tentativas: {mes}/{fase}/{habito}')

    def _renovar_sessao(self, session: requests.Session) -> None:
        """Re-visita a página inicial para renovar o PHPSESSID."""
        try:
            session.get(_INDEX_URL, timeout=30)
            self._info('Sessão renovada.')
        except Exception as e:
            self._warn('Falha ao renovar sessão: %s', e)
