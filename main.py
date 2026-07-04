import argparse
import asyncio

from app.agent.mangaba import Mangaba
from app.config import config
from app.gateway import apply_model_override, preload_default_model
from app.logger import logger


async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Run Mangaba agent with a prompt")
    parser.add_argument(
        "--prompt", type=str, required=False, help="Input prompt for the agent"
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=20,
        help="Maximum agent steps before stopping (default: 20)",
    )
    parser.add_argument(
        "--model",
        type=str,
        required=False,
        help="Override do modelo padrão (ex.: mangaba-pro, mangaba-lite-q4)",
    )
    parser.add_argument(
        "--verificar",
        action="store_true",
        help="Ciclo gerar→criticar→revisar: um revisor de contexto limpo valida os entregáveis e dispara 1 rodada de correção se reprovar",
    )
    args = parser.parse_args()

    # Override de modelo: gateway (mangaba-*) ou GitHub Models (openai/*, etc.)
    if args.model and not await apply_model_override(args.model):
        return

    # Memória persistente do agente entre execuções
    (config.workspace_root / "memoria").mkdir(parents=True, exist_ok=True)
    # plano é por-execução: um todo.md de tarefa anterior confundiria a nova
    (config.workspace_root / "todo.md").unlink(missing_ok=True)

    # Garante o modelo quente no gateway antes do primeiro passo
    await preload_default_model()

    # Use command line prompt if provided, otherwise ask for input
    prompt = args.prompt if args.prompt else input("Enter your prompt: ")
    if not prompt.strip():
        logger.warning("Empty prompt provided.")
        return

    if args.verificar:
        from app.verificador import executar_com_verificacao

        logger.warning("Processing your request (com verificação)...")
        aprovado, parecer = await executar_com_verificacao(prompt, max_steps=args.max_steps)
        logger.info(f"Parecer final do revisor: {parecer[:500]}")
        return

    # Create and initialize Mangaba agent
    agent = await Mangaba.create(max_steps=args.max_steps)
    try:
        logger.warning("Processing your request...")
        await agent.run(prompt)
        logger.info("Request processing completed.")
    except KeyboardInterrupt:
        logger.warning("Operation interrupted.")
    finally:
        # Ensure agent resources are cleaned up before exiting
        await agent.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
