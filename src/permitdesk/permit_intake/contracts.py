from dataclasses import asdict, dataclass
from math import isfinite
from typing import Self


COLUMN_LABELS = {
    'permit': '许可单号',
    'district': '归属辖区',
    'road': '道路编号',
    'work': '施工类别',
    'customer': '申报主体',
    'received': '录入分钟',
    'opened': '收件分钟',
    'version': '受理修订',
    'obstruction': '占道路段米',
    'lanes': '占用车道数',
    'files': '已上传材料',
    'urgent': '应急抢修',
    'withdrawn': '已撤回',
    'planned': '施工计划开工分',
}


@dataclass(frozen=True, slots=True)
class PermitUpdate:
    permit: str
    district: str
    road: str
    work: str
    customer: str
    received: int
    opened: int
    version: int
    obstruction: int
    lanes: int
    files: tuple
    urgent: bool
    withdrawn: bool
    planned: int

    def __post_init__(self):
        if not isinstance(self.permit, str) or not self.permit.strip():
            raise ValueError("许可单号缺失")
        if not isinstance(self.district, str) or not self.district.strip():
            raise ValueError("归属辖区缺失")
        if not isinstance(self.road, str) or not self.road.strip():
            raise ValueError("道路编号缺失")
        if not isinstance(self.work, str) or not self.work.strip():
            raise ValueError("施工类别缺失")
        if not isinstance(self.customer, str) or not self.customer.strip():
            raise ValueError("申报主体缺失")
        if type(self.received) is not int or not 0 <= self.received <= 50000:
            raise ValueError("录入分钟越界")
        if type(self.opened) is not int or not 0 <= self.opened <= 50000:
            raise ValueError("收件分钟越界")
        if type(self.version) is not int or not 1 <= self.version <= 150:
            raise ValueError("受理修订越界")
        if type(self.obstruction) is not int or not 1 <= self.obstruction <= 5000:
            raise ValueError("占道路段米越界")
        if type(self.lanes) is not int or not 1 <= self.lanes <= 16:
            raise ValueError("占用车道数越界")
        if not isinstance(self.files, tuple):
            raise ValueError("已上传材料须为序列")
        if type(self.urgent) is not bool:
            raise ValueError("应急抢修须为布尔值")
        if type(self.withdrawn) is not bool:
            raise ValueError("已撤回须为布尔值")
        if type(self.planned) is not int or not 0 <= self.planned <= 50000:
            raise ValueError("施工计划开工分越界")

    @classmethod
    def parse(cls, row: dict) -> Self:
        try:
            permit = row["permit"]
            permit = permit.strip() if isinstance(permit, str) else permit
            district = row["district"]
            district = district.strip() if isinstance(district, str) else district
            road = row["road"]
            road = road.strip() if isinstance(road, str) else road
            work = row["work"]
            work = work.strip() if isinstance(work, str) else work
            customer = row["customer"]
            customer = customer.strip() if isinstance(customer, str) else customer
            received = row["received"]
            opened = row["opened"]
            version = row["version"]
            obstruction = row["obstruction"]
            lanes = row["lanes"]
            files = row["files"]
            files = tuple(files)
            urgent = row["urgent"]
            withdrawn = row["withdrawn"]
            planned = row["planned"]
        except (KeyError, TypeError) as error:
            raise ValueError(f"缺少可用的业务字段 {error}") from error
        return cls(
            permit=permit,
            district=district,
            road=road,
            work=work,
            customer=customer,
            received=received,
            opened=opened,
            version=version,
            obstruction=obstruction,
            lanes=lanes,
            files=files,
            urgent=urgent,
            withdrawn=withdrawn,
            planned=planned,
        )

    def as_record(self) -> dict:
        return asdict(self)


@dataclass(frozen=True,slots=True)
class Intake:
    active: tuple[PermitUpdate,...]
    log: tuple[dict,...]

def validate_dates(case: PermitUpdate):
    if case.opened>case.received or case.planned<case.opened:
        raise ValueError("施工及受理时钟无效")
    if any(not isinstance(item,str) or not item.strip() for item in case.files):
        raise ValueError("材料名称无效")
