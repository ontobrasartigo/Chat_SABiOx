# sabiox_schema.py - Schema e validação do SABiOx
# Define a estrutura dos dados e valida se tá tudo certo.

from __future__ import annotations
from typing import Any, Dict, List, Tuple

def _as_str(x: Any) -> str:
    if x is None: return ""
    return str(x).strip()

def empty_payload() -> Dict[str, Any]:
    """Retorna a estrutura vazia do SABiOx."""
    return {
        "project": {"name": "", "version": "v.01"},
        "requirements": {
            "purpose": {"what": "", "what_for": "", "why": ""},
            "domain": {"description": "", "horizontal": "", "vertical": ""},
            "subdomains": [], # As RFs/CQs ficam aqui dentro!
            "non_functional_requirements": []
        }
    }

def sanitize_requirements(data: Any) -> Dict[str, Any]:
    """Limpa e padroniza o JSON dos requisitos."""
    out = empty_payload()
    if not isinstance(data, dict): return out

    # Projeto
    src_proj = data.get("project", {})
    if isinstance(src_proj, dict):
        out["project"]["name"] = _as_str(src_proj.get("name"))
        out["project"]["version"] = _as_str(src_proj.get("version", "v.01"))

    src_req = data.get("requirements", {})
    if not isinstance(src_req, dict): return out

    # Purpose
    src_purp = src_req.get("purpose", {})
    if isinstance(src_purp, dict):
        for k in ["what", "what_for", "why"]:
            out["requirements"]["purpose"][k] = _as_str(src_purp.get(k))

    # Domain
    src_dom = src_req.get("domain", {})
    if isinstance(src_dom, dict):
        out["requirements"]["domain"]["description"] = _as_str(src_dom.get("description"))
        out["requirements"]["domain"]["horizontal"] = _as_str(src_dom.get("horizontal"))
        out["requirements"]["domain"]["vertical"] = _as_str(src_dom.get("vertical"))

    # Subdomínios e suas RFs
    src_sub = src_req.get("subdomains", [])
    if isinstance(src_sub, list):
        for sub in src_sub:
            if isinstance(sub, dict):
                clean_sub = {
                    "name": _as_str(sub.get("name")),
                    "requirements": []
                }
                # Pega as RFs que o regex ou a IA colocou no subdomínio
                reqs = sub.get("requirements", [])
                if isinstance(reqs, list):
                    for r in reqs:
                        if isinstance(r, dict):
                            clean_sub["requirements"].append({
                                "id": _as_str(r.get("id")),
                                "question": _as_str(r.get("question"))
                            })
                out["requirements"]["subdomains"].append(clean_sub)

    # Não funcionais
    src_rnf = src_req.get("non_functional_requirements", [])
    if isinstance(src_rnf, list):
        for rnf in src_rnf:
            if isinstance(rnf, dict):
                out["requirements"]["non_functional_requirements"].append({
                    "id": _as_str(rnf.get("id")),
                    "description": _as_str(rnf.get("description"))
                })

    return out

def validate_requirements(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Valida se os campos obrigatórios foram preenchidos."""
    errs: List[str] = []
    req = data.get("requirements", {})
    
    # Valida Purpose
    purp = req.get("purpose", {})
    if not purp.get("what"): errs.append("Propósito: campo 'O que' está vazio.")
    
    # Valida Subdomínios e RFs
    subs = req.get("subdomains", [])
    if not subs:
        errs.append("Elicitação: nenhum subdomínio ou RF foi identificado.")
    else:
        for s in subs:
            if not s.get("requirements"):
                errs.append(f"Subdomínio '{s.get('name')}': não possui RFs listadas.")

    return (len(errs) == 0, errs)