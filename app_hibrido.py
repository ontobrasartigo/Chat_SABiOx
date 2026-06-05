from __future__ import annotations
import streamlit as st

from settings import load_settings
from ui_chat import render_chat_page
from ui_extract import render_extract_page
from Generator.ui_agorf import render_agofrs_page

def _merge_settings(base: dict) -> dict:
    overrides = st.session_state.get("ui_settings_overrides", {})
    out = dict(base)
    if isinstance(overrides, dict):
        out.update(overrides)
    return out


def _load_overrides_from_url() -> dict:
    qp = st.query_params
    def _i(k, d): 
        try: return int(qp.get(k, d))
        except: return d
    def _f(k, d):
        try: return float(qp.get(k, d))
        except: return d

    return {
        "history_window": _i("hw", 14),
        "summary_every_n": _i("sen", 6),
        "summary_max_chars": _i("smc", 7000),
        "cooldown_s": _f("cd", 2.0),
        "max_output_chat": _i("moc", 2048),
        "max_output_report": _i("mor", 4096),
        "max_output_extract": _i("moe", 1200),
    }


def _save_overrides_to_url(overrides: dict):
    st.query_params.update({
        "hw": overrides.get("history_window", 14),
        "sen": overrides.get("summary_every_n", 6),
        "smc": overrides.get("summary_max_chars", 7000),
        "cd": overrides.get("cooldown_s", 2.0),
        "moc": overrides.get("max_output_chat", 2048),
        "mor": overrides.get("max_output_report", 4096),
        "moe": overrides.get("max_output_extract", 1200),
    })


def _settings_popover(settings: dict) -> dict:
    cur = st.session_state.get("ui_settings_overrides", {})

    with st.popover("Config"):
        history_window = st.slider("Janela de histórico", 6, 24, int(cur.get("history_window", settings["history_window"])))
        cooldown_s = st.slider("Cooldown (s)", 0.0, 5.0, float(cur.get("cooldown_s", settings["cooldown_s"])), 0.1)

        summary_every_n = st.slider("Resumo a cada N turnos", 3, 12, int(cur.get("summary_every_n", settings["summary_every_n"])))
        summary_max_chars = st.slider("Resumo máx chars", 600, 5000, int(cur.get("summary_max_chars", settings["summary_max_chars"])), 100)
        
        max_output_chat = st.slider("Max output CHAT", 128, 2048, int(cur.get("max_output_chat", settings["max_output_chat"])), 32)
        max_output_report = st.slider("Max output REPORT", 256, 4096, int(cur.get("max_output_report", settings["max_output_report"])), 64)
        max_output_extract = st.slider("Max output EXTRACT", 256, 4096, int(cur.get("max_output_extract", settings["max_output_extract"])), 64)

        overrides = {
            "history_window": history_window,
            "cooldown_s": cooldown_s,
            "summary_every_n": summary_every_n,
            "summary_max_chars": summary_max_chars,
            "max_output_chat": max_output_chat,
            "max_output_report": max_output_report,
            "max_output_extract": max_output_extract,
        }

        st.session_state["ui_settings_overrides"] = overrides
        _save_overrides_to_url(overrides)

    return _merge_settings(settings)


def main():
    st.set_page_config(page_title="Sistema SABiOx", layout="wide")

    base = load_settings()
    if "ui_settings_overrides" not in st.session_state:
        st.session_state["ui_settings_overrides"] = _load_overrides_from_url()

    settings = _merge_settings(base)

    col1, col2 = st.columns([0.85, 0.15])
    with col1:
        st.title("Sistema SABiOx")
    with col2:
        settings = _settings_popover(settings)

    page = st.sidebar.radio("Navegação", ["Chat", "Extração(REQ)", "Gerador Extra de RFs (REQ)"])
    if page == "Chat":
        render_chat_page(settings)
    elif page == "Extração(REQ)":
        render_extract_page(settings)
    elif page == "Gerador Extra de RFs (REQ)":     
        render_agofrs_page(settings)  

if __name__ == "__main__":
    main()
