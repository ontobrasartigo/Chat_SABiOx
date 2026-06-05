# router.py - Roteamento de mensagens
# Decide se vai pro chat normal ou ajuda.

from __future__ import annotations

def route(user_text: str) -> str:
    """Roteia a mensagem: HELP se for sobre configs, senão CHAT."""
    t = (user_text or "").strip().lower()
    if any(k in t for k in ["streamlit", "secrets", "variave", "limit", "quota", "gemini"]):
        return "HELP"
    return "CHAT"
