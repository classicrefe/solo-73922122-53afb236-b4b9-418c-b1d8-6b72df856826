"""API 端到端测试：登记 -> 复核 -> 查询 -> 更正 -> 换表 -> 拒绝非法更新。"""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app

LEGEND_V1 = {
    "01": ["0101", "0103"],
    "02": ["0201", "0202"],
    "03": ["0301", "0302"],
}
LEGEND_V2 = {
    "01": ["0101", "0102", "0103"],
    "02": ["0201", "0202"],
    "03": ["0301", "0302", "0305"],
}


@pytest.fixture()
def client(tmp_path):
    app = create_app(str(tmp_path / "test.db"))
    with TestClient(app) as c:
        yield c


def seed(client):
    assert client.put("/legend", json={"mapping": LEGEND_V1}).status_code == 200
    assert client.put("/sheets/S1/old-counts",
                      json={"counts": {"01": 1000, "02": 500, "03": 800}}
                      ).status_code == 200
    assert client.put("/sheets/S2/old-counts",
                      json={"counts": {"01": 400, "03": 600}}).status_code == 200


def test_full_workflow(client):
    seed(client)
    # 无复核时：自由拆分区间
    r = client.get("/overlap", params={"sheet_id": "S2", "old_code": "01",
                                       "new_code": "0101"}).json()
    assert (r["min"], r["max"], r["exact"]) == (0, 400, False)
    # 补报复核数：0101=600，只有 01 能划入 0101 -> 确数
    assert client.put("/sheets/S1/review-totals",
                      json={"totals": {"0101": 600}}).status_code == 200
    r = client.get("/overlap", params={"sheet_id": "S1", "old_code": "01",
                                       "new_code": "0101"}).json()
    assert (r["min"], r["max"], r["exact"], r["value"]) == (600, 600, True, 600)
    r = client.get("/overlap", params={"sheet_id": "S1", "old_code": "01",
                                       "new_code": "0103"}).json()
    assert (r["min"], r["max"], r["exact"]) == (400, 400, True)
    # 复核数可更正
    assert client.put("/sheets/S1/review-totals",
                      json={"totals": {"0101": 650}}).status_code == 200
    r = client.get("/overlap", params={"sheet_id": "S1", "old_code": "01",
                                       "new_code": "0101"}).json()
    assert r["value"] == 650


def test_review_correction_and_removal(client):
    seed(client)
    client.put("/sheets/S1/review-totals", json={"totals": {"0101": 600}})
    # 更正为空表 = 撤销全部复核数
    assert client.put("/sheets/S1/review-totals", json={"totals": {}}).status_code == 200
    r = client.get("/overlap", params={"sheet_id": "S1", "old_code": "01",
                                       "new_code": "0101"}).json()
    assert (r["min"], r["max"]) == (0, 1000)


def test_infeasible_review_rejected_and_state_unchanged(client):
    seed(client)
    client.put("/sheets/S1/review-totals", json={"totals": {"0101": 600}})
    # 复核数超过图幅总数 -> 409，且原复核数保持不变
    r = client.put("/sheets/S1/review-totals", json={"totals": {"0101": 99999}})
    assert r.status_code == 409
    assert r.json()["detail"]["affected_sheets"][0]["sheet_id"] == "S1"
    sheet = client.get("/sheets/S1").json()
    assert sheet["review_totals"] == {"0101": 600}


def test_unmappable_old_count_rejected(client):
    seed(client)
    # 旧码 09 不在对照表 -> 登记即无解
    r = client.put("/sheets/S3/old-counts", json={"counts": {"09": 10}})
    assert r.status_code == 409
    assert "S3" in [s["sheet_id"] for s in r.json()["detail"]["affected_sheets"]]
    assert client.get("/sheets/S3").status_code == 404


def test_legend_swap_changes_results(client):
    seed(client)
    client.put("/sheets/S1/review-totals", json={"totals": {"0101": 600}})
    before = client.get("/overlap", params={"sheet_id": "S1", "old_code": "01",
                                            "new_code": "0102"}).json()
    assert before["in_legend"] is False and before["value"] == 0
    # 换表：01 新增可对应 0102
    r = client.put("/legend", json={"mapping": LEGEND_V2})
    assert r.status_code == 200 and r.json()["version"] == 2
    after = client.get("/overlap", params={"sheet_id": "S1", "old_code": "01",
                                           "new_code": "0102"}).json()
    assert after["in_legend"] is True
    assert (after["min"], after["max"]) == (0, 400)  # 0101=600 仍锁定
    assert after["legend_version"] == 2


def test_infeasible_legend_swap_rejected_lists_all_sheets(client):
    seed(client)
    # 新表删掉 03 林地 -> 两个图幅都无解，整次拒绝
    bad = {"01": ["0101"], "02": ["0201"]}
    r = client.put("/legend", json={"mapping": bad})
    assert r.status_code == 409
    affected = {s["sheet_id"] for s in r.json()["detail"]["affected_sheets"]}
    assert affected == {"S1", "S2"}
    # 旧表仍在，版本未变
    legend = client.get("/legend").json()
    assert legend["version"] == 1
    assert legend["mapping"] == {k: sorted(v) for k, v in LEGEND_V1.items()}


def test_review_registration_works_around_swap(client):
    """换表核对期间复核数照常登记，换表以提交时的计数为准。"""
    seed(client)
    # 先登记一个复核数，再换一张仍然可行的表
    client.put("/sheets/S2/review-totals", json={"totals": {"0301": 100}})
    r = client.put("/legend", json={"mapping": LEGEND_V2})
    assert r.status_code == 200
    r = client.get("/overlap", params={"sheet_id": "S2", "old_code": "03",
                                       "new_code": "0301"}).json()
    assert r["value"] == 100


def test_unknown_sheet_404(client):
    seed(client)
    assert client.get("/overlap", params={"sheet_id": "NOPE", "old_code": "01",
                                          "new_code": "0101"}).status_code == 404


def test_negative_count_rejected(client):
    seed(client)
    r = client.put("/sheets/S1/old-counts", json={"counts": {"01": -5}})
    assert r.status_code == 422


def test_counts_replace_semantics(client):
    seed(client)
    assert client.put("/sheets/S2/old-counts",
                      json={"counts": {"01": 100}}).status_code == 200
    sheet = client.get("/sheets/S2").json()
    assert sheet["old_counts"] == {"01": 100}
