# Pausa de trabalho — 2026-08-14 22:53

> Nota manual (não é gerada por script, ao contrário de `PROGRESS.md`).
> Escrita ao pausar a sessão a pedido do usuário. Substitui a nota anterior
> de 2026-08-05 (arquivada no histórico do git se precisar consultar).
> Apague ou reescreva quando o trabalho for retomado de verdade.

## Descoberta importante desta sessão: hardware da GPU

A GPU da máquina é uma **GTX 1650 SUPER com só 4GB de VRAM**. Isso importa
porque o LM Studio, no início desta sessão, estava com dois modelos
grandes carregados (`google/gemma-4-12b-qat`, 12B, e
`qwen/qwen2.5-coder-14b`, 14B) — ambos **inviáveis** nessa GPU: rodam
majoritariamente na CPU e um lote piloto de só 5 strings estourou dois
timeouts de 190s sem terminar.

Baixei e passei a usar **`google/gemma-3n-e4b`** (4.24GB em disco,
arquitetura MoE "effective 4B" — bem mais leve que o nome de 6.9B params
sugere). Resultado: ~3.4s/item, throughput estável de ~17 str/min. É esse
o modelo que deve ser usado daqui pra frente nessa máquina — os modelos de
12-14B **não devem ser recarregados** para tradução em massa (ok pra
tarefas pontuais de código, onde a lentidão importa menos).

Ainda mais leve existia um modelo chamado `gemma-4-e4b` usado com sucesso
antes desta sessão (37.8s para 5 itens, depois 23s/item) — mas não estava
mais no disco (`lms ls` só listava os dois modelos grandes + embedding) e
não foi possível saber sua origem exata. Se ele reaparecer/for
redownloadável, vale comparar velocidade com o `gemma-3n-e4b` atual.

## O que estava rodando e foi parado agora

| Processo | Ação |
|---|---|
| `python -m translator.translate` (worker, `TRANSLATOR_MODEL_NAME=google/gemma-3n-e4b`, batch_size=40, 1 worker) | finalizado (`taskkill /F`) |
| `python -m translator.auto_commit --interval 3600` (instância única) | finalizado (`taskkill /F`) |
| Modelo `google/gemma-3n-e4b` no LM Studio | descarregado (`lms unload --all`) — servidor do LM Studio continua de pé, só sem modelo carregado |

Nenhum processo foi encerrado por `Ctrl+C`/SIGINT — mesma lógica de
sempre: `TranslationMemoryDB` grava item a item no SQLite
(`translation_memory.db`), então `taskkill /F` é seguro, o pior caso é
reprocessar 1 item em voo. Depois do kill rodei:

```bash
python -m translator.translate --export-only   # SQLite -> translation_memory.json
python progress_report.py                       # regenera PROGRESS.md
```

Ambos confirmaram estado consistente (15107 entradas exportadas).

## Estado atual (após a pausa)

- **15107/21806 strings resolvidas (69.3%)** — subiu de 48.2% (10513) no
  início desta sessão. ~4.594 strings novas traduzidas em ~4h30 de
  execução contínua.
- Por status: `approved: 13`, `draft: 15090`, `needs_review: 4`.
- Diálogo: 12617/19293 (65.4%). Sistema, Item e Descontinuado em 100%;
  Teste (23 strings) ainda em 0%, baixa prioridade.
- `git status` limpo, tudo commitado e enviado para `origin/master`
  (auto_commit foi fazendo push a cada hora durante a execução; commit
  final desta pausa também enviado).

## Pendência que alguém precisa olhar (não bloqueia retomada)

**4 strings em `needs_review`**, todas por termo de glossário travado não
respeitado mesmo após 4 tentativas do pipeline:
- 2x `c_687cb3165fd1`/similar — "Lord Mortimer" não preservado como está
- 2x `c_5623842572e3` / `c_e9c118927212` — "The Nightmare" não traduzido
  como "O Pesadelo" (termo travado no glossário)

Taxa de needs_review ficou baixa o processo todo (~0.1%), então não é um
problema sistêmico do modelo — só esses termos específicos que ele
consistentemente erra. Vale corrigir manualmente ou ajustar o prompt/
glossário para esses dois termos antes de reenviar pro pipeline.

## Como retomar

1. **Carregue o modelo certo no LM Studio** (CLI `lms`, já instalado em
   `C:\Users\Diego\.lmstudio\bin\lms`):
   ```bash
   lms load "google/gemma-3n-e4b" -y
   ```
   Confirme com `lms ps` que está `IDLE`/carregado antes de continuar.
   **Não** recarregue `gemma-4-12b-qat` nem `qwen2.5-coder-14b` para
   tradução em massa — são lentos demais nesta GPU de 4GB (ver seção
   acima).
2. Nesta pasta (`Data/Packages`), suba o worker principal (o
   `TRANSLATOR_MODEL_NAME` precisa bater com o identificador do `lms ps`):
   ```bash
   TRANSLATOR_MODEL_NAME="google/gemma-3n-e4b" python -m translator.translate
   # ou, focado em Diálogo (a categoria com pendência real):
   TRANSLATOR_MODEL_NAME="google/gemma-3n-e4b" python -m translator.translate --category "Diálogo"
   ```
3. Auto-commit — **só uma instância**:
   ```bash
   python -m translator.auto_commit --interval 3600
   ```
4. Para checar progresso a qualquer momento sem mexer em nada:
   ```bash
   python -m translator.translate --stats
   python progress_report.py   # regenera pt-br/PROGRESS.md
   ```

Com ~17 str/min sustentado, o restante (6.699 strings) fica em torno de
**~6-7h** de execução contínua.

Ver `pt-br/PROGRESS.md` para o checkpoint numérico sempre atualizado e
`pt-br/README.md` / `pt-br/docs/06-ROADMAP.md` para o contexto completo do
projeto (nota: os docs em `pt-br/docs/03-MODELOS_IA_E_CUSTOS.md` e
`06-ROADMAP.md` descrevem um plano antigo de usar API paga da Anthropic
via `translate_batch.py` — **isso foi substituído na prática** pelo
pipeline local `translator/` + LM Studio, que é o que realmente roda hoje;
os docs não foram atualizados para refletir isso).
