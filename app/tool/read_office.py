"""Leitura de documentos Office e CSV (complemento do read_pdf)."""

import csv as csv_mod

from app.tool.base import BaseTool, ToolResult
from app.tool.gateway_media import _resolve

_PREVIEW = 5000
_MAX_ROWS = 50


class ReadOffice(BaseTool):
    name: str = "read_office"
    description: str = (
        "Extracts the content of .docx (text and tables), .xlsx (spreadsheets, "
        "first rows of each sheet), .pptx (slide text) and .csv (first "
        "rows) documents. For PDF use read_pdf. Relative paths go to the workspace."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the document (.docx, .xlsx, .pptx or .csv)",
            },
        },
        "required": ["file_path"],
    }

    async def execute(self, file_path: str, **kwargs) -> ToolResult:
        path = _resolve(file_path)
        if not path.is_file():
            return ToolResult(error=f"File not found: {path}")
        ext = path.suffix.lower()

        try:
            if ext == ".docx":
                from docx import Document

                doc = Document(str(path))
                parts = [p.text for p in doc.paragraphs if p.text.strip()]
                for ti, table in enumerate(doc.tables, 1):
                    rows = ["\t".join(c.text for c in row.cells) for row in table.rows]
                    parts.append(f"[Table {ti}]\n" + "\n".join(rows))
                text = "\n".join(parts)

            elif ext == ".xlsx":
                from openpyxl import load_workbook

                wb = load_workbook(str(path), read_only=True, data_only=True)
                parts = []
                for ws in wb.worksheets:
                    lines = []
                    for ri, row in enumerate(ws.iter_rows(values_only=True)):
                        if ri >= _MAX_ROWS:
                            lines.append(f"… (+{ws.max_row - _MAX_ROWS} rows)")
                            break
                        lines.append(
                            "\t".join("" if c is None else str(c) for c in row)
                        )
                    parts.append(
                        f"=== Sheet '{ws.title}' ({ws.max_row}x{ws.max_column}) ===\n"
                        + "\n".join(lines)
                    )
                wb.close()
                text = "\n\n".join(parts)

            elif ext == ".pptx":
                from pptx import Presentation

                prs = Presentation(str(path))
                parts = []
                for si, slide in enumerate(prs.slides, 1):
                    texts = [
                        sh.text.strip()
                        for sh in slide.shapes
                        if getattr(sh, "has_text_frame", False) and sh.text.strip()
                    ]
                    parts.append(f"--- Slide {si} ---\n" + "\n".join(texts))
                text = "\n".join(parts)

            elif ext in (".csv", ".tsv"):
                delim = "\t" if ext == ".tsv" else ","
                with open(path, newline="", encoding="utf-8", errors="replace") as fh:
                    reader = csv_mod.reader(fh, delimiter=delim)
                    rows = []
                    total = 0
                    for row in reader:
                        total += 1
                        if total <= _MAX_ROWS:
                            rows.append("\t".join(row))
                text = "\n".join(rows)
                if total > _MAX_ROWS:
                    text += f"\n… (+{total - _MAX_ROWS} rows; total {total})"

            else:
                return ToolResult(
                    error=f"Unsupported extension: {ext} (supported: .docx .xlsx .pptx .csv .tsv)"
                )
        except Exception as e:
            return ToolResult(error=f"Failed to read {path.name}: {e}")

        if not text.strip():
            return ToolResult(output=f"{path.name} contains no extractable text")
        preview = text[:_PREVIEW] + ("… (truncated)" if len(text) > _PREVIEW else "")
        return ToolResult(output=f"Content of {path.name}:\n{preview}")
