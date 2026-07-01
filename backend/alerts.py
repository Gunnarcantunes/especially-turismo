import json
import httpx
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from config import (
    ALERTS_PATH,
    WEBHOOK_URL,
    HORARIO_ATENDIMENTO_INICIO,
    HORARIO_ATENDIMENTO_FIM,
    AGENCIA_NOME,
)


def _carregar_alertas() -> list:
    path = Path(ALERTS_PATH)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _salvar_alertas(alertas: list):
    path = Path(ALERTS_PATH)
    path.write_text(json.dumps(alertas, ensure_ascii=False, indent=2), encoding="utf-8")


def registrar_alerta(tipo: str, mensagem: str, dados: dict | None = None):
    alertas = _carregar_alertas()
    alerta = {
        "id": len(alertas) + 1,
        "tipo": tipo,
        "mensagem": mensagem,
        "dados": dados or {},
        "criado_em": datetime.now().isoformat(),
        "lido": False,
    }
    alertas.append(alerta)
    # Mantém apenas os últimos 200 alertas
    if len(alertas) > 200:
        alertas = alertas[-200:]
    _salvar_alertas(alertas)
    return alerta


def marcar_alertas_lidos():
    alertas = _carregar_alertas()
    for a in alertas:
        a["lido"] = True
    _salvar_alertas(alertas)


def obter_alertas_nao_lidos() -> list:
    return [a for a in _carregar_alertas() if not a.get("lido")]


async def notificar_lead_qualificado(lead: dict):
    alerta = registrar_alerta(
        tipo="LEAD_QUALIFICADO",
        mensagem=f"Novo lead qualificado: {lead.get('nome') or 'Cliente'} — "
                 f"{lead.get('destino')} — R$ {lead.get('orcamento', 0):,.0f}",
        dados=lead,
    )

    if WEBHOOK_URL:
        payload = {
            "agencia": AGENCIA_NOME,
            "evento": "LEAD_QUALIFICADO",
            "alerta": alerta,
            "lead": lead,
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(WEBHOOK_URL, json=payload)
        except Exception:
            pass


async def verificar_saude(base_url: str = "http://localhost:8000"):
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{base_url}/health")
            if resp.status_code != 200:
                registrar_alerta(
                    tipo="HEALTH_CHECK_FALHOU",
                    mensagem=f"Endpoint /health retornou status {resp.status_code}",
                )
    except Exception as e:
        registrar_alerta(
            tipo="HEALTH_CHECK_FALHOU",
            mensagem=f"Agente offline ou inacessível: {str(e)[:100]}",
        )


def verificar_inatividade(ultima_conversa_em: datetime | None):
    agora = datetime.now()
    hora_atual = agora.hour

    em_horario_comercial = HORARIO_ATENDIMENTO_INICIO <= hora_atual < HORARIO_ATENDIMENTO_FIM
    if not em_horario_comercial:
        return

    if ultima_conversa_em is None:
        registrar_alerta(
            tipo="INATIVIDADE",
            mensagem="Nenhuma conversa registrada desde o início do sistema durante horário comercial.",
        )
        return

    delta = agora - ultima_conversa_em
    if delta > timedelta(hours=2):
        horas = int(delta.total_seconds() // 3600)
        registrar_alerta(
            tipo="INATIVIDADE",
            mensagem=f"Sem conversas há {horas}h durante horário comercial.",
        )


async def loop_monitoramento(base_url: str = "http://localhost:8000"):
    """Loop assíncrono de monitoramento — executado em background."""
    while True:
        await verificar_saude(base_url)
        await asyncio.sleep(60)
