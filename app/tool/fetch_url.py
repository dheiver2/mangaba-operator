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

_MAX_CHARS = 12000

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
}


class FetchUrl(BaseTool):
    name: str = "fetch_url"
    description: str = (
        "Baixa uma página web e retorna o conteúdo como markdown. RÁPIDO: use esta "
        "ferramenta para ler páginas estáticas (notícias, documentação, artigos) em vez "
        "do browser_use. Use browser_use apenas quando precisar interagir com a página "
        "(clicar, preencher formulário, login) ou quando fetch_url falhar."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL completa da página (http/https)",
            },
            "max_chars": {
                "type": "integer",
                "description": f"Limite de caracteres do resultado (padrão {_MAX_CHARS})",
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
                error=f"HTTP {e.response.status_code} ao buscar {url}"
            )
        except Exception as e:
            return ToolResult(error=f"Falha ao buscar {url}: {e}")

        content_type = resp.headers.get("content-type", "")
        if "html" in content_type:
            text = markdownify.markdownify(resp.text, strip=["script", "style"])
        else:
            text = resp.text

        text = text.strip()
        max_chars = int(max_chars) if max_chars else _MAX_CHARS
        if len(text) <= max_chars:
            return ToolResult(output=f"Conteúdo de {url}:\n\n{text}")

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
                f"Conteúdo de {url} (mostrando {max_chars} de {len(text)} caracteres):\n\n"
                f"{preview}\n\n"
                f"[CONTEÚDO COMPLETO salvo em {full_path} — se precisar do restante, "
                f"leia esse arquivo com str_replace_editor (command view) ou python_execute]"
            )
        )
