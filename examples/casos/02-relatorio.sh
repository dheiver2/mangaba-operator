#!/usr/bin/env bash
# Case médio: geração de documento estruturado. 2–4 min.
cd "$(dirname "$0")/../.." || exit 1

.venv/bin/python main.py --max-steps 8 --prompt "Execute EXATAMENTE estes 2 passos, um por vez:
1. str_replace_editor com command create, path workspace/proposta.md e file_text contendo uma proposta comercial de provedor de internet para link dedicado 100 Mbps: apresentação, escopo técnico, SLA 99,5%, tabela com 3 planos de preço e condições de contrato, em markdown
2. terminate com status success
Não use navegador nem python_execute."
