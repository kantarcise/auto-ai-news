"""Reviewed topic-word matches shared by collection and offline comparisons."""

import re

# Proposed additions, chosen using the October 6 owner feedback. Small tested additions, not a quality classifier.
TOPICS = {
    "versioned model name": r"\b(?:qwen|gpt|llama|claude|gemini|deepseek|mistral)[- ]?\d+(?:\.\d+)*(?![\w]|\.\d)",
    "framework or GPU term": r"\b(?:pytorch|gpus?|cuda|rocm)\b",
    "vector search": r"\bvector\s+search\b",
}


def topic_matches(title: str) -> list[str]:
    return [
        name
        for name, pattern in TOPICS.items()
        if re.search(pattern, title, re.IGNORECASE)
    ]
