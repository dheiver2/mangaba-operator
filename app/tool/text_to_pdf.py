"""Geração de PDF a partir de texto/markdown leve (reportlab)."""

import time

from app.config import config
from app.tool.base import BaseTool, ToolResult
from app.tool.gateway_media import _resolve


class TextToPdf(BaseTool):
    name: str = "text_to_pdf"
    description: str = (
        "Generates a formatted PDF from plain text or light markdown "
        "(headings with #, ## and lists with -). Ideal for delivering reports and "
        "summaries as a file. For complex layouts use python_execute with "
        "reportlab directly."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Document content"},
            "title": {"type": "string", "description": "Cover title (optional)"},
            "dest": {
                "type": "string",
                "description": "Output .pdf file (default: relatorio_<timestamp>.pdf in the workspace)",
            },
        },
        "required": ["text"],
    }

    async def execute(
        self, text: str, title: str = "", dest: str = "", **kwargs
    ) -> ToolResult:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

        if not text.strip():
            return ToolResult(error="Empty text")

        out = (
            _resolve(dest)
            if dest
            else config.workspace_root / f"relatorio_{time.strftime('%Y%m%d_%H%M%S')}.pdf"
        )
        out.parent.mkdir(parents=True, exist_ok=True)

        styles = getSampleStyleSheet()
        story = []
        if title:
            story += [Paragraph(title, styles["Title"]), Spacer(1, 0.5 * cm)]

        def _esc(s: str) -> str:
            return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        for raw in text.splitlines():
            line = raw.rstrip()
            if not line.strip():
                story.append(Spacer(1, 0.25 * cm))
            elif line.startswith("## "):
                story.append(Paragraph(_esc(line[3:]), styles["Heading2"]))
            elif line.startswith("# "):
                story.append(Paragraph(_esc(line[2:]), styles["Heading1"]))
            elif line.lstrip().startswith(("- ", "* ")):
                story.append(
                    Paragraph("• " + _esc(line.lstrip()[2:]), styles["Normal"])
                )
            else:
                story.append(Paragraph(_esc(line), styles["Normal"]))

        try:
            SimpleDocTemplate(str(out), pagesize=A4).build(story)
        except Exception as e:
            return ToolResult(error=f"Failed to generate PDF: {e}")

        return ToolResult(
            output=f"PDF generated: {out} ({out.stat().st_size} bytes)"
        )
