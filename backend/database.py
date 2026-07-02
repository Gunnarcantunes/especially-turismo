import logging
import os
from datetime import datetime
from contextlib import contextmanager
from config import DATABASE_PATH

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")
IS_POSTGRES = bool(DATABASE_URL)

if IS_POSTGRES:
    import psycopg2
    from psycopg2.extras import RealDictCursor
else:
    import sqlite3


SCHEMA_SQLITE = """
    CREATE TABLE IF NOT EXISTS conversas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        papel TEXT NOT NULL,
        conteudo TEXT NOT NULL,
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT UNIQUE NOT NULL,
        nome TEXT,
        destino TEXT,
        datas TEXT,
        num_pessoas INTEGER,
        orcamento REAL,
        status TEXT DEFAULT 'EM_ANDAMENTO',
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS metricas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        tempo_resposta_ms REAL,
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_conversas_session ON conversas(session_id);
    CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
"""

SCHEMA_POSTGRES = """
    CREATE TABLE IF NOT EXISTS conversas (
        id SERIAL PRIMARY KEY,
        session_id TEXT NOT NULL,
        papel TEXT NOT NULL,
        conteudo TEXT NOT NULL,
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS leads (
        id SERIAL PRIMARY KEY,
        session_id TEXT UNIQUE NOT NULL,
        nome TEXT,
        destino TEXT,
        datas TEXT,
        num_pessoas INTEGER,
        orcamento REAL,
        status TEXT DEFAULT 'EM_ANDAMENTO',
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS metricas (
        id SERIAL PRIMARY KEY,
        session_id TEXT NOT NULL,
        tempo_resposta_ms REAL,
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_conversas_session ON conversas(session_id);
    CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
"""


def _q(query: str) -> str:
    """Converte placeholders '?' (estilo sqlite) para '%s' (estilo psycopg2)."""
    return query.replace("?", "%s") if IS_POSTGRES else query


@contextmanager
def get_conn():
    if IS_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor(cursor_factory=RealDictCursor)
    else:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    finally:
        cur.close()
        conn.close()


def init_db():
    backend = "postgres" if IS_POSTGRES else "sqlite"
    logger.info(f"Inicializando banco de dados (backend={backend})")
    try:
        with get_conn() as cur:
            if IS_POSTGRES:
                cur.execute(SCHEMA_POSTGRES)
            else:
                cur.executescript(SCHEMA_SQLITE)
    except Exception:
        logger.exception(f"Falha ao criar tabelas (backend={backend})")
        raise
    logger.info(f"Banco de dados pronto (backend={backend})")


def salvar_mensagem(session_id: str, papel: str, conteudo: str):
    with get_conn() as cur:
        cur.execute(
            _q("INSERT INTO conversas (session_id, papel, conteudo) VALUES (?, ?, ?)"),
            (session_id, papel, conteudo),
        )


def obter_historico(session_id: str) -> list[dict]:
    with get_conn() as cur:
        cur.execute(
            _q("SELECT papel, conteudo FROM conversas WHERE session_id = ? ORDER BY id"),
            (session_id,),
        )
        rows = cur.fetchall()
    return [{"role": r["papel"], "content": r["conteudo"]} for r in rows]


def upsert_lead(session_id: str, dados: dict):
    with get_conn() as cur:
        cur.execute(_q("SELECT id FROM leads WHERE session_id = ?"), (session_id,))
        existing = cur.fetchone()

        if existing:
            campos = ", ".join(f"{k} = ?" for k in dados if k != "session_id")
            valores = [v for k, v in dados.items() if k != "session_id"]
            valores.append(datetime.now().isoformat())
            valores.append(session_id)
            cur.execute(
                _q(f"UPDATE leads SET {campos}, atualizado_em = ? WHERE session_id = ?"),
                valores,
            )
        else:
            dados["session_id"] = session_id
            cols = ", ".join(dados.keys())
            placeholders = ", ".join("?" * len(dados))
            cur.execute(
                _q(f"INSERT INTO leads ({cols}) VALUES ({placeholders})"),
                list(dados.values()),
            )


def obter_lead(session_id: str) -> dict | None:
    with get_conn() as cur:
        cur.execute(_q("SELECT * FROM leads WHERE session_id = ?"), (session_id,))
        row = cur.fetchone()
    return dict(row) if row else None


def listar_leads(status: str | None = None) -> list[dict]:
    with get_conn() as cur:
        if status:
            cur.execute(
                _q("SELECT * FROM leads WHERE status = ? ORDER BY atualizado_em DESC"),
                (status,),
            )
        else:
            cur.execute("SELECT * FROM leads ORDER BY atualizado_em DESC")
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def salvar_metrica(session_id: str, tempo_ms: float):
    with get_conn() as cur:
        cur.execute(
            _q("INSERT INTO metricas (session_id, tempo_resposta_ms) VALUES (?, ?)"),
            (session_id, tempo_ms),
        )


def obter_stats() -> dict:
    with get_conn() as cur:
        hoje = datetime.now().date().isoformat()

        cur.execute(
            _q("SELECT COUNT(DISTINCT session_id) AS total FROM conversas WHERE DATE(criado_em) = ?"),
            (hoje,),
        )
        conversas_hoje = cur.fetchone()["total"]

        cur.execute("SELECT COUNT(*) AS total FROM leads WHERE status = 'QUALIFICADO'")
        qualificados = cur.fetchone()["total"]

        cur.execute("SELECT COUNT(*) AS total FROM leads WHERE status = 'NURTURING'")
        nurturing = cur.fetchone()["total"]

        total_leads = qualificados + nurturing
        taxa = round((qualificados / total_leads * 100) if total_leads > 0 else 0, 1)

        cur.execute("SELECT AVG(tempo_resposta_ms) AS media FROM metricas")
        tempo_medio = cur.fetchone()["media"] or 0

        if IS_POSTGRES:
            cur.execute("""
                SELECT DATE(criado_em) as dia, COUNT(DISTINCT session_id) as total
                FROM conversas
                WHERE criado_em >= CURRENT_DATE - INTERVAL '6 days'
                GROUP BY dia
                ORDER BY dia
            """)
        else:
            cur.execute("""
                SELECT DATE(criado_em) as dia, COUNT(DISTINCT session_id) as total
                FROM conversas
                WHERE criado_em >= DATE('now', '-6 days')
                GROUP BY dia
                ORDER BY dia
            """)
        conversas_por_dia = cur.fetchall()

    return {
        "conversas_hoje": conversas_hoje,
        "leads_qualificados_total": qualificados,
        "leads_nurturing_total": nurturing,
        "taxa_conversao": taxa,
        "tempo_medio_resposta_ms": round(tempo_medio, 1),
        "conversas_por_dia": [dict(r) for r in conversas_por_dia],
    }


def listar_todas_conversas() -> list[dict]:
    with get_conn() as cur:
        cur.execute("SELECT * FROM conversas ORDER BY session_id, id")
        rows = cur.fetchall()
    return [dict(r) for r in rows]
