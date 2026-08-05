"""
translator/prompt.py

Construção do prompt de localização enviado ao modelo local. O tom e as
regras de negócio (glossário travado, registro formal moderno, nomes
próprios, ambientação) vêm do prompt já usado/validado no projeto em
pt-br/prompts/translation_system_prompt.md (papel "Tradutor de lote"),
adaptado em dois pontos para um modelo local de 7B rodando via LM Studio
em vez da API da Anthropic:

  1. Formato de saída: objeto JSON chave->valor (`{"id": "tradução"}`) em
     vez de lista de objetos - mais robusto para response_format=json_object
     e para um modelo menor, que erra menos mantendo uma estrutura simples.
  2. Só injeta o subconjunto do glossário relevante para o lote atual (os
     termos cujo `source` aparece em algum texto do lote), não a lista
     inteira - reduz o prompt e a chance de o modelo se distrair com
     termos que não aparecem no lote.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

SYSTEM_PROMPT_TEMPLATE = """\
Você é o tradutor oficial da localização em Português do Brasil de The \
Council (jogo de mistério, investigação, política, sociedades secretas, \
filosofia e ocultismo, ambientado na França do século XVIII - o \
português deve transmitir essa atmosfera).

REGRAS DE TRADUÇÃO
- A tradução deve soar como localização comercial oficial, não tradução \
literal.
- Priorize naturalidade, contexto, consistência e fluidez.
- Não invente informações, não resuma frases, não aumente o tamanho das \
frases sem necessidade.
- Mesmo em textos formais de época, NUNCA use conjugação arcaica de \
"vós" (tendes, sereis, convido-vos, vosso/vossa). Use sempre o \
tratamento formal moderno do português do Brasil (você/o senhor/a \
senhora).

NUNCA TRADUZIR, REMOVER OU ALTERAR
- As chaves de identificação (IDs) do JSON de entrada - devolva exatamente \
as mesmas chaves.
- Placeholders de formatação: %d, %s, %1, %2, %.2f e semelhantes.
- Quebras de linha: \\n, \\t, \\r - preserve a mesma quantidade e posição \
relativa.
- Tags: <color>, </color>, <sprite>, <i>, <b> e semelhantes.
- Comandos embutidos: |NomeQualquer(argumentos).
- Sequências que parecem código de puzzle (ex.: letras isoladas, "Return") \
- se um item parecer isso, traduza o mínimo possível e não invente.
- A quantidade de linhas do texto original (se o original tem N linhas, a \
tradução deve ter N linhas).

NOMES PRÓPRIOS
Preserve exatamente como no original: personagens, organizações e locais \
importantes (ex. Lord Mortimer, Sarah, Emily, Golden Order, Bonaparte). Só \
traduza um nome próprio se ele já estiver definido no glossário abaixo com \
uma tradução explícita.

GLOSSÁRIO (obrigatório, travado - use exatamente esta tradução sempre que \
o termo aparecer)
{glossary_block}

FORMATO DE ENTRADA
Você recebe um objeto JSON no formato {{"id": "texto original"}}.

FORMATO DE SAÍDA (obrigatório)
Responda SOMENTE com um objeto JSON válido, sem markdown, sem comentários, \
sem explicações, no formato {{"id": "texto traduzido"}} - uma chave para \
cada chave recebida, na mesma quantidade, sem adicionar nem remover \
chaves.\
"""

USER_MESSAGE_TEMPLATE = """\
Categoria: {category}

Traduza cada valor do JSON abaixo para português do Brasil, devolvendo um \
JSON no mesmo formato (mesmas chaves):

{items_json}\
"""


@dataclass(frozen=True)
class GlossaryTerm:
    source: str
    target: str
    category: str
    definition: str
    locked: bool = True


def load_glossary_terms(glossary_data: dict) -> list[GlossaryTerm]:
    return [
        GlossaryTerm(
            source=t["source"],
            target=t["target"],
            category=t.get("category", ""),
            definition=t.get("definition", ""),
            locked=t.get("locked", True),
        )
        for t in glossary_data.get("terms", [])
    ]


class PromptBuilder:
    def __init__(self, glossary_terms: list[GlossaryTerm]) -> None:
        # Só termos travados entram no prompt - termos não travados são
        # sugestões, não regras (ver glossary.json: locked=false é
        # planejado, mas hoje todos os 30 termos existentes são locked=true).
        self._locked_terms = [t for t in glossary_terms if t.locked]

    def relevant_glossary(self, texts: list[str]) -> list[GlossaryTerm]:
        """Termos cujo `source` aparece (case-insensitive) em pelo menos
        um texto do lote atual - evita mandar os 30 termos inteiros em
        todo lote."""
        relevant = []
        for term in self._locked_terms:
            needle = term.source.lower()
            if any(needle in text.lower() for text in texts):
                relevant.append(term)
        return relevant

    def _format_glossary_block(self, terms: list[GlossaryTerm]) -> str:
        if not terms:
            return "(nenhum termo do glossário aparece neste lote)"
        return "\n".join(f"- {t.source} -> {t.target} ({t.category}): {t.definition}" for t in terms)

    def system_prompt(self, texts: list[str]) -> str:
        relevant = self.relevant_glossary(texts)
        return SYSTEM_PROMPT_TEMPLATE.format(glossary_block=self._format_glossary_block(relevant))

    def user_message(self, category: str, items: list[tuple[str, str]]) -> str:
        """items: lista de (canonical_id, texto original)."""
        items_json = json.dumps(dict(items), ensure_ascii=False, indent=2)
        return USER_MESSAGE_TEMPLATE.format(category=category, items_json=items_json)
