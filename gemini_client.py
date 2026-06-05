# gemini_client.py - Cliente pra interagir com o Gemini
# Cuida de todas as chamadas pro Gemini, cache, fallbacks e configurações.

from __future__ import annotations

import json
import os
import random
import re
import time
import hashlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
from google import genai
from google.genai import types




# Helpers para secrets e env

def _get_secret(name: str, default: Optional[str] = None) -> Optional[str]:
    """Pega segredo do Streamlit ou env, com fallback."""
    if hasattr(st, "secrets") and name in st.secrets:
        v = st.secrets.get(name)
        if v is None:
            return default
        return v  
    return os.getenv(name, default)

def _split_csv(val) -> List[str]:
    """Converte string CSV ou lista em lista de strings limpas."""
    if not val:
        return []

    # Se for lista do TOML
    if isinstance(val, (list, tuple)):
        return [str(x).strip() for x in val if str(x).strip()]

    
    parts = [p.strip() for p in str(val).split(",")]
    return [p for p in parts if p]

def get_gemini_keys() -> List[str]:
    """Pega as chaves da API do Gemini das configurações."""
    raw = _get_secret("GEMINI_API_KEYS", [])
    keys = _split_csv(raw)
    
    if not keys:
        one = _get_secret("GEMINI_API_KEY", "")
        if one:
            keys = [one.strip()]
    return keys

def get_models(mode: str) -> List[str]:
    """Pega os modelos Gemini pra um modo específico (chat, report, etc.)."""
    # mode: chat, report, extract ou summary
    env_map = {
        "chat": "GEMINI_CHAT_MODELS",
        "report": "GEMINI_REPORT_MODELS",
        "extract": "GEMINI_EXTRACT_MODELS",
        "summary": "GEMINI_SUMMARY_MODEL",
    }
    name = env_map.get(mode, "GEMINI_CHAT_MODELS")
    raw = _get_secret(name, [])

    if mode == "summary":
        if isinstance(raw, list):
            return [str(raw[0]).strip()] if raw else []
        return [raw.strip()] if raw else []

    return _split_csv(raw)


def _ui_override(name: str):
    cur = st.session_state.get("ui_settings_overrides", {})
    return cur.get(name) if isinstance(cur, dict) else None

def get_cooldown_s() -> float:
    ov = _ui_override("cooldown_s")
    if ov is not None:
        return float(ov)
    return float(_get_secret("CHAT_COOLDOWN_S", "2.0"))

def get_max_output_tokens(mode: str) -> int:
    # mode: chat/report/extract/summary
    map_key = {
        "chat": "max_output_chat",
        "report": "max_output_report",
        "extract": "max_output_extract",
        
    }
    k = map_key.get(mode)
    if k:
        ov = _ui_override(k)
        if ov is not None:
            return int(ov)
    
    default = {"chat": 800, "summary": 1024, "report": 2048, "extract": 1200}.get(mode, 600)
    return int(_get_secret(f"GEMINI_MAX_OUTPUT_{mode.upper()}", str(default)))




def enforce_cooldown(key: str = "gemini_last_call_ts") -> None:
    cd = get_cooldown_s()
    now = time.time()
    last = st.session_state.get(key)
    if last is not None:
        delta = now - float(last)
        if delta < cd:
            time.sleep(cd - delta)
    st.session_state[key] = time.time()


# ----------------------------
# Cache
# ----------------------------

def _stable_hash(obj: Any) -> str:
    s = json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

@st.cache_data(show_spinner=False, ttl=3600)
def _cached_generate(cache_key: str, payload: Dict[str, Any]) -> str:
    return _generate_uncached(payload)

def _generate_uncached(payload: Dict[str, Any]) -> str:
    return _generate_with_fallback(**payload)




@dataclass
class CallSpec:
    mode: str
    system_prompt: str
    user_text: str
    temperature: float = 0.2
    top_p: float = 0.95


def _extract_json_object(text: str) -> Optional[str]:
    
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i+1].strip()
    return None

def _is_quota_error(e: Exception) -> bool:
    msg = str(e).lower()
    return any(k in msg for k in [
        "429", "resource_exhausted", "quota", "rate limit", "too many requests"
    ])

def _is_retryable_error(e: Exception) -> bool:
    msg = str(e).lower()
    return _is_quota_error(e) or any(k in msg for k in [
        "timeout", "temporarily", "unavailable", "internal", "503", "500", "connection"
    ])


def _generate_once(model_name: str, spec: CallSpec, api_key: str) -> str:
    client = genai.Client(api_key=api_key)
    max_out = get_max_output_tokens(spec.mode)

    prompt = f"{spec.system_prompt}\n\nTEXTO:\n{spec.user_text}" if spec.system_prompt else spec.user_text

    resp = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=spec.temperature,
            top_p=spec.top_p,
            max_output_tokens=max_out,
        ),
    )
    return getattr(resp, "text", "") or ""


def _generate_with_fallback(mode: str, system_prompt: str, user_text: str,
                            temperature: float = 0.2, top_p: float = 0.95) -> str:
    """Gera resposta com Gemini, tentando várias chaves e modelos se der erro."""
    keys = get_gemini_keys()
    keys = get_gemini_keys()
    if not keys:
        raise RuntimeError("Nenhuma chave Gemini configurada. Defina GEMINI_API_KEYS (ou GEMINI_API_KEY).")

    models = get_models(mode)
    if not models:
        if mode == "report":
            models = ["gemini-2.0-flash", "gemini-2.5-flash"]
        else:
            models = ["gemini-2.0-flash"]

    spec = CallSpec(mode=mode, system_prompt=system_prompt, user_text=user_text,
                    temperature=temperature, top_p=top_p)

  
    attempts: List[Tuple[int, str]] = []
    key_start = st.session_state.get("gemini_key_start")
    if key_start is None:
        key_start = random.randint(0, len(keys)-1)
        st.session_state["gemini_key_start"] = key_start
    model_start = st.session_state.get(f"gemini_model_start_{mode}")
    if model_start is None:
        model_start = random.randint(0, len(models)-1)
        st.session_state[f"gemini_model_start_{mode}"] = model_start

    # Cria todas as combinações possíveis de (chave, modelo)
    all_combinations = []
    for ki in range(len(keys)):
        for mi in range(len(models)):
            all_combinations.append((ki, models[mi]))
    
    # Embaralhando pra distribuir a carga entre as chaves
    random.shuffle(all_combinations)

    # Tentando cada combinação, com limite de segurança
    max_tries = min(6, len(all_combinations))
    attempts = all_combinations[:max_tries]

    last_err: Optional[Exception] = None
    for idx, (ki, model_name) in enumerate(attempts, start=1):
        try:
            enforce_cooldown()
            # Tentando gerar com essa combinação
            return _generate_once(model_name, spec, api_key=keys[ki])
        except Exception as e:
            last_err = e
            if not _is_retryable_error(e):
                break
            time.sleep(min(2.0, 0.25 * (2 ** (idx - 1))))

    raise RuntimeError(f"Falha ao chamar Gemini após tentativas. Último erro: {last_err}")



def compact_history(messages: List[Dict[str, str]],
                    summary: str = "",
                    keep_last: int = 8) -> str:
    """Monta um contexto compacto: resumo + últimas N mensagens."""
    tail = messages[-keep_last:] if keep_last > 0 else messages
    lines = []
    if summary.strip():
        lines.append("RESUMO ATÉ AGORA:")
        lines.append(summary.strip())
        lines.append("")
    lines.append("ÚLTIMAS MENSAGENS:")
    for m in tail:
        role = m.get("role", "")
        content = (m.get("content", "") or "").strip()
        if not content:
            continue
        prefix = "USUÁRIO" if role == "user" else "ASSISTENTE"
        lines.append(f"{prefix}: {content}")
    return "\n".join(lines).strip()

def maybe_update_summary(messages: List[Dict[str, str]],
                         summary: str,
                         every_n_user_turns: int = 6,
                         max_chars_trigger: int = 7000) -> str:
    
    user_turns = sum(1 for m in messages if m.get("role") == "user")
    if user_turns == 0:
        return summary


    text_len = sum(len((m.get("content") or "")) for m in messages)
    should = (user_turns % every_n_user_turns == 0) or (text_len >= max_chars_trigger)

    if not should:
        return summary

    models = get_models("summary")
    if not models:
        models = get_models("chat") or ["gemini-1.5-flash"]

    # 1. Primeiro, prepara o texto (Resumo anterior + as últimas 50 mensagens)
    context_to_summarize = compact_history(messages, summary=summary, keep_last=50)
    # Atualize o resumo da conversa em até 12 bullets curtos.
    prompt = (
        "Atualize o resumo da conversa seguindo estas diretrizes:\n"
        "1. Preserve decisões de negócio (Nome, Objetivo, Atores).\n"
        "2. Identifique a 'FASE ATUAL' do roteiro SABiOx (ex: Fase 5 - Conexões).\n"
        "3. Liste o que já foi validado e o que ainda falta coletar.\n"
        "4. No máximo 12 bullets curtos. Mantenha a estrutura SABiOx.\n\n"
        "HISTÓRICO:\n" + context_to_summarize
    )
    
    payload = {
        "mode": "summary",
        "system_prompt": "",
        "user_text": prompt,
        "temperature": 0.1,
        "top_p": 0.9,
    }
    cache_key = _stable_hash({"summary_of": prompt, "models": models})
    try:
        return _cached_generate(cache_key, payload).strip()
    except Exception:
        return summary

def gemini_chat(messages: List[Dict[str, str]],
                system_prompt: str,
                summary: str = "",
                keep_last: int = 8) -> str:
    context = compact_history(messages, summary=summary, keep_last=keep_last)
    payload = {
        "mode": "chat",
        "system_prompt": system_prompt,
        "user_text": context,
        "temperature": 0.4,
        "top_p": 0.95,
    }
    cache_key = _stable_hash({"mode":"chat","system":system_prompt,"context":context})
    return _cached_generate(cache_key, payload).strip()

def gemini_report(messages: List[Dict[str, str]],
                  prompt_architect: str,
                  prompt_formatter: str,
                  summary: str = "",
                  keep_last: int = 14) -> str:
    
    """Gera relatório SABiOx em 2 etapas: arquiteto e formatador."""
    # 1. Recupera o histórico da conversa limpo
    context = compact_history(messages, summary=summary, keep_last=keep_last)

    # 2. Etapa A: Estruturação lógica (Arquiteto)
    payload_architect = {
        "mode": "report",
        "system_prompt": prompt_architect,
        "user_text": context,
        "temperature": 0.3, # Temperatura baixa pra manter a lógica firme
        "top_p": 0.9,
    }
    cache_key_arch = _stable_hash({"mode":"report_arch","system":prompt_architect,"context":context})
    structured_data = _cached_generate(cache_key_arch, payload_architect).strip()

    # 3. Etapa B: O Formatador pega a lógica e aplica o molde visual
    payload_formatter = {
        "mode": "report",
        "system_prompt": prompt_formatter,
        "user_text": structured_data, # Agora o input é a saída do Arquiteto, não o chat!
        "temperature": 0.1, # Quase zero pra não ser criativo com o layout
        "top_p": 0.9,
    }
    cache_key_form = _stable_hash({"mode":"report_form","system":prompt_formatter,"text":structured_data})
    final_report = _cached_generate(cache_key_form, payload_formatter).strip()

    return final_report


def gemini_extract_json(report_text: str, system_prompt: str) -> Dict[str, Any]:
    payload = {
        "mode": "extract",
        "system_prompt": system_prompt,
        "user_text": report_text,
        "temperature": 0.15,
        "top_p": 0.9,
    }
    cache_key = _stable_hash({"mode":"extract","system":system_prompt,"text":report_text})
    raw = _cached_generate(cache_key, payload)

    raw = (raw or "").strip()
    obj_str = _extract_json_object(raw) or raw
    try:
        return json.loads(obj_str)
    except Exception:
        obj_str2 = _extract_json_object(raw)
        if obj_str2:
            return json.loads(obj_str2)
        raise RuntimeError("Resposta do modelo não é JSON válido.")
