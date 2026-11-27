"""Requisições HTTP diretas (APIs REST) e download de arquivos."""

import json

from app.tool.base import BaseTool, ToolResult
from app.tool.gateway_media import _resolve

_PREVIEW = 3000


class HttpRequest(BaseTool):
    name: str = "http_request"
    description: str = (
        "Makes an HTTP request (GET/POST/PUT/PATCH/DELETE) to an API or URL, with "
        "optional headers and JSON body. With 'save_to', downloads the response body "
        "to a workspace file (reports, images, CSVs). Use for REST APIs; "
        "for HTML pages prefer fetch_url or the browser."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Full URL (http/https)"},
            "method": {
                "type": "string",
                "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                "description": "HTTP method (default GET)",
            },
            "headers": {
                "type": "object",
                "description": "Extra headers, e.g. {\"Authorization\": \"Bearer ...\"}",
            },
            "body": {
                "type": "string",
                "description": "Request body. If valid JSON, it is sent as application/json",
            },
            "save_to": {
                "type": "string",
                "description": "Destination path to save the response (relative paths go to the workspace)",
            },
        },
        "required": ["url"],
    }

    async def execute(
        self,
        url: str,
        method: str = "GET",
        headers: dict | None = None,
        body: str = "",
        save_to: str = "",
        **kwargs,
    ) -> ToolResult:
        import requests

        if not url.startswith(("http://", "https://")):
            return ToolResult(error=f"Invalid URL (must be http/https): {url}")
        if isinstance(headers, str):
            try:
                headers = json.loads(headers)
            except json.JSONDecodeError:
                return ToolResult(error="'headers' must be a JSON object")

        kwargs_req: dict = {"headers": headers or {}, "timeout": 60}
        if body:
            try:
                kwargs_req["json"] = json.loads(body)
            except json.JSONDecodeError:
                kwargs_req["data"] = body

        try:
            resp = requests.request(method.upper(), url, stream=bool(save_to), **kwargs_req)
        except requests.RequestException as e:
            return ToolResult(error=f"Request failed: {e}")

        ctype = resp.headers.get("content-type", "?")
        if save_to:
            dest = _resolve(save_to)
            dest.parent.mkdir(parents=True, exist_ok=True)
            size = 0
            with open(dest, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=65536):
                    fh.write(chunk)
                    size += len(chunk)
            return ToolResult(
                output=f"HTTP {resp.status_code} — {size} bytes ({ctype}) saved to {dest}"
            )

        text = resp.text or ""
        preview = text[:_PREVIEW] + ("… (truncated)" if len(text) > _PREVIEW else "")
        return ToolResult(
            output=f"HTTP {resp.status_code} ({ctype}, {len(text)} chars):\n{preview}"
        )
