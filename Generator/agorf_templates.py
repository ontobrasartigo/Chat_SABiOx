# agorf_templates.py — Geração de Competency Questions por templates
# Cenário A: ator → ação → entidade primária
# Cenário C: entidade → composição → componente
# Cenário D: ator → ação → entidade DERIVADA (faturamento, popularidade, etc.)
#
# Fontes:
#   SABiOx (2024) — REQ-ELIC, EVA-MODE
#   Keet & Khan (2024) — SCQ, VCQ, FCQ, RCQ, MpCQ
#   Grüninger & Fox (1995) — CQs de existência e caso-limite
#   CLaRO / AgOCQs (Antia & Keet 2019–2023) — padrões léxico-sintáticos

from .agorf_utils import conjugar_passado, participio_passado, detectar_genero


def generate_rfs_from_pairs(pairs, analise=None):
    """
    Aplica templates nos pares aprovados e retorna lista de CQs (strings).

    Cenário A — entidade primária: 9 templates (SCQ, VCQ, MpCQ, RCQ + estruturais)
    Cenário C — composição: 9 templates (FCQ, MpCQ, VCQ, RCQ, SCQ + estruturais)
    Cenário D — derivada: templates de dependência, enumeração, comparação,
                limiar, ausência + templates por dimensão de análise
    """
    if analise is None:
        analise = {}

    rfs_totals = set()

    # Lookup: nome_derivado → [{dimensao, primaria}]
    derivadas_lookup = {}
    for d in analise.get("derivadas_detalhadas", []):
        nome = d.get("nome", "").lower().strip()
        if nome:
            derivadas_lookup[nome] = d.get("dimensoes", [])

    nomes_derivadas = {d.lower().strip() for d in analise.get("derivadas", [])}
    nomes_derivadas.update(derivadas_lookup.keys())

    for p in pairs:
        cenario = p["cenario"]

        # ── CENÁRIO A / D ──────────────────────────────────────────────
        if cenario == "A":
            suj   = p["suj"]
            verb  = p["verb"]
            obj   = p["obj"]
            art_suj = "uma" if p.get("suj_gen") == "Fem" else "um"
            art_obj = "uma" if p.get("obj_gen") == "Fem" else "um"
            vpp   = conjugar_passado(verb)
            vpart = participio_passado(verb)

            obj_base = obj.split()[0].lower()
            if obj_base in nomes_derivadas or obj.lower() in nomes_derivadas:
                # ── CENÁRIO D — derivado ──
                dimensoes = derivadas_lookup.get(obj.lower(), derivadas_lookup.get(obj_base, []))

                # VCQ — dependência (Grüninger & Fox 1995)
                rfs_totals.add(f"Quais informações são necessárias para calcular '{obj}'?")
                rfs_totals.add(f"'{obj}' pode ser calculado sem {art_suj} '{suj}'?")

                # SCQ — enumeração (SABiOx EVA-MODE)
                rfs_totals.add(f"Que tipos de '{obj}' {art_suj} '{suj}' pode {verb}?")
                rfs_totals.add(f"Quais '{obj}' {art_suj} '{suj}' consegue {verb}?")

                # MpCQ — rigidez (Keet & Khan 2024)
                rfs_totals.add(f"Todo '{obj}' é necessariamente derivado de {art_suj} '{suj}'?")

                # RCQ — analítico por ator (Keet & Khan 2024)
                rfs_totals.add(f"Qual '{suj}' {vpp} mais '{obj}' em um período?")

                # ── Templates universais ──
                # Comparação — clínica, biblioteca, escola, RH
                rfs_totals.add(f"É possível comparar '{obj}' entre diferentes '{suj}'?")

                # Limiar / valor crítico — hospital, escola, e-commerce, RH
                rfs_totals.add(f"Existe um valor mínimo de '{obj}' abaixo do qual {art_suj} '{suj}' precisa agir?")

                # Ausência — testa existência mínima em qualquer domínio
                rfs_totals.add(f"É possível que {art_suj} '{suj}' tenha '{obj}' igual a zero?")

                # Templates por dimensão de análise
                for dim in dimensoes:
                    dim_nome = dim.get("dimensao", "")
                    dim_prim = dim.get("primaria", "")
                    art_prim = "uma" if detectar_genero(dim_prim) == "Fem" else "um"
                    if dim_nome and dim_prim:
                        rfs_totals.add(f"Que tipos de '{obj}' é possível calcular a partir de {art_prim} '{dim_prim}'?")
                        rfs_totals.add(f"Quais '{dim_prim}' compõem o cálculo de '{obj} {dim_nome}'?")
                        # Ranking por dimensão — clínica, biblioteca, e-commerce
                        rfs_totals.add(f"Qual '{dim_prim}' tem o maior '{obj}' no domínio?")

            else:
                # ── CENÁRIO A padrão — entidade primária ──

                # Estruturais originais
                rfs_totals.add(f"Quais '{suj}' podem {verb} {art_obj} '{obj}'?")
                rfs_totals.add(f"Que tipos de '{obj}' {art_suj} '{suj}' pode {verb}?")
                rfs_totals.add(f"{art_suj.capitalize()} '{suj}' pode {verb} múltiplos '{obj}'?")
                rfs_totals.add(f"{art_suj.capitalize()} '{suj}' deve obrigatoriamente {verb} {art_obj} '{obj}'?")
                rfs_totals.add(f"Todo '{suj}' pode {verb} qualquer '{obj}'?")

                # VCQ — existência (Grüninger & Fox 1995)
                rfs_totals.add(f"Existe {art_suj} '{suj}' que {verb} mais de {art_obj} '{obj}'?")

                # MpCQ — rigidez (Keet & Khan 2024)
                rfs_totals.add(f"É necessariamente verdade que todo '{suj}' {verb} {art_obj} '{obj}'?")

                # RCQ — propriedade da relação (Keet & Khan 2024 + CLaRO)
                rfs_totals.add(f"Se {art_suj} '{suj}' {vpp} {art_obj} '{obj}', esse '{obj}' pode ser {vpart} por outro '{suj}'?")

                # SCQ — enumeração completa (SABiOx REQ-ELIC + CLaRO)
                rfs_totals.add(f"Quais são todos os '{suj}' que podem {verb} {art_obj} '{obj}' no domínio?")

                # Analítico
                rfs_totals.add(f"Qual '{suj}' {vpp} mais '{obj}' em um período?")

        # ── CENÁRIO C ──────────────────────────────────────────────────
        elif cenario == "C":
            token_lema = p["token"]
            lema_child = p["child"]
            art_token = "uma" if p.get("token_gen") == "Fem" else "um"
            art_child = "uma" if p.get("child_gen") == "Fem" else "um"

            # Estruturais originais
            rfs_totals.add(f"{art_token.capitalize()} '{token_lema}' pode existir sem {art_child} '{lema_child}'?")
            rfs_totals.add(f"A qual '{token_lema}' {art_child} '{lema_child}' pertence?")
            rfs_totals.add(f"{art_child.capitalize()} '{lema_child}' pode fazer parte de mais de {art_token} '{token_lema}'?")
            rfs_totals.add(f"Quantos '{lema_child}' {art_token} '{token_lema}' pode ter?")

            # SCQ — listagem natural (CLaRO "What are the EC1 of EC2?")
            rfs_totals.add(f"Quais são os '{lema_child}' de {art_token} '{token_lema}'?")

            # FCQ — hierarquia/taxonomia (Keet & Khan 2024 + CLaRO "Is EC1 a type of EC2?")
            rfs_totals.add(f"'{lema_child}' é um tipo de '{token_lema}'?")

            # MpCQ — necessidade de existência (Keet & Khan 2024 + SABiOx EVA-MODE)
            rfs_totals.add(f"Todo '{token_lema}' possui necessariamente {art_child} '{lema_child}'?")

            # VCQ — existência do atributo (CLaRO "Does EC1 have EC2?" + Grüninger & Fox)
            rfs_totals.add(f"{art_token.capitalize()} '{token_lema}' sempre tem {art_child} '{lema_child}' associado?")

            # RCQ — exclusividade/funcionalidade (CLaRO + SABiOx axiomas)
            rfs_totals.add(f"{art_child.capitalize()} '{lema_child}' pode pertencer a exatamente {art_token} '{token_lema}'?")

    rfs_lista = list(rfs_totals)
    if len(rfs_lista) > 100:
        rfs_lista = rfs_lista[:100]
    return rfs_lista
