import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import csv
import io

from config import AGENCIA_NOME, AGENTE_NOME
from database import (
    init_db,
    salvar_mensagem,
    obter_historico,
    upsert_lead,
    obter_lead,
    listar_leads,
    salvar_metrica,
    obter_stats,
    listar_todas_conversas,
)
from agent import processar_mensagem, gerar_primeira_mensagem
from alerts import (
    loop_monitoramento,
    notificar_lead_qualificado,
    obter_alertas_nao_lidos,
    verificar_inatividade,
)
from models import MensagemEntrada


_ultima_conversa_em: datetime | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    task = asyncio.create_task(loop_monitoramento())
    yield
    task.cancel()


app = FastAPI(
    title=f"{AGENCIA_NOME} — API de Atendimento",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {
        "status": "online",
        "agente": AGENTE_NOME,
        "agencia": AGENCIA_NOME,
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/chat")
async def chat(entrada: MensagemEntrada):
    global _ultima_conversa_em
    _ultima_conversa_em = datetime.now()

    session_id = entrada.session_id

    # Inicializa lead se for sessão nova
    lead_atual = obter_lead(session_id)
    if lead_atual is None:
        upsert_lead(session_id, {"status": "EM_ANDAMENTO"})

    historico = obter_historico(session_id)

    # Saudação inicial automática quando não há histórico e cliente enviou mensagem vazia
    if not historico and entrada.mensagem.strip() == "":
        resposta, _, _ = gerar_primeira_mensagem()
        salvar_mensagem(session_id, "assistant", resposta)
        return {"resposta": resposta, "session_id": session_id, "lead_status": "EM_ANDAMENTO"}

    # Salva mensagem do usuário
    salvar_mensagem(session_id, "user", entrada.mensagem)

    inicio = time.monotonic()
    resposta, dados, status = processar_mensagem(historico, entrada.mensagem)
    tempo_ms = (time.monotonic() - inicio) * 1000

    salvar_mensagem(session_id, "assistant", resposta)
    salvar_metrica(session_id, tempo_ms)

    # Atualiza lead com dados extraídos
    if dados:
        lead_update = {k: v for k, v in dados.items() if v is not None}
        lead_update["status"] = status
        upsert_lead(session_id, lead_update)

        # Dispara alerta se recém qualificado
        lead_salvo = obter_lead(session_id)
        status_anterior = (lead_atual or {}).get("status", "EM_ANDAMENTO")
        if status == "QUALIFICADO" and status_anterior != "QUALIFICADO":
            await notificar_lead_qualificado(lead_salvo)

    # Verifica inatividade (não bloqueia resposta)
    verificar_inatividade(_ultima_conversa_em)

    return {"resposta": resposta, "session_id": session_id, "lead_status": status}


@app.get("/iniciar")
async def iniciar_sessao():
    """Gera session_id e retorna saudação inicial da Sofia."""
    session_id = str(uuid.uuid4())
    upsert_lead(session_id, {"status": "EM_ANDAMENTO"})
    resposta, _, _ = gerar_primeira_mensagem()
    salvar_mensagem(session_id, "assistant", resposta)
    return {"session_id": session_id, "resposta": resposta}


@app.get("/leads")
def leads(status: str | None = Query(default=None)):
    return listar_leads(status)


@app.get("/conversas")
def conversas():
    return listar_todas_conversas()


@app.get("/conversas/{session_id}")
def conversa_por_sessao(session_id: str):
    historico = obter_historico(session_id)
    if not historico:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    return {"session_id": session_id, "mensagens": historico}


@app.get("/stats")
def stats():
    dados = obter_stats()
    dados["status_agente"] = "online"
    dados["alertas_nao_lidos"] = len(obter_alertas_nao_lidos())
    return dados


@app.get("/alertas")
def alertas():
    return obter_alertas_nao_lidos()


@app.get("/leads/exportar/csv")
def exportar_leads_csv():
    leads_data = listar_leads()
    output = io.StringIO()
    if leads_data:
        writer = csv.DictWriter(output, fieldnames=leads_data[0].keys())
        writer.writeheader()
        writer.writerows(leads_data)

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads_especially_turismo.csv"},
    )
