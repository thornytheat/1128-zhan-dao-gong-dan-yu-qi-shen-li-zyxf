from dataclasses import asdict, dataclass
from math import isfinite
from typing import Self


COLUMN_LABELS = {
    'handle': '审理员',
    'district': '业务辖区',
    'skills': '允许签审种类',
    'available': '可约分钟',
    'shift_end': '下班分钟',
    'allow_emergency': '签发抢修授权',
    'stock': '最多工单数',
    'paused': '不可约时间',
    'second_sign': '可承接二审',
}


@dataclass(frozen=True, slots=True)
class Reviewer:
    handle: str
    district: str
    skills: tuple
    available: int
    shift_end: int
    allow_emergency: bool
    stock: int
    paused: tuple
    second_sign: bool

    def __post_init__(self):
        if not isinstance(self.handle, str) or not self.handle.strip():
            raise ValueError("审理员缺失")
        if not isinstance(self.district, str) or not self.district.strip():
            raise ValueError("业务辖区缺失")
        if not isinstance(self.skills, tuple):
            raise ValueError("允许签审种类须为序列")
        if type(self.available) is not int or not 0 <= self.available <= 50000:
            raise ValueError("可约分钟越界")
        if type(self.shift_end) is not int or not 0 <= self.shift_end <= 50000:
            raise ValueError("下班分钟越界")
        if type(self.allow_emergency) is not bool:
            raise ValueError("签发抢修授权须为布尔值")
        if type(self.stock) is not int or not 1 <= self.stock <= 40:
            raise ValueError("最多工单数越界")
        if not isinstance(self.paused, tuple):
            raise ValueError("不可约时间须为序列")
        if type(self.second_sign) is not bool:
            raise ValueError("可承接二审须为布尔值")

    @classmethod
    def parse(cls, row: dict) -> Self:
        try:
            handle = row["handle"]
            handle = handle.strip() if isinstance(handle, str) else handle
            district = row["district"]
            district = district.strip() if isinstance(district, str) else district
            skills = row["skills"]
            skills = tuple(skills)
            available = row["available"]
            shift_end = row["shift_end"]
            allow_emergency = row["allow_emergency"]
            stock = row["stock"]
            paused = row["paused"]
            paused = tuple(tuple(span) for span in paused)
            second_sign = row["second_sign"]
        except (KeyError, TypeError) as error:
            raise ValueError(f"缺少可用的业务字段 {error}") from error
        return cls(
            handle=handle,
            district=district,
            skills=skills,
            available=available,
            shift_end=shift_end,
            allow_emergency=allow_emergency,
            stock=stock,
            paused=paused,
            second_sign=second_sign,
        )

    def as_record(self) -> dict:
        return asdict(self)


@dataclass(frozen=True,slots=True)
class Appointment:
    permit: str
    state: str
    reviewer: str | None
    second: str | None
    start: int | None
    finish: int | None
    reason: str

def validate_reviewer(item: Reviewer):
    if item.available>=item.shift_end:
        raise ValueError("审理员班次已倒序")
    if any(len(span)!=2 or span[0]>=span[1] for span in item.paused):
        raise ValueError("审理员不可约时段无效")
