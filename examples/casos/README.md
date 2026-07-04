# Casos de exemplo — Mangaba Operator

Scripts prontos pra rodar da raiz do projeto (com o venv ativo). Resultados ficam em `workspace/`.

| Script | Nível | Ferramentas | Duração típica* |
|---|---|---|---|
| `01-basico.sh` | 🟢 Básico | python_execute + editor | ~1 min |
| `02-relatorio.sh` | 🟡 Médio | editor (geração de conteúdo) | 2–4 min |
| `03-navegador.sh` | 🔴 Avançado | browser_use (abre o Chromium) | 2–5 min |

\* com `mangaba-max` (9B) no Mangaba Gateway.

```bash
bash examples/casos/01-basico.sh
```

## Regras de ouro pra prompts com modelos locais (9B)

1. **Passos numerados** — "Execute EXATAMENTE estes N passos, um por vez".
2. **Nomeie as ferramentas** — `browser_use com action go_to_url`, `str_replace_editor com command create`.
3. **Proíba desvios** — "não role a página", "não use python_execute", "não instale nada".
4. **Sempre finalize** — o último passo deve ser `terminate com status success`.
5. **`--max-steps` baixo** (6–10) — limita o estrago se o modelo se perder.
6. **Um objetivo por prompt** — divida tarefas grandes em execuções separadas.
