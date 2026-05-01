"""Qwen2.5-0.5B 意图分类模型加载与推理。

使用transformers pipeline做零样本分类，轻量级模型适合做入口过滤。
实际部署时可由CTranslate2/ONNX加速。
"""

from __future__ import annotations

from typing import Any

# 意图标签体系
INTENT_LABELS = [
    "safe_file_read",
    "safe_system_info",
    "safe_process_query",
    "safe_service_query",
    "safe_package_query",
    "unsafe_file_write",
    "unsafe_file_delete",
    "unsafe_process_kill",
    "unsafe_system_modify",
    "unsafe_user_mgmt",
    "unsafe_network_scan",
    "unsafe_privilege_escalation",
    "needs_review_sensitive",
]

INTENT_MAPPING = {
    "safe_file_read": "safe",
    "safe_system_info": "safe",
    "safe_process_query": "safe",
    "safe_service_query": "safe",
    "safe_package_query": "safe",
    "unsafe_file_write": "unsafe",
    "unsafe_file_delete": "unsafe",
    "unsafe_process_kill": "unsafe",
    "unsafe_system_modify": "unsafe",
    "unsafe_user_mgmt": "unsafe",
    "unsafe_network_scan": "unsafe",
    "unsafe_privilege_escalation": "unsafe",
    "needs_review_sensitive": "needs-review",
}


class IntentModel:
    """Qwen2.5-0.5B zero-shot分类器包装器。"""

    def __init__(self, model_name: str = "Qwen/Qwen2.5-0.5B"):
        self._model_name = model_name
        self._pipeline: Any = None

    @property
    def model_name(self) -> str:
        return self._model_name

    def load(self) -> None:
        """延迟加载模型，避免启动时占用内存。"""
        from transformers import pipeline  # type: ignore[import-untyped]

        self._pipeline = pipeline(
            "zero-shot-classification",
            model=self._model_name,
            device=-1,  # CPU，GPU环境改为0
        )

    def classify(self, query: str) -> dict[str, Any]:
        """对用户输入做多标签零样本分类。

        Returns:
            {"labels": [...], "scores": [...]} 按score降序排列
        """
        if self._pipeline is None:
            self.load()
        result = self._pipeline(query, INTENT_LABELS)
        return {"labels": result["labels"], "scores": result["scores"]}

    def unload(self) -> None:
        """释放模型内存。"""
        self._pipeline = None
