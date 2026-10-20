"""预算：daily/monthly/total 桶，乐观扣减，超限降级。"""
from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone


class BudgetExceeded(Exception):
    """llm.budget_exceeded"""


class Budget:
    def __init__(self, workspace_id: str, conn: sqlite3.Connection,
                 monthly_limit: float, per_query_limit: float):
        self.workspace_id = workspace_id
        self.conn = conn
        self.monthly_limit = monthly_limit
        self.per_query_limit = per_query_limit

    @staticmethod
    def _period_keys() -> tuple[str, str]:
        now = datetime.now(timezone.utc).astimezone()
        return now.strftime("%Y-%m"), now.strftime("%Y-%m-%d")

    def remaining(self, bucket: str, period: str) -> float:
        row = self.conn.execute(
            "SELECT cost_usd, limit_usd FROM llm_budget WHERE bucket=? AND period_key=?",
            (bucket, period),
        ).fetchone()
        if not row:
            return self.monthly_limit if bucket == "monthly" else 1e9
        return row["limit_usd"] - row["cost_usd"]

    def check(self, estimated: float) -> None:
        if self.monthly_limit <= 0:
            raise BudgetExceeded("预算为 0，LLM 已禁用")
        monthly, daily = self._period_keys()
        if self.remaining("monthly", monthly) < estimated or self.remaining("daily", daily) < estimated:
            raise BudgetExceeded("预算不足")

    def record(self, input_tokens: int, output_tokens: int, cost_usd: float) -> None:
        monthly, daily = self._period_keys()
        now = int(time.time())
        for bucket, period, limit in (
            ("monthly", monthly, self.monthly_limit),
            ("daily", daily, self.monthly_limit / 30),
            ("total", "all", 1e9),
        ):
            self.conn.execute(
                "INSERT INTO llm_budget(bucket,period_key,requests,input_tokens,output_tokens,"
                "cost_usd,limit_usd,updated_at) VALUES (?,?,1,?,?,?,?,?) "
                "ON CONFLICT(bucket) DO UPDATE SET requests=requests+1, "
                "input_tokens=input_tokens+excluded.input_tokens, "
                "output_tokens=output_tokens+excluded.output_tokens, "
                "cost_usd=cost_usd+excluded.cost_usd, updated_at=excluded.updated_at",
                (bucket, period, input_tokens, output_tokens, cost_usd, limit, now),
            )
        self.conn.commit()

    def snapshot(self) -> dict:
        monthly, daily = self._period_keys()
        out = {}
        for bucket, period in (("daily", daily), ("monthly", monthly), ("total", "all")):
            row = self.conn.execute(
                "SELECT requests, input_tokens, output_tokens, cost_usd, limit_usd "
                "FROM llm_budget WHERE bucket=? AND period_key=?",
                (bucket, period),
            ).fetchone()
            out[bucket] = {
                "requests": row["requests"] if row else 0,
                "cost_usd": round(row["cost_usd"], 6) if row else 0.0,
                "limit_usd": row["limit_usd"] if row else 0.0,
            }
        return out


def estimate_cost_usd(input_tokens: int, output_tokens: int,
                      in_price: float = 0.15 / 1e6, out_price: float = 0.60 / 1e6) -> float:
    return input_tokens * in_price + output_tokens * out_price
