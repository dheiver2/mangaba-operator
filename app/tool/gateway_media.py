"""Ferramentas multimodais do Mangaba Gateway (visão e áudio).

Usam os endpoints nativos do gateway (/image/describe e /audio/transcribe),
que ficavam ociosos: o agente ganha olhos (mangaba-vision-q8) e ouvidos
(Whisper) sem nenhum provedor adicional.
"""

import re
from pathlib import Path

import httpx

from app.config import config
from app.tool.base import BaseTool, ToolResult

_TIMEOUT = 300  # carga a frio do modelo de visão pode demorar


def _gateway_root() -> str:
    """Raiz do gateway derivada do base_url OpenAI-compatível (remove /v1)."""
    settings = config.llm.get("vision") or config.llm["default"]
    return str(settings.base_url).rstrip("/").removesuffix("/v1")


def _resolve(path: str) -> Path:
    p = Path(path)
    # modelos às vezes escrevem "/workspace/x" como se fosse raiz absoluta
    if p.is_absolute() and not p.exists() and p.parts[:2] == ("/", "workspace"):
        p = Path(*p.parts[2:]) if len(p.parts) > 2 else Path(".")
    if not p.is_absolute():
        rel = p
        if rel.parts and rel.parts[0] == config.workspace_root.name:
            rel = Path(*rel.parts[1:]) if len(rel.parts) > 1 else Path(".")
        p = config.workspace_root / rel
    return p


class DescribeImage(BaseTool):
    name: str = "describe_image"
    description: str = (
        "Analyzes a local image (photo, screenshot, chart, scanned document) and "
        "answers in text what it contains. Use when you need to understand visual "
        "content: describe images, read charts, extract information from photos of "
        "documents. Accepts a specific prompt (e.g. 'extract the values from the table')."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "image_path": {
                "type": "string",
                "description": "Path to the image file (png/jpg/webp); relative paths resolve against the workspace",
            },
            "prompt": {
                "type": "string",
                "description": "Question or instruction about the image (default: 'Describe this image.')",
            },
        },
        "required": ["image_path"],
    }

    async def execute(self, image_path: str, prompt: str = "Describe this image.", **kwargs) -> ToolResult:
        path = _resolve(image_path)
        if not path.is_file():
            return ToolResult(error=f"Image not found: {path}")

        vision_model = (config.llm.get("vision") or config.llm["default"]).model
        url = f"{_gateway_root()}/api/v1/{vision_model}/image/describe"
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    url,
                    files={"file": (path.name, path.read_bytes())},
                    data={"prompt": prompt, "max_new_tokens": 512},
                )
                resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            return ToolResult(error=f"Gateway returned HTTP {e.response.status_code}: {e.response.text[:300]}")
        except Exception as e:
            return ToolResult(error=f"Failed to analyze image: {e}")

        data = resp.json()
        text = data.get("description") or data.get("reply") or data.get("text") or str(data)
        # o modelo de visão às vezes vaza tags de raciocínio na resposta
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        return ToolResult(output=f"Analysis of {path.name}:\n\n{text}")


class AudioChat(BaseTool):
    name: str = "audio_chat"
    description: str = (
        "Listens to a local audio file and REPLIES to what was said, in a single "
        "call (transcription + model reply). Use when the audio contains a "
        "question or request to answer directly (e.g. replying to a voice "
        "message). To only convert speech to text, prefer transcribe_audio."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "audio_path": {
                "type": "string",
                "description": "Path to the audio file; relative paths resolve against the workspace",
            },
            "instructions": {
                "type": "string",
                "description": "Instruction on how to reply (e.g. 'reply briefly and formally')",
            },
            "language": {
                "type": "string",
                "description": "Language spoken in the audio, e.g. 'pt' (default)",
            },
        },
        "required": ["audio_path"],
    }

    async def execute(
        self,
        audio_path: str,
        instructions: str = "You are a helpful assistant. Reply in the user's language; default to English.",
        language: str = "pt",
        **kwargs,
    ) -> ToolResult:
        path = _resolve(audio_path)
        if not path.is_file():
            return ToolResult(error=f"Audio not found: {path}")

        # usa o modelo padrão (já quente pela pré-carga) pra gerar a resposta
        model = config.llm["default"].model
        url = f"{_gateway_root()}/api/v1/{model}/audio/chat"
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    url,
                    files={"file": (path.name, path.read_bytes())},
                    data={
                        "language": language,
                        "system_prompt": instructions,
                        "max_new_tokens": 512,
                    },
                )
                resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            return ToolResult(error=f"Gateway returned HTTP {e.response.status_code}: {e.response.text[:300]}")
        except Exception as e:
            return ToolResult(error=f"audio_chat failed: {e}")

        data = resp.json()
        reply = re.sub(r"<think>.*?</think>", "", data.get("reply", ""), flags=re.DOTALL).strip()
        return ToolResult(
            output=(
                f"Transcript of {path.name}:\n{data.get('transcription', '')}\n\n"
                f"Reply:\n{reply}"
            )
        )


class TranscribeAudio(BaseTool):
    name: str = "transcribe_audio"
    description: str = (
        "Transcribes a local audio file (wav/mp3/m4a/ogg) to text using "
        "Whisper. Use to transcribe meetings, voice messages, calls or "
        "any speech recording."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "audio_path": {
                "type": "string",
                "description": "Path to the audio file; relative paths resolve against the workspace",
            },
            "language": {
                "type": "string",
                "description": "Language code spoken in the audio, e.g. 'pt' (default), 'en', 'es'",
            },
        },
        "required": ["audio_path"],
    }

    async def execute(self, audio_path: str, language: str = "pt", **kwargs) -> ToolResult:
        path = _resolve(audio_path)
        if not path.is_file():
            return ToolResult(error=f"Audio not found: {path}")

        # Whisper independe do modelo de texto; o slug leve evita swap desnecessário
        url = f"{_gateway_root()}/api/v1/mangaba-lite-q4/audio/transcribe"
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    url,
                    files={"file": (path.name, path.read_bytes())},
                    data={"language": language},
                )
                resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            return ToolResult(error=f"Gateway returned HTTP {e.response.status_code}: {e.response.text[:300]}")
        except Exception as e:
            return ToolResult(error=f"Failed to transcribe audio: {e}")

        data = resp.json()
        transcription = data.get("transcription", str(data))
        # persistência (context engineering): sobrevive a cortes de histórico
        cache_dir = config.workspace_root / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        saved = cache_dir / f"transcricao-{path.stem}.txt"
        saved.write_text(transcription, encoding="utf-8")
        return ToolResult(
            output=(
                f"Transcript of {path.name} (saved to {saved}):\n\n{transcription}"
            )
        )
