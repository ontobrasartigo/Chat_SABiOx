# agorf_utils.py — Utilitários compartilhados do pipeline SABiOx/AgOCQs
# Contém: setup do spaCy, helpers de texto, conjugação verbal e detecção de gênero.

import re
import unicodedata

import numpy as np
import streamlit as st
import spacy

@st.cache_resource
def load_spacy():
    try:
        return spacy.load("pt_core_news_md")
    except OSError:
        st.warning("Modelo spaCy não encontrado. Instale com: python -m spacy download pt_core_news_md")
        return None

nlp = load_spacy()


def calculate_similarity(v1, v2):
    if not v1 or not v2:
        return 0.0
    return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))


def limpar_texto(texto):
    texto = re.sub(r'\(([^)]*)\)', r', \1,', texto)
    texto = re.sub(r'^[\-\*\•]\s+', '', texto, flags=re.MULTILINE)
    texto = re.sub(r'\.(?=[A-Za-zÀ-ÖØ-öø-ÿ])', '. ', texto)
    texto = re.sub(r'\n+', ' ', texto)
    texto = re.sub(r'\s{2,}', ' ', texto)
    return texto.strip()


def extrair_nome_projeto(report_input):
    """Extrai variações do nome do projeto para blacklist dinâmica."""
    match = re.search(r'Projeto\s*:\s*(.+)', report_input, re.IGNORECASE)
    if not match:
        return set()
    nome = match.group(1).strip().lower()
    variacoes = {nome}
    for palavra in nome.split():
        variacoes.add(palavra)
    sem_acento = {
        unicodedata.normalize('NFKD', v).encode('ASCII', 'ignore').decode()
        for v in variacoes
    }
    return variacoes | sem_acento


# CONJUGAÇÃO VERBAL
def conjugar_passado(verb):
    """Pretérito perfeito, 3ª pessoa singular — 'cadastrou'."""
    irregulares = {
        "fazer": "fez", "ter": "teve", "vir": "veio", "manter": "manteve",
        "ver": "viu", "ir": "foi", "trazer": "trouxe", "dizer": "disse",
        "querer": "quis", "saber": "soube", "pôr": "pôs", "dar": "deu",
        "ler": "leu", "crer": "creu", "perder": "perdeu", "valer": "valeu",
        "conter": "conteve", "obter": "obteve", "deter": "deteve",
    }
    if verb in irregulares:
        return irregulares[verb]
    if verb.endswith("ar"):
        return verb[:-2] + "ou"
    if verb.endswith("er"):
        return verb[:-2] + "eu"
    if verb.endswith("ir"):
        return verb[:-2] + "iu"
    return verb


def participio_passado(verb):
    """Particípio passado — 'foram cadastrados'."""
    irregulares_part = {
        "fazer": "feito", "ver": "visto", "vir": "vindo", "pôr": "posto",
        "dizer": "dito", "escrever": "escrito", "abrir": "aberto",
        "cobrir": "coberto", "descobrir": "descoberto",
    }
    if verb in irregulares_part:
        return irregulares_part[verb]
    if verb.endswith("ar"):
        return verb[:-2] + "ado"
    if verb.endswith("er") or verb.endswith("ir"):
        return verb[:-2] + "ido"
    return verb



def detectar_genero(termo):
    """
    Usa spaCy em frase mínima de contexto para detectar gênero morfológico.
    Retorna "Fem" ou "Masc".
    """
    frase = f"a {termo} existe"
    doc = nlp(frase)
    for token in doc:
        if token.text == termo:
            gender = token.morph.get("Gender")
            if gender:
                return gender[0]
    if termo.endswith(("ista", "agem", "ção", "são", "dade", "tude", "eza")):
        return "Fem"
    return "Masc"
