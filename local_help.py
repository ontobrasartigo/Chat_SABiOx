# local_help.py - Ajuda local para o chat
# Responde perguntas sobre deploy, limites, etc.

HELP_TOPICS = {
    "deploy": (
        "Deploy no Streamlit Community Cloud:\n"
        "1) Suba o projeto no GitHub\n"
        "2) Crie o app apontando para app_hibrido.py\n"
        "3) Em Secrets, configure GEMINI_API_KEYS e modelos\n"
        "4) Garanta requirements.txt e spaCy model (pt_core_news_sm)\n"
    ),
    "limits": (
        "Para reduzir estouro de cota: limite max_output_chat, "
        "mantenha janela de histórico curta + resumo e use cooldown/caching."
    ),
    "secrets": (
        "Secrets esperados: GEMINI_API_KEYS, GEMINI_CHAT_MODELS, GEMINI_REPORT_MODELS, "
        "GEMINI_EXTRACT_MODELS, GEMINI_SUMMARY_MODEL, HISTORY_WINDOW, SUMMARY_EVERY_N, "
        "SUMMARY_MAX_CHARS, CHAT_COOLDOWN_S."
    ),
}

def answer_help(user_text: str):
    """Verifica se a pergunta é sobre tópicos de ajuda e responde."""
    t = (user_text or "").lower()
    if any(k in t for k in ["deploy", "streamlit cloud", "community cloud", "publicar", "hospedar"]):
        return HELP_TOPICS["deploy"]
    if any(k in t for k in ["limit", "quota", "erro 429", "rate limit", "cota"]):
        return HELP_TOPICS["limits"]
    if any(k in t for k in ["secrets", "variaveis", "variáveis", "env", ".toml"]):
        return HELP_TOPICS["secrets"]
    return None
