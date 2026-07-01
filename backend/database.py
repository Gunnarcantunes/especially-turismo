import sqlite3
import json
from datetime import datetime
from contextlib import contextmanager
from config import DATABASE_PATH


def init_db():
    with get_conn() as conn:
        conn.executescript("""
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
        """)


@contextmanager
def get_conn():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def salvar_mensagem(session_id: str, papel: str, conteudo: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO conversas (session_id, papel, conteudo) VALUES (?, ?, ?)",
            (session_id, papel, conteudo),
        )


def obter_historico(session_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT papel, conteudo FROM conversas WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
    return [{"role": r["papel"], "content": r["conteudo"]} for r in rows]


def upsert_lead(session_id: str, dados: dict):
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM leads WHERE session_id = ?", (session_id,)
        ).fetchone()

        if existing:
            campos = ", ".join(f"{k} = ?" for k in dados if k != "session_id")
            valores = [v for k, v in dados.items() if k != "session_id"]
            valores.append(datetime.now().isoformat())
            valores.append(session_id)
            conn.execute(
                f"UPDATE leads SET {campos}, atualizado_em = ? WHERE session_id = ?",
                valores,
            )
        else:
            dados["session_id"] = session_id
            cols = ", ".join(dados.keys())
            placeholders = ", ".join("?" * len(dados))
            conn.execute(
                f"INSERT INTO leads ({cols}) VALUES ({placeholders})",
                list(dados.values()),
            )


def obter_lead(session_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM leads WHERE session_id = ?", (session_id,)
        ).fetchone()
    return dict(row) if row else None


def listar_leads(status: str | None = None) -> list[dict]:
    with get_conn() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM leads WHERE status = ? ORDER BY atualizado_em DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM leads ORDER BY atualizado_em DESC"
            ).fetchall()
    return [dict(r) for r in rows]


def salvar_metrica(session_id: str, tempo_ms: float):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO metricas (session_id, tempo_resposta_ms) VALUES (?, ?)",
            (session_id, tempo_ms),
        )


def obter_stats() -> dict:
    with get_conn() as conn:
        hoje = datetime.now().date().isoformat()

        conversas_hoje = conn.execute(
            "SELECT COUNT(DISTINCT session_id) FROM conversas WHERE DATE(criado_em) = ?",
            (hoje,),
        ).fetchone()[0]

        qualificados = conn.execute(
            "SELECT COUNT(*) FROM leads WHERE status = 'QUALIFICADO'"
        ).fetchone()[0]

        nurturing = conn.execute(
            "SELECT COUNT(*) FROM leads WHERE status = 'NURTURING'"
        ).fetchone()[0]

        total_leads = qualificados + nurturing
        taxa = round((qualificados / total_leads * 100) if total_leads > 0 else 0, 1)

        tempo_medio = conn.execute(
            "SELECT AVG(tempo_resposta_ms) FROM metricas"
        ).fetchone()[0] or 0

        conversas_por_dia = conn.execute("""
            SELECT DATE(criado_em) as dia, COUNT(DISTINCT session_id) as total
            FROM conversas
            WHERE criado_em >= DATE('now', '-6 days')
            GROUP BY dia
            ORDER BY dia
        """).fetchall()

    return {
        "conversas_hoje": conversas_hoje,
        "leads_qualificados_total": qualificados,
        "leads_nurturing_total": nurturing,
        "taxa_conversao": taxa,
        "tempo_medio_resposta_ms": round(tempo_medio, 1),
        "conversas_por_dia": [dict(r) for r in conversas_por_dia],
    }


def listar_todas_conversas() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM conversas ORDER BY session_id, id"
        ).fetchall()
    return [dict(r) for r in rows]
