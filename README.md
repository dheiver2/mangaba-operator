<p align="center">
  <img src="assets/logo.svg" width="220" alt="Mangaba AI"/>
</p>

<h1 align="center">🥭 Mangaba AI — Agente Autônomo</h1>

<p align="center">
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/Python-3.12+-F97518.svg" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/Made%20in-Brasil-009c3b.svg" alt="Made in Brasil">
</p>

**Mangaba AI** é um agente de IA autônomo e versátil: você descreve a tarefa em linguagem natural e ele planeja, usa ferramentas (navegador, editor de arquivos, execução de Python, busca na web, MCP) e executa até concluir.

## ✨ Capacidades

- 🧠 **Agente geral** — programação, pesquisa, processamento de arquivos e navegação web
- 🛠️ **Ferramentas integradas** — execução de código Python, editor de arquivos, automação de navegador, busca web, visualização de dados
- 🔌 **MCP (Model Context Protocol)** — conecte ferramentas externas via servidores MCP
- 🤝 **Multi-agente** — fluxos com múltiplos agentes coordenados (`run_flow.py`), incluindo agente de análise de dados
- 🌐 **Protocolo A2A** — interoperabilidade agente-a-agente (`protocol/a2a`)
- 📦 **Sandbox** — execução isolada em Docker/Daytona

## 🚀 Instalação

Requer **Python 3.12+**. Recomendamos [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/dheiver2/mangaba-agent-ai.git
cd mangaba-agent-ai

uv venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt
```

Ou com conda:

```bash
conda create -n mangaba python=3.12
conda activate mangaba
pip install -r requirements.txt
```

Para automação de navegador (opcional):

```bash
playwright install
```

## ⚙️ Configuração

Crie o arquivo de configuração a partir do exemplo:

```bash
cp config/config.example.toml config/config.toml
```

O provedor padrão é o **Mangaba Gateway** (API OpenAI-compatível com os modelos Mangaba):

```toml
[llm]
model = "mangaba-max"          # 9B · raciocínio (também: mangaba-pro, mangaba-lite-q4)
base_url = "https://walton-undepreciatory-tracee.ngrok-free.dev/v1"
api_key = "mangaba"            # o gateway não exige chave
max_tokens = 4096
temperature = 0.0

[llm.vision]
model = "mangaba-vision-q8"    # multimodal · descreve imagens
base_url = "https://walton-undepreciatory-tracee.ngrok-free.dev/v1"
api_key = "mangaba"
```

Modelos disponíveis em `GET /v1/models`; o gateway suporta function-calling (`tools`) e streaming (SSE). Exemplos para outros provedores (Anthropic, Azure, Google, Ollama) em `config/config.example-model-*.toml`.

## ▶️ Uso

Agente principal:

```bash
python main.py
```

Digite sua tarefa no terminal e deixe o agente trabalhar. Também é possível passar a tarefa direto:

```bash
python main.py --prompt "pesquise os preços de fibra óptica em Alagoas e gere um relatório em Markdown"
```

Outras formas de execução:

```bash
python run_mcp.py         # versão com ferramentas MCP
python run_flow.py        # fluxo multi-agente (instável)
python run_mcp_server.py  # sobe o servidor MCP do Mangaba AI
python sandbox_main.py    # agente em sandbox isolado
```

Para habilitar o agente de análise de dados no fluxo multi-agente, adicione ao `config.toml`:

```toml
[runflow]
use_data_analysis_agent = true
```

Dependências extras em [app/tool/chart_visualization/README.md](app/tool/chart_visualization/README.md).

## 📁 Estrutura

```
app/
├── agent/          # agentes (Mangaba, browser, MCP, SWE, sandbox)
├── tool/           # ferramentas (python_execute, browser_use_tool, editor, busca, gráficos)
├── prompt/         # prompts de sistema
├── mcp/            # servidor MCP
├── sandbox/        # execução isolada em Docker
└── flow/           # orquestração multi-agente
config/             # exemplos de configuração por provedor
protocol/a2a/       # protocolo agente-a-agente
examples/           # casos de uso e benchmarks
```

## 🙏 Créditos

Este projeto é um fork rebrandizado do [OpenManus](https://github.com/FoundationAgents/OpenManus) (MIT), criado pela equipe MetaGPT/FoundationAgents, que por sua vez se apoia em [browser-use](https://github.com/browser-use/browser-use), [crawl4ai](https://github.com/unclecode/crawl4ai) e [anthropic-computer-use](https://github.com/anthropics/anthropic-quickstarts/tree/main/computer-use-demo).

## 📄 Licença

[MIT](LICENSE) — © Mangaba AI. Contém código do projeto OpenManus (MIT, © 2025 manna_and_poem).
