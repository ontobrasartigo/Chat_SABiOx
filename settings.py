# settings.py - Configurações do app
# Carrega todas as configurações do ambiente e secrets.

import os
import streamlit as st
from typing import Any, List

def _get(name: str, default: str):
    """Pega valor de secret ou env."""
    if hasattr(st, "secrets") and name in st.secrets:
        v = st.secrets.get(name)
        if v is None:
            return default
        return v  
    return os.getenv(name, default)

def _list_or_csv(val) -> List[str]:
    if val is None:
        return []
    if isinstance(val, (list, tuple)):
        return [str(x).strip() for x in val if str(x).strip()]
    return [x.strip() for x in str(val).split(",") if x.strip()]

def load_settings() -> dict:
    """Carrega todas as configurações do app."""
    return {
        # === GEMINI ===
        "gemini_api_keys": _list_or_csv(_get("GEMINI_API_KEYS", [])),
        "chat_models": _list_or_csv(_get("GEMINI_CHAT_MODELS", [])),
        "report_models": _list_or_csv(_get("GEMINI_REPORT_MODELS", [])),
        "extract_models": _list_or_csv(_get("GEMINI_EXTRACT_MODELS", [])),
        "summary_model": _get("GEMINI_SUMMARY_MODEL", "gemini-1.5-flash"),

        # === LIMITES ===
        "cooldown_s": float(_get("CHAT_COOLDOWN_S", 2.0)),
        "max_output_chat": int(_get("GEMINI_MAX_OUTPUT_CHAT", 512)),
        "max_output_report": int(_get("GEMINI_MAX_OUTPUT_REPORT", 1400)),
        "max_output_extract": int(_get("GEMINI_MAX_OUTPUT_EXTRACT", 1200)),

        # === CONTEXTO / RESUMO ===
        "history_window": int(_get("HISTORY_WINDOW", 14)),
        "summary_every_n": int(_get("SUMMARY_EVERY_N", 6)),
        "summary_max_chars": int(_get("SUMMARY_MAX_CHARS", 7000)),
        
    }

