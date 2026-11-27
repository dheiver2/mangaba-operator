"""Leitura direta de PDFs (texto e tabelas) com cache reversível."""

from pathlib import Path

from app.config import config
from app.tool.base import BaseTool, ToolResult
from app.tool.gateway_media import _resolve

_PREVIEW = 5000


class ReadPdf(BaseTool):
    name: str = "read_pdf"
    description: str = (
        "Extracts text (and detects tables) from a local PDF file — contracts, "
        "invoices, reports. Faster and more reliable than opening the PDF by "
        "other means. The full text is saved to workspace/cache/."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "pdf_path": {
                "type": "string",
                "description": "Path to the PDF; relative paths resolve against the workspace",
            },
            "pages": {
                "type": "string",
                "description": "Optional page range, e.g. '1-3' or '2' (default: all)",
            },
        },
        "required": ["pdf_path"],
    }

    async def execute(self, pdf_path: str, pages: str = "", **kwargs) -> ToolResult:
        import pdfplumber

        path = _resolve(pdf_path)
        if not path.is_file():
            return ToolResult(error=f"PDF not found: {path}")

        try:
            with pdfplumber.open(path) as pdf:
                total = len(pdf.pages)
                if pages:
                    parts = pages.split("-")
                    start = max(1, int(parts[0]))
                    end = min(total, int(parts[-1]))
                else:
                    start, end = 1, total
                chunks, n_tables = [], 0
                for i in range(start - 1, end):
                    page = pdf.pages[i]
                    chunks.append(f"--- Page {i + 1} ---\n{page.extract_text() or '(no extractable text)'}")
                    for tb in page.extract_tables():
                        n_tables += 1
                        linhas = ["\t".join(str(c) if c is not None else "" for c in row) for row in tb]
                        chunks.append(f"[Table {n_tables} on page {i + 1}]\n" + "\n".join(linhas))
        except Exception as e:
            return ToolResult(error=f"Failed to read PDF: {e}")

        text = "\n\n".join(chunks).strip()
        cache_dir = config.workspace_root / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        saved = cache_dir / f"pdf-{path.stem}.txt"
        saved.write_text(text, encoding="utf-8")

        header = (
            f"PDF {path.name}: {total} page(s), read {start}-{end}, "
            f"{n_tables} table(s). Full text saved to {saved}.\n\n"
        )
        if len(text) > _PREVIEW:
            return ToolResult(output=header + text[:_PREVIEW] + "\n[...rest in the cache file...]")
        return ToolResult(output=header + text)
