"""Modo pipeline do Mangaba Operator: tarefas grandes em fases com contexto limpo.

Estratégia pra janela de contexto pequena (8k no gateway): em vez de uma
execução monolítica que estoura o histórico, a tarefa é dividida em fases
sequenciais — cada fase roda num AGENTE NOVO (contexto zerado) e os resultados
passam de uma fase pra outra pelos ARQUIVOS do workspace, não pelo histórico.

Uso:
    python pipeline.py --prompt "tarefa grande"
    python pipeline.py --prompt "..." --max-steps 6     # passos por fase
    python pipeline.py --prompt "..." --fases "transcrever o áudio X; buscar contexto na web; gerar briefing.md"
"""

import argparse
import asyncio
import json
import re

from app.agent.mangaba import Mangaba
from app.config import config
from app.gateway import preload_default_model
from app.llm import LLM
from app.logger import logger
from app.schema import Message

PLAN_PROMPT = """Divida a tarefa abaixo em 2 a 5 fases sequenciais e autocontidas.
Cada fase deve: caber em poucos passos, produzir resultado em arquivo no workspace
quando relevante, e poder ser executada sem ver o histórico das anteriores
(apenas os arquivos que elas deixaram).
Responda SOMENTE um array JSON de strings, ex.: ["fase 1...", "fase 2..."].

TAREFA: {task}"""


def _listar_workspace() -> str:
    itens = []
    for p in sorted(config.workspace_root.rglob("*")):
        if p.is_file() and ".gitkeep" not in p.name:
            itens.append(str(p.relative_to(config.workspace_root)))
    return ", ".join(itens[:40]) or "(vazio)"


async def planejar(task: str) -> list[str]:
    llm = LLM()
    resposta = await llm.ask(
        [Message.user_message(PLAN_PROMPT.format(task=task))], stream=False
    )
    match = re.search(r"\[.*\]", resposta, re.DOTALL)
    if match:
        try:
            fases = json.loads(match.group(0))
            if isinstance(fases, list) and all(isinstance(f, str) for f in fases):
                return fases[:5]
        except json.JSONDecodeError:
            pass
    logger.warning("Plano não veio em JSON; executando como fase única")
    return [task]


async def executar_fase(task: str, fase: str, i: int, total: int, max_steps: int) -> None:
    prompt = (
        f"Você está executando a fase {i}/{total} de uma tarefa maior.\n"
        f"TAREFA GLOBAL (contexto): {task}\n\n"
        f"SUA FASE (execute SOMENTE isto): {fase}\n\n"
        f"Arquivos já disponíveis no workspace: {_listar_workspace()}\n"
        "Leia os arquivos que precisar, salve seu resultado no workspace e chame "
        "terminate assim que ESTA fase estiver concluída. Não execute as outras fases."
    )
    agent = await Mangaba.create(max_steps=max_steps)
    try:
        await agent.run(prompt)
    finally:
        await agent.cleanup()


async def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline de fases do Mangaba Operator")
    parser.add_argument("--prompt", type=str, required=True, help="Tarefa completa")
    parser.add_argument("--max-steps", type=int, default=8, help="Passos por fase (padrão 8)")
    parser.add_argument(
        "--fases", type=str, help="Fases manuais separadas por ';' (pula o planejamento)"
    )
    args = parser.parse_args()

    (config.workspace_root / "memoria").mkdir(parents=True, exist_ok=True)
    await preload_default_model()

    if args.fases:
        fases = [f.strip() for f in args.fases.split(";") if f.strip()]
    else:
        logger.info("🧭 Planejando fases...")
        fases = await planejar(args.prompt)

    logger.info(f"📋 Pipeline com {len(fases)} fase(s):")
    for i, f in enumerate(fases, 1):
        logger.info(f"   {i}. {f}")

    for i, fase in enumerate(fases, 1):
        logger.warning(f"▶️  Fase {i}/{len(fases)}: {fase}")
        await executar_fase(args.prompt, fase, i, len(fases), args.max_steps)

    logger.info(f"✅ Pipeline concluído. Workspace: {_listar_workspace()}")


if __name__ == "__main__":
    asyncio.run(main())
