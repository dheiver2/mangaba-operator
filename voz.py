"""Modo voz do Mangaba Operator: fale a tarefa, o agente executa e responde falando.

Pipeline 100% local: microfone (ffmpeg) → Whisper (gateway) → agente → voz (say).

Uso:
    python voz.py                          # grava 6s do microfone e executa como tarefa
    python voz.py --seconds 10             # gravação mais longa
    python voz.py --chat                   # conversa direta (audio_chat), sem agente
    python voz.py --file caminho/audio.wav # usa um áudio pronto em vez do microfone
"""

import argparse
import asyncio
import subprocess
import tempfile
from pathlib import Path

from app.agent.mangaba import Mangaba
from app.config import config
from app.gateway import preload_default_model
from app.logger import logger
from app.tool.gateway_media import AudioChat, TranscribeAudio

VOICE = "Luciana"


def gravar(seconds: int) -> Path:
    """Grava o microfone padrão em wav 16kHz mono via ffmpeg/avfoundation."""
    out = Path(tempfile.mkstemp(suffix=".wav", prefix="mangaba-voz-")[1])
    logger.warning(f"🎙️  Gravando {seconds}s... fale agora!")
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "avfoundation", "-i", ":0",
            "-t", str(seconds), "-ar", "16000", "-ac", "1",
            str(out),
        ],
        check=True,
    )
    return out


def falar(texto: str) -> None:
    texto = texto.strip()
    if texto:
        subprocess.run(["say", "-v", VOICE, texto[:600]])


async def main() -> None:
    parser = argparse.ArgumentParser(description="Modo voz do Mangaba Operator")
    parser.add_argument("--file", type=str, help="Áudio pronto (pula a gravação)")
    parser.add_argument("--seconds", type=int, default=6, help="Duração da gravação (padrão 6s)")
    parser.add_argument("--chat", action="store_true", help="Resposta direta via audio_chat, sem agente")
    parser.add_argument("--max-steps", type=int, default=10)
    args = parser.parse_args()

    (config.workspace_root / "memoria").mkdir(parents=True, exist_ok=True)
    (config.workspace_root / "todo.md").unlink(missing_ok=True)
    await preload_default_model()

    audio = Path(args.file) if args.file else gravar(args.seconds)

    if args.chat:
        r = await AudioChat().execute(audio_path=str(audio), instructions="Responda em português, de forma breve e natural.")
        if r.error:
            logger.error(r.error)
            return
        print(r.output)
        resposta = r.output.split("Resposta:", 1)[-1]
        falar(resposta)
        return

    # transcreve e entrega a tarefa ao agente completo
    t = await TranscribeAudio().execute(audio_path=str(audio), language="pt")
    if t.error:
        logger.error(t.error)
        return
    tarefa = t.output.split("\n\n", 1)[-1].strip()
    logger.info(f"📝 Tarefa entendida: {tarefa}")
    falar("Entendido. Executando.")

    agent = await Mangaba.create(max_steps=args.max_steps)
    try:
        await agent.run(tarefa)
        # última mensagem do assistente com conteúdo vira a resposta falada
        finais = [m.content for m in agent.memory.messages if m.role == "assistant" and m.content]
        resposta = finais[-1] if finais else "Tarefa concluída. Veja os resultados no workspace."
        print(f"\n🥭 {resposta}\n")
        falar(resposta)
    finally:
        await agent.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
