from dataclasses import asdict, dataclass
from math import isfinite
from typing import Self


COLUMN_LABELS = {
    'permit': '结办许可号',
    'submitted': '入册时点',
    'recorded': '结案录入分钟',
    'late': '是否逾期',
    'signature': '复核签名人',
    'disposition': '工单终态',
    'primary': '首审人员',
    'ticket': '结案流水号',
}


@dataclass(frozen=True, slots=True)
class Closure:
    permit: str
    submitted: int
    recorded: int
    late: bool
    signature: str
    disposition: str
    primary: str
    ticket: str

    def __post_init__(self):
        if not isinstance(self.permit, str) or not self.permit.strip():
            raise ValueError("结办许可号缺失")
        if type(self.submitted) is not int or not 0 <= self.submitted <= 50000:
            raise ValueError("入册时点越界")
        if type(self.recorded) is not int or not 0 <= self.recorded <= 50000:
            raise ValueError("结案录入分钟越界")
        if type(self.late) is not bool:
            raise ValueError("是否逾期须为布尔值")
        if not isinstance(self.signature, str) or not self.signature.strip():
            raise ValueError("复核签名人缺失")
        if not isinstance(self.disposition, str) or not self.disposition.strip():
            raise ValueError("工单终态缺失")
        if not isinstance(self.primary, str) or not self.primary.strip():
            raise ValueError("首审人员缺失")
        if not isinstance(self.ticket, str) or not self.ticket.strip():
            raise ValueError("结案流水号缺失")

    @classmethod
    def parse(cls, row: dict) -> Self:
        try:
            permit = row["permit"]
            permit = permit.strip() if isinstance(permit, str) else permit
            submitted = row["submitted"]
            recorded = row["recorded"]
            late = row["late"]
            signature = row["signature"]
            signature = signature.strip() if isinstance(signature, str) else signature
            disposition = row["disposition"]
            disposition = disposition.strip() if isinstance(disposition, str) else disposition
            primary = row["primary"]
            primary = primary.strip() if isinstance(primary, str) else primary
            ticket = row["ticket"]
            ticket = ticket.strip() if isinstance(ticket, str) else ticket
        except (KeyError, TypeError) as error:
            raise ValueError(f"缺少可用的业务字段 {error}") from error
        return cls(
            permit=permit,
            submitted=submitted,
            recorded=recorded,
            late=late,
            signature=signature,
            disposition=disposition,
            primary=primary,
            ticket=ticket,
        )

    def as_record(self) -> dict:
        return asdict(self)


@dataclass(frozen=True,slots=True)
class HoldoutReport:
    reviews: int
    observed: int
    pos: int
    avg_brier: float | None
    average_precision: float | None
    null_buckets: int
    rows: tuple[dict,...]
