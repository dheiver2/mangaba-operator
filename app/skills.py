"""Skills empresariais com progressive disclosure (arquitetura dos plugins Claude).

Cada skill é uma pasta em skills/<nome>/SKILL.md com frontmatter (name,
description) e instruções detalhadas no corpo. Só o CATÁLOGO (1 linha por
skill) entra no system prompt; o agente lê o arquivo completo apenas quando a
tarefa é daquele tipo — conhecimento da empresa sem estourar a janela.
"""

import re
from pathlib import Path

from app.config import PROJECT_ROOT

SKILLS_DIR = Path(PROJECT_ROOT) / "skills"


def _frontmatter(texto: str) -> dict:
    m = re.match(r"\s*---\s*\n(.*?)\n---", texto, re.DOTALL)
    meta = {}
    if m:
        for linha in m.group(1).splitlines():
            if ":" in linha:
                k, v = linha.split(":", 1)
                meta[k.strip()] = v.strip()
    return meta


def catalogo() -> str:
    """Catálogo compacto pro system prompt (nome, quando usar, onde ler)."""
    if not SKILLS_DIR.is_dir():
        return ""
    linhas = []
    for skill_md in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        meta = _frontmatter(skill_md.read_text(encoding="utf-8", errors="replace"))
        nome = meta.get("name", skill_md.parent.name)
        desc = meta.get("description", "")
        linhas.append(f"- {nome}: {desc} -> READ {skill_md} FIRST")
    if not linhas:
        return ""
    return (
        "\nCOMPANY SKILLS: before doing a task that matches one of these, read the "
        "skill file with str_replace_editor (command view) and follow its instructions exactly:\n"
        + "\n".join(linhas)
    )
