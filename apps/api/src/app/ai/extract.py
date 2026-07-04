"""Knowledge extraction passes (docs/03 §3).

Two implementations behind one contract:

- `OntologyExtractor` — deterministic, driven by the industry pack's
  vocabulary and cue patterns. Runs everywhere (dev/test/CI), and stands as
  the honest floor: ontology-anchored matches are `high` confidence,
  inferences (pain points, rules, steps) are `medium` and therefore land in
  the analyst review queue rather than being silently asserted.
- `LLMExtractor` — Claude with a strict JSON contract, used when a key is
  configured. Its output passes through exactly the same validation and
  evidence checks; a hallucinated element id is dropped, not stored.

Both emit `ExtractedItem`s; the pipeline owns persistence and dedupe.
"""

import json
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from app.ai.providers import NoLLMConfigured, get_llm_provider
from app.logging import get_logger
from app.modules.documents.elements import DocumentElement, ElementKind
from app.modules.documents.models import Document
from app.modules.knowledge.models import Confidence
from app.modules.knowledge.service import EvidenceRef, ExtractedItem
from app.packs import insurance_claims as pack

log = get_logger("extract")

CAMELCASE_SYSTEM = re.compile(r"\b[A-Z][a-z]+[A-Z][a-z]\w*\b")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass
class ExtractionOutput:
    items: list[ExtractedItem] = field(default_factory=list)
    # (process_name, [ordered step items]) — relations are built by the pipeline
    processes: list[tuple[ExtractedItem, list[ExtractedItem]]] = field(default_factory=list)


def _sentence_around(text: str, match: re.Match) -> str:
    sentences = _SENTENCE_SPLIT.split(text)
    offset = 0
    for sentence in sentences:
        if offset <= match.start() < offset + len(sentence) + 1:
            return sentence.strip()
        offset += len(sentence) + 1
    return text[:200]


class OntologyExtractor:
    name = "ontology"

    def extract(self, doc: Document, elements: list[DocumentElement]) -> ExtractionOutput:
        out = ExtractionOutput()
        self._actors(doc, elements, out)
        self._systems(doc, elements, out)
        self._pain_points(doc, elements, out)
        self._business_rules(doc, elements, out)
        self._process(doc, elements, out)
        return out

    def _actors(self, doc, elements, out: ExtractionOutput) -> None:
        seen: dict[str, list[EvidenceRef]] = defaultdict(list)
        for element in elements:
            lower = element.text.lower()
            for canonical, aliases in pack.ACTORS.items():
                if any(alias in lower for alias in aliases) and len(seen[canonical]) < 3:
                    seen[canonical].append(
                        EvidenceRef(element.id, doc.id, element.text[:300])
                    )
        for canonical, evidence in seen.items():
            out.items.append(
                ExtractedItem("actor", canonical, Confidence.high, evidence)
            )

    def _systems(self, doc, elements, out: ExtractionOutput) -> None:
        seen: dict[str, tuple[list[EvidenceRef], bool]] = {}
        for element in elements:
            for name in CAMELCASE_SYSTEM.findall(element.text):
                known = name in pack.SYSTEM_SEEDS
                refs, _ = seen.get(name, ([], known))
                if len(refs) < 3:
                    refs.append(EvidenceRef(element.id, doc.id, element.text[:300]))
                seen[name] = (refs, known)
            lower = element.text.lower()
            for term, canonical in pack.GENERIC_SYSTEM_TERMS.items():
                if term in lower:
                    refs, _ = seen.get(canonical, ([], True))
                    if len(refs) < 3:
                        refs.append(EvidenceRef(element.id, doc.id, element.text[:300]))
                    seen[canonical] = (refs, True)
        for name, (evidence, known) in seen.items():
            out.items.append(
                ExtractedItem(
                    "system", name,
                    Confidence.high if known else Confidence.medium,
                    evidence, novel=not known,
                )
            )

    def _pain_points(self, doc, elements, out: ExtractionOutput) -> None:
        for element in elements:
            for cue, taxonomy in pack.PAIN_CUES:
                match = re.search(cue, element.text, re.I)
                if match:
                    sentence = _sentence_around(element.text, match)
                    out.items.append(
                        ExtractedItem(
                            "pain_point",
                            sentence[:200],
                            Confidence.medium,
                            [EvidenceRef(element.id, doc.id, sentence[:500])],
                            attrs={"taxonomy": taxonomy},
                        )
                    )
                    break  # one pain point per element; the strongest cue wins

    def _business_rules(self, doc, elements, out: ExtractionOutput) -> None:
        if doc.doc_class not in ("policy", "sop"):
            return
        for element in elements:
            if element.kind == ElementKind.heading:
                continue
            match = re.search(pack.RULE_CUES, element.text, re.I)
            if match:
                sentence = _sentence_around(element.text, match)
                if len(sentence) > 30:
                    out.items.append(
                        ExtractedItem(
                            "business_rule",
                            sentence[:200],
                            Confidence.medium,
                            [EvidenceRef(element.id, doc.id, sentence[:500])],
                        )
                    )

    def _process(self, doc, elements, out: ExtractionOutput) -> None:
        if doc.doc_class not in pack.PROCESS_DOC_CLASSES:
            return
        title = next(
            (e.text for e in elements if e.kind == ElementKind.heading), doc.filename
        )
        title = re.sub(
            r"^(standard operating procedure|sop)[:\s]*", "", title, flags=re.I
        ).strip() or doc.filename
        process = ExtractedItem(
            "process", title, Confidence.high,
            [EvidenceRef(elements[0].id, doc.id, title)],
            attrs={"source_document": str(doc.id)},
        )

        # Steps: list items are the strongest signal; fall back to level-2
        # headings for prose-structured SOPs. Local assembly is section-local
        # by design — cross-document stitching is the analyst's canvas (docs/06 M2).
        step_elements = [e for e in elements if e.kind == ElementKind.list_item]
        if not step_elements:
            step_elements = [
                e for e in elements
                if e.kind == ElementKind.heading and (e.meta or {}).get("level", 1) >= 2
            ]
        steps: list[ExtractedItem] = []
        for order, element in enumerate(step_elements[:20]):
            text = element.text
            systems = list(CAMELCASE_SYSTEM.findall(text))
            if re.search(pack.MANUAL_STEP_CUES, text, re.I):
                step_type = "manual"
            elif re.search(pack.DECISION_STEP_CUES, text, re.I):
                step_type = "decision"
            elif systems:
                step_type = "system"
            else:
                # No system touched, no decision made: it's human work.
                step_type = "manual"
            performer = None
            lower = text.lower()
            for canonical, aliases in pack.ACTORS.items():
                if any(alias in lower for alias in aliases):
                    performer = canonical
                    break
            steps.append(
                ExtractedItem(
                    "process_step",
                    text[:200],
                    Confidence.medium,
                    [EvidenceRef(element.id, doc.id, text[:500])],
                    attrs={
                        "order": order,
                        "step_type": step_type,
                        "performer": performer,
                        "systems": systems,
                    },
                )
            )
        if steps:
            out.processes.append((process, steps))


_LLM_SYSTEM = """You extract structured business-analysis entities from documents.
Return ONLY a JSON array. Each item:
{"type": "actor|system|process|process_step|business_rule|pain_point|risk|metric",
 "name": "...", "confidence": "high|medium|low",
 "element_ids": ["uuid", ...],  // ids of elements that evidence this item
 "attrs": {}}
Rules: every item MUST cite element_ids that actually support it. Extract only
what the text states; do not invent. Prefer the ontology vocabulary when the
text matches it, but emit novel entities when the document names things the
ontology lacks."""


class LLMExtractor:
    """Claude-backed pass. Output flows through the same validation: items
    citing unknown element ids are dropped and logged, never stored."""

    name = "llm"

    def extract(self, doc: Document, elements: list[DocumentElement]) -> ExtractionOutput:
        provider = get_llm_provider()
        payload = "\n".join(
            f"[{e.id}] ({e.kind.value}) {e.text[:400]}" for e in elements[:120]
        )
        ontology = ", ".join(sorted(pack.ACTORS)) + "; systems: " + ", ".join(
            pack.SYSTEM_SEEDS
        )
        raw = provider.complete(
            system=_LLM_SYSTEM + f"\nOntology hints: {ontology}",
            user=f"Document: {doc.filename} (class: {doc.doc_class})\n\n{payload}",
            max_tokens=4000,
        )
        valid_ids = {str(e.id) for e in elements}
        out = ExtractionOutput()
        try:
            items = json.loads(raw[raw.index("[") : raw.rindex("]") + 1])
        except (ValueError, json.JSONDecodeError) as exc:
            log.warning("extract.llm_bad_json", doc=str(doc.id), error=str(exc))
            return out
        for item in items:
            ids = [i for i in item.get("element_ids", []) if i in valid_ids]
            if not ids or item.get("type") not in {
                "actor", "system", "process", "process_step",
                "business_rule", "pain_point", "risk", "metric",
            }:
                continue
            out.items.append(
                ExtractedItem(
                    item["type"],
                    str(item.get("name", ""))[:200],
                    Confidence(item.get("confidence", "medium")),
                    [EvidenceRef(uuid.UUID(i), doc.id) for i in ids[:3]],
                    attrs=item.get("attrs") or {},
                )
            )
        return out


def get_extractor():
    try:
        get_llm_provider()
        return LLMExtractor()
    except NoLLMConfigured:
        return OntologyExtractor()
