"""Fetch rápido de páginas web sem navegador.

Para páginas estáticas substitui o par go_to_url + extract_content do
browser_use: uma única ação, sem Chromium e sem chamada extra de LLM.
"""

import hashlib
import re

import httpx
import markdownify

from app.config import config
from app.tool.base import BaseTool, ToolResult

# Janela do gateway é 8192 tokens; preview precisa deixar espaço pro histórico
_MAX_CHARS = 6000

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
}


class FetchUrl(BaseTool):
    name: str = "fetch_url"
    description: str = (
        "Downloads a web page and returns its content as markdown. FAST: use this "
        "tool to read static pages (news, documentation, articles) instead of "
        "browser_use. Use browser_use only when you need to interact with the page "
        "(click, fill a form, log in) or when fetch_url fails."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Full page URL (http/https)",
            },
            "max_chars": {
                "type": "integer",
                "description": f"Character limit for the result (default {_MAX_CHARS})",
            },
        },
        "required": ["url"],
    }

    async def execute(self, url: str, max_chars: int = _MAX_CHARS, **kwargs) -> ToolResult:
        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=30, headers=_HEADERS
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            return ToolResult(
                error=f"HTTP {e.response.status_code} fetching {url}"
            )
        except Exception as e:
            return ToolResult(error=f"Failed to fetch {url}: {e}")

        content_type = resp.headers.get("content-type", "")
        if "html" in content_type:
            text = markdownify.markdownify(resp.text, strip=["script", "style"])
        else:
            text = resp.text

        text = text.strip()
        max_chars = int(max_chars) if max_chars else _MAX_CHARS
        if len(text) <= max_chars:
            return ToolResult(output=f"Content of {url}:\n\n{text}")

        # Compressão reversível (context engineering): o conteúdo completo sai
        # do contexto mas fica recuperável em arquivo — nada é perdido.
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", url.split("//", 1)[-1]).strip("-")[:60]
        digest = hashlib.md5(url.encode()).hexdigest()[:8]
        cache_dir = config.workspace_root / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        full_path = cache_dir / f"{slug}-{digest}.md"
        full_path.write_text(text, encoding="utf-8")

        preview = text[:max_chars]
        return ToolResult(
            output=(
                f"Content of {url} (showing {max_chars} of {len(text)} characters):\n\n"
                f"{preview}\n\n"
                f"[FULL CONTENT saved to {full_path} — if you need the rest, "
                f"read that file with str_replace_editor (command view) or python_execute]"
            )
        )
