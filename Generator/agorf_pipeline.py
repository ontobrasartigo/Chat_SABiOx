# agorf_pipeline.py — Pipeline de extração e processamento SABiOx/AgOrfs
# Etapas: análise do domínio, extração de proposições, parser, verificador,
#         filtro de answerabilidade, filtro semântico, juiz de qualidade.

import re
import json
import time

import streamlit as st
from google import genai
from google.genai import types

from .agorf_utils import (
    limpar_texto, detectar_genero, calculate_similarity
)


# PRÉ-PROCESSAMENTO — Análise e resolução de conflitos do domínio
def analisar_dominio(celulas, api_keys):
    """
    Análise e resolução de conflitos do domínio antes da extração ontológica.

    Retorna dict com:
      "sinonimos", "compostos", "atores", "primarias", "derivadas",
      "derivadas_detalhadas", "atributos", "fora_de_escopo", "conflitos"
    """
    if isinstance(api_keys, str):
        api_keys = [api_keys]

    texto_dominio = (
        f"Domínio:\n{celulas['dominio']}\n\n"
        f"Dimensão Horizontal:\n{celulas['horizontal']}\n\n"
        f"Dimensão Vertical:\n{celulas['vertical']}"
    ).strip()

    prompt = f"""Você é um Engenheiro de Ontologias Sênior especializado em SABiOx.
Analise o texto do domínio abaixo e produza um dicionário consensual que resolve todos os conflitos terminológicos antes da extração ontológica.

### TEXTO DO DOMÍNIO:
{texto_dominio}

### O QUE ANALISAR:

1. SINÔNIMOS E ALIASES: Termos diferentes que se referem ao mesmo conceito.
   Regra: escolha o mais específico como canônico.
   Exemplo: "profissional" e "esteticista" → canônico: "esteticista"
   Exemplo: "agenda" e "agendamento" → canônico: "agendamento" (agenda é a visão, agendamento é o registro)

2. COMPOSTOS A NORMALIZAR: Frases que devem ser reduzidas ao núcleo semântico.
   Exemplos: "procedimento agendado" → "procedimento", "cadastro de clientes" → "cliente"

3. ATORES: Pessoas ou papéis que realizam ações (não são entidades da ontologia).

4. ENTIDADES PRIMÁRIAS: Objetos manipulados diretamente no domínio.
   REGRA DE DESEMPATE CRÍTICA: Quando houver dúvida entre primária e derivada,
   classifique como PRIMÁRIA. É melhor tratar uma derivada como primária do que
   perder uma entidade real — o verificador lógico refinará depois.
   Exemplos típicos: cliente, agendamento, procedimento.

5. ENTIDADES DERIVADAS: Conceitos calculados ou visualizados a partir de primárias.
   Só classifique como derivada se houver certeza — não existe sem as primárias.
   Exemplos claros: faturamento (calculado de agendamentos+procedimentos), popularidade (contagem de procedimentos).

6. DERIVADAS DETALHADAS: Para cada entidade derivada identificada, liste suas dimensões
   de análise conforme mencionadas no texto, e qual entidade primária gera cada dimensão.
   Exemplo para "faturamento" num domínio de clínica:
     - "faturamento por esteticista" → primária: "esteticista"
     - "faturamento por procedimento" → primária: "procedimento"
   Isso é essencial para gerar perguntas de qualidade sobre gestão financeira e desempenho.
   Se o texto mencionar "faturamento por X" ou "rentabilidade de Y", capture essas dimensões.

7. ATRIBUTOS PRIMITIVOS: Dados simples que caracterizam entidades — NÃO são entidades em si.
   Exemplos: nome, telefone, endereço, horário, valor, cpf, identificação.

8. FORA DE ESCOPO: Termos que o texto indica explicitamente como não pertencentes ao domínio.
   Inclua termos mencionados com "ficam de fora", "não processará", "excluído", etc.

9. CONFLITOS SEMÂNTICOS: Mesmo termo com significados distintos entre as células.
   Descreva brevemente como resolver cada caso.

### RETORNE SOMENTE JSON VÁLIDO, sem markdown:
{{
  "sinonimos": {{"alias": "canonico"}},
  "compostos": {{"frase composta": "nucleo"}},
  "atores": ["lista", "de", "atores"],
  "primarias": ["lista", "de", "entidades", "primarias"],
  "derivadas": ["lista", "simples", "de", "derivadas"],
  "derivadas_detalhadas": [
    {{
      "nome": "faturamento",
      "dimensoes": [
        {{"dimensao": "por esteticista", "primaria": "esteticista"}},
        {{"dimensao": "por procedimento", "primaria": "procedimento"}}
      ]
    }}
  ],
  "atributos": ["lista", "de", "atributos", "primitivos"],
  "fora_de_escopo": ["lista", "de", "termos", "excluidos"],
  "conflitos": [{{"termo": "nome do termo", "resolucao": "como usar"}}]
}}"""

    generative_models = ["gemma-3-27b-it", "gemini-2.5-flash", "gemini-2.0-flash" ]
    for model_name in generative_models:
        for trying, api_key in enumerate(api_keys):
            try:
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(model=model_name, contents=prompt)
                raw = re.sub(r"```json|```", "", response.text.strip()).strip()
                resultado = json.loads(raw)

                print("── Análise do domínio ──")
                print(f"  Sinônimos:            {resultado.get('sinonimos', {})}")
                print(f"  Compostos:            {resultado.get('compostos', {})}")
                print(f"  Atores:               {resultado.get('atores', [])}")
                print(f"  Primárias:            {resultado.get('primarias', [])}")
                print(f"  Derivadas:            {resultado.get('derivadas', [])}")
                print(f"  Derivadas detalhadas: {resultado.get('derivadas_detalhadas', [])}")
                print(f"  Atributos:            {resultado.get('atributos', [])}")
                print(f"  Fora de escopo:       {resultado.get('fora_de_escopo', [])}")
                print(f"  Conflitos:            {resultado.get('conflitos', [])}")
                return resultado

            except Exception as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    time.sleep(2)
                    continue
                else:
                    print(f"Erro na análise do domínio: {e}")
                    break

    print("Análise do domínio indisponível. Continuando com fallback vazio.")
    return {
        "sinonimos": {}, "compostos": {}, "atores": [],
        "primarias": [], "derivadas": [], "derivadas_detalhadas": [],
        "atributos": [], "fora_de_escopo": [], "conflitos": []
    }


def construir_mapa_normalizacao(analise):
    """Combina sinônimos e compostos num dict flat {alias: canônico}."""
    mapa = {}
    for alias, canonico in analise.get("sinonimos", {}).items():
        mapa[alias.lower().strip()] = canonico.lower().strip()
    for composto, nucleo in analise.get("compostos", {}).items():
        mapa[composto.lower().strip()] = nucleo.lower().strip()
    return mapa


# PRÉ-PROCESSAMENTO — Extração das 3 células do domínio
def extrair_celulas_dominio(report_input):
    """
    Extrai Domínio, Horizontal e Vertical da seção 2.
    Remove frases negativas/de exclusão da Vertical antes de qualquer IA ver o texto.
    """
    celulas = {"dominio": "", "horizontal": "", "vertical": ""}

    secao2_match = re.search(
        r"2\)\s*Domain.*?\n(.*?)(?=###\s*3\)|$)",
        report_input, re.IGNORECASE | re.DOTALL
    )
    if not secao2_match:
        return celulas, ""

    secao2 = secao2_match.group(1)

    dom_match = re.search(
        r"Domínio\s*:(.*?)(?=Dimensão\s*Horizontal\s*:|Dimensão\s*Vertical\s*:|$)",
        secao2, re.IGNORECASE | re.DOTALL
    )
    if dom_match:
        celulas["dominio"] = limpar_texto(dom_match.group(1).strip())

    horiz_match = re.search(
        r"Dimensão\s*Horizontal\s*:(.*?)(?=Dimensão\s*Vertical\s*:|$)",
        secao2, re.IGNORECASE | re.DOTALL
    )
    if horiz_match:
        celulas["horizontal"] = limpar_texto(horiz_match.group(1).strip())

    vert_match = re.search(
        r"Dimensão\s*Vertical\s*:(.*?)$",
        secao2, re.IGNORECASE | re.DOTALL
    )
    if vert_match:
        texto_vert = vert_match.group(1).strip()
        frases = re.split(r'(?<=[.!?])\s+', texto_vert)
        PADROES_EXCLUSAO = re.compile(
            r'\bNÃO\b'
            r'|não processará|não emitirá|não fará|não controla'
            r'|não inclui|não abrange|não contempla|não será'
            r'|ficam? (explicitamente )?de fora'
            r'|fora das? fronteiras'
            r'|fora do escopo'
            r'|está(rá)? exclu[íi]d[oa]'
            r'|ficam? exclu[íi]d[oa]'
            r'|nesta fase.*exclu'
            r'|exclu[íi]d[oa]s? (nesta fase|por ora|no momento)'
            r'|não (se aplica|é contemplad|será contemplad)'
            r'|limita[-‐]se a'
            r'|restrito a'
            r'|apenas.*não',
            re.IGNORECASE
        )
        frases_positivas = [f for f in frases if not PADROES_EXCLUSAO.search(f)]
        celulas["vertical"] = limpar_texto(" ".join(frases_positivas).strip())

    texto_base = (
        f"Domínio: {celulas['dominio']} "
        f"Dimensão Horizontal: {celulas['horizontal']} "
        f"Dimensão Vertical: {celulas['vertical']}"
    ).strip()

    return celulas, texto_base


# ETAPA 0 — Extração Estruturada de Proposições via IA
PROMPT_EXTRACAO = """Você é um extrator de fatos ontológicos para a metodologia SABiOx.
Sua tarefa é ler a descrição de um domínio de negócio e extrair todas as relações relevantes em um formato estruturado fixo.

### FORMATO DE SAÍDA (siga rigorosamente):
Para ações com ator explícito:
AÇÃO: <ator> | <verbo no infinitivo> | <objeto>

Para composições (o que uma entidade contém ou registra):
COMPOSIÇÃO: <entidade> | tem | <componente>

### REGRAS CRÍTICAS:
1. CADA CAMPO DEVE SER UMA ÚNICA PALAVRA SIMPLES. Nunca use frases, preposições, adjetivos ou compostos.
   - ERRADO: "cadastro de clientes", "procedimento agendado", "cálculo do faturamento"
   - CORRETO: "cliente", "procedimento", "faturamento"
2. Use EXATAMENTE os substantivos do texto — nunca substitua por sinônimos ou generalizações.
3. VERBOS sempre no infinitivo: "cadastrar", "realizar", "consultar".
4. Todo par AÇÃO deve ter um ator explícito — nunca use sujeito implícito ou genérico.
5. NÃO extraia atributos primitivos como entidades em COMPOSIÇÃO (nome, telefone, endereço, cpf, senha).
6. Extraia TODAS as relações entre atores (ex: recepcionista associa esteticista).
7. Não invente relações que não estão no texto.

### EXEMPLOS DE SAÍDA CORRETA:
AÇÃO: recepcionista | cadastrar | cliente
AÇÃO: recepcionista | realizar | agendamento
AÇÃO: recepcionista | associar | esteticista
AÇÃO: esteticista | consultar | agendamento
AÇÃO: dona | analisar | faturamento
COMPOSIÇÃO: agendamento | tem | cliente
COMPOSIÇÃO: agendamento | tem | procedimento
COMPOSIÇÃO: agendamento | tem | esteticista
COMPOSIÇÃO: agendamento | tem | horário

### EXEMPLOS DE SAÍDA ERRADA (nunca faça isso):
AÇÃO: profissional | executar | procedimento agendado  ← "procedimento agendado" tem adjetivo
COMPOSIÇÃO: cadastro de clientes | tem | telefone  ← composto e atributo primitivo
AÇÃO: (implícito) | agendar | procedimento  ← sujeito implícito não é permitido

### TEXTO DO DOMÍNIO:
{texto}

Retorne APENAS as linhas no formato acima, sem títulos, explicações ou markdown."""


def extrair_proposicoes_com_ia(celulas, api_keys, analise=None):
    """
    Etapa 0 — extração estruturada por célula com contexto do domínio injetado.
    """
    if isinstance(api_keys, str):
        api_keys = [api_keys]
    if analise is None:
        analise = {}

    vocab_map = construir_mapa_normalizacao(analise)
    fora_de_escopo = analise.get("fora_de_escopo", [])
    primarias = analise.get("primarias", [])
    derivadas = analise.get("derivadas", [])

    contexto_dominio = ""
    if primarias:
        contexto_dominio += f"Entidades PRIMÁRIAS deste domínio: {', '.join(primarias)}\n"
    if derivadas:
        contexto_dominio += f"Entidades DERIVADAS (calculadas, não primárias): {', '.join(derivadas)}\n"
    if fora_de_escopo:
        contexto_dominio += f"Termos FORA DE ESCOPO — nunca extrair: {', '.join(fora_de_escopo)}\n"

    textos_por_celula = {
        "dominio": (
            "INSTRUÇÕES PARA ESTA CÉLULA: Foco em atores e suas responsabilidades. "
            "Extraia quem faz o quê e quais entidades existem. Use UMA ÚNICA PALAVRA por campo.\n\n"
            + celulas["dominio"]
        ),
        "horizontal": (
            "INSTRUÇÕES PARA ESTA CÉLULA: Foco em fluxos de processo e ações concretas. "
            "Extraia cada ação com seu ator e objeto. Use UMA ÚNICA PALAVRA por campo.\n\n"
            + celulas["horizontal"]
        ),
        "vertical": (
            "INSTRUÇÕES PARA ESTA CÉLULA: Foco em composições — o que cada entidade contém. "
            "Extraia apenas linhas COMPOSIÇÃO. Não extraia atributos primitivos (nome, telefone, endereço, cpf). "
            "Use UMA ÚNICA PALAVRA por campo.\n\n"
            + celulas["vertical"]
        ),
    }

    generative_models = ["gemma-3-27b-it", "gemini-2.0-flash", "gemini-2.5-flash"]
    todas_proposicoes = []
    seen_props = set()

    for tipo, texto_celula in textos_por_celula.items():
        if not celulas[tipo].strip():
            continue

        prompt_celula = PROMPT_EXTRACAO.format(texto=texto_celula)
        if contexto_dominio:
            prompt_celula = (
                PROMPT_EXTRACAO.split("### TEXTO DO DOMÍNIO:")[0]
                + f"\n### CONTEXTO DESTE DOMÍNIO ESPECÍFICO:\n{contexto_dominio}"
                + "\n### TEXTO DO DOMÍNIO:\n{texto}\n\nRetorne APENAS as linhas no formato acima, sem títulos, explicações ou markdown."
            ).format(texto=texto_celula)
        extraido = False

        for model_name in generative_models:
            if extraido:
                break
            for trying, api_key in enumerate(api_keys):
                try:
                    client = genai.Client(api_key=api_key)
                    response = client.models.generate_content(model=model_name, contents=prompt_celula)
                    linhas = response.text.strip().split("\n")

                    for linha in linhas:
                        linha = linha.strip()
                        if not linha:
                            continue
                        if not (linha.startswith("AÇÃO:") or linha.startswith("COMPOSIÇÃO:")):
                            continue
                        partes = linha.split("|")
                        if len(partes) != 3:
                            continue
                        if vocab_map:
                            tipo_linha = "AÇÃO:" if linha.startswith("AÇÃO:") else "COMPOSIÇÃO:"
                            # Remove o prefixo de tipo de partes[0] antes de normalizar
                            partes[0] = partes[0][len(tipo_linha):].strip()
                            partes_norm = [
                                vocab_map.get(p.strip().lower(), p.strip())
                                for p in partes
                            ]
                            linha = f"{tipo_linha} {partes_norm[0]} | {partes_norm[1]} | {partes_norm[2]}"
                        key = linha.lower()
                        if key not in seen_props:
                            seen_props.add(key)
                            todas_proposicoes.append(linha)

                    print(f"Célula '{tipo}': {len([l for l in linhas if l.startswith(('AÇÃO:', 'COMPOSIÇÃO:'))])} proposições extraídas.")
                    extraido = True
                    break

                except Exception as e:
                    if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                        time.sleep(2)
                        continue
                    else:
                        print(f"Erro na extração da célula '{tipo}': {e}")
                        break

    print(f"Total: {len(todas_proposicoes)} proposições únicas extraídas.")
    return todas_proposicoes


# ETAPA 1 — Parser de Proposições + Detecção de Gênero
def parse_proposicoes(proposicoes, blacklist_projeto=None, analise=None):
    """
    Parser de linhas estruturadas + detecção de gênero via spaCy.
    Usa fora_de_escopo e atributos da análise para filtros precisos.
    """
    if analise is None:
        analise = {}

    blacklist = {
        "propósito", "ontologia", "domínio", "dimensão", "horizontal", "vertical",
        "projeto", "versão", "sistema", "requisito", "escopo", "subdomínio",
        "metodologia", "documento", "funcionalidade", "tela", "botão", "interface",
    }
    fora_escopo_analise = {t.lower().strip() for t in analise.get("fora_de_escopo", [])}
    blacklist.update(fora_escopo_analise)

    atributos_primitivos = {
        "nome", "telefone", "endereço", "cpf", "rg", "senha", "email",
        "identificação", "identificacao", "data", "hora", "cep", "numero",
        "número", "valor", "preco", "preço",
    }
    atributos_analise = {a.lower().strip() for a in analise.get("atributos", [])}
    atributos_primitivos.update(atributos_analise)

    COLETIVOS = {"cadastro", "lista", "registro", "conjunto", "histórico",
                 "agenda", "relatório", "relatorio", "cálculo", "calculo",
                 "análise", "analise", "informação", "informacao"}

    def normalizar_termo(termo):
        termo = termo.lower().strip()
        palavras = termo.split()
        if len(palavras) == 1:
            return termo
        if len(palavras) >= 3 and palavras[1] in ("de", "do", "da", "dos", "das") and palavras[0] in COLETIVOS:
            return palavras[2]
        for i, palavra in enumerate(palavras):
            if palavra in ("de", "do", "da", "dos", "das") and i + 1 < len(palavras):
                candidato = palavras[i + 1]
                if candidato not in COLETIVOS and candidato not in ("um", "uma", "o", "a"):
                    if palavras[0] in COLETIVOS:
                        return candidato
        return palavras[0]

    if blacklist_projeto:
        blacklist.update(blacklist_projeto)

    gender_cache = {}

    def get_gender(termo):
        termo_lower = normalizar_termo(termo)
        if termo_lower not in gender_cache:
            gender_cache[termo_lower] = detectar_genero(termo_lower)
        return gender_cache[termo_lower]

    pairs = []
    seen = set()

    for linha in proposicoes:
        linha = linha.strip()
        if not linha:
            continue
        try:
            if linha.startswith("AÇÃO:"):
                conteudo = linha[5:].strip()
                partes = [p.strip() for p in conteudo.split("|")]
                if len(partes) != 3:
                    continue

                suj_raw, verb_raw, obj_raw = partes
                verb = verb_raw.lower().strip()
                obj  = normalizar_termo(obj_raw)
                suj  = suj_raw.lower().strip()

                if obj in atributos_primitivos or obj in blacklist:
                    print(f"  Parser: descartando '{obj}' (primitivo ou blacklist)")
                    continue

                if suj == "(implícito)":
                    print(f"  Parser: ignorando proposição com sujeito implícito ({verb} → {obj})")
                    continue
                else:
                    suj = normalizar_termo(suj)
                    if suj in blacklist or suj in atributos_primitivos:
                        continue
                    if suj == obj:
                        continue
                    key = ("A", suj, verb, obj)
                    if key not in seen:
                        seen.add(key)
                        pairs.append({
                            "cenario": "A",
                            "suj": suj,
                            "verb": verb,
                            "obj": obj,
                            "suj_gen": get_gender(suj),
                            "obj_gen": get_gender(obj),
                        })

            elif linha.startswith("COMPOSIÇÃO:"):
                conteudo = linha[11:].strip()
                partes = [p.strip() for p in conteudo.split("|")]
                if len(partes) != 3:
                    continue

                token_raw, _, child_raw = partes
                token_lema = normalizar_termo(token_raw)
                lema_child = normalizar_termo(child_raw)

                if token_lema in blacklist or lema_child in blacklist:
                    continue
                if lema_child in atributos_primitivos:
                    print(f"  Parser: descartando composição com primitivo '{lema_child}'")
                    continue
                if token_lema == lema_child:
                    continue

                key = ("C", token_lema, lema_child)
                if key not in seen:
                    seen.add(key)
                    pairs.append({
                        "cenario": "C",
                        "token": token_lema,
                        "child": lema_child,
                        "token_gen": get_gender(token_lema),
                        "child_gen": get_gender(lema_child),
                    })

        except Exception as e:
            print(f"Erro ao parsear linha '{linha}': {e}")
            continue

    print(f"Parser: {len(proposicoes)} proposições → {len(pairs)} pares únicos.")
    return pairs


# ETAPA 1b — Deduplicação de pares
def deduplicar_pares(pairs):
    seen_keys = set()
    deduplicados = []
    for p in pairs:
        k = (p.get("cenario"), p.get("suj", ""), p.get("verb", ""), p.get("obj", ""),
             p.get("token", ""), p.get("child", ""))
        if k not in seen_keys:
            seen_keys.add(k)
            deduplicados.append(p)
    print(f"Deduplicação: {len(pairs)} → {len(deduplicados)} pares.")
    return deduplicados


# ETAPA 2 — Verificador Lógico
def verify_pairs_with_ai(celulas, texto_base, pairs, api_keys):
    if not pairs:
        return pairs
    if isinstance(api_keys, str):
        api_keys = [api_keys]

    pairs_text = ""
    for i, p in enumerate(pairs):
        if p["cenario"] == "A":
            pairs_text += f"{i}: [A] '{p['suj']}' → {p['verb']} → '{p['obj']}'\n"
        elif p["cenario"] == "C":
            pairs_text += f"{i}: [C] '{p['token']}' possui → '{p['child']}'\n"

    contexto = (
        f"Domínio (atores e objetos centrais):\n{celulas['dominio']}\n\n"
        f"Dimensão Horizontal (fluxos e ações):\n{celulas['horizontal']}\n\n"
        f"Dimensão Vertical (composições e atributos):\n{celulas['vertical']}"
    )

    prompt = f"""Você é um Engenheiro de Ontologias Sênior especializado na metodologia SABiOx.
Filtre as tríades abaixo aprovando apenas as ontologicamente válidas e úteis.

### CONTEXTO DO DOMÍNIO:
{contexto}

### PASSO 1 — Identifique antes de avaliar:
- Entidades PRIMÁRIAS: objetos manipulados diretamente (cliente, agendamento, procedimento).
- Entidades DERIVADAS: existem como resultado de operações sobre primárias.
- Atores: pessoas ou papéis que realizam ações.

### PASSO 2 — Descarte se:
1. Verbo sem sentido lógico com os substantivos.
2. Substantivo puramente sistêmico (botão, tela, banco de dados).
3. Atributo primitivo como entidade principal.
4. Agente e paciente invertidos de forma ilógica.
5. Entidade derivada como componente físico de outra.
6. Entidade abstrata ou métrica como sujeito agindo sobre entidade concreta.

### EXEMPLOS FEW-SHOT:
✅ APROVADO: [A] 'recepcionista' → cadastrar → 'cliente' — ator realizando ação sobre objeto primário.
✅ APROVADO: [A] 'dona' → analisar → 'faturamento' — ator analisando métrica derivada.
✅ APROVADO: [A] 'recepcionista' → associar → 'esteticista' — relação ator→ator válida no processo.
✅ APROVADO: [C] 'agendamento' possui → 'procedimento' — composição real e direta.
❌ REJEITADO: [A] 'histórico' → ter → 'cliente' — entidade derivada como sujeito sobre primária.
❌ REJEITADO: [C] 'histórico' possui → 'agendamento' — invertido: agendamento compõe o histórico.
❌ REJEITADO: [A] 'faturamento' → incluir → 'procedimento' — métrica como sujeito agindo sobre primária.
❌ REJEITADO: [A] 'agenda' → revisar → 'cliente' — "agenda" é alias de "agendamento"; use o termo canônico.

### PARES:
{pairs_text}

Retorne SOMENTE JSON válido, sem markdown:
{{"aprovados": [lista de índices inteiros], "rejeitados": {{"indice": "razão resumida"}}}}"""

    generative_models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemma-3-27b-it"]
    for model_name in generative_models:
        for trying, api_key in enumerate(api_keys):
            try:
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(model=model_name, contents=prompt)
                raw = re.sub(r"```json|```", "", response.text.strip()).strip()
                resultado = json.loads(raw)
                indices_aprovados = set(resultado.get("aprovados", []))
                rejeitados = resultado.get("rejeitados", {})
                if rejeitados:
                    print("── Pares rejeitados ──")
                    for idx, razao in rejeitados.items():
                        par = pairs[int(idx)] if int(idx) < len(pairs) else "?"
                        print(f"  [{idx}] {par} → {razao}")
                approved = [p for i, p in enumerate(pairs) if i in indices_aprovados]
                print(f"Verificador: {len(pairs)} pares → {len(approved)} aprovados.")
                return approved
            except Exception as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    time.sleep(2)
                    continue
                else:
                    break

    print("Verificador indisponível. Usando todos os pares como fallback.")
    return pairs


# ETAPA 3b — Filtro de answerabilidade
def filtrar_answerability(rfs_lista, pares_aprovados, analise=None):
    """
    Descarta rfs cujos termos entre aspas não existem nos pares aprovados
    nem nas derivadas/atores da análise do domínio.
    """
    if analise is None:
        analise = {}

    termos_validos = set()
    for p in pares_aprovados:
        if p["cenario"] == "A":
            termos_validos.add(p["suj"].lower())
            termos_validos.add(p["obj"].lower())
        elif p["cenario"] == "C":
            termos_validos.add(p["token"].lower())
            termos_validos.add(p["child"].lower())

    for t in analise.get("derivadas", []):
        termos_validos.add(t.lower().strip())
    for t in analise.get("atores", []):
        termos_validos.add(t.lower().strip())

    aprovadas = []
    descartadas = 0
    for rf in rfs_lista:
        termos_na_rf = re.findall(r"'([^']+)'", rf)
        if all(t.lower() in termos_validos for t in termos_na_rf):
            aprovadas.append(rf)
        else:
            termos_invalidos = [t for t in termos_na_rf if t.lower() not in termos_validos]
            print(f"  Answerability: descartada '{rf[:60]}' — termos não modeláveis: {termos_invalidos}")
            descartadas += 1

    print(f"Answerability: {len(rfs_lista)} rfs → {len(aprovadas)} aprovadas ({descartadas} descartadas).")
    return aprovadas


# ETAPA 4 — Filtro Semântico por Embeddings
def filter_rfs_by_semantics(texto_base, lista_rfs, api_keys, limiar=0.72, limiar_redundancia=0.92):
    if isinstance(api_keys, str):
        api_keys = [api_keys]
    list_models = ["gemini-embedding-001", "gemini-embedding-2-preview"]

    for actual_model in list_models:
        for trying, actual_key in enumerate(api_keys):
            try:
                client = genai.Client(api_key=actual_key)
                response_base = client.models.embed_content(
                    model=actual_model, contents=texto_base,
                    config=types.EmbedContentConfig(task_type="SEMANTIC_SIMILARITY")
                )
                vetor_base = response_base.embeddings[0].values

                vetores_rfs = []
                # Reduzindo o lote para 20 para não estourar o RPM de 100 tão rápido
                for i in range(0, len(lista_rfs), 20):
                    lote = lista_rfs[i:i + 20]
                    response_lote = client.models.embed_content(
                        model=actual_model, contents=lote,
                        config=types.EmbedContentConfig(task_type="SEMANTIC_SIMILARITY")
                    )
                    vetores_rfs.extend([emb.values for emb in response_lote.embeddings])
                    
                    # Aumentando o tempo de pausa para dar margem à janela de 1 minuto da API
                    time.sleep(3)

                vectors_approved = []
                rfs_filtered = []
                for rf, vetor_rf in zip(lista_rfs, vetores_rfs):
                    score = calculate_similarity(vetor_base, vetor_rf)
                    if score >= limiar:
                        is_redundant = any(
                            calculate_similarity(vetor_rf, v) > limiar_redundancia
                            for v in vectors_approved
                        )
                        if not is_redundant:
                            rfs_filtered.append((rf, score))
                            vectors_approved.append(vetor_rf)

                rfs_filtered.sort(key=lambda x: x[1], reverse=True)
                return rfs_filtered

            except Exception as e:
                mensagem_erro = str(e)
                if "429" in mensagem_erro or "RESOURCE_EXHAUSTED" in mensagem_erro:
                    time.sleep(2)
                    continue
                elif "not found" in mensagem_erro.lower() or "invalid model" in mensagem_erro.lower():
                    break
                else:
                    if trying == len(api_keys) - 1:
                        break

    st.error("Limite Atingido nos Embeddings. Aguarde e tente novamente.")
    return []


# ETAPA 5 — Juiz de Qualidade (LLM-as-Judge)
def judge_questions_with_ai(celulas, rfs_filtradas, api_keys, nota_minima=6.0):
    if not rfs_filtradas:
        return rfs_filtradas
    if isinstance(api_keys, str):
        api_keys = [api_keys]

    perguntas_text = "\n".join(
        f"{i}: {rf}" for i, (rf, _) in enumerate(rfs_filtradas)
    )
    contexto = (
        f"Domínio: {celulas['dominio']}\n"
        f"Dimensão Horizontal: {celulas['horizontal']}\n"
        f"Dimensão Vertical: {celulas['vertical']}"
    )

    prompt = f"""Você é especialista em ontologias formais e metodologia SABiOx.
Avalie cada Competency Question abaixo como rf ontológica para o domínio descrito.

### DOMÍNIO:
{contexto}

### HIERARQUIA DO DOMÍNIO — considere antes de pontuar:
- Entidades PRIMÁRIAS (manipuladas diretamente): perguntas sobre elas têm maior valor ontológico.
- Entidades DERIVADAS (calculadas a partir de primárias): perguntas sobre elas têm valor secundário.
- Perguntas que tratam derivadas como primárias devem receber notas menores.

### CRITÉRIOS (0–10 cada, nota_final = média):
1. Validade ontológica: representa relação real e relevante no domínio?
2. Clareza e naturalidade em português: gramaticalmente correta e compreensível?
3. Utilidade como rf SABiOx: pode guiar a modelagem de forma concreta?

### REFERÊNCIA:
- 9–10: rf sobre entidade primária, clara, revela restrição ou composição real.
- 7–8: rf válida sobre primária com pequena imprecisão, ou sobre derivada bem formulada.
- 5–6: rf sobre derivada tratada como primária, ou trivial demais.
- 1–4: rf sem valor — absurda, agramatical ou fora de contexto.

### PERGUNTAS:
{perguntas_text}

Retorne SOMENTE JSON válido, sem markdown:
{{"avaliacoes": [{{"indice": 0, "nota_final": 8.5, "justificativa": "razão em uma frase"}}]}}"""

    generative_models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
    for model_name in generative_models:
        for trying, api_key in enumerate(api_keys):
            try:
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(model=model_name, contents=prompt)
                raw = re.sub(r"```json|```", "", response.text.strip()).strip()
                resultado = json.loads(raw)
                avaliacoes = {item["indice"]: item for item in resultado.get("avaliacoes", [])}

                rfs_julgadas = []
                for i, (rf, score_emb) in enumerate(rfs_filtradas):
                    av = avaliacoes.get(i, {})
                    nota = float(av.get("nota_final", 5.0))
                    justificativa = av.get("justificativa", "—")
                    if nota >= nota_minima:
                        rfs_julgadas.append((rf, score_emb, nota, justificativa))

                rfs_julgadas.sort(key=lambda x: (x[2], x[1]), reverse=True)
                cortadas = len(rfs_filtradas) - len(rfs_julgadas)
                print(f"Juiz: {len(rfs_filtradas)} avaliadas → {len(rfs_julgadas)} aprovadas ({cortadas} cortadas por nota < {nota_minima}).")
                return rfs_julgadas

            except Exception as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    time.sleep(2)
                    continue
                else:
                    break

    print("Juiz indisponível. Retornando com score semântico sem corte.")
    return [(rf, score, 5.0, "juiz indisponível") for rf, score in rfs_filtradas]