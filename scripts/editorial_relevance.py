"""Corpus-weighted lexical relevance; no training, network calls or dependencies."""

from __future__ import annotations

import html
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config/editorial_profiles.json"
MAX_TEXT_CHARS = 4000


@dataclass(frozen=True)
class Relevance:
    similarity: float = 0.0
    topic: str = ""
    terms: tuple[str, ...] = ()
    admitted: bool = False
    event_listing: bool = False
    proposed_rank_bonus: float = 0.0
    model_family: bool = False


def load_config(path: Path = DEFAULT_CONFIG) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config["schema_version"] != 1:
        raise ValueError("Unsupported editorial profile schema")
    if config["ranking_mode"] != "shadow":
        raise ValueError("Editorial ranking is currently supported only in shadow mode")
    if not 0 <= config["maximum_rank_bonus"] <= 1:
        raise ValueError("Editorial bonus must be bounded by one point")
    if not config["profiles"] or not config["model_families"]:
        raise ValueError("Editorial profiles and families must not be empty")
    return config


def tokens(
    text: str,
    families: list[str],
    ambiguous: list[str] | None = None,
    *,
    context: str = "",
    variants: dict | None = None,
    non_model_phrases: list[str] | None = None,
    version_formats: dict | None = None,
) -> list[str]:
    text = html.unescape(re.sub(r"<[^>]*>", " ", text[:MAX_TEXT_CHARS])).casefold()
    # Require a whole family/version: Qwen99.2 works, Qwen99foo does not.
    family_pattern = "|".join(re.escape(name) for name in families)

    def replace_family(match: re.Match) -> str:
        extra = match.group("extra")
        if not (match.group("number") or extra) and re.match(
            r"[- ]m?\d", text[match.end() :]
        ):
            return match.group()
        if extra and not any(
            re.fullmatch(pattern, extra)
            for pattern in (version_formats or {}).get(match.group(1), [])
        ):
            return match.group()
        if any(
            re.match(re.escape(phrase) + r"\b", text[match.start() :])
            for phrase in (non_model_phrases or [])
        ):
            return match.group()
        if (
            match.group(1) in (ambiguous or [])
            and not re.search(r"\d", match.group())
            and not (has_ai_context(text) or has_ai_context(context))
            and not re.match(r"[- ]+models?\b", text[match.end() :])
            and not any(
                re.match(rf"[- ]+{re.escape(variant)}\b", text[match.end() :])
                for variant in (variants or {}).get(match.group(1), [])
            )
        ):
            return match.group()
        return " model_family "

    text = re.sub(
        rf"\b({family_pattern})(?:(?P<number>[- ]?\d+(?:\.\d+)*)|"
        rf"(?P<extra>\.\d+(?:\.\d+)*|[- ]m\d+(?:\.\d+)*))?"
        rf"(?![\w]|\.\d)",
        replace_family,
        text,
    )
    words = re.findall(r"[a-z][a-z_]+", text)
    aliases = {"gpus": "gpu", "robots": "robot", "agents": "agent"}
    return [aliases.get(word, word) for word in words]


def has_ai_context(text: str) -> bool:
    """Recognizable AI/compute context; a bare model/agent/transformer isn't enough."""
    text = html.unescape(re.sub(r"<[^>]*>", " ", text[:MAX_TEXT_CHARS])).casefold()
    return bool(
        re.search(
            r"\b(?:ai|agi|llms?|gpt|chatgpt|openai|anthropic|pytorch|cuda|gpus?|rocm|"
            r"inference|tokenizers?|multimodal|interpretability|recommenders?|"
            r"triton|tokenization|fine[- ]tuning)\b|"
            r"\b(?:artificial intelligence|machine learning|language models?|neural networks?|"
            r"deep learning|natural language|reinforcement learning|computer vision|"
            r"vector search|model[- ]distillation|reward hacks?|model weights|context window|"
            r"performance bottleneck|speech synthesis|self[- ]attention|"
            r"cross[- ]attention|attention mechanism)\b|인공지능|\b(?:npm|registries)\b",
            text,
        )
    )


def keyword_admission(title: str, summary: str, keywords: set[str]) -> bool:
    """Context-check fallback keywords without vetoing all unmatched profiles."""
    config = load_config()
    families = set(config["model_families"])
    ambiguous = set(config["ambiguous_fallback_keywords"])
    context = has_ai_context(title) or has_ai_context(summary)
    for keyword in keywords:
        # Family interpretations belong to assess; the fallback must not undo
        # rejection of Claude Monet or Gemini astrology.
        if keyword in families or keyword in {"muse spark", "muse image", "muse video"}:
            continue
        if re.search(r"\b" + re.escape(keyword) + r"\b", title, re.IGNORECASE) and (
            keyword not in ambiguous or context
        ):
            return True
    return False


def assess(rows: list[dict], config: dict | None = None) -> list[Relevance]:
    """Use one bounded document per URL to calculate this pool's IDF weights.

    Eligibility is a fixed anchor/context rule, independent of pool frequency.
    Adaptive similarities are recorded only as experimental ranking features.
    """
    config = load_config() if config is None else config
    families = config["model_families"]
    ambiguous = config.get("ambiguous_model_families", [])
    variants = config.get("model_variants", {})
    titles = [
        set(
            tokens(
                row["title"],
                families,
                ambiguous,
                context=row.get("summary", "")[:MAX_TEXT_CHARS],
                variants=variants,
                non_model_phrases=config.get("non_model_family_phrases", []),
                version_formats=config.get("family_version_formats", {}),
            )
        )
        for row in rows
    ]
    documents = [
        Counter(
            tokens(
                row["title"],
                families,
                ambiguous,
                context=row.get("summary", "")[:MAX_TEXT_CHARS],
                variants=variants,
                non_model_phrases=config.get("non_model_family_phrases", []),
                version_formats=config.get("family_version_formats", {}),
            )
            * 2
            + tokens(row.get("summary", ""), families, ambiguous)
        )
        for row in rows
    ]
    unique = {}
    for row, document in zip(rows, documents):
        unique.setdefault(row["url"], set()).update(document)
    frequency = Counter(term for document in unique.values() for term in document)
    count = len(unique)

    def vector(document: Counter) -> dict[str, float]:
        return {
            term: (1 + math.log(min(occurrences, 3)))
            * (1 + math.log((1 + count) / (1 + frequency[term])))
            for term, occurrences in document.items()
        }

    def norm(vector: dict[str, float]) -> float:
        return math.sqrt(sum(value * value for value in vector.values()))

    profiles = [
        (profile, vector(Counter(profile["description"].split())))
        for profile in config["profiles"]
    ]
    results = []
    for row, title, document in zip(rows, titles, documents):
        # A long or noisy summary must not erase a useful headline match.
        evidence_vectors = [vector(document), vector(Counter(title))]
        best = Relevance()
        admitted = "model_family" in title
        for profile, reference in profiles:
            anchors = title.intersection(profile["anchors"])
            supported_anchors = {
                anchor
                for anchor in anchors
                if anchor not in config["ambiguous_topic_anchors"]
                or (document.keys() & set(profile["supporting_terms"])) - {anchor}
            }
            if not supported_anchors:
                continue
            admitted = True
            for weighted in evidence_vectors:
                overlap = tuple(sorted(weighted.keys() & reference.keys()))
                length = norm(weighted)
                similarity = (
                    sum(weighted[term] * reference[term] for term in overlap)
                    / (length * norm(reference))
                    if length
                    else 0.0
                )
                if similarity > best.similarity:
                    best = Relevance(similarity, profile["name"], overlap)
        # Technical context is independent of configured topic admission.
        # Generic "AI" alone cannot distinguish a protest from a workshop.
        technical_context = (
            admitted
            or bool(
                title
                & {"inference", "training", "llm", "cuda", "gpu", "pytorch", "rocm"}
            )
            or {"machine", "learning"} <= title
            or bool(
                title & {"ai", "model", "models"}
                and title & {"research", "optimization", "evaluation", "engineering"}
            )
        )
        event = bool(re.search(r"/(?:events?|meetups?)/", urlsplit(row["url"]).path))
        results.append(
            Relevance(
                best.similarity,
                best.topic,
                best.terms,
                admitted,
                event and not technical_context,
                min(config["maximum_rank_bonus"], 2 * best.similarity)
                if admitted
                else 0.0,
                model_family="model_family" in title,
            )
        )
    return results
