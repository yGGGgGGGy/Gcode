"""意图分类器 — 入口安全过滤。

流程:
1. 接收用户自然语言输入
2. 调用Qwen2.5-0.5B做多标签分类
3. 根据阈值判定 safe / unsafe / needs-review
4. 返回 IntentClassification 结果
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from .model import INTENT_MAPPING, IntentModel

IntentResult = Literal["safe", "unsafe", "needs-review"]

SAFE_THRESHOLD = 0.6
NEEDS_REVIEW_THRESHOLD = 0.4


@dataclass
class IntentClassification:
    query: str
    intent: IntentResult
    confidence: float
    categories: list[str] = field(default_factory=list)
    top_label: str = ""
    model: str = "Qwen/Qwen2.5-0.5B"


class IntentClassifier:
    """意图分类器，三层判定: safe / unsafe / needs-review。"""

    def __init__(self, model: IntentModel | None = None):
        self._model = model or IntentModel()
        self._loaded = False

    def load(self) -> None:
        if not self._loaded:
            self._model.load()
            self._loaded = True

    def classify(self, query: str) -> IntentClassification:
        self.load()
        result = self._model.classify(query)

        top_label: str = result["labels"][0]
        top_score: float = result["scores"][0]

        intent: IntentResult = self._determine_intent(top_label, top_score)

        return IntentClassification(
            query=query,
            intent=intent,
            confidence=top_score,
            categories=self._extract_safe_categories(result),
            top_label=top_label,
        )

    def _determine_intent(self, top_label: str, top_score: float) -> IntentResult:
        mapped = INTENT_MAPPING.get(top_label, "needs-review")
        if mapped == "unsafe":
            return "unsafe"
        if top_score < NEEDS_REVIEW_THRESHOLD:
            return "needs-review"
        if mapped == "needs-review":
            return "needs-review"
        if top_score < SAFE_THRESHOLD:
            return "needs-review"
        return "safe"

    @staticmethod
    def _extract_safe_categories(result: dict) -> list[str]:
        return [label for label in result["labels"] if "safe_" in label]

    def unload(self) -> None:
        self._model.unload()
        self._loaded = False
