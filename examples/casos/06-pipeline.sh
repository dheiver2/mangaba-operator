#!/usr/bin/env bash
# Case pipeline: tarefa grande dividida em fases com contexto limpo. ~5-10 min.
# Estratégia certa pra tarefas que estouram a janela de 8k numa execução única.
# Gere o áudio antes:
#   say -v Luciana -o workspace/reuniao.wav --data-format=LEI16@16000 "Sua fala aqui"
cd "$(dirname "$0")/../.." || exit 1

.venv/bin/python pipeline.py --max-steps 6 \
  --prompt "Gerar um briefing a partir do áudio workspace/reuniao.wav" \
  --fases "transcrever workspace/reuniao.wav com transcribe_audio; ler a transcrição em workspace/cache e criar workspace/temas.md com os temas citados; criar workspace/briefing.md juntando transcrição e temas num briefing curto"

# Sem --fases, o próprio modelo planeja as fases a partir do --prompt.
