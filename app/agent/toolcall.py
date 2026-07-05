import asyncio
import json
import re
from typing import Any, List, Optional, Union

from pydantic import Field

from app.agent.react import ReActAgent
from app.exceptions import TokenLimitExceeded
from app.logger import logger
from app.prompt.toolcall import NEXT_STEP_PROMPT, SYSTEM_PROMPT
from app.schema import (
    TOOL_CHOICE_TYPE,
    AgentState,
    Function,
    Message,
    ToolCall,
    ToolChoice,
)
from app.tool import CreateChatCompletion, Terminate, ToolCollection


TOOL_CALL_REQUIRED = "Tool calls required but none provided"


class ToolCallAgent(ReActAgent):
    """Base agent class for handling tool/function calls with enhanced abstraction"""

    name: str = "toolcall"
    description: str = "an agent that can execute tool calls."

    system_prompt: str = SYSTEM_PROMPT
    next_step_prompt: str = NEXT_STEP_PROMPT

    available_tools: ToolCollection = ToolCollection(
        CreateChatCompletion(), Terminate()
    )
    tool_choices: TOOL_CHOICE_TYPE = ToolChoice.AUTO  # type: ignore
    special_tool_names: List[str] = Field(default_factory=lambda: [Terminate().name])

    tool_calls: List[ToolCall] = Field(default_factory=list)
    _current_base64_image: Optional[str] = None

    max_steps: int = 30
    max_observe: Optional[Union[int, bool]] = None

    def _audit(self, tool: str, args: dict, result: str) -> None:
        """Trilha de auditoria: 1 linha JSON por tool call em workspace/logs/.

        Compliance empresarial: quem (agente/passo), quando, qual ferramenta,
        com quais argumentos e o começo do resultado. Nunca deve quebrar o loop.
        """
        try:
            from datetime import datetime, timezone

            from app.config import config

            logs = config.workspace_root / "logs"
            logs.mkdir(parents=True, exist_ok=True)
            registro = {
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "agent": self.name,
                "step": self.current_step,
                "tool": tool,
                "args": {k: (str(v)[:200]) for k, v in args.items()},
                "result_preview": result[:200],
                "error": result.startswith("Error"),
            }
            with (logs / "audit.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(registro, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _shrink_context(self) -> bool:
        """Reduz o histórico pra caber na janela de contexto do modelo.

        1º truncando observações de ferramenta longas; se não bastar, descarta
        os passos mais antigos preservando a tarefa original e a cauda recente.
        Retorna False quando não há mais o que encolher (evita loop infinito).
        """
        msgs = self.memory.messages
        shrunk = False

        # 1) trunca conteúdos longos (tool results e páginas coladas)
        for m in msgs[:-2]:  # preserva as 2 mensagens mais recentes na íntegra
            if m.content and len(m.content) > 1500:
                m.content = (
                    m.content[:1500] + "\n[...truncado para caber na janela de contexto...]"
                )
                shrunk = True
        if shrunk:
            return True

        # 2) descarta o miolo antigo: mantém a 1ª mensagem (tarefa) + cauda
        if len(msgs) <= 8:
            return False
        cut = len(msgs) - 6
        # não começar a cauda com tool_result órfão (quebraria o pareamento)
        while cut > 1 and msgs[cut].role == "tool":
            cut -= 1
        head = msgs[:1]
        note = Message.assistant_message(
            "[Earlier steps were omitted to fit the context window. "
            "The original task and current plan remain unchanged.]"
        )
        self.memory.messages = head + [note] + msgs[cut:]
        return True

    def _recover_tool_calls_from_text(self, content: str) -> List[ToolCall]:
        """Extrai chamadas escritas como texto, ex.: 'browser_use({"action": ...})'.

        Modelos menores às vezes degradam e emitem a chamada no content em vez
        de tool_calls estruturado; sem isso o passo é desperdiçado.
        """
        recovered: List[ToolCall] = []
        vistos: set = set()  # dedupe: o modelo repete a mesma chamada no texto
        for i, match in enumerate(re.finditer(r"(\w+)\s*\(\s*(?=\{)", content)):
            name = match.group(1)
            if name not in self.available_tools.tool_map:
                continue
            # varre a partir da '{' contando chaves, ignorando as internas a strings
            start = match.end()
            depth, in_string, escape = 0, False, False
            end = None
            for pos in range(start, len(content)):
                ch = content[pos]
                if in_string:
                    if escape:
                        escape = False
                    elif ch == "\\":
                        escape = True
                    elif ch == '"':
                        in_string = False
                    continue
                if ch == '"':
                    in_string = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = pos + 1
                        break
            if end is None:
                continue
            args = content[start:end]
            try:
                json.loads(args)
            except json.JSONDecodeError:
                continue
            if (name, args) in vistos:
                continue
            vistos.add((name, args))
            recovered.append(
                ToolCall(
                    id=f"recovered_{self.current_step}_{i}",
                    function=Function(name=name, arguments=args),
                )
            )
        return recovered

    async def think(self) -> bool:
        """Process current state and decide next actions using tools"""
        if self.next_step_prompt:
            user_msg = Message.user_message(self.next_step_prompt)
            self.messages += [user_msg]

        try:
            # Get response with tool options
            response = await self.llm.ask_tool(
                messages=self.messages,
                system_msgs=(
                    [Message.system_message(self.system_prompt)]
                    if self.system_prompt
                    else None
                ),
                tools=self.available_tools.to_params(),
                tool_choice=self.tool_choices,
            )
        except ValueError:
            raise
        except Exception as e:
            # Check if this is a RetryError containing TokenLimitExceeded
            if hasattr(e, "__cause__") and isinstance(e.__cause__, TokenLimitExceeded):
                token_limit_error = e.__cause__
                logger.error(
                    f"🚨 Token limit error (from RetryError): {token_limit_error}"
                )
                self.memory.add_message(
                    Message.assistant_message(
                        f"Maximum token limit reached, cannot continue execution: {str(token_limit_error)}"
                    )
                )
                self.state = AgentState.FINISHED
                return False
            # Janela de contexto do provedor estourou: erro permanente — em vez
            # de repetir/crashar, encolhe o histórico e tenta o passo de novo
            err_text = f"{e} {getattr(e, '__cause__', '')}"
            if "context window" in err_text or "exceed" in err_text.lower():
                if self._shrink_context():
                    logger.warning(
                        "🧹 Contexto excedeu a janela do modelo; histórico encolhido, repetindo o passo"
                    )
                    return await self.think()
            raise

        self.tool_calls = tool_calls = (
            response.tool_calls if response and response.tool_calls else []
        )
        content = response.content if response and response.content else ""

        # Modelos menores às vezes escrevem a chamada como texto em vez de
        # emitir tool_calls estruturado; recupera antes de desperdiçar o passo
        if not tool_calls and content:
            recovered = self._recover_tool_calls_from_text(content)
            if recovered:
                self.tool_calls = tool_calls = recovered
                logger.info(
                    f"♻️ Recuperado {len(recovered)} tool call(s) emitido(s) como texto"
                )

        # Log response info
        logger.info(f"✨ {self.name}'s thoughts: {content}")
        logger.info(
            f"🛠️ {self.name} selected {len(tool_calls) if tool_calls else 0} tools to use"
        )
        if tool_calls:
            logger.info(
                f"🧰 Tools being prepared: {[call.function.name for call in tool_calls]}"
            )
            logger.info(f"🔧 Tool arguments: {tool_calls[0].function.arguments}")

        try:
            if response is None:
                raise RuntimeError("No response received from the LLM")

            # Handle different tool_choices modes
            if self.tool_choices == ToolChoice.NONE:
                if tool_calls:
                    logger.warning(
                        f"🤔 Hmm, {self.name} tried to use tools when they weren't available!"
                    )
                if content:
                    self.memory.add_message(Message.assistant_message(content))
                    return True
                return False

            # Create and add assistant message
            assistant_msg = (
                Message.from_tool_calls(content=content, tool_calls=self.tool_calls)
                if self.tool_calls
                else Message.assistant_message(content)
            )
            self.memory.add_message(assistant_msg)

            if self.tool_choices == ToolChoice.REQUIRED and not self.tool_calls:
                return True  # Will be handled in act()

            # For 'auto' mode, continue with content if no commands but content exists
            if self.tool_choices == ToolChoice.AUTO and not self.tool_calls:
                return bool(content)

            return bool(self.tool_calls)
        except Exception as e:
            logger.error(f"🚨 Oops! The {self.name}'s thinking process hit a snag: {e}")
            self.memory.add_message(
                Message.assistant_message(
                    f"Error encountered while processing: {str(e)}"
                )
            )
            return False

    async def act(self) -> str:
        """Execute tool calls and handle their results"""
        if not self.tool_calls:
            if self.tool_choices == ToolChoice.REQUIRED:
                raise ValueError(TOOL_CALL_REQUIRED)

            # Return last message content if no tool calls
            return self.messages[-1].content or "No content or commands to execute"

        results = []
        for command in self.tool_calls:
            # Reset base64_image for each tool call
            self._current_base64_image = None

            result = await self.execute_tool(command)

            if self.max_observe:
                result = result[: self.max_observe]

            logger.info(
                f"🎯 Tool '{command.function.name}' completed its mission! Result: {result}"
            )

            # Add tool response to memory
            tool_msg = Message.tool_message(
                content=result,
                tool_call_id=command.id,
                name=command.function.name,
                base64_image=self._current_base64_image,
            )
            self.memory.add_message(tool_msg)
            results.append(result)
            self._check_insistence(command, result)

        return "\n\n".join(results)

    def _check_insistence(self, command: ToolCall, result: str) -> None:
        """Anti-insistência: a mesma chamada falhando repetidamente exige mudança.

        Modelos pequenos tendem a repetir a ação que acabou de falhar. Após 2
        falhas idênticas (mesma ferramenta + argumentos), injeta uma diretiva
        no contexto forçando troca de estratégia.
        """
        falhou = result.startswith("Error") or "No content was extracted" in result
        if not falhou:
            return
        assinatura = f"{command.function.name}|{command.function.arguments}"
        repeticoes = 0
        for m in self.memory.messages:
            if m.role == "assistant" and m.tool_calls:
                for tc in m.tool_calls:
                    if f"{tc.function.name}|{tc.function.arguments}" == assinatura:
                        repeticoes += 1
        ja_avisado = any(
            m.role == "user" and m.content and "STRATEGY CHANGE REQUIRED" in m.content
            for m in self.memory.messages[-6:]
        )
        if repeticoes >= 2 and not ja_avisado:
            logger.warning(
                f"🔁 Ação '{command.function.name}' falhou {repeticoes}x com os mesmos argumentos; forçando mudança de estratégia"
            )
            self.memory.add_message(
                Message.user_message(
                    "STRATEGY CHANGE REQUIRED: the action "
                    f"`{command.function.name}` with these exact arguments has now "
                    f"failed {repeticoes} times. Repeating it again is FORBIDDEN. "
                    "Choose a DIFFERENT approach: a different tool (fetch_url, "
                    "web_search), a different target/URL, or — if no alternative "
                    "exists — save a short report of what was attempted to the "
                    "workspace and call terminate."
                )
            )

    async def execute_tool(self, command: ToolCall) -> str:
        """Execute a single tool call with robust error handling"""
        if not command or not command.function or not command.function.name:
            return "Error: Invalid command format"

        name = command.function.name
        if name not in self.available_tools.tool_map:
            return f"Error: Unknown tool '{name}'"

        try:
            # Parse arguments
            args = json.loads(command.function.arguments or "{}")

            # Execute the tool
            logger.info(f"🔧 Activating tool: '{name}'...")
            result = await self.available_tools.execute(name=name, tool_input=args)
            self._audit(name, args, str(result) if result else "")

            # Handle special tools
            await self._handle_special_tool(name=name, result=result)

            # Check if result is a ToolResult with base64_image
            if hasattr(result, "base64_image") and result.base64_image:
                # Store the base64_image for later use in tool_message
                self._current_base64_image = result.base64_image

            # Format result for display (standard case)
            observation = (
                f"Observed output of cmd `{name}` executed:\n{str(result)}"
                if result
                else f"Cmd `{name}` completed with no output"
            )

            return observation
        except json.JSONDecodeError:
            error_msg = f"Error parsing arguments for {name}: Invalid JSON format"
            logger.error(
                f"📝 Oops! The arguments for '{name}' don't make sense - invalid JSON, arguments:{command.function.arguments}"
            )
            return f"Error: {error_msg}"
        except Exception as e:
            error_msg = f"⚠️ Tool '{name}' encountered a problem: {str(e)}"
            logger.exception(error_msg)
            return f"Error: {error_msg}"

    async def _handle_special_tool(self, name: str, result: Any, **kwargs):
        """Handle special tool execution and state changes"""
        if not self._is_special_tool(name):
            return

        if self._should_finish_execution(name=name, result=result, **kwargs):
            # Set agent state to finished
            logger.info(f"🏁 Special tool '{name}' has completed the task!")
            self.state = AgentState.FINISHED

    @staticmethod
    def _should_finish_execution(**kwargs) -> bool:
        """Determine if tool execution should finish the agent"""
        return True

    def _is_special_tool(self, name: str) -> bool:
        """Check if tool name is in special tools list"""
        return name.lower() in [n.lower() for n in self.special_tool_names]

    async def cleanup(self):
        """Clean up resources used by the agent's tools."""
        logger.info(f"🧹 Cleaning up resources for agent '{self.name}'...")
        for tool_name, tool_instance in self.available_tools.tool_map.items():
            if hasattr(tool_instance, "cleanup") and asyncio.iscoroutinefunction(
                tool_instance.cleanup
            ):
                try:
                    logger.debug(f"🧼 Cleaning up tool: {tool_name}")
                    await tool_instance.cleanup()
                except Exception as e:
                    logger.error(
                        f"🚨 Error cleaning up tool '{tool_name}': {e}", exc_info=True
                    )
        logger.info(f"✨ Cleanup complete for agent '{self.name}'.")

    async def run(self, request: Optional[str] = None) -> str:
        """Run the agent with cleanup when done."""
        try:
            return await super().run(request)
        finally:
            await self.cleanup()
