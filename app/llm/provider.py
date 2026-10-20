"""LLM Provider 抽象：OpenAI 协议统一适配，超时/预算/解析失败全部降级。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

PROMPT_VERSION = "pivot-v1"

PIVOT_PROMPT = """你是本地知识库的查询连接词生成器。只输出 JSON，不解释。
用户原问题：{query}
任务：产出 3-8 个最能扩展检索的关系词/连接词，每个 1-6 个 token，
与问题领域相关、不重复、不含原文整句、不含人名/机密编号。
输出：{{"pivots":["词1","词2",...],"confidence":0.0-1.0}}
示例：问题="服务器频繁重启" -> {{"pivots":["宕机","崩溃","日志","内存溢出","电源","蓝屏"]}}"""


class LLMError(Exception):
    """llm.unavailable / llm.timeout / llm.parse_failed"""


@dataclass
class LLMResult:
    pivots: list[str] = field(default_factory=list)
    confidence: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    degraded: bool = False
    reason: str = ""


def parse_pivots(raw: str) -> tuple[list[str], float]:
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise LLMError("llm.parse_failed")
    data: dict[str, Any] = json.loads(m.group(0))
    pivots = [str(p).strip()[:36] for p in data.get("pivots", []) if str(p).strip()]
    seen: set[str] = set()
    uniq = []
    for p in pivots:
        if p.lower() not in seen:
            seen.add(p.lower())
            uniq.append(p)
    return uniq[:8], float(data.get("confidence", 0.5))


class LLMProvider:
    def __init__(self, endpoint: str, api_key: str, model: str, timeout_ms: int = 8000):
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_ms / 1000

    def generate_pivots(self, query: str) -> LLMResult:
        if not self.endpoint:
            return LLMResult(degraded=True, reason="llm.not_configured")
        prompt = PIVOT_PROMPT.format(query=query[:200])
        try:
            resp = httpx.post(
                f"{self.endpoint}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 64,
                    "temperature": 0.2,
                },
                timeout=self.timeout_s,
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            pivots, conf = parse_pivots(raw)
            return LLMResult(pivots=pivots, confidence=conf,
                             input_tokens=usage.get("prompt_tokens", 0),
                             output_tokens=usage.get("completion_tokens", 0))
        except httpx.TimeoutException:
            return LLMResult(degraded=True, reason="llm.timeout")
        except httpx.HTTPError as e:
            return LLMResult(degraded=True, reason=f"llm.unavailable: {e}")
        except (KeyError, json.JSONDecodeError) as e:
            return LLMResult(degraded=True, reason=f"llm.parse_failed: {e}")
