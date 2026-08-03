# Ferramentas e Tooling

## Lição aprendida: fragmentação de saída

Nas sessões anteriores (`.aider.chat.history.md`), aconteceram dois
problemas que moldam as recomendações abaixo:

1. `openrouter/deepseek/deepseek-r1:free` retornou `404 NotFoundError`
   (modelo gratuito descontinuado/indisponível na hora). Modelos `:free`
   no OpenRouter somem, mudam de slug ou ficam rate-limited sem aviso —
   **não são confiáveis como dependência única** de um pipeline de meses.
2. Com `qwen3-coder:free` e depois `nemotron-3-ultra-550b-a55b:free`, o
   modelo devolveu um relatório em Markdown com cabeçalhos numerados
   (`1.2 Estrutura do JSON`, `7.2 \`glossary.json\``...), e o aider
   interpretou cada cabeçalho como um novo arquivo a criar — resultado: 5
   arquivos-lixo na raiz do repo em vez de um relatório único. Isso é um
   sintoma de usar uma ferramenta de *edição de código orientada a diff*
   para gerar *conteúdo de relatório/tradução em massa*, tarefa para a
   qual ela não foi desenhada.

**Consequência prática**: usar o aider para o que ele é bom
(escrever/manter os scripts Python do pipeline — parser, preprocessador,
validador, repacker) e **não** usar o aider como motor de tradução em lote.
Tradução em lote deve ser uma chamada de API direta, com schema JSON de
saída, feita por um script pequeno e determinístico.

## Ferramentas por etapa

| Etapa | Ferramenta hoje | Ferramenta recomendada |
|---|---|---|
| Unpack `.cpk` | `unpack_cpk.py` (funcional) | manter |
| Parse `.db` → JSON | `dump_texts.py` (funcional) | manter |
| Pré-processamento (dedup, categorização, detecção de não-traduzível) | não existe | novo script Python, puro (sem IA) — regras determinísticas, ver [01-PIPELINE.md](01-PIPELINE.md#etapa-1--pré-processamento-a-construir) |
| Armazenamento de TM/Glossário | JSON solto | ver [05-GLOSSARIO_E_MEMORIA.md](05-GLOSSARIO_E_MEMORIA.md) — considerar SQLite como fonte da verdade com export JSON para git |
| Tradução em lote | aider + modelo `:free` via chat | script Python usando a API OpenRouter (ou Anthropic/OpenAI direto) com **structured outputs / JSON schema**, não edição de arquivo. Ver [03-MODELOS_IA_E_CUSTOS.md](03-MODELOS_IA_E_CUSTOS.md) |
| Validação de lote | manual/nenhuma | `validate_batch.py` — checagem de placeholders, tags, glossário, tamanho |
| Revisão humana | nenhuma interface | ver opção de UI abaixo |
| Repack `.db`/`.cpk` | não existe | a construir e **validar com round-trip antes de traduzir em massa** — ver [04-RISCOS_TECNICOS.md](04-RISCOS_TECNICOS.md) |
| Controle de progresso/versão | git no `Data/Packages` | manter git, mas considerar mover os `.cpk`/`.cpkh` (binários de GBs) para fora do controle de versão — ver nota abaixo |

## Nota sobre o repositório git atual

O `git status` mostra os `.cpk`/`.cpkh` (arquivos do jogo, alguns de vários
GB — `Worlds_Main_0.cpk` tem 5GB) como *untracked*. Bom, não commitar isso.
Recomendo formalizar num `.gitignore`:

```gitignore
.aider*
*.cpk
*.cpkh
Extracted_Loc_En/
```

Só o que é *seu trabalho de tradução* (scripts, JSON de dump/TM/glossário,
docs) deveria estar no git. Os assets do jogo, não — além do tamanho, é
conteúdo protegido por direitos autorais da Cyanide/Big Bad Wolf/Focus
Entertainment (ver [06-ROADMAP.md](06-ROADMAP.md#nota-legal-distribuição)
sobre como isso afeta a distribuição do resultado final).

## Interface de revisão humana (opcional, mas recomendável a partir de ~5k strings)

Editar `translation_memory.json` na mão para 21.836 strings únicas não é
viável. Duas opções, em ordem de esforço:

1. **Planilha (mínimo esforço)**: exportar lotes para CSV/XLSX
   (original | tradução sugerida | categoria | status) e revisar em
   Excel/Google Sheets, reimportando depois. Rápido de montar, funciona
   sozinho ou com colaboradores não-técnicos.
2. **Ferramenta de tradução dedicada (OmegaT ou Weblate)**: se o projeto
   crescer e você quiser trazer outros tradutores da comunidade, essas
   ferramentas já resolvem TM, glossário, progresso por arquivo e
   múltiplos revisores — evita reinventar isso em JSON solto. Overhead de
   setup maior, só compensa se o projeto for colaborativo.

Para uso solo no começo, planilha é suficiente e mais rápido de começar.

## Sobre skills/automação neste ambiente (Claude Code)

Dá para empacotar as regras que você já definiu (não traduzir
placeholders, nomes próprios, formato de lote, checklist de QA) como uma
**skill reutilizável** em vez de reescrever o prompt em cada sessão. Na
prática:

- `pt-br/prompts/translation_system_prompt.md` — o prompt de sistema fixo
  para tradução em lote (a extrair do histórico do aider), usado pelo
  script de tradução, não por uma sessão de chat manual.
- Uma skill de projeto (`.claude/skills/`) que sabe rodar o pipeline
  (pré-processar → traduzir lote N → validar → relatório) sob comando, se
  você quiser que eu (ou outra instância do Claude Code) execute etapas do
  pipeline de forma consistente entre sessões. Não criei isso ainda —
  proponho como próximo passo depois que o repack estiver provado (Fase 0
  do roadmap), porque não faz sentido automatizar tradução em massa antes
  de saber que dá pra reinjetar o resultado no jogo.
