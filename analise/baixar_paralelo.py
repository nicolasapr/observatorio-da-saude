#!/usr/bin/env python3
"""
baixar_paralelo — recupera em paralelo os relatórios do SISVAN que faltam.

POR QUE ISTO FUNCIONA E O recuperar_sisvan.py ANTERIOR NÃO
-----------------------------------------------------------
O comentário do recuperar_sisvan.py dizia que "requisições concorrentes
serializam (lock da sessão PHP)" e concluía "por isso: UMA por vez".
A primeira metade está certa; a conclusão, não.

Medições feitas em 21/08/2026 contra o servidor, com três requisições
disparadas ao mesmo tempo:

    mesma sessão (cookie PHPSESSID compartilhado)   120 s · 364 s · >400 s
    sessão nova por requisição (sem cookie nenhum)  187 s · 182 s · 161 s

O lock é da SESSÃO, não do servidor. Como o relatório é inteiramente
determinado pelo corpo do POST — o formulário não guarda estado nenhum entre
requisições —, não há motivo para mandar cookie. Sem cookie, o servidor abre
uma sessão nova a cada requisição e elas rodam de fato em paralelo.

Por isso este script usa requests.post() direto, sem Session: uma Session
reaproveita o cookie e reintroduz exatamente o gargalo que queremos evitar.

Com 6 trabalhadores, as 92 combinações que faltam levam ~40 min em vez das
~12 h do modo serial.

USO (a partir de codigo/):
    python3 ../analise/baixar_paralelo.py              # baixa e aplica tudo
    python3 ../analise/baixar_paralelo.py --workers 3  # mais conservador
    python3 ../analise/baixar_paralelo.py --so-baixar  # não mexe nos sumários

É resumível: relance quantas vezes quiser, pula o que já está em disco.
"""
import argparse
import csv
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent / 'codigo'
sys.path.insert(0, str(RAIZ))

import requests                                                    # noqa: E402
from scripts.config import SISVAN_MENSAIS_DIR                      # noqa: E402
from scripts.extract.sisvan import (                               # noqa: E402
    _PAYLOAD_FIXO, _FASE_VALOR, _HABITO_VALOR, _MES_VALOR,
    _SUBMIT_URL, _HEADERS, validar_relatorio,
)
from scripts.transform.aplicar_recuperado import aplicar           # noqa: E402

TIMEOUT = 900          # o servidor responde entre 120 s e 480 s
MIN_BYTES = 10_000     # abaixo disso é página de erro, não relatório
MES_NOME = {v: k for k, v in _MES_VALOR.items()}
FAIXA_SLUG = {'2 a 4 anos': 'Crianças_de_2_a_4_anos',
              '5 a 9 anos': 'Crianças_de_5_a_9_anos',
              'Adolescentes': 'Adolescentes'}
SLUG_HABITO = {
 'refeicoes_principais': 'Hábito de realizar no mínimo as três refeições principais do dia',
 'refeicoes_tv':         'Hábito de realizar as refeições assistindo à televisão',
 'feijao':               'Consumo de feijão',
 'fruta':                'Consumo de fruta',
 'verduras_legumes':     'Consumo de verduras e legumes',
 'ultraprocessados':     'Consumo de Alimentos Ultraprocessados',
 'hamburguer_embutidos': 'Consumo de hambúrguer e/ou embutidos',
 'bebidas_adocadas':     'Consumo de bebidas adoçadas',
 'macarrao_salgadinho':  'Consumo de macarrão instantâneo, salgadinho de pacote ou biscoito salgado',
 'biscoito_doces':       'Consumo de biscoito recheado, doces ou guloseimas'}

_trava = threading.Lock()


def destino(ano, mes_nome, faixa_slug, habito) -> Path:
    return (SISVAN_MENSAIS_DIR / str(ano) / mes_nome / faixa_slug /
            f"{habito[:60].replace('/', '_')}.xls")


def conferir(
    conteudo: bytes,
    ano: int,
    mes_nome: str,
    faixa_slug: str,
    habito: str,
) -> str:
    """Confirma que o relatório recebido é o que foi pedido.

    O servidor às vezes devolve a página inicial ou um relatório antigo em vez
    de um erro explícito; gravar isso sem conferir contamina a série.
    Devolve '' se estiver correto, ou a descrição da divergência.
    """
    try:
        validar_relatorio(
            conteudo,
            ano=ano,
            mes=mes_nome,
            fase=faixa_slug.replace('_', ' '),
            habito=habito,
        )
    except ValueError as exc:
        return str(exc)
    return ''


def baixar(tarefa):
    ano, mes_num, faixa, slug = tarefa
    mes_nome = MES_NOME[f'{mes_num:02d}']
    faixa_slug, habito = FAIXA_SLUG[faixa], SLUG_HABITO[slug]
    rot = f'{ano}-{mes_num:02d} {faixa[:12]:12s} {slug[:22]:22s}'
    dest = destino(ano, mes_nome, faixa_slug, habito)

    if dest.exists() and dest.stat().st_size > MIN_BYTES:
        return ('pulado', tarefa, rot + ' já em disco')

    payload = {**_PAYLOAD_FIXO,
               'nuAno': str(ano), 'nuMes[]': f'{mes_num:02d}',
               'MAIOR_2_ANOS5': _FASE_VALOR[faixa_slug.replace('_', ' ')
                                            if faixa_slug != 'Adolescentes' else 'Adolescentes'],
               'OPCOES_MAIOR_2_ANOS5': _HABITO_VALOR[habito]}
    t0 = time.time()
    try:
        # requests.post SEM Session: nenhuma requisição manda cookie, então cada
        # uma ganha sua própria sessão no servidor e elas não se enfileiram.
        r = requests.post(_SUBMIT_URL, data=payload, headers=_HEADERS, timeout=TIMEOUT)
    except Exception as e:
        return ('falha', tarefa, f'{rot} {type(e).__name__} em {time.time()-t0:.0f}s')

    dt = time.time() - t0
    if len(r.content) < MIN_BYTES:
        return ('falha', tarefa, f'{rot} resposta curta ({len(r.content)} B) em {dt:.0f}s')

    erro = conferir(r.content, ano, mes_nome, faixa_slug, habito)
    if erro:
        return ('falha', tarefa, f'{rot} conteúdo divergente: {erro}')

    with _trava:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
    return ('ok', tarefa, f'{rot} {len(r.content)//1024} KB em {dt:.0f}s')


def carregar_tarefas(caminho: Path):
    tarefas = []
    with caminho.open() as f:
        for r in csv.DictReader(f):
            tarefas.append((int(r['ano']), int(r['mes']), r['faixa'], r['slug']))
    return tarefas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=6,
                    help='requisições simultâneas (6 é o melhor medido; acima disso '
                         'o tempo por requisição cresce quase na mesma proporção)')
    ap.add_argument('--lista', default=str(Path(__file__).resolve().parent / 'lacunas_v2.csv'),
                    help='CSV com colunas faixa,ano,mes,slug')
    ap.add_argument('--so-baixar', action='store_true',
                    help='baixa sem enxertar nos sumários mensais')
    args = ap.parse_args()

    tarefas = carregar_tarefas(Path(args.lista))
    print(f'{len(tarefas)} combinações · {args.workers} em paralelo\n')

    ok, falhas = [], []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futuros = {ex.submit(baixar, t): t for t in tarefas}
        for i, fut in enumerate(as_completed(futuros), 1):
            estado, tarefa, msg = fut.result()
            print(f'[{i}/{len(tarefas)}] {estado.upper():7s} {msg}', flush=True)
            (ok if estado in ('ok', 'pulado') else falhas).append(tarefa)

    print(f'\nbaixados/já existentes: {len(ok)}   falharam: {len(falhas)}')
    if falhas:
        print('Relance o script para tentar de novo apenas os que faltaram.')

    if args.so_baixar:
        return

    # O enxerto nos sumários é serial de propósito: dois marcadores do mesmo mês
    # gravam no mesmo .xlsx, e escrita concorrente corromperia o arquivo.
    print('\nAplicando aos sumários mensais...')
    for ano, mes_num, faixa, slug in ok:
        mes_nome = MES_NOME[f'{mes_num:02d}']
        faixa_slug, habito = FAIXA_SLUG[faixa], SLUG_HABITO[slug]
        try:
            r = aplicar(ano, mes_nome, faixa_slug, habito)
            print(f'  {ano}-{mes_num:02d} {faixa_slug:24s} {slug:22s} '
                  f'válidas {r["validas_antes"]:.0f} → {r["validas_depois"]:.0f}')
        except Exception as e:
            print(f'  ERRO {ano}-{mes_num:02d} {faixa_slug} {slug}: {e}')

    print('\nDepois: sumarios_anuais → sumarios_totais → series_mensais → percen')


if __name__ == '__main__':
    main()
