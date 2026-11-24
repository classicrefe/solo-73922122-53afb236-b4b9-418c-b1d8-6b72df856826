"""求解器单元测试：手工可验算的小例子。"""
import pytest

from app.solver import SheetProblem, check_feasible, overlap_bounds


def make(old_counts, review=None, mapping=None):
    return SheetProblem(
        old_counts=old_counts,
        review_totals=review or {},
        mapping={k: set(v) for k, v in (mapping or {}).items()},
    )


def test_free_split_bounds():
    # A(100) 可入 X/Y，B(200) 只能入 Y，无复核
    p = make({"A": 100, "B": 200}, {}, {"A": ["X", "Y"], "B": ["Y"]})
    assert check_feasible(p) == []
    assert overlap_bounds(p, "A", "X") == (0, 100)
    assert overlap_bounds(p, "A", "Y") == (0, 100)
    assert overlap_bounds(p, "B", "Y") == (200, 200)  # 确数


def test_review_pins_column_exactly():
    # A(100) -> X/Y，复核 X=60，X 只能来自 A
    p = make({"A": 100}, {"X": 60}, {"A": ["X", "Y"]})
    assert check_feasible(p) == []
    assert overlap_bounds(p, "A", "X") == (60, 60)
    assert overlap_bounds(p, "A", "Y") == (40, 40)


def test_review_shifts_bounds():
    # A(100) B(200) 都可入 X/Y，复核 X=150
    p = make({"A": 100, "B": 200}, {"X": 150}, {"A": ["X", "Y"], "B": ["X", "Y"]})
    assert check_feasible(p) == []
    assert overlap_bounds(p, "A", "X") == (0, 100)
    assert overlap_bounds(p, "B", "X") == (50, 150)
    assert overlap_bounds(p, "A", "Y") == (0, 100)
    assert overlap_bounds(p, "B", "Y") == (50, 150)


def test_chain_bounds():
    # A(30)->{X,Y}, B(70)->{Y,Z}，复核 Y=50
    p = make({"A": 30, "B": 70}, {"Y": 50}, {"A": ["X", "Y"], "B": ["Y", "Z"]})
    assert check_feasible(p) == []
    assert overlap_bounds(p, "A", "Y") == (0, 30)
    assert overlap_bounds(p, "A", "X") == (0, 30)
    assert overlap_bounds(p, "B", "Y") == (20, 50)
    assert overlap_bounds(p, "B", "Z") == (20, 50)


def test_unmappable_old_code_rejected():
    p = make({"A": 5}, {}, {"B": ["X"]})
    assert check_feasible(p)  # 有问题


def test_unsatisfiable_review_rejected():
    # A 只能入 Y，却复核 X=60
    p = make({"A": 100}, {"X": 60}, {"A": ["Y"]})
    assert check_feasible(p)


def test_review_exceeds_total_rejected():
    p = make({"A": 100}, {"X": 101}, {"A": ["X"]})
    assert check_feasible(p)


def test_competing_reviews_rejected():
    # X+Y 复核合计 150 > 总数 100
    p = make({"A": 100}, {"X": 80, "Y": 70}, {"A": ["X", "Y"]})
    assert check_feasible(p)


def test_pair_not_in_legend_is_zero():
    p = make({"A": 10}, {}, {"A": ["X"]})
    assert overlap_bounds(p, "A", "Z") == (0, 0)
    assert overlap_bounds(p, "Z", "X") == (0, 0)


def test_zero_count_old_code_is_zero():
    p = make({"A": 10}, {}, {"A": ["X"]})
    assert overlap_bounds(p, "B", "X") == (0, 0)


def test_many_to_many_exact_split():
    # 两个旧码、三个新码，复核两列后第三列被唯一确定
    p = make({"A": 40, "B": 60}, {"X": 25, "Y": 35},
             {"A": ["X", "Y", "Z"], "B": ["X", "Y", "Z"]})
    assert check_feasible(p) == []
    lo, hi = overlap_bounds(p, "A", "Z")
    assert (lo, hi) == (0, 40)
    # Z 列总和恒为 100-60=40，但 A/B 之间分配自由
    assert overlap_bounds(p, "B", "Z") == (0, 40)


def test_empty_sheet_feasible():
    assert check_feasible(make({}, {}, {"A": ["X"]})) == []
