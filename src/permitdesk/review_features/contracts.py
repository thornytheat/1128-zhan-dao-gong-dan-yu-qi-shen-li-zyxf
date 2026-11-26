from dataclasses import asdict, dataclass
from math import isfinite
from typing import Self


COLUMN_LABELS = {
    'key': '样本许可号',
    'district': '辖区',
    'road_class': '道路等级',
    'work': '施工类型',
    'elapsed': '已用审理分钟',
    'allowed': '法定审理分钟',
    'length': '围挡米',
    'lanes': '占用车道数',
    'missing': '未收齐材料件',
    'anticipated': '截面已知的任务数',
    'urgent': '应急抢修',
    'recorded': '截面分钟',
    'closed': '判定分钟',
    'late': '实际超时',
}


@dataclass(frozen=True, slots=True)
class CaseObservation:
    key: str
    district: str
    road_class: str
    work: str
    elapsed: int
    allowed: int
    length: int
    lanes: int
    missing: int
    anticipated: int
    urgent: bool
    recorded: int
    closed: int
    late: bool

    def __post_init__(self):
        if not isinstance(self.key, str) or not self.key.strip():
            raise ValueError("样本许可号缺失")
        if not isinstance(self.district, str) or not self.district.strip():
            raise ValueError("辖区缺失")
        if not isinstance(self.road_class, str) or not self.road_class.strip():
            raise ValueError("道路等级缺失")
        if not isinstance(self.work, str) or not self.work.strip():
            raise ValueError("施工类型缺失")
        if type(self.elapsed) is not int or not 0 <= self.elapsed <= 4000:
            raise ValueError("已用审理分钟越界")
        if type(self.allowed) is not int or not 1 <= self.allowed <= 4000:
            raise ValueError("法定审理分钟越界")
        if type(self.length) is not int or not 1 <= self.length <= 5000:
            raise ValueError("围挡米越界")
        if type(self.lanes) is not int or not 1 <= self.lanes <= 16:
            raise ValueError("占用车道数越界")
        if type(self.missing) is not int or not 0 <= self.missing <= 40:
            raise ValueError("未收齐材料件越界")
        if type(self.anticipated) is not int or not 0 <= self.anticipated <= 200:
            raise ValueError("截面已知的任务数越界")
        if type(self.urgent) is not bool:
            raise ValueError("应急抢修须为布尔值")
        if type(self.recorded) is not int or not 0 <= self.recorded <= 50000:
            raise ValueError("截面分钟越界")
        if type(self.closed) is not int or not 0 <= self.closed <= 50000:
            raise ValueError("判定分钟越界")
        if type(self.late) is not bool:
            raise ValueError("实际超时须为布尔值")

    @classmethod
    def parse(cls, row: dict) -> Self:
        try:
            key = row["key"]
            key = key.strip() if isinstance(key, str) else key
            district = row["district"]
            district = district.strip() if isinstance(district, str) else district
            road_class = row["road_class"]
            road_class = road_class.strip() if isinstance(road_class, str) else road_class
            work = row["work"]
            work = work.strip() if isinstance(work, str) else work
            elapsed = row["elapsed"]
            allowed = row["allowed"]
            length = row["length"]
            lanes = row["lanes"]
            missing = row["missing"]
            anticipated = row["anticipated"]
            urgent = row["urgent"]
            recorded = row["recorded"]
            closed = row["closed"]
            late = row["late"]
        except (KeyError, TypeError) as error:
            raise ValueError(f"缺少可用的业务字段 {error}") from error
        return cls(
            key=key,
            district=district,
            road_class=road_class,
            work=work,
            elapsed=elapsed,
            allowed=allowed,
            length=length,
            lanes=lanes,
            missing=missing,
            anticipated=anticipated,
            urgent=urgent,
            recorded=recorded,
            closed=closed,
            late=late,
        )

    def as_record(self) -> dict:
        return asdict(self)


@dataclass(frozen=True,slots=True)
class ReviewVector:
    key: str
    zone: str
    values: tuple[float,...]
    outcome: bool | None
    visible: int
    settled: int | None

@dataclass(frozen=True,slots=True)
class EncodedSamples:
    history: tuple[ReviewVector,...]
    calibration: tuple[ReviewVector,...]
    held_back: tuple[str,...]
