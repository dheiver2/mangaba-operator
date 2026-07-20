<p align="center">
  <img src="assets/logo.svg" width="220" alt="Mangaba Operator"/>
</p>

<h1 align="center">🥭 Mangaba Operator</h1>

<p align="center">
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/Python-3.12+-F97518.svg" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/Made%20in-Brasil-009c3b.svg" alt="Made in Brasil">
</p>

**Mangaba Operator** é um agente de IA autônomo e versátil: você descreve a tarefa em linguagem natural e ele planeja, usa ferramentas (navegador, editor de arquivos, execução de Python, busca na web, MCP) e executa até concluir.

## ✨ Capacidades

- 🧠 **Agente geral** — programação, pesquisa, processamento de arquivos e navegação web
- 🛠️ **Ferramentas integradas** — execução de código Python, shell (bash), editor de arquivos, fetch de páginas como markdown (`fetch_url`), busca web, automação de navegador, visualização de dados
- 🕹️ **Automação web avançada** — além de clique/digitação por índice DOM, coordenadas cruas e ações visuais (`visual_query`/`visual_click`): hover, duplo clique, clique direito, upload de arquivo, preenchimento de formulário em lote (`fill_form`), espera por texto dinâmico (`wait_for_text`), execução de JavaScript (`execute_js`), captura de evidências (`screenshot_save`/`save_page`) e inspeção de elementos (`get_element_info`)
- 👁️🎙️ **Multimodal via Mangaba Gateway** — análise de imagens (`describe_image`, mangaba-vision-q8) e transcrição de áudio (`transcribe_audio`, Whisper)
- 📊 **Documentos empresariais** — gera e lê `.xlsx`, `.docx`, `.pptx` e PDF de verdade (openpyxl, python-docx, python-pptx, reportlab, pypdf/pdfplumber, pandas, matplotlib via `python_execute`)
- 🔌 **MCP (Model Context Protocol)** — conecte ferramentas externas via servidores MCP
- 🤝 **Multi-agente** — fluxos com múltiplos agentes coordenados (`run_flow.py`), incluindo agente de análise de dados
- 🌐 **Protocolo A2A** — interoperabilidade agente-a-agente (`protocol/a2a`)
- 📦 **Sandbox** — execução isolada em Docker/Daytona

## 🚀 Instalação

Requer **Python 3.12+**. Recomendamos [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/dheiver2/mangaba-operator.git
cd mangaba-operator

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

Pra trocar o modelo de uma execução sem editar o config (validado contra o gateway):

```bash
python main.py --model mangaba-pro --prompt "sua tarefa"
```

### 🐙 Janela de contexto grande via GitHub Models (grátis)

Tarefas que estouram a janela de 8k do gateway podem rodar no **GitHub Models** — inferência gratuita da sua conta GitHub com contexto de até **1M tokens** e modelos de ponta. Basta usar um modelo com `/` na flag (o token vem do `gh auth token` ou de `GITHUB_TOKEN`):

```bash
python main.py     --model openai/gpt-4.1-mini --prompt "tarefa grande"
python pipeline.py --model openai/gpt-4.1      --prompt "tarefa gigante"
```

Catálogo completo em `https://models.github.ai/catalog/models` (gpt-4.1 = 1M ctx, gpt-5/o3/o4-mini = 200k). O tier gratuito tem rate limits — use o gateway local pro dia a dia e o GitHub Models pros casos grandes. Config fixa: `config/config.example-model-github.toml`.

### Cobertura do Mangaba Gateway (100%)

| Endpoint do gateway | Uso no Operator |
|---|---|
| `POST /v1/chat/completions` | Cérebro do agente — perfis `[llm]`, `[llm.fast]`, `[llm.vision]` |
| `POST /api/v1/{slug}/image/describe` | Ferramenta `describe_image` |
| `POST /api/v1/{slug}/audio/transcribe` | Ferramenta `transcribe_audio` (Whisper) |
| `POST /api/v1/{slug}/audio/chat` | Ferramenta `audio_chat` (áudio → resposta em 1 chamada) |
| `GET /v1/models` | Validação da flag `--model` |
| `GET /api/v1/health` + `POST /api/v1/{slug}/load` | Pré-carga automática no boot |
| `POST /api/v1/{slug}/text/chat` e `/text/generate` | Cobertos pelo `/v1/chat/completions` (superset com tools/streaming) |

## ▶️ Uso

Agente principal:

```bash
python main.py
```

Digite sua tarefa no terminal e deixe o agente trabalhar. Também é possível passar a tarefa direto:

```bash
python main.py --prompt "pesquise os preços de fibra óptica em Alagoas e gere um relatório em Markdown"
```

### 🏢 Uso empresarial: canais e operação

**Canais** (configure as seções `[email]` e `[webhook]` no `config.toml` — exemplos no `config.example.toml`):
- `read_pdf` — extrai texto e tabelas de contratos, notas fiscais, relatórios (sem config)
- `send_email` — envia e-mail via SMTP; o agente é instruído a nunca enviar sem pedido explícito e destinatário definido pelo usuário
- `notify_webhook` — notificação pra Slack, gateway de WhatsApp, n8n etc.

**Verificação antes da entrega** (padrão Reflexion: gerar → criticar → revisar): um revisor com contexto limpo compara os entregáveis com a tarefa; se reprovar, roda uma rodada de correção com o parecer como feedback:

```bash
python main.py --verificar --prompt "..."
python fila.py run --verificar               # reprovadas são escaladas pro humano
```

**Fila de tarefas** (processamento em série — o gateway atende 1 inferência por vez):

```bash
python fila.py add "Gerar o relatório semanal em workspace/relatorio.xlsx"
python fila.py list
python fila.py run --max-steps 10            # processa tudo; aceita --model e --verificar
```

**Human-in-the-loop embutido no modo autônomo** (`fila.py`):
- Tarefa que falha ou é reprovada pelo revisor → **escalada** via `notify_webhook` com contexto completo (você só é chamado na exceção)
- `send_email` em execução autônoma vira **rascunho** em `workspace/rascunhos/` aguardando aprovação (envio direto só interativo, ou com `allow_autonomous_send = true` no `[email]`)

**Agendamento** — combine a fila com cron (`crontab -e`):

```cron
# processa a fila toda hora / relatório toda segunda 8h
0 * * * * cd ~/Downloads/Projetos/mangaba-operator && .venv/bin/python fila.py run >> workspace/fila/cron.log 2>&1
0 8 * * 1 cd ~/Downloads/Projetos/mangaba-operator && .venv/bin/python fila.py add "Gerar relatório semanal em workspace/"
```

### 🐙 @mangaba nos issues (agente no GitHub Actions)

Mencione **@mangaba** em qualquer issue ou comentário do repositório e o Operator executa a tarefa no runner do GitHub — com **GitHub Models grátis** (token nativo do Actions) e verificação do revisor — e responde no próprio issue com resultado, progresso e artefatos. Restrito a owner/membros/colaboradores. Workflow: `.github/workflows/mangaba.yml`.

### 🎓 Skills empresariais (progressive disclosure)

Ensine padrões da SUA empresa sem estourar o contexto: cada pasta `skills/<nome>/SKILL.md` (frontmatter `name`/`description` + instruções) entra no prompt só como 1 linha de catálogo — o agente lê o arquivo completo quando a tarefa é daquele tipo. Incluídas: `proposta-comercial` e `ata-reuniao`. Crie as suas copiando o formato.

### 🧾 Auditoria

Toda tool call vira uma linha JSON em `workspace/logs/audit.jsonl` (timestamp, agente, passo, ferramenta, argumentos, preview do resultado, flag de erro) — trilha de compliance pronta pra inspeção.

### 🔗 Modo pipeline (tarefas grandes)

Pra tarefas que não cabem numa execução só (janela de 8k do gateway), o pipeline divide em fases — **cada fase roda num agente novo com contexto zerado**, e os resultados passam entre fases pelos arquivos do workspace:

```bash
python pipeline.py --prompt "tarefa grande"                       # o modelo planeja as fases
python pipeline.py --prompt "..." --fases "fase 1; fase 2; ..."   # fases manuais
```

Regra prática: execução única (`main.py`) pra até ~6 passos; pipeline pra qualquer coisa maior ou multi-domínio (áudio + web + relatório).

### 🎙️ Modo voz

Fale a tarefa e o agente executa e responde falando — pipeline 100% local (ffmpeg → Whisper do gateway → agente → `say`):

```bash
python voz.py                # grava 6s do microfone e executa como tarefa
python voz.py --seconds 10   # gravação mais longa
python voz.py --chat         # pergunta e resposta direta, sem agente
python voz.py --file x.wav   # usa um áudio pronto
```

Requer `ffmpeg` (`brew install ffmpeg`) e permissão de microfone no terminal.

Outras formas de execução:

```bash
python run_mcp.py         # versão com ferramentas MCP
python run_flow.py        # fluxo multi-agente (instável)
python run_mcp_server.py  # sobe o servidor MCP do Mangaba Operator
python sandbox_main.py    # agente em sandbox isolado
```

Recursos automáticos a cada execução:

- **Pré-carga do modelo**: o `main.py` aquece o modelo no Mangaba Gateway antes do primeiro passo (sem cold start de minutos).
- **Roteamento inteligente**: passos internos simples (ex. extração de conteúdo do navegador) usam o perfil `[llm.fast]` (`mangaba-lite-q4`), reservando o modelo pesado pro raciocínio.
- **Memória persistente**: o agente lê e grava notas curtas em `workspace/memoria/` entre execuções (aprendizados, preferências — nunca segredos).
- **Recitação de plano**: em tarefas longas o agente mantém `workspace/todo.md` e o plano é reinjetado no fim do contexto a cada passo — evita perder o objetivo (técnica de context engineering do Manus).
- **Cache reversível**: páginas grandes baixadas pela `fetch_url` são salvas integralmente em `workspace/cache/`; o contexto recebe só um preview + o caminho, sem perda de informação.
- **Auto-encolhimento de contexto**: se o histórico estourar a janela do modelo (8192 tokens no gateway), o agente trunca observações antigas e/ou descarta o miolo do histórico (preservando a tarefa e o plano) e repete o passo — em vez de crashar.

### Agente de análise de dados

Pra cases de CSV/gráficos, ative no `config.toml` (deps: `cd app/tool/chart_visualization && npm install`, requer Node 18+):

```toml
[runflow]
use_data_analysis_agent = true
```

E rode via `python run_flow.py`.

### Usar como servidor MCP

O Operator pode virar ferramenta de qualquer cliente MCP (Claude Code, VS Code, chats):

```bash
python run_mcp_server.py
```

Configuração no cliente (ex. `mcp.json`):

```json
{
  "mcpServers": {
    "mangaba-operator": {
      "command": "/caminho/para/mangaba-operator/.venv/bin/python",
      "args": ["/caminho/para/mangaba-operator/run_mcp_server.py"]
    }
  }
}
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
