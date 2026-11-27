"""Modo pipeline do Mangaba Operator: tarefas grandes em fases com contexto limpo.

Estratégia pra janela de contexto pequena (8k no gateway): em vez de uma
execução monolítica que estoura o histórico, a tarefa é dividida em fases
sequenciais — cada fase roda num AGENTE NOVO (contexto zerado) e os resultados
passam de uma fase pra outra pelos ARQUIVOS do workspace, não pelo histórico.

Uso:
    python pipeline.py --prompt "large task"
    python pipeline.py --prompt "..." --max-steps 6     # passos por fase
    python pipeline.py --prompt "..." --fases "transcribe audio X; search the web for context; generate briefing.md"
"""

import argparse
import asyncio
import json
import re

from app.agent.mangaba import Mangaba
from app.config import config
from app.gateway import apply_model_override, preload_default_model
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
    logger.warning("Plan did not come back as JSON; running as a single phase")
    return [task]


async def executar_fase(task: str, fase: str, i: int, total: int, max_steps: int) -> None:
    prompt = (
        f"You are running phase {i}/{total} of a larger task.\n"
        f"GLOBAL TASK (context): {task}\n\n"
        f"SUA FASE (execute SOMENTE isto): {fase}\n\n"
        f"Files already available in the workspace: {_listar_workspace()}\n"
        "Leia os arquivos que precisar, salve seu resultado no workspace e chame "
        "call terminate as soon as THIS phase is complete. Do not run the other phases."
    )
    agent = await Mangaba.create(max_steps=max_steps)
    try:
        await agent.run(prompt)
    finally:
        await agent.cleanup()


async def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline de fases do Mangaba Operator")
    parser.add_argument("--prompt", type=str, required=True, help="Full task")
    parser.add_argument("--max-steps", type=int, default=8, help="Steps per phase (default 8)")
    parser.add_argument(
        "--fases", type=str, help="Fases manuais separadas por ';' (pula o planejamento)"
    )
    parser.add_argument(
        "--model", type=str, help="Override do modelo (mangaba-* ou GitHub Models, ex. openai/gpt-4.1-mini)"
    )
    args = parser.parse_args()

    if args.model and not await apply_model_override(args.model):
        return

    (config.workspace_root / "memoria").mkdir(parents=True, exist_ok=True)
    (config.workspace_root / "todo.md").unlink(missing_ok=True)
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

    logger.info(f"✅ Pipeline completed. Workspace: {_listar_workspace()}")


if __name__ == "__main__":
    asyncio.run(main())
