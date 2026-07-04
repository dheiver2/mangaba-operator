---
name: ata-reuniao
description: Padrão para transcrever áudios de reunião e gerar ata formal em .docx
---

# Skill: Ata de Reunião

Use quando o usuário pedir ata, resumo de reunião ou transcrição de áudio de reunião.

## Fluxo
1. `transcribe_audio` no arquivo indicado
2. Gerar `workspace/ata-<data>.docx` com python-docx

## Estrutura obrigatória da ata
1. Título: "Ata de Reunião — <data>"
2. **Participantes**: liste os citados na fala (se nenhum, "[[preencher]]")
3. **Pauta**: temas identificados na transcrição (bullets)
4. **Decisões**: apenas o que foi DECIDIDO (não discussões)
5. **Ações**: tabela Responsável | Ação | Prazo (o que não tiver, "[[a definir]]")
6. **Transcrição completa**: no final, como anexo

## Regras
- Não invente decisões ou prazos que não estão no áudio
- Datas relativas ("amanhã") → converter usando a data atual, anotando a original entre parênteses
