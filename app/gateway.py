"""Utilitários de provedores (Mangaba Gateway e GitHub Models)."""

import asyncio
import os
import subprocess

import httpx

from app.config import config
from app.logger import logger

GITHUB_MODELS_URL = "https://models.github.ai/inference"


async def apply_model_override(model: str) -> bool:
    """Aplica o --model na config. Retorna False se o modelo for inválido.

    Modelos com '/' (ex.: openai/gpt-4.1-mini) são do GitHub Models — API
    gratuita OpenAI-compatível com janelas de até 1M tokens; o token vem de
    GITHUB_TOKEN ou do `gh auth token`. Sem '/', é um modelo do gateway,
    validado contra o /v1/models.
    """
    settings = config.llm["default"]
    if "/" in model:
        token = os.getenv("GITHUB_TOKEN") or subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True
        ).stdout.strip()
        if not token:
            logger.error(
                "GitHub Models requer token: exporte GITHUB_TOKEN ou faça `gh auth login`"
            )
            return False
        settings.model = model
        settings.base_url = GITHUB_MODELS_URL
        settings.api_key = token
        logger.info(f"🐙 Provedor desta execução: GitHub Models · {model} (janela grande)")
        return True

    available = await list_models()
    if available and model not in available:
        logger.error(f"Modelo '{model}' indisponível no gateway. Opções: {', '.join(available)}")
        return False
    settings.model = model
    logger.info(f"🔀 Modelo padrão desta execução: {model}")
    return True


async def list_models() -> list[str]:
    """Lista os modelos disponíveis no gateway via /v1/models (vazio se falhar)."""
    settings = config.llm["default"]
    root = str(settings.base_url).rstrip("/").removesuffix("/v1")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            data = (await client.get(f"{root}/v1/models")).json()
        return [m["id"] for m in data.get("data", [])]
    except Exception:
        return []


async def preload_default_model(max_wait: int = 300) -> None:
    """Dispara a carga do modelo padrão no gateway e aguarda ficar pronto.

    Evita que o primeiro passo do agente trave na carga a frio (HD USB pode
    levar minutos). Silencioso se o provedor não for o Mangaba Gateway ou se
    o modelo já estiver quente.
    """
    settings = config.llm["default"]
    root = str(settings.base_url).rstrip("/").removesuffix("/v1")
    model = settings.model
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            health = (await client.get(f"{root}/api/v1/health")).json()
            if health.get("ready") and model in health.get("loaded_models", []):
                return
            logger.info(f"⏳ Pré-carregando '{model}' no gateway...")
            await client.post(f"{root}/api/v1/{model}/load")
        deadline = asyncio.get_event_loop().time() + max_wait
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(5)
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    health = (await client.get(f"{root}/api/v1/health")).json()
                if health.get("ready") and model in health.get("loaded_models", []):
                    logger.info(f"✅ Modelo '{model}' pronto no gateway")
                    return
            except Exception:
                continue
        logger.warning(f"Modelo '{model}' ainda carregando após {max_wait}s; seguindo mesmo assim")
    except Exception:
        # provedor sem endpoint de health (ex.: outra API OpenAI-compatível)
        return
