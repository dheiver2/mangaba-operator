"""Edição básica de imagens (Pillow) — evidências, anexos, thumbnails."""

from app.tool.base import BaseTool, ToolResult
from app.tool.gateway_media import _resolve


class ImageEdit(BaseTool):
    name: str = "image_edit"
    description: str = (
        "Basic operations on local images: info (dimensions/format), resize, "
        "crop, rotate and convert (png/jpg/webp). To UNDERSTAND the content of an "
        "image use describe_image; this tool only transforms the file."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["info", "resize", "crop", "rotate", "convert"],
                "description": "Operation to apply",
            },
            "image_path": {"type": "string", "description": "Source image"},
            "dest": {
                "type": "string",
                "description": "Output file (default: _editado suffix; the extension sets the format in 'convert')",
            },
            "width": {"type": "integer", "description": "Target width for 'resize'"},
            "height": {
                "type": "integer",
                "description": "Target height for 'resize' (omitted = keep aspect ratio)",
            },
            "box": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Rectangle [left, top, right, bottom] for 'crop'",
            },
            "degrees": {
                "type": "integer",
                "description": "Counter-clockwise degrees for 'rotate' (90/180/270...)",
            },
        },
        "required": ["action", "image_path"],
    }

    async def execute(
        self,
        action: str,
        image_path: str,
        dest: str = "",
        width: int | None = None,
        height: int | None = None,
        box: list | None = None,
        degrees: int | None = None,
        **kwargs,
    ) -> ToolResult:
        from PIL import Image

        src = _resolve(image_path)
        if not src.is_file():
            return ToolResult(error=f"Image not found: {src}")

        try:
            im = Image.open(src)
            im.load()
        except Exception as e:
            return ToolResult(error=f"File is not a readable image: {e}")

        if action == "info":
            return ToolResult(
                output=(
                    f"{src.name}: {im.width}x{im.height} px, format {im.format}, "
                    f"mode {im.mode}, {src.stat().st_size} bytes"
                )
            )

        try:
            if action == "resize":
                if not width and not height:
                    return ToolResult(error="'resize' requires width and/or height")
                w = int(width) if width else round(im.width * int(height) / im.height)
                h = int(height) if height else round(im.height * int(width) / im.width)
                im = im.resize((w, h), Image.LANCZOS)
            elif action == "crop":
                if not box or len(box) != 4:
                    return ToolResult(error="'crop' requires box=[left, top, right, bottom]")
                im = im.crop(tuple(int(v) for v in box))
            elif action == "rotate":
                if degrees is None:
                    return ToolResult(error="'rotate' requires 'degrees'")
                im = im.rotate(int(degrees), expand=True)
            elif action == "convert":
                if not dest:
                    return ToolResult(
                        error="'convert' requires 'dest' with the new extension (e.g. photo.webp)"
                    )
            else:
                return ToolResult(error=f"Unknown action: {action}")

            out = _resolve(dest) if dest else src.with_stem(src.stem + "_editado")
            out.parent.mkdir(parents=True, exist_ok=True)
            if out.suffix.lower() in (".jpg", ".jpeg") and im.mode in ("RGBA", "P"):
                im = im.convert("RGB")  # JPEG não tem alfa
            im.save(out)
            return ToolResult(
                output=f"{action} OK → {out} ({im.width}x{im.height}, {out.stat().st_size} bytes)"
            )
        except Exception as e:
            return ToolResult(error=f"'{action}' failed: {e}")
