# ui_extract.py - Interface de extração de requisitos
# Permite extrair JSON do relatório e editar manualmente.

import json
import streamlit as st

from prompts_sabiox import SYSTEM_EXTRACT_JSON
from gemini_client import gemini_extract_json
from sabiox_schema import sanitize_requirements, validate_requirements
from hybrid_extractor import extract_requirements_rule_based, should_use_ai_fallback

# Estado
def _init_state():
    st.session_state.setdefault("last_report", "")
    st.session_state.setdefault("last_json", None)


# IA pra refinar
SYSTEM_REFINE_JSON = """
Você é um assistente de engenharia de requisitos.
Você receberá:
1) RELATORIO
2) JSON_BASE

Tarefa:
- Retorne um JSON FINAL refinado, seguindo o mesmo schema do JSON_BASE.
- Preserve IDs e estrutura.
- Não invente conteúdo.
- Responda APENAS com JSON válido.
"""

def gemini_refine_json(report_text: str, base_json: dict) -> dict:
    payload = (
        "RELATORIO:\n"
        f"{report_text}\n\n"
        "JSON_BASE:\n"
        f"{json.dumps(base_json, ensure_ascii=False, indent=2)}\n"
    )
    return gemini_extract_json(payload, system_prompt=SYSTEM_REFINE_JSON)


# Interface principal
def render_extract_page(settings: dict):
    _init_state()
    st.title("Extração de Requisitos – SABiOx")

    if not settings.get("gemini_api_keys"):
        st.warning("Configure GEMINI_API_KEYS em Secrets/ENV.")
        st.stop()


    # Relatório: sempre pega o último do chat
    report_text = st.text_area(
        "Relatório",
        height=320,
        value=st.session_state.last_report or "",
    )

    colA, colB, colC = st.columns([1, 1, 1])
    do_extract = colA.button("Extrair JSON", type="primary")
    do_clear = colB.button("Limpar")
    
    # Upload rápido de JSON
    uploaded = colC.file_uploader(" Upload JSON", type="json", key="quick_upload")
    if uploaded:
        try:
            data = json.load(uploaded)
            data = sanitize_requirements(data)
            st.session_state.last_json = data
            st.success("JSON carregado.")
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao carregar JSON: {e}")

    if do_clear:
        st.session_state.last_json = None
        st.session_state.last_report = ""
        st.rerun()

    # Extração
    if do_extract:
        if not report_text.strip():
            st.error("Cole ou gere um relatório antes de extrair.")
            return

        with st.spinner("Extraindo JSON…"):
            rules = extract_requirements_rule_based(report_text)
            data = sanitize_requirements(rules)

            # Se o regex falhar, usa IA pra consertar
            if should_use_ai_fallback(data):
                raw = gemini_extract_json(report_text, system_prompt=SYSTEM_EXTRACT_JSON)
            else:
                raw = data

        data = sanitize_requirements(raw)

        ok, errors = validate_requirements(data)
        st.session_state.last_json = data
        st.session_state.last_report = report_text

        if ok:
            st.success("JSON extraído e validado.")
        else:
            st.warning("JSON extraído com avisos.")
            st.write(errors)

    # Editor do JSON
    if st.session_state.last_report or st.session_state.last_json is not None:
        st.subheader("JSON")

        json_str = json.dumps(st.session_state.last_json or {}, ensure_ascii=False, indent=2)
        edited_str = st.text_area("Editor JSON", value=json_str, height=320)

        col1, col2, col3 = st.columns(3)

        if col1.button("Salvar alterações"):
            try:
                candidate = json.loads(edited_str)
                candidate = sanitize_requirements(candidate)
                ok, errors = validate_requirements(candidate)
                st.session_state.last_json = candidate
                if ok:
                    st.success("Salvo com sucesso.")
                else:
                    st.warning("Salvo com avisos.")
                    st.write(errors)
            except Exception as e:
                st.error(f"JSON inválido: {e}")

        if col2.button("Melhorar com IA"):
            with st.spinner("Aprimorando com IA…"):
                refined = gemini_refine_json(report_text, st.session_state.last_json or {})
                refined = sanitize_requirements(refined)
                st.session_state.last_json = refined
                st.success("JSON refinado.")

        col3.download_button(
            "Download JSON",
            data=edited_str,
            file_name="sabiox_requirements.json",
            mime="application/json",
        )
