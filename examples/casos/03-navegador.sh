#!/usr/bin/env bash
# Case avançado: navegação real (abre janela do Chromium) + extração + arquivo. 2–5 min.
# Pré-requisito (uma vez): .venv/bin/playwright install chromium
cd "$(dirname "$0")/../.." || exit 1

.venv/bin/python main.py --max-steps 8 --prompt "Execute EXATAMENTE estes 4 passos, um por vez:
1. browser_use com action go_to_url e url https://news.ycombinator.com
2. browser_use com action extract_content e goal 'títulos das 10 primeiras notícias'
3. str_replace_editor com command create, path workspace/hn-hoje.md e file_text contendo os títulos extraídos no passo 2
4. terminate com status success
Não role a página, não clique em nada, não use python_execute."
