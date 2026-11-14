"""Acesso ao Postgres (tendências coletadas, pautas e vídeos produzidos)."""
from __future__ import annotations

import json
from contextlib import contextmanager

import psycopg

from .config import DATABASE_URL


@contextmanager
def conexao():
    with psycopg.connect(DATABASE_URL, autocommit=True) as c:
        yield c


def salvar_tendencias(itens: list[dict]):
    with conexao() as c, c.cursor() as cur:
        cur.executemany(
            "INSERT INTO tendencias (fonte, regiao, termo, url, metrica, score_bruto, score, cruzamento, extra) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            [(i["fonte"], i["regiao"], i["termo"], i.get("url"), i.get("metrica"), i.get("score_bruto"),
              i.get("score"), json.dumps(i.get("cruzamento")), json.dumps(i.get("extra"))) for i in itens])


def temas_recentes(dias: int = 90) -> list[str]:
    try:
        with conexao() as c, c.cursor() as cur:
            cur.execute("SELECT tema FROM pautas WHERE criado_em > now() - make_interval(days => %s)", (dias,))
            return [r[0] for r in cur.fetchall()]
    except Exception:
        return []


def salvar_pauta(tema: dict, roteiro: dict) -> int:
    with conexao() as c, c.cursor() as cur:
        cur.execute("INSERT INTO pautas (tema, angulo, origem, titulo, roteiro, dados) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                    (tema["tema"], tema.get("angulo"), tema.get("origem"), roteiro["titulo"],
                     roteiro["roteiro_markdown"], json.dumps({"tema": tema, "roteiro": roteiro})))
        return cur.fetchone()[0]


def salvar_video(job_id: str, resultado: dict):
    with conexao() as c, c.cursor() as cur:
        cur.execute("INSERT INTO videos (job_id, titulo, duracao, resultado) VALUES (%s,%s,%s,%s) "
                    "ON CONFLICT (job_id) DO UPDATE SET resultado = EXCLUDED.resultado, atualizado_em = now()",
                    (job_id, resultado.get("titulo"), resultado.get("duracao"), json.dumps(resultado)))
