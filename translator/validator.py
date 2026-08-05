"""
translator/validator.py

QA automática de cada tradução antes de gravar no banco - mesmas
checagens mecânicas de validate_batch.py (placeholders, tags, comandos,
quebras de linha, termos travados do glossário, cluster de menu de boot),
reimplementadas aqui de propósito para operar item a item, em memória,
dentro do loop do worker (validate_batch.py existente opera em lote sobre
arquivo e continua servindo como segunda checagem manual/offline).

Uma falha de validação NUNCA descarta o lote inteiro: o worker (ver
worker.py) usa `validate_batch` para separar itens válidos (gravados
imediatamente) dos inválidos (reenviados isoladamente ao LLM até
item_retry_limit, depois marcados needs_review, nunca perdidos).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .prompt import GlossaryTerm
from .utils import fit_to_byte_length, mechanical_signature

LENGTH_GROWTH_WARNING_THRESHOLD = 1.40


@dataclass
class ItemValidationResult:
    canonical_id: str
    valid: bool
    target: str | None  # já com auto-fix aplicado (ex.: byte-fit de menu de boot)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class BatchValidator:
    def __init__(self, glossary_terms: list[GlossaryTerm]) -> None:
        self._locked_terms = [t for t in glossary_terms if t.locked]

    def validate_item(
        self,
        canonical_id: str,
        source: str,
        target: str | None,
        *,
        menu_boot_suspect: bool = False,
    ) -> ItemValidationResult:
        if target is None:
            return ItemValidationResult(canonical_id, False, None, errors=["tradução ausente na resposta do modelo"])

        errors: list[str] = []
        warnings: list[str] = []
        fixed_target = target

        if source.strip() and not target.strip():
            return ItemValidationResult(canonical_id, False, target, errors=["tradução vazia para original não-vazio"])

        source_sig = mechanical_signature(source)
        target_sig = mechanical_signature(target)

        if source_sig["placeholders"] != target_sig["placeholders"]:
            errors.append(
                f"placeholders divergem: original={source_sig['placeholders']} tradução={target_sig['placeholders']}"
            )
        if source_sig["braces"] != target_sig["braces"]:
            errors.append(f"chaves {{}} divergem: original={source_sig['braces']} tradução={target_sig['braces']}")
        if source_sig["tags"] != target_sig["tags"]:
            errors.append(f"tags divergem: original={source_sig['tags']} tradução={target_sig['tags']}")
        if source_sig["commands"] != target_sig["commands"]:
            errors.append(f"comandos divergem: original={source_sig['commands']} tradução={target_sig['commands']}")
        if source_sig["linebreaks"] != target_sig["linebreaks"]:
            errors.append(
                f"quebras de linha divergem: original={source_sig['linebreaks']} tradução={target_sig['linebreaks']}"
            )

        for term in self._locked_terms:
            source_re = re.compile(r"\b" + re.escape(term.source) + r"\b", re.IGNORECASE)
            if source_re.search(source):
                target_re = re.compile(r"\b" + re.escape(term.target) + r"\b", re.IGNORECASE)
                if not target_re.search(target):
                    errors.append(f"termo travado '{term.source}' não respeitado (esperado '{term.target}')")

        if errors:
            return ItemValidationResult(canonical_id, False, target, errors=errors, warnings=warnings)

        if menu_boot_suspect:
            orig_bytes = len(source.encode("utf-8"))
            trans_bytes = len(target.encode("utf-8"))
            if trans_bytes != orig_bytes:
                fixed_target = fit_to_byte_length(source, target)
                warnings.append(
                    f"cluster de menu de boot: tamanho ajustado automaticamente ({trans_bytes}b -> {orig_bytes}b)"
                )

        if source.strip():
            growth = len(target) / max(1, len(source))
            if growth > LENGTH_GROWTH_WARNING_THRESHOLD:
                warnings.append(f"tradução {growth:.0%} do tamanho do original (acima do esperado ~15-20%)")

        return ItemValidationResult(canonical_id, True, fixed_target, errors=[], warnings=warnings)

    def validate_batch(
        self,
        items: list[tuple[str, str]],  # (canonical_id, source)
        response: dict[str, str],
        menu_boot_suspect_ids: set[str],
    ) -> tuple[list[ItemValidationResult], list[ItemValidationResult]]:
        """Valida cada item do lote contra a resposta do modelo (dict
        canonical_id -> tradução). Retorna (válidos, inválidos) - itens
        cuja chave nem veio na resposta contam como inválidos com
        target=None (resposta incompleta), nunca são descartados
        silenciosamente."""
        valid: list[ItemValidationResult] = []
        invalid: list[ItemValidationResult] = []

        for canonical_id, source in items:
            target = response.get(canonical_id)
            result = self.validate_item(
                canonical_id, source, target,
                menu_boot_suspect=canonical_id in menu_boot_suspect_ids,
            )
            (valid if result.valid else invalid).append(result)

        return valid, invalid
