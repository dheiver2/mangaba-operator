"""Auto-agendamento: o agente enfileira tarefas futuras na fila do Operator.

Não importa fila.py (que importa o agente — ciclo); replica o formato
de arquivo .task que `fila.py run` consome (cron a cada hora).
"""

import time

from app.config import config
from app.tool.base import BaseTool, ToolResult

_FILA = config.workspace_root / "fila"


class ScheduleTask(BaseTool):
    name: str = "schedule_task"
    description: str = (
        "Schedules a task for later by adding it to the Operator queue "
        "(processed by the `fila.py run` cron). Use when the request has a part "
        "that should run later or repeatedly (follow-up, monitoring, recurring "
        "report). Actions: add (queues 'prompt') and list (shows the queue)."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "list"],
                "description": "add: queue a task; list: show queue status",
            },
            "prompt": {
                "type": "string",
                "description": "Complete, self-contained instruction for the future task (for 'add')",
            },
        },
        "required": ["action"],
    }

    async def execute(self, action: str, prompt: str = "", **kwargs) -> ToolResult:
        for sub in ("", "concluidas", "falhas"):
            (_FILA / sub).mkdir(parents=True, exist_ok=True)

        if action == "add":
            if not prompt.strip():
                return ToolResult(error="'add' requires a non-empty 'prompt'")
            nome = f"{int(time.time() * 1000)}.task"
            (_FILA / nome).write_text(prompt.strip(), encoding="utf-8")
            return ToolResult(
                output=(
                    f"Task queued as {nome}. It will run on the next "
                    "pass of the queue processor (fila.py run)."
                )
            )

        if action == "list":
            pend = sorted(_FILA.glob("*.task"))
            done = len(list((_FILA / "concluidas").glob("*.task")))
            fail = len(list((_FILA / "falhas").glob("*.task")))
            lines = [
                f"  • {p.name}: {p.read_text(encoding='utf-8')[:80]}" for p in pend[:20]
            ]
            body = "\n".join(lines) if lines else "  (empty)"
            return ToolResult(
                output=f"Pending: {len(pend)}\n{body}\nCompleted: {done} · Failed: {fail}"
            )

        return ToolResult(error=f"Unknown action: {action}")
