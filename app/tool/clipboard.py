"""Área de transferência do sistema (pbcopy/pbpaste) — ponte com apps do usuário."""

import asyncio
import shutil

from app.tool.base import BaseTool, ToolResult

_PREVIEW = 3000


class Clipboard(BaseTool):
    name: str = "clipboard"
    description: str = (
        "Reads (paste) or writes (copy) the system clipboard — a quick way to "
        "exchange text with the user's open apps (paste into a field, "
        "receive something the user copied)."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["copy", "paste"],
                "description": "copy: put 'text' on the clipboard; paste: return the current contents",
            },
            "text": {"type": "string", "description": "Text to copy (for 'copy')"},
        },
        "required": ["action"],
    }

    async def execute(self, action: str, text: str = "", **kwargs) -> ToolResult:
        if not shutil.which("pbcopy"):
            return ToolResult(error="pbcopy/pbpaste unavailable (requires macOS)")

        if action == "copy":
            if not text:
                return ToolResult(error="'copy' requires 'text'")
            proc = await asyncio.create_subprocess_exec(
                "pbcopy", stdin=asyncio.subprocess.PIPE
            )
            await proc.communicate(text.encode("utf-8"))
            return ToolResult(output=f"Copied {len(text)} characters to the clipboard")

        if action == "paste":
            proc = await asyncio.create_subprocess_exec(
                "pbpaste", stdout=asyncio.subprocess.PIPE
            )
            out, _ = await proc.communicate()
            content = out.decode("utf-8", errors="replace")
            if not content:
                return ToolResult(output="Clipboard is empty")
            preview = content[:_PREVIEW] + (
                "… (truncated)" if len(content) > _PREVIEW else ""
            )
            return ToolResult(output=f"Clipboard ({len(content)} chars):\n{preview}")

        return ToolResult(error=f"Unknown action: {action}")
