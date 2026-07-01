from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class MensagemEntrada(BaseModel):
    session_id: str
    mensagem: str
    nome_cliente: Optional[str] = None


class MensagemSaida(BaseModel):
    resposta: str
    session_id: str
    lead_status: Optional[str] = None  # QUALIFICADO | NURTURING | EM_ANDAMENTO


class Lead(BaseModel):
    id: int
    session_id: str
    nome: Optional[str]
    destino: Optional[str]
    datas: Optional[str]
    num_pessoas: Optional[int]
    orcamento: Optional[float]
    status: str
    criado_em: datetime
    atualizado_em: datetime


class Conversa(BaseModel):
    id: int
    session_id: str
    papel: str  # "user" | "assistant"
    conteudo: str
    criado_em: datetime


class Stats(BaseModel):
    conversas_hoje: int
    leads_qualificados_total: int
    leads_nurturing_total: int
    taxa_conversao: float
    tempo_medio_resposta_ms: float
    conversas_por_dia: list[dict]
    status_agente: str
