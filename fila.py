"""Fila de tarefas do Mangaba Operator (camada de operação p/ empresas).

Tarefas entram como arquivos em workspace/fila/ e são processadas em série —
o gateway local atende uma inferência por vez, então a fila evita concorrência.
Combine com cron/launchd pra agendamento (ver README).

Uso:
    python fila.py add "Gerar relatório X e salvar em workspace/relatorio.xlsx"
    python fila.py list
    python fila.py run [--max-steps 10] [--model openai/gpt-4.1-mini]
"""

import argparse
import asyncio
import os
import time
from pathlib import Path

from app.agent.mangaba import Mangaba
from app.config import config
from app.gateway import apply_model_override, preload_default_model
from app.logger import logger

FILA = config.workspace_root / "fila"


def _dirs() -> None:
    for sub in ("", "concluidas", "falhas"):
        (FILA / sub).mkdir(parents=True, exist_ok=True)


def add(prompt: str) -> None:
    _dirs()
    nome = f"{int(time.time() * 1000)}.task"
    (FILA / nome).write_text(prompt, encoding="utf-8")
    print(f"➕ Tarefa enfileirada: {nome}")


def listar() -> None:
    _dirs()
    pend = sorted(FILA.glob("*.task"))
    print(f"Pendentes: {len(pend)}")
    for p in pend:
        print(f"  • {p.name}: {p.read_text()[:80]}")
    print(f"Concluídas: {len(list((FILA / 'concluidas').glob('*.task')))} · Falhas: {len(list((FILA / 'falhas').glob('*.task')))}")


async def _escalar(tarefa: str, prompt: str, motivo: str) -> None:
    """HITL: exceção vira notificação pro humano com contexto completo."""
    from app.tool.comms import NotifyWebhook

    msg = (
        f"🚨 Mangaba Operator — tarefa escalada pra revisão humana\n"
        f"Tarefa: {tarefa}\nPedido: {prompt[:300]}\nMotivo: {motivo[:500]}\n"
        f"Arquivos parciais em: {config.workspace_root}"
    )
    r = await NotifyWebhook().execute(message=msg)
    if r.error:
        logger.warning(f"Escalação registrada só em log (webhook indisponível): {r.error[:120]}")


async def run(max_steps: int, model: str | None, verificar: bool = False) -> None:
    _dirs()
    # trava estrutural HITL: em modo autônomo, ações irreversíveis viram rascunho
    os.environ["MANGABA_AUTONOMO"] = "1"
    if model and not await apply_model_override(model):
        return
    (config.workspace_root / "memoria").mkdir(parents=True, exist_ok=True)
    await preload_default_model()

    pendentes = sorted(FILA.glob("*.task"))
    if not pendentes:
        logger.info("Fila vazia.")
        return
    logger.info(f"📥 {len(pendentes)} tarefa(s) na fila")
    for tarefa in pendentes:
        prompt = tarefa.read_text(encoding="utf-8").strip()
        logger.warning(f"▶️  {tarefa.name}: {prompt[:80]}")
        (config.workspace_root / "todo.md").unlink(missing_ok=True)
        try:
            if verificar:
                from app.verificador import executar_com_verificacao

                aprovado, parecer = await executar_com_verificacao(prompt, max_steps=max_steps)
                if not aprovado:
                    tarefa.rename(FILA / "falhas" / tarefa.name)
                    await _escalar(tarefa.name, prompt, f"Reprovada pelo revisor: {parecer}")
                    continue
            else:
                agent = await Mangaba.create(max_steps=max_steps)
                try:
                    await agent.run(prompt)
                finally:
                    await agent.cleanup()
            tarefa.rename(FILA / "concluidas" / tarefa.name)
            logger.info(f"✅ {tarefa.name} concluída")
        except Exception as e:
            logger.error(f"❌ {tarefa.name}: {e}")
            tarefa.rename(FILA / "falhas" / tarefa.name)
            await _escalar(tarefa.name, prompt, f"Erro de execução: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fila de tarefas do Mangaba Operator")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_add = sub.add_parser("add", help="Enfileira uma tarefa")
    p_add.add_argument("prompt")
    sub.add_parser("list", help="Mostra a fila")
    p_run = sub.add_parser("run", help="Processa a fila em série")
    p_run.add_argument("--max-steps", type=int, default=10)
    p_run.add_argument("--model", type=str)
    p_run.add_argument(
        "--verificar", action="store_true",
        help="Revisor valida cada tarefa; reprovadas são escaladas pro humano",
    )
    args = parser.parse_args()

    if args.cmd == "add":
        add(args.prompt)
    elif args.cmd == "list":
        listar()
    else:
        asyncio.run(run(args.max_steps, args.model, args.verificar))


if __name__ == "__main__":
    main()
