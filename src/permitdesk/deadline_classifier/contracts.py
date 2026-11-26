from dataclasses import asdict, dataclass
from math import isfinite
from typing import Self


COLUMN_LABELS = {
    'key': '模型版序',
    'ridge': '正则力度',
    'maximum_iterations': '迭代上限',
    'learning_rate': '更新步长',
    'cut_low': '建议阈值',
    'cut_high': '重点阈值',
    'reject': '分布外阈值',
    'low_count': '分桶最低记录数',
}


@dataclass(frozen=True, slots=True)
class ModelPolicy:
    key: str
    ridge: float
    maximum_iterations: int
    learning_rate: float
    cut_low: float
    cut_high: float
    reject: float
    low_count: int

    def __post_init__(self):
        if not isinstance(self.key, str) or not self.key.strip():
            raise ValueError("模型版序缺失")
        if isinstance(self.ridge, bool) or not isinstance(self.ridge, (float, int)):
            raise ValueError("正则力度须为数值")
        if not isfinite(self.ridge) or not 0.0001 <= self.ridge <= 50:
            raise ValueError("正则力度越界")
        if type(self.maximum_iterations) is not int or not 10 <= self.maximum_iterations <= 1000:
            raise ValueError("迭代上限越界")
        if isinstance(self.learning_rate, bool) or not isinstance(self.learning_rate, (float, int)):
            raise ValueError("更新步长须为数值")
        if not isfinite(self.learning_rate) or not 0.001 <= self.learning_rate <= 1:
            raise ValueError("更新步长越界")
        if isinstance(self.cut_low, bool) or not isinstance(self.cut_low, (float, int)):
            raise ValueError("建议阈值须为数值")
        if not isfinite(self.cut_low) or not 0 <= self.cut_low <= 1:
            raise ValueError("建议阈值越界")
        if isinstance(self.cut_high, bool) or not isinstance(self.cut_high, (float, int)):
            raise ValueError("重点阈值须为数值")
        if not isfinite(self.cut_high) or not 0 <= self.cut_high <= 1:
            raise ValueError("重点阈值越界")
        if isinstance(self.reject, bool) or not isinstance(self.reject, (float, int)):
            raise ValueError("分布外阈值须为数值")
        if not isfinite(self.reject) or not 0.1 <= self.reject <= 100:
            raise ValueError("分布外阈值越界")
        if type(self.low_count) is not int or not 1 <= self.low_count <= 500:
            raise ValueError("分桶最低记录数越界")

    @classmethod
    def parse(cls, row: dict) -> Self:
        try:
            key = row["key"]
            key = key.strip() if isinstance(key, str) else key
            ridge = row["ridge"]
            maximum_iterations = row["maximum_iterations"]
            learning_rate = row["learning_rate"]
            cut_low = row["cut_low"]
            cut_high = row["cut_high"]
            reject = row["reject"]
            low_count = row["low_count"]
        except (KeyError, TypeError) as error:
            raise ValueError(f"缺少可用的业务字段 {error}") from error
        return cls(
            key=key,
            ridge=ridge,
            maximum_iterations=maximum_iterations,
            learning_rate=learning_rate,
            cut_low=cut_low,
            cut_high=cut_high,
            reject=reject,
            low_count=low_count,
        )

    def as_record(self) -> dict:
        return asdict(self)


@dataclass(frozen=True,slots=True)
class Model:
    policy: ModelPolicy
    weights: tuple[float,...]
    center: tuple[float,...]
    spread: tuple[float,...]
    buckets: tuple[tuple[float,float,int],...]
    labels: int
    train: int

@dataclass(frozen=True,slots=True)
class RiskNote:
    probability: float
    raw: float
    reliability: str
    label: str
    evidence: tuple[int,...]
