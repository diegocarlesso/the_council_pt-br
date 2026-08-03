# The Council — Localização PT-BR

Projeto de tradução fã-feita do jogo *The Council* para Português do
Brasil. Este ciclo é só planejamento — nenhuma string foi traduzida ainda.

## Documentação
- [docs/00-VISAO_GERAL.md](docs/00-VISAO_GERAL.md) — estado atual, escala
  do trabalho, o que já existe vs. o que falta
- [docs/01-PIPELINE.md](docs/01-PIPELINE.md) — fluxo completo, etapa por
  etapa
- [docs/02-FERRAMENTAS_E_TOOLING.md](docs/02-FERRAMENTAS_E_TOOLING.md) —
  ferramentas por etapa, lição aprendida sobre o aider
- [docs/03-MODELOS_IA_E_CUSTOS.md](docs/03-MODELOS_IA_E_CUSTOS.md) —
  estratégia de modelos de IA e economia de créditos/limites
- [docs/04-RISCOS_TECNICOS.md](docs/04-RISCOS_TECNICOS.md) — riscos que
  podem inviabilizar o projeto se não forem resolvidos cedo (reinjeção no
  jogo é o principal)
- [docs/05-GLOSSARIO_E_MEMORIA.md](docs/05-GLOSSARIO_E_MEMORIA.md) —
  convenções de glossário/TM
- [docs/06-ROADMAP.md](docs/06-ROADMAP.md) — fases do projeto

## Dados de trabalho
- `glossary.json` — termos travados
- `translation_memory.json` — pares original→tradução aprovados
- `json_structure.json` — exemplo da estrutura do dump de localização
- `pipeline.md` — diagrama original (uma linha), superado por `docs/01-PIPELINE.md`
- `puzzle_codes.md` — sequências de puzzle identificadas, não traduzir
- `prompts/translation_system_prompt.md` — prompts de sistema consolidados
  por papel (arquiteto / tradutor de lote / revisor-chefe)

## Próximo passo sugerido
Fase 0 do roadmap: provar que dá para reempacotar `.db`/`.cpk` com texto
alterado e o jogo carregar corretamente — antes de investir em tradução em
massa. Ver [docs/06-ROADMAP.md](docs/06-ROADMAP.md).
