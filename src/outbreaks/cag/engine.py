from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_KNOWLEDGE_DIR = REPO_ROOT / "knowledge"
WORD_RE = re.compile(r"[a-z0-9]+")
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "be",
    "for",
    "from",
    "how",
    "in",
    "is",
    "of",
    "on",
    "or",
    "should",
    "the",
    "to",
    "we",
    "what",
    "when",
    "with",
}


def tokenize(text: str) -> set[str]:
    return {word for word in WORD_RE.findall(text.lower()) if word not in STOP_WORDS}


def normalize_region_key(region_key: str | None) -> str | None:
    if not region_key:
        return None
    candidate = region_key.strip().lower().replace("-", "_")
    if not re.fullmatch(r"[a-z0-9_]+", candidate):
        raise ValueError("region_key may only contain letters, numbers, underscores, and hyphens.")
    return candidate


def markdown_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                blocks.append(" ".join(current))
                current = []
            continue

        if line.startswith("#"):
            if current:
                blocks.append(" ".join(current))
            current = [line.lstrip("# ").strip()]
            continue

        current.append(line.lstrip("- ").strip())

    if current:
        blocks.append(" ".join(current))
    return [block for block in blocks if block]


@dataclass(frozen=True)
class CAGAnswer:
    answer: str
    used_region: str | None
    cache_type: str


@dataclass(frozen=True)
class CachedPrompt:
    prompt_text: str
    sections: list[str]
    cache_type: str
    region_key: str | None


class DynamicCache:
    """Small in-memory cache for prompt bundles."""

    def __init__(self) -> None:
        self._bundles: dict[str, CachedPrompt] = {}
        self._question_tokens: set[str] = set()

    def get_or_load(self, key: str, loader) -> CachedPrompt:
        if key not in self._bundles:
            self._bundles[key] = loader()
        return self._bundles[key]

    def cleanup_for_question(self) -> None:
        self._question_tokens.clear()

    def set_question(self, question: str) -> None:
        self._question_tokens = tokenize(question)


class CAGEngine:
    def __init__(self, knowledge_dir: Path | None = None) -> None:
        self.knowledge_dir = knowledge_dir or DEFAULT_KNOWLEDGE_DIR
        self.cache = DynamicCache()

    def ask(self, question: str, region_key: str | None = None) -> CAGAnswer:
        prompt = question.strip()
        if not prompt:
            raise ValueError("question must not be empty")

        self.cache.cleanup_for_question()
        self.cache.set_question(prompt)
        bundle = self._load_prompt_bundle(region_key)
        ranked_sections = self._rank_sections(prompt, bundle.sections)
        selected_sections = ranked_sections[:2] or bundle.sections[:2]

        intro = (
            f"Using the regional cache for {bundle.region_key}. "
            if bundle.cache_type == "region"
            else "Using the general cache. "
        )
        answer = intro + "Priority guidance: " + " ".join(selected_sections)
        return CAGAnswer(
            answer=answer.strip(),
            used_region=bundle.region_key,
            cache_type=bundle.cache_type,
        )

    def _load_prompt_bundle(self, region_key: str | None) -> CachedPrompt:
        normalized_region = normalize_region_key(region_key)
        if normalized_region:
            region_path = self.knowledge_dir / "regions" / f"{normalized_region}.md"
            if region_path.exists():
                cache_key = f"region:{normalized_region}"
                return self.cache.get_or_load(
                    cache_key,
                    lambda: self._build_bundle(region_path, normalized_region),
                )

        return self.cache.get_or_load("general", self._build_general_bundle)

    def _build_general_bundle(self) -> CachedPrompt:
        playbook_path = self.knowledge_dir / "playbooks" / "general.md"
        text = playbook_path.read_text(encoding="utf-8")
        return CachedPrompt(
            prompt_text=text,
            sections=markdown_blocks(text),
            cache_type="general",
            region_key=None,
        )

    def _build_bundle(self, region_path: Path, region_key: str) -> CachedPrompt:
        general_bundle = self._build_general_bundle()
        region_text = region_path.read_text(encoding="utf-8")
        prompt_text = general_bundle.prompt_text + "\n\n" + region_text
        return CachedPrompt(
            prompt_text=prompt_text,
            sections=markdown_blocks(prompt_text),
            cache_type="region",
            region_key=region_key,
        )

    def _rank_sections(self, question: str, sections: list[str]) -> list[str]:
        question_tokens = tokenize(question)
        scored_sections: list[tuple[int, int, str]] = []
        for index, section in enumerate(sections):
            overlap = len(question_tokens & tokenize(section))
            if overlap > 0:
                scored_sections.append((overlap, -index, section))

        scored_sections.sort(reverse=True)
        return [section for _, _, section in scored_sections]
