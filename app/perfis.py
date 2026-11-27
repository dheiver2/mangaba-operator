"""Perfis de ferramentas por execução (aceleração de prefill).

Os schemas das 14 ferramentas custam ~3.3k tokens ENVIADOS EM TODA chamada.
Sem cache de prefixo no gateway (~200 tok/s de prefill), isso é ~16s/passo só
de custo fixo. Tarefas que não usam navegador/mídia podem cortar os schemas
mais pesados e ganhar ~5-8s por passo.
"""

from app.logger import logger

# 'rapido' remove os schemas pesados/raros; mantém o núcleo de trabalho
_EXCLUI_RAPIDO = {
    "browser_use",      # 2.9k chars — o mais pesado; fetch_url/web_search cobrem leitura
    "audio_chat",
    "describe_image",
    "send_email",
    "notify_webhook",
}

PERFIS = ("completo", "rapido")


def aplicar_perfil(agent, perfil: str) -> None:
    if perfil in (None, "", "completo"):
        return
    if perfil != "rapido":
        logger.warning(f"Perfil desconhecido '{perfil}'; usando completo")
        return
    from app.tool import ToolCollection

    manter = [t for t in agent.available_tools.tools if t.name not in _EXCLUI_RAPIDO]
    agent.available_tools = ToolCollection(*manter)
    logger.info(
        f"⚡ Fast profile: {len(manter)} tools (removed: {', '.join(sorted(_EXCLUI_RAPIDO))})"
    )
