import asyncio
import base64
import json
import os
from datetime import datetime
from typing import Generic, Optional, TypeVar

from browser_use import Browser as BrowserUseBrowser
from browser_use import BrowserConfig
from browser_use.browser.context import BrowserContext, BrowserContextConfig
from browser_use.dom.service import DomService
from pydantic import Field, field_validator
from pydantic_core.core_schema import ValidationInfo

from app.config import config
from app.llm import LLM, model_supports_images
from app.tool.base import BaseTool, ToolResult
from app.tool.web_search import WebSearch


_BROWSER_DESCRIPTION = """\
A powerful browser automation tool that allows interaction with web pages through various actions.
* This tool provides commands for controlling a browser session, navigating web pages, and extracting information
* It maintains state across calls, keeping the browser session alive until explicitly closed
* Use this when you need to browse websites, fill forms, click buttons, extract content, or perform web searches
* Each action requires specific parameters as defined in the tool's dependencies

Key capabilities include:
* Navigation: Go to specific URLs, go back, search the web, or refresh pages
* Interaction: Click elements, input text, select from dropdowns, send keyboard commands
* Scrolling: Scroll up/down by pixel amount or scroll to specific text
* Content extraction: Extract and analyze content from web pages based on specific goals
* Tab management: Switch between tabs, open new tabs, or close tabs
* Coordinate interaction: Click or drag at raw (x, y) viewport coordinates — works on canvas, maps and pages whose elements are not in the DOM tree
* Vision: 'visual_query' answers questions about the rendered page via screenshot; 'visual_click' locates an element described in natural language and clicks it (requires a multimodal model in the [llm.vision] profile)
* Rich interaction: hover over elements (reveal menus/tooltips), double click and right click by element index or coordinates
* Forms & files: 'fill_form' fills several fields in one call; 'upload_file' attaches a local file to a file input; 'clear_input' empties a field
* Synchronization: 'wait_for_text' blocks until a text appears on the page (dynamic/SPA content)
* Scripting: 'execute_js' runs JavaScript in the page and returns its JSON result
* Artifacts: 'screenshot_save' and 'save_page' persist a full-page screenshot / the page HTML to the workspace
* Introspection: 'get_element_info' returns tag, attributes, value, text and bounding box of an element
* Page survey: 'find_on_page' counts and locates a text with context; 'list_links' lists every link (text + URL)
* Infinite feeds: 'scroll_to_bottom' keeps scrolling until the page stops growing
* Session: 'get_cookies'/'set_cookies' export and restore login sessions between runs
* Device emulation: 'set_viewport' resizes the viewport (mobile/tablet layouts)
* Downloads: 'download_file' fetches a URL with the browser's cookies and saves it to the workspace
* Dialogs: 'handle_dialog' arms auto accept/dismiss for alert/confirm/prompt popups

Note: When using element indices, refer to the numbered elements shown in the current browser state.
Prefer DOM actions (click_element/input_text). Fall back to coordinate/vision actions only when the target is not in the interactive elements list (canvas, maps, custom widgets, broken pages).
"""

Context = TypeVar("Context")


class BrowserUseTool(BaseTool, Generic[Context]):
    name: str = "browser_use"
    description: str = _BROWSER_DESCRIPTION
    parameters: dict = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "go_to_url",
                    "click_element",
                    "input_text",
                    "scroll_down",
                    "scroll_up",
                    "scroll_to_text",
                    "send_keys",
                    "get_dropdown_options",
                    "select_dropdown_option",
                    "go_back",
                    "web_search",
                    "wait",
                    "extract_content",
                    "switch_tab",
                    "open_tab",
                    "close_tab",
                    "click_coordinates",
                    "drag_coordinates",
                    "visual_query",
                    "visual_click",
                    "hover_element",
                    "double_click",
                    "right_click",
                    "upload_file",
                    "fill_form",
                    "wait_for_text",
                    "execute_js",
                    "screenshot_save",
                    "save_page",
                    "get_element_info",
                    "go_forward",
                    "find_on_page",
                    "list_links",
                    "scroll_to_bottom",
                    "clear_input",
                    "get_cookies",
                    "set_cookies",
                    "set_viewport",
                    "download_file",
                    "handle_dialog",
                ],
                "description": "The browser action to perform",
            },
            "url": {
                "type": "string",
                "description": "URL for 'go_to_url', 'open_tab' or 'download_file' actions",
            },
            "index": {
                "type": "integer",
                "description": "Element index for 'click_element', 'input_text', 'get_dropdown_options', 'select_dropdown_option', 'hover_element', 'double_click', 'right_click', 'upload_file' or 'get_element_info' actions",
            },
            "text": {
                "type": "string",
                "description": "Text for 'input_text', 'scroll_to_text', 'select_dropdown_option', 'wait_for_text' or 'find_on_page'; JSON cookie list for 'set_cookies'; 'accept'/'dismiss' for 'handle_dialog'",
            },
            "scroll_amount": {
                "type": "integer",
                "description": "Pixels to scroll (positive for down, negative for up) for 'scroll_down' or 'scroll_up' actions",
            },
            "tab_id": {
                "type": "integer",
                "description": "Tab ID for 'switch_tab' action",
            },
            "query": {
                "type": "string",
                "description": "Search query for 'web_search' action",
            },
            "goal": {
                "type": "string",
                "description": "Extraction goal for 'extract_content', question for 'visual_query', or natural-language description of the target element for 'visual_click'",
            },
            "x": {
                "type": "integer",
                "description": "X viewport coordinate (CSS pixels) for 'click_coordinates'/'drag_coordinates', or viewport WIDTH for 'set_viewport'",
            },
            "y": {
                "type": "integer",
                "description": "Y viewport coordinate (CSS pixels) for 'click_coordinates'/'drag_coordinates', or viewport HEIGHT for 'set_viewport'",
            },
            "x2": {
                "type": "integer",
                "description": "Drag end X coordinate for 'drag_coordinates'",
            },
            "y2": {
                "type": "integer",
                "description": "Drag end Y coordinate for 'drag_coordinates'",
            },
            "keys": {
                "type": "string",
                "description": "Keys to send for 'send_keys' action",
            },
            "seconds": {
                "type": "integer",
                "description": "Seconds to wait for 'wait' action, or timeout for 'wait_for_text' (default 10)",
            },
            "path": {
                "type": "string",
                "description": "File path for 'upload_file' (local file to attach), 'screenshot_save', 'save_page' or 'download_file' (destination; relative paths land in the workspace; optional except for upload_file)",
            },
            "script": {
                "type": "string",
                "description": "JavaScript expression/IIFE for 'execute_js'. Its return value comes back JSON-serialized",
            },
            "fields": {
                "type": "array",
                "description": "For 'fill_form': list of {\"index\": <element index>, \"text\": <value>} objects, filled in order",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer"},
                        "text": {"type": "string"},
                    },
                    "required": ["index", "text"],
                },
            },
        },
        "required": ["action"],
        "dependencies": {
            "go_to_url": ["url"],
            "click_element": ["index"],
            "input_text": ["index", "text"],
            "switch_tab": ["tab_id"],
            "open_tab": ["url"],
            "scroll_down": ["scroll_amount"],
            "scroll_up": ["scroll_amount"],
            "scroll_to_text": ["text"],
            "send_keys": ["keys"],
            "get_dropdown_options": ["index"],
            "select_dropdown_option": ["index", "text"],
            "go_back": [],
            "web_search": ["query"],
            "wait": ["seconds"],
            "extract_content": ["goal"],
            "click_coordinates": ["x", "y"],
            "drag_coordinates": ["x", "y", "x2", "y2"],
            "visual_query": ["goal"],
            "visual_click": ["goal"],
            "hover_element": ["index"],
            "double_click": [],
            "right_click": [],
            "upload_file": ["index", "path"],
            "fill_form": ["fields"],
            "wait_for_text": ["text"],
            "execute_js": ["script"],
            "screenshot_save": [],
            "save_page": [],
            "get_element_info": ["index"],
            "go_forward": [],
            "find_on_page": ["text"],
            "list_links": [],
            "scroll_to_bottom": [],
            "clear_input": ["index"],
            "get_cookies": [],
            "set_cookies": ["text"],
            "set_viewport": ["x", "y"],
            "download_file": ["url"],
            "handle_dialog": [],
        },
    }

    lock: asyncio.Lock = Field(default_factory=asyncio.Lock)
    browser: Optional[BrowserUseBrowser] = Field(default=None, exclude=True)
    context: Optional[BrowserContext] = Field(default=None, exclude=True)
    dom_service: Optional[DomService] = Field(default=None, exclude=True)
    web_search_tool: WebSearch = Field(default_factory=WebSearch, exclude=True)

    # Context for generic functionality
    tool_context: Optional[Context] = Field(default=None, exclude=True)

    # handler ativo de handle_dialog (removido/trocado a cada chamada)
    dialog_handler: Optional[object] = Field(default=None, exclude=True)

    llm: Optional[LLM] = Field(default_factory=LLM)

    @field_validator("parameters", mode="before")
    def validate_parameters(cls, v: dict, info: ValidationInfo) -> dict:
        if not v:
            raise ValueError("Parameters cannot be empty")
        return v

    async def _ensure_browser_initialized(self) -> BrowserContext:
        """Ensure browser and context are initialized."""
        if self.browser is None:
            browser_config_kwargs = {"headless": False, "disable_security": True}

            if config.browser_config:
                from browser_use.browser.browser import ProxySettings

                # handle proxy settings.
                if config.browser_config.proxy and config.browser_config.proxy.server:
                    browser_config_kwargs["proxy"] = ProxySettings(
                        server=config.browser_config.proxy.server,
                        username=config.browser_config.proxy.username,
                        password=config.browser_config.proxy.password,
                    )

                browser_attrs = [
                    "headless",
                    "disable_security",
                    "extra_chromium_args",
                    "chrome_instance_path",
                    "wss_url",
                    "cdp_url",
                ]

                for attr in browser_attrs:
                    value = getattr(config.browser_config, attr, None)
                    if value is not None:
                        if not isinstance(value, list) or value:
                            browser_config_kwargs[attr] = value

            self.browser = BrowserUseBrowser(BrowserConfig(**browser_config_kwargs))

        if self.context is None:
            context_config = BrowserContextConfig()

            # if there is context config in the config, use it.
            if (
                config.browser_config
                and hasattr(config.browser_config, "new_context_config")
                and config.browser_config.new_context_config
            ):
                context_config = config.browser_config.new_context_config

            self.context = await self.browser.new_context(context_config)
            self.dom_service = DomService(await self.context.get_current_page())

        return self.context

    async def execute(
        self,
        action: str,
        url: Optional[str] = None,
        index: Optional[int] = None,
        text: Optional[str] = None,
        scroll_amount: Optional[int] = None,
        tab_id: Optional[int] = None,
        query: Optional[str] = None,
        goal: Optional[str] = None,
        keys: Optional[str] = None,
        seconds: Optional[int] = None,
        x: Optional[int] = None,
        y: Optional[int] = None,
        x2: Optional[int] = None,
        y2: Optional[int] = None,
        path: Optional[str] = None,
        script: Optional[str] = None,
        fields: Optional[list] = None,
        **kwargs,
    ) -> ToolResult:
        """
        Execute a specified browser action.

        Args:
            action: The browser action to perform
            url: URL for navigation or new tab
            index: Element index for click or input actions
            text: Text for input action or search query
            scroll_amount: Pixels to scroll for scroll action
            tab_id: Tab ID for switch_tab action
            query: Search query for Google search
            goal: Extraction goal for content extraction
            keys: Keys to send for keyboard actions
            seconds: Seconds to wait
            **kwargs: Additional arguments

        Returns:
            ToolResult with the action's output or error
        """
        async with self.lock:
            try:
                # FIX: LLMs as vezes enviam indices como string ("28" em vez de 28)
                def _to_int(value):
                    if value is None:
                        return None
                    try:
                        return int(value)
                    except (TypeError, ValueError):
                        return None

                index = _to_int(index)
                scroll_amount = _to_int(scroll_amount)
                tab_id = _to_int(tab_id)
                seconds = _to_int(seconds)
                x = _to_int(x)
                y = _to_int(y)
                x2 = _to_int(x2)
                y2 = _to_int(y2)

                context = await self._ensure_browser_initialized()

                # Get max content length from config
                max_content_length = getattr(
                    config.browser_config, "max_content_length", 2000
                )

                # Navigation actions
                if action == "go_to_url":
                    if not url:
                        return ToolResult(
                            error="URL is required for 'go_to_url' action"
                        )
                    page = await context.get_current_page()
                    await page.goto(url)
                    await page.wait_for_load_state()
                    return ToolResult(output=f"Navigated to {url}")

                elif action == "go_back":
                    await context.go_back()
                    return ToolResult(output="Navigated back")

                elif action == "refresh":
                    await context.refresh_page()
                    return ToolResult(output="Refreshed current page")

                elif action == "web_search":
                    if not query:
                        return ToolResult(
                            error="Query is required for 'web_search' action"
                        )
                    # Execute the web search and return results directly without browser navigation
                    search_response = await self.web_search_tool.execute(
                        query=query, fetch_content=True, num_results=1
                    )
                    # Navigate to the first search result
                    # FIX: busca pode falhar e voltar vazia -> goto("") explode
                    if not getattr(search_response, "results", None):
                        return ToolResult(
                            error=(
                                f"Search for '{query}' returned no results. "
                                "If the goal is YouTube, use 'go_to_url' with "
                                "https://www.youtube.com/results?search_query=YOUR+TERM"
                            )
                        )
                    first_search_result = search_response.results[0]
                    url_to_navigate = first_search_result.url
                    if not url_to_navigate or not str(url_to_navigate).startswith("http"):
                        return ToolResult(
                            error=(
                                f"Search returned an invalid URL: {url_to_navigate!r}. "
                                "Use 'go_to_url' with a full URL."
                            )
                        )

                    page = await context.get_current_page()
                    await page.goto(url_to_navigate)
                    await page.wait_for_load_state()

                    return search_response

                # Element interaction actions
                elif action == "click_element":
                    if index is None:
                        return ToolResult(
                            error="Index is required for 'click_element' action"
                        )
                    element = await context.get_dom_element_by_index(index)
                    if not element:
                        return ToolResult(error=f"Element with index {index} not found")
                    download_path = await context._click_element_node(element)
                    output = f"Clicked element at index {index}"
                    if download_path:
                        output += f" - Downloaded file to {download_path}"
                    return ToolResult(output=output)

                elif action == "input_text":
                    if index is None or not text:
                        return ToolResult(
                            error="Index and text are required for 'input_text' action"
                        )
                    element = await context.get_dom_element_by_index(index)
                    if not element:
                        return ToolResult(error=f"Element with index {index} not found")
                    await context._input_text_element_node(element, text)
                    return ToolResult(
                        output=f"Input '{text}' into element at index {index}"
                    )

                elif action == "scroll_down" or action == "scroll_up":
                    direction = 1 if action == "scroll_down" else -1
                    amount = (
                        scroll_amount
                        if scroll_amount is not None
                        else context.config.browser_window_size["height"]
                    )
                    await context.execute_javascript(
                        f"window.scrollBy(0, {direction * amount});"
                    )
                    return ToolResult(
                        output=f"Scrolled {'down' if direction > 0 else 'up'} by {amount} pixels"
                    )

                elif action == "scroll_to_text":
                    if not text:
                        return ToolResult(
                            error="Text is required for 'scroll_to_text' action"
                        )
                    page = await context.get_current_page()
                    try:
                        locator = page.get_by_text(text, exact=False)
                        await locator.scroll_into_view_if_needed()
                        return ToolResult(output=f"Scrolled to text: '{text}'")
                    except Exception as e:
                        return ToolResult(error=f"Failed to scroll to text: {str(e)}")

                elif action == "send_keys":
                    if not keys:
                        return ToolResult(
                            error="Keys are required for 'send_keys' action"
                        )
                    page = await context.get_current_page()
                    await page.keyboard.press(keys)
                    return ToolResult(output=f"Sent keys: {keys}")

                elif action == "get_dropdown_options":
                    if index is None:
                        return ToolResult(
                            error="Index is required for 'get_dropdown_options' action"
                        )
                    element = await context.get_dom_element_by_index(index)
                    if not element:
                        return ToolResult(error=f"Element with index {index} not found")
                    page = await context.get_current_page()
                    options = await page.evaluate(
                        """
                        (xpath) => {
                            const select = document.evaluate(xpath, document, null,
                                XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                            if (!select) return null;
                            return Array.from(select.options).map(opt => ({
                                text: opt.text,
                                value: opt.value,
                                index: opt.index
                            }));
                        }
                    """,
                        element.xpath,
                    )
                    return ToolResult(output=f"Dropdown options: {options}")

                elif action == "select_dropdown_option":
                    if index is None or not text:
                        return ToolResult(
                            error="Index and text are required for 'select_dropdown_option' action"
                        )
                    element = await context.get_dom_element_by_index(index)
                    if not element:
                        return ToolResult(error=f"Element with index {index} not found")
                    page = await context.get_current_page()
                    await page.select_option(element.xpath, label=text)
                    return ToolResult(
                        output=f"Selected option '{text}' from dropdown at index {index}"
                    )

                # Content extraction actions
                elif action == "extract_content":
                    if not goal:
                        return ToolResult(
                            error="Goal is required for 'extract_content' action"
                        )

                    page = await context.get_current_page()
                    import markdownify

                    # SPAs pesadas: espera o render antes de capturar, e tenta
                    # de novo se o HTML veio praticamente vazio
                    try:
                        await page.wait_for_load_state("networkidle", timeout=8000)
                    except Exception:
                        pass
                    content = markdownify.markdownify(await page.content())
                    if len(content.strip()) < 500:
                        await asyncio.sleep(3)
                        content = markdownify.markdownify(await page.content())
                    if len(content.strip()) < 500:
                        # fallback: texto visível renderizado
                        try:
                            content = await page.inner_text("body")
                        except Exception:
                            content = content
                    if len(content.strip()) < 200:
                        return ToolResult(
                            output=(
                                "The page exposed no extractable content (likely an SPA "
                                "that blocks automation or loads content on "
                                "demand). Do NOT repeat extract_content here: try "
                                "another URL, use fetch_url, or web_search on the topic."
                            )
                        )

                    prompt = f"""\
Your task is to extract the content of the page. You will be given a page and a goal, and you should extract all relevant information around this goal from the page. If the goal is vague, summarize the page. Respond in json format.
Extraction goal: {goal}

Page content:
{content[:max_content_length]}
"""
                    # role "user": provedores OpenAI-compatíveis (incl. Mangaba
                    # Gateway) exigem ao menos uma mensagem de usuário
                    messages = [{"role": "user", "content": prompt}]

                    # Define extraction function schema
                    extraction_function = {
                        "type": "function",
                        "function": {
                            "name": "extract_content",
                            "description": "Extract specific information from a webpage based on a goal",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "extracted_content": {
                                        "type": "object",
                                        "description": "The content extracted from the page according to the goal",
                                        "properties": {
                                            "text": {
                                                "type": "string",
                                                "description": "Text content extracted from the page",
                                            },
                                            "metadata": {
                                                "type": "object",
                                                "description": "Additional metadata about the extracted content",
                                                "properties": {
                                                    "source": {
                                                        "type": "string",
                                                        "description": "Source of the extracted content",
                                                    }
                                                },
                                            },
                                        },
                                    }
                                },
                                "required": ["extracted_content"],
                            },
                        },
                    }

                    # Roteamento: extração é tarefa simples — usa o perfil
                    # [llm.fast] (modelo leve) se configurado, senão o default
                    fast_llm = LLM(config_name="fast")
                    response = await fast_llm.ask_tool(
                        messages,
                        tools=[extraction_function],
                        tool_choice="required",
                    )

                    if response and response.tool_calls:
                        args = json.loads(response.tool_calls[0].function.arguments)
                        extracted_content = args.get("extracted_content", {})
                        return ToolResult(
                            output=f"Extracted from page:\n{extracted_content}\n"
                        )

                    return ToolResult(
                        output=(
                            "No content was extracted from the page. Do NOT repeat the "
                            "same extract_content here — change strategy (scroll to the "
                            "relevant section, another URL, fetch_url, or web_search)."
                        )
                    )

                # Tab management actions
                elif action == "switch_tab":
                    if tab_id is None:
                        return ToolResult(
                            error="Tab ID is required for 'switch_tab' action"
                        )
                    await context.switch_to_tab(tab_id)
                    page = await context.get_current_page()
                    await page.wait_for_load_state()
                    return ToolResult(output=f"Switched to tab {tab_id}")

                elif action == "open_tab":
                    if not url:
                        return ToolResult(error="URL is required for 'open_tab' action")
                    await context.create_new_tab(url)
                    return ToolResult(output=f"Opened new tab with {url}")

                elif action == "close_tab":
                    await context.close_current_tab()
                    return ToolResult(output="Closed current tab")

                # Ações por coordenada — funcionam onde a árvore DOM não
                # alcança (canvas, mapas, widgets custom, páginas quebradas)
                elif action == "click_coordinates":
                    if x is None or y is None:
                        return ToolResult(
                            error="x and y are required for 'click_coordinates' action"
                        )
                    page = await context.get_current_page()
                    await page.mouse.click(x, y)
                    await asyncio.sleep(0.5)
                    return ToolResult(output=f"Clicked at coordinates ({x}, {y})")

                elif action == "drag_coordinates":
                    if None in (x, y, x2, y2):
                        return ToolResult(
                            error="x, y, x2 and y2 are required for 'drag_coordinates' action"
                        )
                    page = await context.get_current_page()
                    await page.mouse.move(x, y)
                    await page.mouse.down()
                    # passos intermediários: mapas/sliders ignoram saltos únicos
                    steps = 12
                    for i in range(1, steps + 1):
                        await page.mouse.move(
                            x + (x2 - x) * i / steps, y + (y2 - y) * i / steps
                        )
                    await page.mouse.up()
                    await asyncio.sleep(0.5)
                    return ToolResult(
                        output=f"Dragged from ({x}, {y}) to ({x2}, {y2})"
                    )

                # Ações visuais — screenshot do viewport interpretado pelo
                # perfil [llm.vision] (exige modelo multimodal)
                elif action in ("visual_query", "visual_click"):
                    if not goal:
                        return ToolResult(
                            error=f"Goal is required for '{action}' action"
                        )
                    vision_llm = LLM(config_name="vision")
                    if not model_supports_images(vision_llm.model):
                        return ToolResult(
                            error=(
                                f"The [llm.vision] profile points to '{vision_llm.model}', "
                                "which does not accept images (the DeepSeek API is text-only). "
                                "Use the DOM actions (click_element/input_text) or "
                                "click_coordinates; to enable vision, configure a "
                                "multimodal model in [llm.vision] in config.toml."
                            )
                        )

                    page = await context.get_current_page()
                    viewport = page.viewport_size or {"width": 1280, "height": 720}
                    # scale="css": imagem 1:1 com as coordenadas do mouse,
                    # mesmo em telas retina
                    screenshot = await page.screenshot(
                        full_page=False,
                        animations="disabled",
                        type="jpeg",
                        quality=70,
                        scale="css",
                    )
                    image_b64 = base64.b64encode(screenshot).decode("utf-8")
                    image_url = f"data:image/jpeg;base64,{image_b64}"

                    if action == "visual_query":
                        answer = await vision_llm.ask_with_images(
                            [
                                {
                                    "role": "user",
                                    "content": (
                                        "You are looking at a screenshot of the visible window of a "
                                        f"web page ({viewport['width']}x{viewport['height']} px). "
                                        f"Answer concisely: {goal}"
                                    ),
                                }
                            ],
                            images=[image_url],
                        )
                        return ToolResult(output=f"Visual answer: {answer}")

                    # visual_click: o modelo devolve as coordenadas do alvo
                    answer = await vision_llm.ask_with_images(
                        [
                            {
                                "role": "user",
                                "content": (
                                    "You are looking at a screenshot of the visible window of a "
                                    f"web page ({viewport['width']}x{viewport['height']} pixels). "
                                    f"Locate the following element: \"{goal}\". "
                                    "Reply ONLY with JSON in the format "
                                    '{"found": true, "x": <int>, "y": <int>} using the '
                                    "center of the element in image pixels, or "
                                    '{"found": false} if it is not visible.'
                                ),
                            }
                        ],
                        images=[image_url],
                    )
                    import re

                    match = re.search(r"\{[^{}]*\}", answer or "")
                    if not match:
                        return ToolResult(
                            error=f"Vision model returned no coordinates: {answer!r}"
                        )
                    try:
                        target = json.loads(match.group(0))
                    except json.JSONDecodeError:
                        return ToolResult(
                            error=f"Vision model returned invalid JSON: {answer!r}"
                        )
                    if not target.get("found"):
                        return ToolResult(
                            output=(
                                f"Element '{goal}' not visible in current viewport. "
                                "Scroll or navigate before retrying visual_click."
                            )
                        )
                    cx = max(0, min(int(target["x"]), viewport["width"] - 1))
                    cy = max(0, min(int(target["y"]), viewport["height"] - 1))
                    await page.mouse.click(cx, cy)
                    await asyncio.sleep(0.5)
                    return ToolResult(
                        output=f"Visually located '{goal}' and clicked at ({cx}, {cy})"
                    )

                # Interações ricas — hover/duplo clique/clique direito, por
                # índice DOM ou coordenada crua
                elif action == "hover_element":
                    if index is None:
                        return ToolResult(
                            error="Index is required for 'hover_element' action"
                        )
                    element = await context.get_dom_element_by_index(index)
                    if not element:
                        return ToolResult(error=f"Element with index {index} not found")
                    page = await context.get_current_page()
                    await page.hover(f"xpath={element.xpath}")
                    await asyncio.sleep(0.5)
                    return ToolResult(output=f"Hovered over element at index {index}")

                elif action in ("double_click", "right_click"):
                    button = "left" if action == "double_click" else "right"
                    page = await context.get_current_page()
                    if index is not None:
                        element = await context.get_dom_element_by_index(index)
                        if not element:
                            return ToolResult(
                                error=f"Element with index {index} not found"
                            )
                        selector = f"xpath={element.xpath}"
                        if action == "double_click":
                            await page.dblclick(selector)
                        else:
                            await page.click(selector, button="right")
                        target = f"element at index {index}"
                    elif x is not None and y is not None:
                        if action == "double_click":
                            await page.mouse.dblclick(x, y)
                        else:
                            await page.mouse.click(x, y, button="right")
                        target = f"coordinates ({x}, {y})"
                    else:
                        return ToolResult(
                            error=f"'{action}' requires an element index or x/y coordinates"
                        )
                    await asyncio.sleep(0.5)
                    verb = "Double-clicked" if action == "double_click" else "Right-clicked"
                    return ToolResult(output=f"{verb} {target}")

                elif action == "upload_file":
                    if index is None or not path:
                        return ToolResult(
                            error="Index and path are required for 'upload_file' action"
                        )
                    if not os.path.isfile(path):
                        return ToolResult(error=f"Local file not found: {path}")
                    element = await context.get_dom_element_by_index(index)
                    if not element:
                        return ToolResult(error=f"Element with index {index} not found")
                    page = await context.get_current_page()
                    try:
                        await page.set_input_files(f"xpath={element.xpath}", path)
                    except Exception as e:
                        return ToolResult(
                            error=(
                                f"Element at index {index} did not accept a file "
                                f"(precisa ser um <input type='file'>): {e}"
                            )
                        )
                    return ToolResult(
                        output=f"Attached '{path}' to file input at index {index}"
                    )

                elif action == "fill_form":
                    # LLMs às vezes mandam a lista como string JSON
                    if isinstance(fields, str):
                        try:
                            fields = json.loads(fields)
                        except json.JSONDecodeError:
                            return ToolResult(
                                error="'fields' must be a JSON list of {index, text}"
                            )
                    if not fields or not isinstance(fields, list):
                        return ToolResult(
                            error="A non-empty 'fields' list is required for 'fill_form'"
                        )
                    filled, errors = [], []
                    for item in fields:
                        f_index = _to_int((item or {}).get("index"))
                        f_text = (item or {}).get("text")
                        if f_index is None or f_text is None:
                            errors.append(f"invalid item: {item!r}")
                            continue
                        element = await context.get_dom_element_by_index(f_index)
                        if not element:
                            errors.append(f"index {f_index} not found")
                            continue
                        try:
                            await context._input_text_element_node(element, str(f_text))
                            filled.append(f_index)
                        except Exception as e:
                            errors.append(f"index {f_index}: {e}")
                    summary = f"Filled {len(filled)} field(s): {filled}"
                    if errors:
                        summary += f" | Failures: {'; '.join(errors)}"
                    return ToolResult(output=summary)

                elif action == "wait_for_text":
                    if not text:
                        return ToolResult(
                            error="Text is required for 'wait_for_text' action"
                        )
                    timeout_s = seconds if seconds else 10
                    page = await context.get_current_page()
                    try:
                        await page.get_by_text(text, exact=False).first.wait_for(
                            state="visible", timeout=timeout_s * 1000
                        )
                        return ToolResult(
                            output=f"Text '{text}' is now visible on the page"
                        )
                    except Exception:
                        return ToolResult(
                            output=(
                                f"Text '{text}' did NOT appear within {timeout_s}s. "
                                "The page may still be loading or the text may never "
                                "render — check the current state before retrying."
                            )
                        )

                elif action == "execute_js":
                    if not script:
                        return ToolResult(
                            error="Script is required for 'execute_js' action"
                        )
                    page = await context.get_current_page()
                    result = await page.evaluate(script)
                    try:
                        rendered = json.dumps(result, ensure_ascii=False, default=str)
                    except (TypeError, ValueError):
                        rendered = repr(result)
                    if len(rendered) > max_content_length:
                        rendered = rendered[:max_content_length] + "… (truncated)"
                    return ToolResult(output=f"JavaScript result: {rendered}")

                # Artefatos — persistem evidências no workspace
                elif action in ("screenshot_save", "save_page"):
                    page = await context.get_current_page()
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    default_name = (
                        f"screenshot_{ts}.png"
                        if action == "screenshot_save"
                        else f"page_{ts}.html"
                    )
                    dest = path or default_name
                    if not os.path.isabs(dest):
                        dest = str(config.workspace_root / dest)
                    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
                    if action == "screenshot_save":
                        await page.screenshot(
                            path=dest, full_page=True, animations="disabled"
                        )
                        return ToolResult(output=f"Saved full-page screenshot to {dest}")
                    html = await page.content()
                    with open(dest, "w", encoding="utf-8") as fh:
                        fh.write(html)
                    return ToolResult(
                        output=f"Saved page HTML ({len(html)} bytes) to {dest}"
                    )

                elif action == "get_element_info":
                    if index is None:
                        return ToolResult(
                            error="Index is required for 'get_element_info' action"
                        )
                    element = await context.get_dom_element_by_index(index)
                    if not element:
                        return ToolResult(error=f"Element with index {index} not found")
                    page = await context.get_current_page()
                    info = await page.evaluate(
                        """
                        (xpath) => {
                            const el = document.evaluate(xpath, document, null,
                                XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                            if (!el) return null;
                            const r = el.getBoundingClientRect();
                            const attrs = {};
                            for (const a of el.attributes) attrs[a.name] = a.value;
                            return {
                                tag: el.tagName.toLowerCase(),
                                attributes: attrs,
                                value: el.value ?? null,
                                text: (el.innerText || '').trim().slice(0, 300),
                                bbox: {x: Math.round(r.x), y: Math.round(r.y),
                                       width: Math.round(r.width), height: Math.round(r.height)},
                                visible: r.width > 0 && r.height > 0,
                                disabled: el.disabled ?? false,
                            };
                        }
                    """,
                        element.xpath,
                    )
                    if info is None:
                        return ToolResult(
                            error=f"Element at index {index} vanished from the DOM"
                        )
                    return ToolResult(
                        output=f"Element info: {json.dumps(info, ensure_ascii=False)}"
                    )

                elif action == "go_forward":
                    page = await context.get_current_page()
                    # go_back do browser_use retorna antes da navegação
                    # completar; um forward imediato acha o histórico em
                    # trânsito e o Playwright devolve None sem erro — retry
                    resp = None
                    for _ in range(3):
                        try:
                            resp = await page.go_forward(
                                timeout=3000, wait_until="domcontentloaded"
                            )
                        except Exception:
                            resp = None
                        if resp is not None:
                            break
                        await asyncio.sleep(0.5)
                    if resp is None:
                        return ToolResult(
                            output=(
                                f"Could not go forward (no forward history). "
                                f"Still at {page.url}"
                            )
                        )
                    return ToolResult(output=f"Navigated forward to {page.url}")

                elif action == "find_on_page":
                    if not text:
                        return ToolResult(
                            error="Text is required for 'find_on_page' action"
                        )
                    page = await context.get_current_page()
                    hits = await page.evaluate(
                        """
                        (needle) => {
                            const body = document.body.innerText || '';
                            const low = body.toLowerCase();
                            const n = needle.toLowerCase();
                            const out = [];
                            let i = low.indexOf(n);
                            while (i !== -1 && out.length < 10) {
                                out.push(body.slice(Math.max(0, i - 60), i + n.length + 60)
                                             .replace(/\\s+/g, ' ').trim());
                                i = low.indexOf(n, i + n.length);
                            }
                            let total = 0; i = low.indexOf(n);
                            while (i !== -1) { total++; i = low.indexOf(n, i + n.length); }
                            return {total, samples: out};
                        }
                    """,
                        text,
                    )
                    if not hits["total"]:
                        return ToolResult(
                            output=f"'{text}' not found in the visible page text"
                        )
                    samples = "\n".join(f"  …{s}…" for s in hits["samples"])
                    return ToolResult(
                        output=(
                            f"Found {hits['total']} occurrence(s) of '{text}':\n{samples}"
                        )
                    )

                elif action == "list_links":
                    page = await context.get_current_page()
                    links = await page.evaluate(
                        """
                        () => Array.from(document.querySelectorAll('a[href]'))
                            .map(a => ({text: (a.innerText || '').trim().slice(0, 80),
                                        href: a.href}))
                            .filter(l => l.href.startsWith('http'))
                    """
                    )
                    # dedup preservando ordem
                    seen, uniq = set(), []
                    for l in links:
                        if l["href"] not in seen:
                            seen.add(l["href"])
                            uniq.append(l)
                    shown = uniq[:60]
                    lines = "\n".join(
                        f"  [{l['text'] or '(sem texto)'}] {l['href']}" for l in shown
                    )
                    extra = f" (+{len(uniq) - 60} omitted)" if len(uniq) > 60 else ""
                    return ToolResult(
                        output=f"{len(uniq)} unique link(s){extra}:\n{lines}"
                    )

                elif action == "scroll_to_bottom":
                    page = await context.get_current_page()
                    last = -1
                    rounds = 0
                    while rounds < 20:
                        height = await page.evaluate(
                            "window.scrollTo(0, document.body.scrollHeight);"
                            "document.body.scrollHeight"
                        )
                        if height == last:
                            break
                        last = height
                        rounds += 1
                        await asyncio.sleep(1.0)  # dá tempo do feed carregar
                    return ToolResult(
                        output=(
                            f"Reached the bottom after {rounds} scroll round(s); "
                            f"final page height {last}px"
                        )
                    )

                elif action == "clear_input":
                    if index is None:
                        return ToolResult(
                            error="Index is required for 'clear_input' action"
                        )
                    element = await context.get_dom_element_by_index(index)
                    if not element:
                        return ToolResult(error=f"Element with index {index} not found")
                    page = await context.get_current_page()
                    await page.fill(f"xpath={element.xpath}", "")
                    return ToolResult(output=f"Cleared input at index {index}")

                # Sessão — exporta/restaura cookies (login entre execuções)
                elif action == "get_cookies":
                    page = await context.get_current_page()
                    cookies = await page.context.cookies()
                    slim = [
                        {k: c.get(k) for k in ("name", "value", "domain", "path")}
                        for c in cookies
                    ]
                    return ToolResult(
                        output=f"{len(slim)} cookie(s): {json.dumps(slim, ensure_ascii=False)[:max_content_length]}"
                    )

                elif action == "set_cookies":
                    if not text:
                        return ToolResult(
                            error=(
                                "'set_cookies' requires 'text' with a JSON list like "
                                '[{"name": "...", "value": "...", "url": "https://site.com"}]'
                            )
                        )
                    try:
                        cookie_list = json.loads(text)
                        assert isinstance(cookie_list, list)
                    except (json.JSONDecodeError, AssertionError):
                        return ToolResult(
                            error="'text' must be a JSON LIST of cookie objects"
                        )
                    page = await context.get_current_page()
                    await page.context.add_cookies(cookie_list)
                    return ToolResult(output=f"Set {len(cookie_list)} cookie(s)")

                elif action == "set_viewport":
                    if x is None or y is None:
                        return ToolResult(
                            error="'set_viewport' requires x (width) and y (height)"
                        )
                    if not (200 <= x <= 3840 and 200 <= y <= 2160):
                        return ToolResult(
                            error="Viewport must be between 200x200 and 3840x2160"
                        )
                    page = await context.get_current_page()
                    await page.set_viewport_size({"width": x, "height": y})
                    return ToolResult(output=f"Viewport set to {x}x{y}")

                elif action == "download_file":
                    if not url:
                        return ToolResult(
                            error="URL is required for 'download_file' action"
                        )
                    page = await context.get_current_page()
                    # request context do navegador: leva os cookies da sessão
                    resp = await page.context.request.get(url)
                    if resp.status >= 400:
                        return ToolResult(
                            error=f"Download failed: HTTP {resp.status} for {url}"
                        )
                    body = await resp.body()
                    name = path or url.split("?")[0].rstrip("/").split("/")[-1] or "download.bin"
                    dest = name if os.path.isabs(name) else str(config.workspace_root / name)
                    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
                    with open(dest, "wb") as fh:
                        fh.write(body)
                    ctype = resp.headers.get("content-type", "?")
                    return ToolResult(
                        output=f"Downloaded {len(body)} bytes ({ctype}) from {url} to {dest}"
                    )

                elif action == "handle_dialog":
                    mode = (text or "accept").strip().lower()
                    if mode not in ("accept", "dismiss"):
                        return ToolResult(
                            error="'handle_dialog' accepts text='accept' or 'dismiss'"
                        )
                    page = await context.get_current_page()
                    if self.dialog_handler is not None:
                        try:
                            page.remove_listener("dialog", self.dialog_handler)
                        except Exception:
                            pass

                    async def _on_dialog(dialog):
                        try:
                            if mode == "accept":
                                await dialog.accept()
                            else:
                                await dialog.dismiss()
                        except Exception:
                            pass

                    page.on("dialog", _on_dialog)
                    self.dialog_handler = _on_dialog
                    return ToolResult(
                        output=f"Armed: future alert/confirm/prompt dialogs will be auto-{mode}ed"
                    )

                # Utility actions
                elif action == "wait":
                    # int(): modelos às vezes passam seconds como string ("2")
                    seconds_to_wait = int(seconds) if seconds is not None else 3
                    await asyncio.sleep(seconds_to_wait)
                    return ToolResult(output=f"Waited for {seconds_to_wait} seconds")

                else:
                    return ToolResult(error=f"Unknown action: {action}")

            except Exception as e:
                return ToolResult(error=f"Browser action '{action}' failed: {str(e)}")

    async def get_current_state(
        self, context: Optional[BrowserContext] = None
    ) -> ToolResult:
        """
        Get the current browser state as a ToolResult.
        If context is not provided, uses self.context.
        """
        try:
            # Use provided context or fall back to self.context
            ctx = context or self.context
            if not ctx:
                return ToolResult(error="Browser context not initialized")

            state = await ctx.get_state()

            # Create a viewport_info dictionary if it doesn't exist
            viewport_height = 0
            if hasattr(state, "viewport_info") and state.viewport_info:
                viewport_height = state.viewport_info.height
            elif hasattr(ctx, "config") and hasattr(ctx.config, "browser_window_size"):
                viewport_height = ctx.config.browser_window_size.get("height", 0)

            # Take a screenshot for the state
            page = await ctx.get_current_page()

            await page.bring_to_front()
            await page.wait_for_load_state()

            screenshot = await page.screenshot(
                full_page=True, animations="disabled", type="jpeg", quality=100
            )

            screenshot = base64.b64encode(screenshot).decode("utf-8")

            # Build the state info with all required fields
            state_info = {
                "url": state.url,
                "title": state.title,
                "tabs": [tab.model_dump() for tab in state.tabs],
                "help": "[0], [1], [2], etc., represent clickable indices corresponding to the elements listed. Clicking on these indices will navigate to or interact with the respective content behind them.",
                "interactive_elements": (
                    state.element_tree.clickable_elements_to_string()
                    if state.element_tree
                    else ""
                ),
                "scroll_info": {
                    "pixels_above": getattr(state, "pixels_above", 0),
                    "pixels_below": getattr(state, "pixels_below", 0),
                    "total_height": getattr(state, "pixels_above", 0)
                    + getattr(state, "pixels_below", 0)
                    + viewport_height,
                },
                "viewport_height": viewport_height,
            }

            return ToolResult(
                output=json.dumps(state_info, indent=4, ensure_ascii=False),
                base64_image=screenshot,
            )
        except Exception as e:
            return ToolResult(error=f"Failed to get browser state: {str(e)}")

    async def cleanup(self):
        """Clean up browser resources."""
        async with self.lock:
            if self.context is not None:
                await self.context.close()
                self.context = None
                self.dom_service = None
            if self.browser is not None:
                await self.browser.close()
                self.browser = None

    def __del__(self):
        """Ensure cleanup when object is destroyed."""
        if self.browser is not None or self.context is not None:
            try:
                asyncio.run(self.cleanup())
            except RuntimeError:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(self.cleanup())
                loop.close()

    @classmethod
    def create_with_context(cls, context: Context) -> "BrowserUseTool[Context]":
        """Factory method to create a BrowserUseTool with a specific context."""
        tool = cls()
        tool.tool_context = context
        return tool
