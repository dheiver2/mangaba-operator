"""Utilitários do Mangaba Gateway (pré-carga de modelo)."""

import asyncio

import httpx

from app.config import config
from app.logger import logger


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
