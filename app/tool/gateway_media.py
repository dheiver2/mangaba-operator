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
        "Analisa uma imagem local (foto, screenshot, gráfico, documento escaneado) e "
        "responde em texto o que ela contém. Use quando precisar entender conteúdo "
        "visual: descrever imagens, ler gráficos, extrair informação de fotos de "
        "documentos. Aceita um prompt específico (ex.: 'extraia os valores da tabela')."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "image_path": {
                "type": "string",
                "description": "Caminho do arquivo de imagem (png/jpg/webp); relativo é resolvido contra o workspace",
            },
            "prompt": {
                "type": "string",
                "description": "Pergunta ou instrução sobre a imagem (padrão: 'Descreva esta imagem.')",
            },
        },
        "required": ["image_path"],
    }

    async def execute(self, image_path: str, prompt: str = "Descreva esta imagem.", **kwargs) -> ToolResult:
        path = _resolve(image_path)
        if not path.is_file():
            return ToolResult(error=f"Imagem não encontrada: {path}")

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
            return ToolResult(error=f"Gateway retornou HTTP {e.response.status_code}: {e.response.text[:300]}")
        except Exception as e:
            return ToolResult(error=f"Falha ao analisar imagem: {e}")

        data = resp.json()
        text = data.get("description") or data.get("reply") or data.get("text") or str(data)
        # o modelo de visão às vezes vaza tags de raciocínio na resposta
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        return ToolResult(output=f"Análise de {path.name}:\n\n{text}")


class AudioChat(BaseTool):
    name: str = "audio_chat"
    description: str = (
        "Ouve um arquivo de áudio local e RESPONDE ao que foi falado, em uma única "
        "chamada (transcrição + resposta do modelo). Use quando o áudio contém uma "
        "pergunta ou pedido a ser respondido diretamente (ex.: responder mensagem de "
        "voz). Para apenas converter fala em texto, prefira transcribe_audio."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "audio_path": {
                "type": "string",
                "description": "Caminho do arquivo de áudio; relativo é resolvido contra o workspace",
            },
            "instructions": {
                "type": "string",
                "description": "Instrução de como responder (ex.: 'responda de forma breve e formal')",
            },
            "language": {
                "type": "string",
                "description": "Idioma falado no áudio, ex. 'pt' (padrão)",
            },
        },
        "required": ["audio_path"],
    }

    async def execute(
        self,
        audio_path: str,
        instructions: str = "Você é um assistente útil em português.",
        language: str = "pt",
        **kwargs,
    ) -> ToolResult:
        path = _resolve(audio_path)
        if not path.is_file():
            return ToolResult(error=f"Áudio não encontrado: {path}")

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
            return ToolResult(error=f"Gateway retornou HTTP {e.response.status_code}: {e.response.text[:300]}")
        except Exception as e:
            return ToolResult(error=f"Falha no audio_chat: {e}")

        data = resp.json()
        reply = re.sub(r"<think>.*?</think>", "", data.get("reply", ""), flags=re.DOTALL).strip()
        return ToolResult(
            output=(
                f"Transcrição de {path.name}:\n{data.get('transcription', '')}\n\n"
                f"Resposta:\n{reply}"
            )
        )


class TranscribeAudio(BaseTool):
    name: str = "transcribe_audio"
    description: str = (
        "Transcreve um arquivo de áudio local (wav/mp3/m4a/ogg) para texto usando "
        "Whisper. Use para transcrever reuniões, mensagens de voz, ligações ou "
        "qualquer gravação de fala."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "audio_path": {
                "type": "string",
                "description": "Caminho do arquivo de áudio; relativo é resolvido contra o workspace",
            },
            "language": {
                "type": "string",
                "description": "Código do idioma falado, ex. 'pt' (padrão), 'en', 'es'",
            },
        },
        "required": ["audio_path"],
    }

    async def execute(self, audio_path: str, language: str = "pt", **kwargs) -> ToolResult:
        path = _resolve(audio_path)
        if not path.is_file():
            return ToolResult(error=f"Áudio não encontrado: {path}")

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
            return ToolResult(error=f"Gateway retornou HTTP {e.response.status_code}: {e.response.text[:300]}")
        except Exception as e:
            return ToolResult(error=f"Falha ao transcrever áudio: {e}")

        data = resp.json()
        transcription = data.get("transcription", str(data))
        # persistência (context engineering): sobrevive a cortes de histórico
        cache_dir = config.workspace_root / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        saved = cache_dir / f"transcricao-{path.stem}.txt"
        saved.write_text(transcription, encoding="utf-8")
        return ToolResult(
            output=(
                f"Transcrição de {path.name} (salva em {saved}):\n\n{transcription}"
            )
        )
