import json
import os
import re
from groq import Groq
from config import (
    AGENCIA_NOME,
    AGENTE_NOME,
    ORCAMENTO_MINIMO_QUALIFICACAO,
    GROQ_MODEL,
)

api_key = os.environ.get("GROQ_API_KEY", "").strip()
client = Groq(api_key=api_key)

SYSTEM_PROMPT = f"""Você é {AGENTE_NOME}, consultora de viagens de luxo da {AGENCIA_NOME}.

PERSONALIDADE E TOM:
- Linguagem refinada, elegante e acolhedora — jamais informal ou coloquial
- Demonstra conhecimento profundo em viagens de alto padrão e destinos exclusivos
- Sugere destinos premium naturalmente durante a conversa (Maldivas, Toscana, Patagônia,
  Gramado, Fernando de Noronha, Lisboa, Paris, Bali, Santorini, Machu Picchu, Dubai)
- Nunca pressiona o cliente — conduz com elegância e paciência
- Trata o cliente como "senhor" ou "senhora" até que ele forneça o nome
- Após o cliente fornecer o nome, usa-o com naturalidade

OBJETIVO:
Coletar, de forma natural e conversacional, as seguintes informações:
1. DESTINO — para onde o cliente deseja viajar
2. DATAS — período de viagem (datas de ida e volta, ou mês aproximado)
3. NÚMERO DE PESSOAS — quantas pessoas viajarão
4. ORÇAMENTO — investimento disponível para a viagem (em Reais)

REGRAS DE COLETA:
- Nunca faça mais de uma pergunta por mensagem
- Confirme cada informação coletada de forma elegante antes de seguir
- Se o cliente mencionar um orçamento sem especificar moeda, assuma Reais (BRL)
- Extraia valores numéricos de orçamento mesmo quando escritos por extenso (ex: "dez mil" → 10000)
- Se o cliente disser algo vago sobre datas, peça uma estimativa de mês e duração

EXTRAÇÃO DE DADOS:
Ao final de cada resposta, inclua um bloco JSON oculto com os dados extraídos até o momento.
Formato OBRIGATÓRIO — inclua SEMPRE, mesmo que os campos estejam nulos:

<!--DADOS_SOFIA
{{
  "nome": null,
  "destino": null,
  "datas": null,
  "num_pessoas": null,
  "orcamento": null
}}
DADOS_SOFIA-->

Preencha apenas os campos que já foram confirmados na conversa. Use null para os não coletados.
Para orçamento, use sempre o valor numérico (ex: 15000, não "R$ 15.000").

PRIMEIRA MENSAGEM:
Ao iniciar uma conversa (histórico vazio), apresente-se com elegância e pergunte sobre o sonho de viagem do cliente.

ESTILO DE ESCRITA:
- Parágrafos curtos e elegantes
- Emojis ocasionais e sofisticados (✈️ 🌟 🗺️ 🍷) — use com moderação
- Nunca use gírias, abreviações ou linguagem informal
- Demonstre entusiasmo genuíno pelos destinos mencionados
"""


def _extrair_dados(texto: str) -> dict | None:
    match = re.search(r"<!--DADOS_SOFIA\s*(.*?)\s*DADOS_SOFIA-->", texto, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _limpar_resposta(texto: str) -> str:
    return re.sub(r"<!--DADOS_SOFIA.*?DADOS_SOFIA-->", "", texto, flags=re.DOTALL).strip()


def _classificar_lead(dados: dict) -> str:
    campos_obrigatorios = ["destino", "datas", "num_pessoas", "orcamento"]
    todos_presentes = all(dados.get(c) is not None for c in campos_obrigatorios)

    if not todos_presentes:
        return "EM_ANDAMENTO"

    orcamento = float(dados.get("orcamento") or 0)
    if orcamento >= ORCAMENTO_MINIMO_QUALIFICACAO:
        return "QUALIFICADO"
    return "NURTURING"


def _chamar_openai(mensagens: list[dict]) -> str:
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        max_tokens=1024,
        messages=mensagens,
    )
    return response.choices[0].message.content


def processar_mensagem(historico: list[dict], mensagem_usuario: str) -> tuple[str, dict | None, str]:
    """Retorna: (resposta_limpa, dados_extraidos, status_lead)"""
    mensagens = (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + historico
        + [{"role": "user", "content": mensagem_usuario}]
    )

    texto_completo = _chamar_openai(mensagens)
    dados = _extrair_dados(texto_completo)
    resposta_limpa = _limpar_resposta(texto_completo)
    status = _classificar_lead(dados) if dados else "EM_ANDAMENTO"

    return resposta_limpa, dados, status


def gerar_primeira_mensagem() -> tuple[str, dict | None, str]:
    """Gera a saudação inicial da Sofia para sessões novas."""
    mensagens = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "[INÍCIO DE CONVERSA — apresente-se e inicie o atendimento]"},
    ]
    texto_completo = _chamar_openai(mensagens)
    resposta_limpa = _limpar_resposta(texto_completo)
    return resposta_limpa, None, "EM_ANDAMENTO"
