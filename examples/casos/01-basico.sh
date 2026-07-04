#!/usr/bin/env bash
# Case básico: cálculo em Python + salvar arquivo. ~1 min.
cd "$(dirname "$0")/../.." || exit 1

.venv/bin/python main.py --max-steps 6 --prompt "Execute EXATAMENTE estes 3 passos, um por vez:
1. python_execute com um código que calcule os 20 primeiros números de Fibonacci e imprima a lista
2. str_replace_editor com command create, path workspace/fibonacci.txt e file_text contendo a lista calculada
3. terminate com status success
Não use navegador nem outros passos."
