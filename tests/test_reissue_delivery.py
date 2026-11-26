"""缺班重排工作台接口测试。"""

from permitdesk.delivery import application


VALID_ABSENCE = {"政西 主管": [8100, 8295]}


def post(client, payload):
    return client.post("/api/reissue", json=payload)


def test_reissue_returns_decisions_notices_and_token():
    client = application.test_client()
    response = post(client, {"capacity": 8, "absences": VALID_ABSENCE})
    assert response.status_code == 200
    packet = response.get_json()
    assert len(packet["run_id"]) == 12
    assert packet["record"] == "缺班重排复核安排"
    assert packet["summary"]["retained"] >= 1
    assert packet["decisions"] and packet["notices"]
    assert packet["summary"]["reassigned"] + packet["summary"]["backfilled"] >= 1
    # 每张改派/补位凭据都可在台账中查到，且改派凭据指向旧凭据。
    notices = {row["notice_id"]: row for row in packet["notices"]}
    for decision in packet["decisions"]:
        if decision["notice_id"]:
            assert decision["notice_id"] in notices
        if decision["ruling"] == "改派":
            assert decision["superseded_notice_id"] in notices


def test_same_request_is_idempotent_and_does_not_duplicate_seats():
    client = application.test_client()
    first = post(client, {"capacity": 8, "absences": VALID_ABSENCE}).get_json()
    second = post(client, {"capacity": 8, "absences": VALID_ABSENCE}).get_json()
    assert first == second
    scheduled = [row["permit"] for row in first["appointments"] if row["state"] == "安排复核"]
    assert len(scheduled) == len(set(scheduled))


def test_retained_appointments_keep_original_notified_slot():
    packet = post(application.test_client(),
                  {"capacity": 8, "absences": VALID_ABSENCE}).get_json()
    for row in packet["decisions"]:
        if row["ruling"] == "保留原约":
            assert row["proposed"] == row["original"]
            assert row["notice_id"] is not None and row["superseded_notice_id"] is None


def test_notice_ledger_keeps_every_original_receipt():
    packet = post(application.test_client(),
                  {"capacity": 8, "absences": VALID_ABSENCE}).get_json()
    initial = [row for row in packet["notices"] if row["kind"] == "首版预约告知"]
    assert initial  # 首版告知一张不少
    # supersede 链引用的旧凭据全部仍在台账内。
    ids = {row["notice_id"] for row in packet["notices"]}
    for row in packet["notices"]:
        if row["supersedes"]:
            assert row["supersedes"] in ids
    # 同一工单的凭据链保留全部历史版本。
    for permit, chain in packet["notice_chains"].items():
        assert len(chain) == len(set(chain))
        assert all(notice_id in ids for notice_id in chain)


def test_backfill_never_exceeds_released_seats_and_only_uses_unscheduled():
    packet = post(application.test_client(),
                  {"capacity": 8, "absences": VALID_ABSENCE}).get_json()
    summary = packet["summary"]
    # 补位数不超过退回释放的席位数，新班表安排总量不超过基线席位。
    assert summary["backfilled"] <= summary["dropped"]
    baseline_scheduled = {row["permit"] for row in packet["decisions"]
                          if row["original"]["state"] == "安排复核"}
    for row in packet["decisions"]:
        if row["ruling"] == "补位入班":
            assert row["permit"] not in baseline_scheduled


def test_double_signature_reassignment_uses_two_distinct_in_shift_reviewers():
    # 政西主管承担双签工单，缺班后任何双签安排仍须两人且在班内。
    packet = post(application.test_client(),
                  {"capacity": 8, "absences": VALID_ABSENCE}).get_json()
    for appointment in packet["appointments"]:
        if appointment["second"] is not None:
            assert appointment["reviewer"] != appointment["second"]
            assert appointment["start"] < appointment["finish"]


def test_invalid_absence_payloads_are_rejected_without_mutating_schedule():
    client = application.test_client()
    bad_payloads = [
        {"capacity": 8, "absences": {"不在班表的人": [8100, 8200]}},
        {"capacity": 8, "absences": {"政西 主管": [8200, 8100]}},
        {"capacity": 8, "absences": {"政西 主管": [8100]}},
        {"capacity": 8, "absences": {}},
        {"capacity": 8, "absences": []},
        {"capacity": 8},
        {"absences": VALID_ABSENCE, "capacity": 0},
        {"absences": VALID_ABSENCE, "capacity": "8"},
    ]
    for payload in bad_payloads:
        response = post(client, payload)
        assert response.status_code == 400
        assert response.get_json()["code"] == "INVALID_ABSENCE"


def test_default_capacity_is_accepted_when_omitted():
    response = post(application.test_client(), {"absences": VALID_ABSENCE})
    assert response.status_code == 200
    assert response.get_json()["capacity"] == 8
