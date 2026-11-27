"""Servidor HTTP local para publicar arquivos do workspace (estilo deploy)."""

import functools
import http.server
import threading

from app.config import config
from app.tool.base import BaseTool, ToolResult
from app.tool.gateway_media import _resolve

# registro global: sobrevive a re-instanciações do tool no mesmo processo
_SERVERS: dict[int, "http.server.ThreadingHTTPServer"] = {}


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # sem ruído no stdout do agente
        pass


class LocalServer(BaseTool):
    name: str = "local_server"
    description: str = (
        "Serves a folder (default: the workspace) on a local HTTP server — useful "
        "to 'deploy' a generated HTML site/report and open it in the browser, or "
        "to test downloads. Actions: start (returns the URL), stop, status."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["start", "stop", "status"],
                "description": "start: launch the server; stop: shut it down; status: list active servers",
            },
            "port": {
                "type": "integer",
                "description": "TCP port (default 8700)",
            },
            "dir": {
                "type": "string",
                "description": "Folder to serve (default: workspace; relative paths go to the workspace)",
            },
        },
        "required": ["action"],
    }

    async def execute(
        self, action: str, port: int = 8700, dir: str = "", **kwargs
    ) -> ToolResult:
        try:
            port = int(port)
        except (TypeError, ValueError):
            return ToolResult(error=f"Invalid port: {port!r}")

        if action == "status":
            if not _SERVERS:
                return ToolResult(output="No local server running")
            lines = [
                f"  http://localhost:{p} → {srv.RequestHandlerClass.directory}"
                for p, srv in _SERVERS.items()
            ]
            return ToolResult(output="Active servers:\n" + "\n".join(lines))

        if action == "stop":
            srv = _SERVERS.pop(port, None)
            if not srv:
                return ToolResult(output=f"No server on port {port}")
            srv.shutdown()
            srv.server_close()
            return ToolResult(output=f"Server on port {port} stopped")

        if action == "start":
            if port in _SERVERS:
                return ToolResult(
                    output=f"Already running: http://localhost:{port}"
                )
            root = _resolve(dir) if dir else config.workspace_root
            if not root.is_dir():
                return ToolResult(error=f"Folder not found: {root}")
            handler = functools.partial(_QuietHandler, directory=str(root))
            handler.directory = str(root)  # p/ o status
            try:
                srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
            except OSError as e:
                return ToolResult(error=f"Port {port} unavailable: {e}")
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            _SERVERS[port] = srv
            return ToolResult(
                output=f"Serving {root} at http://localhost:{port} (use 'stop' when done)"
            )

        return ToolResult(error=f"Unknown action: {action}")
