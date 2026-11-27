"""Consultas SQL em bancos SQLite, com importação opcional de CSV."""

import csv
import sqlite3

from app.tool.base import BaseTool, ToolResult
from app.tool.gateway_media import _resolve

_MAX_ROWS = 100


class SqliteQuery(BaseTool):
    name: str = "sqlite_query"
    description: str = (
        "Runs SQL on a workspace SQLite database (SELECT, CREATE, INSERT...). "
        "With 'csv_import', first loads a CSV as a table — a quick way to "
        "analyze tabular data with SQL without writing Python. The default database is "
        "workspace/dados.db."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "SQL statement to run"},
            "db_path": {
                "type": "string",
                "description": "The .db/.sqlite file (default: dados.db in the workspace)",
            },
            "csv_import": {
                "type": "string",
                "description": "CSV to import before the query; becomes a table named after the file",
            },
        },
        "required": ["sql"],
    }

    async def execute(
        self, sql: str, db_path: str = "dados.db", csv_import: str = "", **kwargs
    ) -> ToolResult:
        db = _resolve(db_path)
        db.parent.mkdir(parents=True, exist_ok=True)

        try:
            con = sqlite3.connect(db)
        except sqlite3.Error as e:
            return ToolResult(error=f"Could not open database {db}: {e}")

        try:
            if csv_import:
                src = _resolve(csv_import)
                if not src.is_file():
                    return ToolResult(error=f"CSV not found: {src}")
                table = src.stem.replace("-", "_").replace(" ", "_")
                with open(src, newline="", encoding="utf-8", errors="replace") as fh:
                    reader = csv.reader(fh)
                    header = next(reader, None)
                    if not header:
                        return ToolResult(error=f"CSV is empty: {src}")
                    cols = ", ".join(f'"{c.strip()}"' for c in header)
                    ph = ", ".join("?" for _ in header)
                    con.execute(f'DROP TABLE IF EXISTS "{table}"')
                    con.execute(f'CREATE TABLE "{table}" ({cols})')
                    n = 0
                    for row in reader:
                        row = (row + [""] * len(header))[: len(header)]
                        con.execute(f'INSERT INTO "{table}" VALUES ({ph})', row)
                        n += 1
                    con.commit()

            cur = con.execute(sql)
            if cur.description:  # query returned rows
                cols = [d[0] for d in cur.description]
                rows = cur.fetchmany(_MAX_ROWS)
                more = cur.fetchone() is not None
                lines = ["\t".join(cols)]
                lines += ["\t".join("" if v is None else str(v) for v in r) for r in rows]
                tail = "\n… (more rows; refine with LIMIT)" if more else ""
                out = f"{len(rows)} row(s):\n" + "\n".join(lines) + tail
            else:
                con.commit()
                out = f"OK — {cur.rowcount if cur.rowcount >= 0 else 0} row(s) affected"
            if csv_import:
                out = f"CSV imported as table '{table}' ({n} rows).\n" + out
            return ToolResult(output=out)
        except sqlite3.Error as e:
            return ToolResult(error=f"SQL error: {e}")
        finally:
            con.close()
