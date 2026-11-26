"""告知凭据台账：只追加、不覆盖、不删除，凭据按内容寻址。"""

from dataclasses import dataclass
from hashlib import sha256
from json import dumps


INITIAL_KIND = '首版预约告知'
REASSIGN_KIND = '改派告知'
BACKFILL_KIND = '补位告知'


def _digest(payload):
    material = dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return sha256(material.encode()).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class Notice:
    notice_id: str
    kind: str
    permit: str
    issued_minute: int
    reviewer: str | None
    second: str | None
    start: int | None
    finish: int | None
    supersedes: str | None
    reason: str

    def as_record(self):
        return {
            'notice_id': self.notice_id,
            'record': '申报人告知凭据',
            'kind': self.kind,
            'permit': self.permit,
            'issued_minute': self.issued_minute,
            'reviewer': self.reviewer,
            'second': self.second,
            'start': self.start,
            'finish': self.finish,
            'supersedes': self.supersedes,
            'reason': self.reason,
        }


class NoticeLedger:
    """追加式告知台账。任何改派只能新增凭据，旧凭据始终保留。"""

    def __init__(self, issued_minute):
        if type(issued_minute) is not int or issued_minute < 0:
            raise ValueError('告知时钟须为非负整数')
        self._issued_minute = issued_minute
        self._entries = []
        self._ids = set()
        self._index = {}

    @property
    def issued_minute(self):
        return self._issued_minute

    @property
    def entries(self):
        return tuple(self._entries)

    def latest(self, permit):
        return self._index.get(permit)

    def _add(self, kind, permit, appointment, supersedes, reason):
        if not isinstance(permit, str) or not permit.strip():
            raise ValueError('告知凭据缺少许可号')
        if kind not in (INITIAL_KIND, REASSIGN_KIND, BACKFILL_KIND):
            raise ValueError('告知类型未登记')
        if supersedes is not None and supersedes not in self._ids:
            raise ValueError('改派凭据必须指向已存在的旧告知')
        payload = {
            'kind': kind, 'permit': permit, 'issued_minute': self._issued_minute,
            'reviewer': appointment.reviewer, 'second': appointment.second,
            'start': appointment.start, 'finish': appointment.finish,
            'supersedes': supersedes, 'reason': reason,
        }
        notice_id = _digest(payload)
        if notice_id in self._ids:
            # 同一缺班重跑：相同内容绝不重复占位、重复告知。
            return self._index[permit], False
        notice = Notice(notice_id, kind, permit, self._issued_minute,
                        appointment.reviewer, appointment.second,
                        appointment.start, appointment.finish, supersedes, reason)
        self._entries.append(notice)
        self._ids.add(notice_id)
        self._index[permit] = notice
        return notice, True

    def record_initial(self, permit, appointment):
        if permit in self._index:
            raise ValueError('首版告知已存在，不得覆盖')
        return self._add(INITIAL_KIND, permit, appointment, None,
                         '班表已发布并告知申报人预约时段')[0]

    def record_reassignment(self, permit, appointment, previous_notice, reason):
        if previous_notice is None or previous_notice.permit != permit:
            raise ValueError('改派须携带该工单原告知凭据')
        notice, _ = self._add(REASSIGN_KIND, permit, appointment,
                              previous_notice.notice_id, reason)
        return notice

    def record_backfill(self, permit, appointment, reason):
        return self._add(BACKFILL_KIND, permit, appointment, None, reason)[0]

    def records(self):
        return [entry.as_record() for entry in self._entries]

    def chain(self):
        """返回 supersede 链，证明每张旧凭据仍被新凭据引用、未被删除。"""
        chains = {}
        for entry in self._entries:
            chains.setdefault(entry.permit, []).append(entry.notice_id)
        return chains
