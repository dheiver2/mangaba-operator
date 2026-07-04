---
name: proposta-comercial
description: Padrão obrigatório para orçamentos e propostas comerciais (planilha + documento)
---

# Skill: Proposta Comercial

Use este padrão SEMPRE que gerar orçamento ou proposta comercial.

## Entregáveis obrigatórios
1. `workspace/orcamento-<cliente>.xlsx` — planilha com openpyxl
2. `workspace/proposta-<cliente>.docx` — documento com python-docx

## Padrão da planilha (.xlsx)
- Aba "Planos" com colunas: Plano | Velocidade/Escopo | Valor Mensal (R$) | Prazo Contratual
- Linha de cabeçalho em negrito
- Valores como número (não texto), formato brasileiro

## Padrão do documento (.docx)
Estrutura fixa, nesta ordem:
1. Título: "Proposta Comercial — <Empresa> para <Cliente>"
2. Apresentação (2-3 frases sobre a empresa)
3. Escopo técnico (bullets)
4. Tabela de investimento (mesmos valores da planilha)
5. SLA e suporte (padrão: SLA 99,5%, suporte 24/7)
6. Validade da proposta: 15 dias
7. Fecho: "Atenciosamente, Equipe Comercial"

## Regras
- Nunca invente CNPJ, endereço ou dados bancários — deixe "[[preencher]]"
- Preços: se o usuário não deu, use valores de mercado e marque "(estimativa)"
- Tom: profissional, direto, sem superlativos
