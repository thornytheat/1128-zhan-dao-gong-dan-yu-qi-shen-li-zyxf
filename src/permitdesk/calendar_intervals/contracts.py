from dataclasses import asdict, dataclass
from math import isfinite
from typing import Self


COLUMN_LABELS = {
    'district': '辖区',
    'start': '可审起始分钟',
    'end': '可审结束分钟',
    'work': '工作日',
    'closure': '因节假日停办',
    'team': '当值分队',
    'authority': '时段来源',
    'revision': '审批日历版',
}


@dataclass(frozen=True, slots=True)
class OfficeWindow:
    district: str
    start: int
    end: int
    work: bool
    closure: bool
    team: str
    authority: str
    revision: int

    def __post_init__(self):
        if not isinstance(self.district, str) or not self.district.strip():
            raise ValueError("辖区缺失")
        if type(self.start) is not int or not 0 <= self.start <= 50000:
            raise ValueError("可审起始分钟越界")
        if type(self.end) is not int or not 0 <= self.end <= 50000:
            raise ValueError("可审结束分钟越界")
        if type(self.work) is not bool:
            raise ValueError("工作日须为布尔值")
        if type(self.closure) is not bool:
            raise ValueError("因节假日停办须为布尔值")
        if not isinstance(self.team, str) or not self.team.strip():
            raise ValueError("当值分队缺失")
        if not isinstance(self.authority, str) or not self.authority.strip():
            raise ValueError("时段来源缺失")
        if type(self.revision) is not int or not 1 <= self.revision <= 200:
            raise ValueError("审批日历版越界")

    @classmethod
    def parse(cls, row: dict) -> Self:
        try:
            district = row["district"]
            district = district.strip() if isinstance(district, str) else district
            start = row["start"]
            end = row["end"]
            work = row["work"]
            closure = row["closure"]
            team = row["team"]
            team = team.strip() if isinstance(team, str) else team
            authority = row["authority"]
            authority = authority.strip() if isinstance(authority, str) else authority
            revision = row["revision"]
        except (KeyError, TypeError) as error:
            raise ValueError(f"缺少可用的业务字段 {error}") from error
        return cls(
            district=district,
            start=start,
            end=end,
            work=work,
            closure=closure,
            team=team,
            authority=authority,
            revision=revision,
        )

    def as_record(self) -> dict:
        return asdict(self)


@dataclass(frozen=True,slots=True)
class TimeAccount:
    permit: str
    elapsed: int
    paused: int
    allowed: int
    remaining: int
    due: int | None
    overdue: bool
