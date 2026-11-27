"""Síntese de voz local (macOS `say`) — voz para relatórios e avisos."""

import asyncio
import shutil
import time

from app.config import config
from app.tool.base import BaseTool, ToolResult


class TextToSpeech(BaseTool):
    name: str = "text_to_speech"
    description: str = (
        "Converts text to spoken audio (local macOS speech synthesis) and saves an "
        ".aiff file in the workspace — good for audible summaries and spoken notifications. "
        "PT-BR voices: 'Luciana' (default) and 'Joana'."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Text to speak (up to ~2000 chars)"},
            "voice": {
                "type": "string",
                "description": "System voice (default: Luciana, PT-BR)",
            },
            "play": {
                "type": "boolean",
                "description": "true: also play the audio through the speakers (default false)",
            },
        },
        "required": ["text"],
    }

    async def execute(
        self, text: str, voice: str = "Luciana", play: bool = False, **kwargs
    ) -> ToolResult:
        if not shutil.which("say"):
            return ToolResult(
                error="'say' command unavailable (speech synthesis requires macOS)"
            )
        text = text.strip()
        if not text:
            return ToolResult(error="Empty text")
        text = text[:2000]

        dest = config.workspace_root / f"fala_{time.strftime('%Y%m%d_%H%M%S')}.aiff"
        dest.parent.mkdir(parents=True, exist_ok=True)
        proc = await asyncio.create_subprocess_exec(
            "say", "-v", voice, "-o", str(dest), text,
            stderr=asyncio.subprocess.PIPE,
        )
        _, err = await proc.communicate()
        if proc.returncode != 0:
            return ToolResult(
                error=f"say failed (does voice '{voice}' exist?): {err.decode()[:200]}"
            )

        if play:
            await asyncio.create_subprocess_exec("afplay", str(dest))

        size = dest.stat().st_size
        return ToolResult(
            output=f"Audio generated ({size} bytes, voice {voice}): {dest}"
            + (" — playing now" if play else "")
        )
