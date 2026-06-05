# ui_agorf.py — Interface Streamlit do Gerador de Requisitos Funcionais (SABiOx)
# Pipeline: Análise do Domínio → Extração → Parser → Verificador →
#           Templates (A/C/D) → Answerabilidade → Embeddings → Juiz

import re
import json
import time

import streamlit as st
from google import genai

from .agorf_utils import load_spacy, extrair_nome_projeto
from .agorf_pipeline import (
    analisar_dominio,
    extrair_celulas_dominio,
    extrair_proposicoes_com_ia,
    parse_proposicoes,
    deduplicar_pares,
    verify_pairs_with_ai,
    filtrar_answerability,
    filter_rfs_by_semantics,
    judge_questions_with_ai,
)
from .agorf_templates import generate_rfs_from_pairs

nlp = load_spacy()


def gerar_subdominios_com_ia(rfs_selecionadas, analise, api_keys):
    if isinstance(api_keys, str):
        api_keys = [api_keys]
    if not rfs_selecionadas:
        return []

    primarias = analise.get("primarias", [])
    derivadas = analise.get("derivadas", [])
    perguntas_text = "\n".join(f"{i}: {rf}" for i, rf in enumerate(rfs_selecionadas))

    prompt = f"""Você é um Engenheiro de Ontologias especializado em SABiOx.
Agrupe as Requisitos Funcionais abaixo em subdomínios coerentes.

### ENTIDADES PRIMÁRIAS DO DOMÍNIO: {', '.join(primarias)}
### ENTIDADES DERIVADAS DO DOMÍNIO: {', '.join(derivadas)}

### Requisitos Funcionais:
{perguntas_text}

### REGRAS:
1. Crie entre 2 e 5 subdomínios.
2. Nome curto e descritivo (máximo 3 palavras).
3. Agrupe por afinidade semântica.
4. Toda rf pertence a exatamente um subdomínio.
5. Use nomes das entidades primárias como base.

Retorne SOMENTE JSON válido, sem markdown:
{{"subdominios": [{{"nome": "Nome do Subdomínio", "indices": [0, 1, 2]}}]}}"""

    generative_models = ["gemma-3-27b-it", "gemma-3-12b-it", "gemini-2.0-flash"]
    for model_name in generative_models:
        for trying, api_key in enumerate(api_keys):
            try:
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(model=model_name, contents=prompt)
                raw = re.sub(r"```json|```", "", response.text.strip()).strip()
                return json.loads(raw).get("subdominios", [])
            except Exception as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    time.sleep(2)
                    continue
                else:
                    break
    return []


def render_agofrs_page(settings: dict):
    st.title("Gerador de Requisitos Funcionais (RFs)")
    st.markdown("""
    Pipeline **SABiOx + AgOrfs**: Análise do Domínio → Extração Estruturada (IA) → Parser + Gênero (spaCy) → Deduplicação → Verificador Lógico (IA) → Templates (A/C/D) → Filtro de Answerabilidade → Filtro Semântico (Embeddings) → Juiz de Qualidade (IA).
    """)

    api_keys = settings.get("gemini_api_keys", [])

    if "agorf_report" not in st.session_state:
        st.session_state["agorf_report"] = st.session_state.get("last_report", "")
    if "agorf_rfs" not in st.session_state:
        st.session_state["agorf_rfs"] = []
    if "agorf_analise" not in st.session_state:
        st.session_state["agorf_analise"] = {}
    if "agorf_rfs_edits" not in st.session_state:
        st.session_state["agorf_rfs_edits"] = {}
    if "agorf_subdominios" not in st.session_state:
        st.session_state["agorf_subdominios"] = []
    if "agorf_rfs_version" not in st.session_state:
        st.session_state["agorf_rfs_version"] = 0

    aba_geracao, aba_revisao = st.tabs(["Geração", "Revisão e Organização"])

    with aba_geracao:
        st.subheader("Relatório de entrada")
        chat_report = st.session_state.get("last_report", "")
        if chat_report and not st.session_state["agorf_report"]:
            st.session_state["agorf_report"] = chat_report

        report_input = st.text_area(
            "Relatório de Requisitos:",
            value=st.session_state["agorf_report"],
            height=280,
            key="agorf_report_textarea",
        )

        col_atualizar, col_gerar = st.columns([1, 2])
        with col_atualizar:
            if st.button("Atualizar Relatório", use_container_width=True):
                st.session_state["agorf_report"] = report_input
                st.success("Relatório atualizado para esta página.")
                st.rerun()
        with col_gerar:
            gerar = st.button("Gerar Requisitos Funcionais", type="primary", use_container_width=True)

        if gerar:
            if not nlp:
                st.error("O modelo spaCy não está instalado.")
                return
            if not api_keys:
                st.error("Nenhuma chave da API do Gemini foi encontrada.")
                return
            if not report_input.strip():
                st.warning("Cole um relatório válido para analisar.")
                return

            st.session_state["agorf_report"] = report_input

            with st.spinner("Extraindo células do domínio..."):
                celulas, texto_base = extrair_celulas_dominio(report_input)
                blacklist_projeto = extrair_nome_projeto(report_input)
                if not any(celulas.values()):
                    st.error("Formato não reconhecido. Verifique a seção '2) Domain + Dimension'.")
                    return

            with st.spinner("Analisando domínio: resolvendo conflitos, sinônimos e escopo..."):
                analise = analisar_dominio(celulas, api_keys)
                st.session_state["agorf_analise"] = analise

            with st.spinner("Extraindo proposições estruturadas por célula (IA)..."):
                proposicoes = extrair_proposicoes_com_ia(celulas, api_keys, analise)
                if not proposicoes:
                    st.warning("A extração estruturada não retornou proposições.")
                    return

            st.info(f"{len(proposicoes)} proposições extraídas. Iniciando parser...")

            with st.spinner("Parseando proposições e detectando gênero (spaCy)..."):
                raw_pairs = parse_proposicoes(proposicoes, blacklist_projeto, analise)
                if not raw_pairs:
                    st.warning("Nenhum par válido encontrado.")
                    return
                raw_pairs = deduplicar_pares(raw_pairs)

            st.info(f"{len(raw_pairs)} pares únicos. Iniciando verificação...")

            with st.spinner("Verificando coerência lógica dos pares (IA)..."):
                verified_pairs = verify_pairs_with_ai(celulas, texto_base, raw_pairs, api_keys)
                if not verified_pairs:
                    st.warning("Nenhum par aprovado. Tente enriquecer a descrição do domínio.")
                    return

            st.info(f"✅ {len(verified_pairs)} pares aprovados. Aplicando templates...")

            with st.spinner("Gerando perguntas e aplicando filtro de answerabilidade..."):
                raw_rfs = generate_rfs_from_pairs(verified_pairs, analise)
                raw_rfs = filtrar_answerability(raw_rfs, verified_pairs, analise)
                if not raw_rfs:
                    st.warning("Nenhuma rf respondível gerada.")
                    return

            with st.spinner("Filtrando por similaridade semântica..."):
                rfs_filtradas = filter_rfs_by_semantics(
                    texto_base, raw_rfs, api_keys, limiar=0.72, limiar_redundancia=0.92
                )
                if not rfs_filtradas:
                    st.warning("As perguntas não passaram pelo filtro semântico.")
                    return

            st.info(f"{len(rfs_filtradas)} perguntas passaram pelo filtro. Avaliando qualidade...")

            with st.spinner("Avaliando qualidade ontológica (Juiz IA)..."):
                rfs_julgadas = judge_questions_with_ai(
                    celulas, rfs_filtradas, api_keys, nota_minima=6.0
                )

            st.session_state["agorf_rfs"] = rfs_julgadas
            st.session_state["agorf_rfs_edits"] = {}
            st.session_state["agorf_rfs_version"] += 1

            chaves_para_limpar = [
                k for k in st.session_state.keys() 
                if k.startswith("rf_edit_") or k.startswith("rf_sel_")
            ]
            for k in chaves_para_limpar:
                del st.session_state[k]

        rfs_julgadas = st.session_state.get("agorf_rfs", [])
        if rfs_julgadas:
            st.subheader("Requisitos Funcionais Geradas (SABiOx)")
            st.write(f"Sobreviveram ao pipeline completo: **{len(rfs_julgadas)} perguntas**.")
            st.caption(
                "💡 **Nota** mede qualidade ontológica. **Aderência** mede sobreposição semântica com o domínio. "
                "Acesse a aba **Revisão e Organização** para selecionar, editar e agrupar as rfs."
            )
            for i, (rf, score_emb, nota_juiz, justificativa) in enumerate(rfs_julgadas, 1):
                qualidade = (
                    "🟩 Alta Qualidade" if nota_juiz >= 8.0
                    else "🟨 Boa Qualidade" if nota_juiz >= 6.0
                    else "🟧 Qualidade Específica"
                )
                st.info(
                    f"**rf/RF{i:02d}:** {rf}\n\n"
                    f"*({qualidade} — Nota: {nota_juiz:.1f}/10 · Aderência: {score_emb:.2f})*\n\n"
                    f"*Juiz: {justificativa}*"
                )

    with aba_revisao:
        rfs_julgadas = st.session_state.get("agorf_rfs", [])
        analise = st.session_state.get("agorf_analise", {})

        if not rfs_julgadas:
            st.info("Gere os Requisitos Funcionais na aba **Geração** para revisar aqui.")
            return

        #  BOTÃO DE ATUALIZAR
        col_titulo, col_btn_refresh = st.columns([0.8, 0.2])
        with col_titulo:
            st.subheader("Seleção e edição de rfs")
            
        with col_btn_refresh:
            if st.button("⟳", use_container_width=True, help="Restaura as perguntas para a última versão gerada pela IA, descartando edições manuais."):
                # Limpa o dicionário de edições
                st.session_state["agorf_rfs_edits"] = {}
                
                # Força o Streamlit a esquecer os textos antigos dos widgets
                chaves_para_limpar = [
                    k for k in st.session_state.keys() 
                    if k.startswith("rf_edit_") or k.startswith("rf_sel_")
                ]
                for k in chaves_para_limpar:
                    del st.session_state[k]
                    
                # Limpa os subdomínios antigos, já que as perguntas mudaram
                st.session_state["agorf_subdominios"] = []
                # Mudar a versão força os inputs a recarregarem
                st.session_state["agorf_rfs_version"] += 1
                # Recarrega a tela instantaneamente
                st.rerun()
        
        
        st.caption("Selecione as rfs que deseja manter, edite o texto se necessário, e agrupe em subdomínios.")

        edits = st.session_state.get("agorf_rfs_edits", {})
        selecionadas_idx = []
        v = st.session_state.get("agorf_rfs_version", 0)

        for i, (rf, score_emb, nota_juiz, justificativa) in enumerate(rfs_julgadas):
            qualidade = "🟩" if nota_juiz >= 8.0 else "🟨" if nota_juiz >= 6.0 else "🟧"
            with st.container():
                col_check, col_edit = st.columns([0.05, 0.95])
                with col_check:
                    selecionada = st.checkbox(f"Selecionar RF{i+1}", value=True, key=f"cq_sel_{v}_{i}", label_visibility="collapsed")
                with col_edit:
                    texto_atual = edits.get(i, rf)
                    novo_texto = st.text_input(
                        f"{qualidade} RF{i+1:02d} · Nota {nota_juiz:.1f} · Aderência {score_emb:.2f}",
                        value=texto_atual,
                        key=f"rf_edit_{v}_{i}",
                    )
                    if novo_texto != rf:
                        edits[i] = novo_texto
                if selecionada:
                    selecionadas_idx.append(i)

        st.session_state["agorf_rfs_edits"] = edits
        st.divider()

        col_sub, col_limpar = st.columns([2, 1])
        with col_sub:
            if st.button("Gerar Subdomínios das rfs selecionadas", type="primary", use_container_width=True):
                if not selecionadas_idx:
                    st.warning("Selecione pelo menos uma rf.")
                else:
                    rfs_para_subdomain = [edits.get(i, rfs_julgadas[i][0]) for i in selecionadas_idx]
                    with st.spinner("Agrupando rfs em subdomínios..."):
                        subdominios = gerar_subdominios_com_ia(rfs_para_subdomain, analise, api_keys)
                    st.session_state["agorf_subdominios"] = subdominios
                    st.rerun()
        with col_limpar:
            if st.button("Limpar subdomínios", use_container_width=True):
                st.session_state["agorf_subdominios"] = []
                st.rerun()

        subdominios = st.session_state.get("agorf_subdominios", [])
        if subdominios:
            st.subheader("Subdomínios gerados")
            for sub in subdominios:
                nome_sub = sub.get("nome", "Subdomínio")
                indices_sub = sub.get("indices", [])
                with st.expander(f"📂 {nome_sub} ({len(indices_sub)} rfs)", expanded=True):
                    for idx_global in indices_sub:
                        if idx_global < len(selecionadas_idx):
                            idx_real = selecionadas_idx[idx_global]
                            texto_rf = edits.get(idx_real, rfs_julgadas[idx_real][0])
                            st.markdown(f"**RF{idx_real+1:02d}:** {texto_rf}")

        st.divider()
        st.subheader("Edição do relatório")
        st.caption("Edite o relatório e clique em **Atualizar Relatório**. Esta edição **não afeta** o Chat SABiOx.")
        relatorio_editado = st.text_area(
            "Relatório:",
            value=st.session_state.get("agorf_report", ""),
            height=320,
            key="agorf_report_revisao",
        )
        if st.button("Atualizar Relatório", key="btn_atualizar_relatorio_revisao"):
            st.session_state["agorf_report"] = relatorio_editado
            st.success("Relatório atualizado. A próxima geração usará esta versão.")
            st.rerun()
