"""意图分类器 — 入口安全过滤。

流程:
1. 接收用户自然语言输入
2. 调用Qwen2.5-0.5B做多标签分类（模型不可用时降级为正则匹配）
3. 根据阈值判定 safe / unsafe / needs-review
4. 返回 IntentClassification 结果
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from .model import INTENT_MAPPING, IntentModel

IntentResult = Literal["safe", "unsafe", "needs-review"]

SAFE_THRESHOLD = 0.6
NEEDS_REVIEW_THRESHOLD = 0.4

# 正则降级规则（模型不可用时使用）
_UNSAFE_PATTERNS = [
    (r"rm\s+(-rf?|--recursive)", "unsafe_file_delete"),
    (r"mkfs", "unsafe_system_modify"),
    (r"dd\s+if=", "unsafe_system_modify"),
    (r"chmod\s+777", "unsafe_system_modify"),
    (r">\s*/dev/sd", "unsafe_system_modify"),
    (r"kill\s+-9", "unsafe_process_kill"),
    (r"killall", "unsafe_process_kill"),
    (r"userdel|useradd", "unsafe_user_mgmt"),
    (r"passwd\s+root", "unsafe_privilege_escalation"),
    (r"sudo\s+su|sudo\s+bash", "unsafe_privilege_escalation"),
    (r"/etc/shadow|/etc/passwd", "needs_review_sensitive"),
    (r"/root/\.ssh", "needs_review_sensitive"),
    (r"nmap|masscan", "unsafe_network_scan"),
    (r"iptables\s+-F", "unsafe_system_modify"),
]
_SAFE_PATTERNS = [
    (r"查看|查询|看看|显示|查看|状态|信息|列表", "safe_system_info"),
    (r"df\s|disk|磁盘|空间|存储", "safe_file_read"),
    (r"cpu|内存|mem|进程|ps\s|top", "safe_system_info"),
    (r"日志|log|journalctl", "safe_file_read"),
    (r"服务|service|systemctl\s+status", "safe_service_query"),
    (r"端口|网络|netstat|ss\s|ping", "safe_system_info"),
    (r"rpm\s+-[qQ]|yum\s+list|dnf\s+list|apt\s+list", "safe_package_query"),
]


def _regex_classify(query: str) -> dict:
    """正则降级分类器，模型不可用时使用。"""
    for pattern, label in _UNSAFE_PATTERNS:
        if re.search(pattern, query, re.IGNORECASE):
            return {"labels": [label, "safe_system_info"], "scores": [0.95, 0.05]}
    for pattern, label in _SAFE_PATTERNS:
        if re.search(pattern, query, re.IGNORECASE):
            return {"labels": [label, "unsafe_system_modify"], "scores": [0.9, 0.1]}
    # 无法判断时标记为 needs-review
    return {"labels": ["needs_review_sensitive", "safe_system_info"], "scores": [0.6, 0.4]}


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
            try:
                self._model.load()
                self._loaded = True
            except Exception as e:
                print(f"[意图分类器] 模型加载失败，使用正则降级: {e}")
                self._loaded = True  # 标记为已加载，不再重试

    def classify(self, query: str) -> IntentClassification:
        self.load()
        # 优先使用正则分类器（快速可靠）
        result = _regex_classify(query)
        top_label: str = result["labels"][0]
        top_score: float = result["scores"][0]
        # 如果正则无法判断（needs_review），且模型可用，再用模型
        if "needs_review" in top_label and self._model._pipeline is not None:
            try:
                model_result = self._model.classify(query)
                model_label = model_result["labels"][0]
                model_mapped = INTENT_MAPPING.get(model_label, "needs-review")
                # 模型结果只有在判定为 safe 时才采纳
                if model_mapped == "safe":
                    result = model_result
            except Exception:
                pass  # 模型推理失败，继续用正则结果

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
