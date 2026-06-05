# hybrid_extractor.py - Extração híbrida de requisitos
# Combina regex e IA pra extrair dados do relatório SABiOx.

from __future__ import annotations

import re
from typing import Dict, List, Any, Optional


def extract_section(text: str, section_header: str) -> Optional[str]:
    """Extrai uma seção específica do texto, tipo 'Purpose' ou 'Domain'."""
    pattern = rf"(?:###\s*)?\d+\)\s*.*?{re.escape(section_header)}.*?\n(.*?)(?=(?:###\s*)?\d+\)|$)"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else None
    pattern = rf"(?:###\s*)?\d+\)\s*.*?{re.escape(section_header)}.*?\n(.*?)(?=(?:###\s*)?\d+\)|$)"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else None


def parse_bullet_list(text: str) -> List[str]:
    """Extrai itens de lista com bullets, ou separa por vírgula se for corrido."""
    lines = text.split("\n")
    lines = text.split("\n")
    items: List[str] = []
    
    for line in lines:
        line = line.strip()
        if line.startswith("-") or line.startswith("•") or line.startswith("*"):
            item = re.sub(r"^[-•*]\s*", "", line).strip()
            if item:
                items.append(item)
                
    
    if not items and text.strip():
        return [x.strip() for x in re.split(r"[;,]", text) if x.strip()]
        
    return items


def extract_requirements_rule_based(report_text: str) -> Dict[str, Any]:
    """Extrai requisitos do relatório usando regex, sem IA."""
    result = {
        "project": {"name": "", "version": "v.01"},
        "requirements": {
            "purpose": {"what": "", "what_for": "", "why": ""},
            "domain": {"description": "", "horizontal": "", "vertical": ""},
            "subdomains": [],
            "non_functional_requirements": []
        }
    }

    # Projeto
    name_m = re.search(r"Projeto:\s*([^\n\r]*)", report_text, re.IGNORECASE)
    if name_m: 
        result["project"]["name"] = name_m.group(1).strip()

    # Propósito
    purp_text = extract_section(report_text, "Purpose")
    if purp_text:
        w = re.search(r"representar\s+(.*?)(?:,\s*para que|para que)", purp_text, re.I | re.S)
        f = re.search(r"para que\s+(.*?)(?:,\s*porque|porque)", purp_text, re.I | re.S)
        y = re.search(r"porque\s+(.*)", purp_text, re.I | re.S)
        result["requirements"]["purpose"]["what"] = w.group(1).strip() if w else ""
        result["requirements"]["purpose"]["what_for"] = f.group(1).strip() if f else ""
        result["requirements"]["purpose"]["why"] = y.group(1).strip() if y else ""

    # Domínio e dimensões
    dom_text = extract_section(report_text, "Domain")
    if dom_text: 
        d_match = re.search(r"Dom[ií]nio:\s*([^\n\r]*)", dom_text, re.IGNORECASE)
        if d_match:
            result["requirements"]["domain"]["description"] = d_match.group(1).strip()
        else:
            result["requirements"]["domain"]["description"] = dom_text
    
    dim_text = extract_section(report_text, "Dimension")
    if dim_text:
        h = re.search(r"Dimensão Horizontal:\s*([^\n\r]*)", dim_text, re.IGNORECASE)
        v = re.search(r"Dimensão Vertical:\s*([^\n\r]*)", dim_text, re.IGNORECASE)
        result["requirements"]["domain"]["horizontal"] = h.group(1).strip() if h else ""
        result["requirements"]["domain"]["vertical"] = v.group(1).strip() if v else ""

    # Elicitação e subdomínios
    elic_text = extract_section(report_text, "Elicitation")
    if elic_text:
        parts = re.split(r"Subdom[ií]nio:\s*", elic_text, flags=re.I)
        for part in parts:
            if not part.strip(): continue
            lines = part.strip().split('\n')
            sub_name = lines[0].strip()
            rf_list = [{"id": m.group(1), "question": m.group(2).strip()} 
                       for line in lines if (m := re.search(r"(RF\d+):\s*(.*)", line))]
            if rf_list:
                result["requirements"]["subdomains"].append({"name": sub_name, "requirements": rf_list})

        # Requisitos não funcionais
        rnf_matches = re.finditer(r"(RNF\d+):\s*(.*)", elic_text)
        for m in rnf_matches:
            result["requirements"]["non_functional_requirements"].append({
                "id": m.group(1), "description": m.group(2).strip()
            })

    return result


def should_use_ai_fallback(rule_based_result: Dict[str, Any]) -> bool:
    """Decide se precisa de IA pra complementar a extração."""
    if not isinstance(rule_based_result, dict):
        return True

    req = rule_based_result.get("requirements", {})
    if not isinstance(req, dict):
        return True

    purpose = req.get("purpose", {})
    subdomains = req.get("subdomains", [])
    domain = req.get("domain", {})

    empty_checks = [
        not str(purpose.get("what", "") or "").strip(),
        len(subdomains) == 0,
        not str(domain.get("description", "") or "").strip(),
    ]

    necessita_fallback = sum(bool(x) for x in empty_checks) > 1

    if necessita_fallback:
        print("\n[DEBUG]  FALLBACK ACIONADO: Mais de uma seção crítica está vazia no Regex.")
    else:
        print("\n[DEBUG] SUCESSO: Regex capturou as seções principais.")

    return necessita_fallback