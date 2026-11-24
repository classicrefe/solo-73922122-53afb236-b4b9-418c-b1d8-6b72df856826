"""地类拆分核算核心求解器。

每个图幅构成一个运输型拆分问题：

- 变量 x[o][n] >= 0（整数）：旧地类 o 中划入新地类 n 的像元数，
  仅当对照表允许 (o, n) 时该变量存在（一个旧码可对应多个新码）；
- 行约束：对每个旧地类 o，sum_n x[o][n] = 旧图登记的 o 像元数；
- 列约束：对每个已复核的新地类 n，sum_o x[o][n] = 复核补报的整幅总数；
- 未复核的新地类列和不受限，吸收剩余像元。

在上述约束（非负整数拆分）下，求某对 (old, new) 重合像元数能取到的
最小值与最大值。该约束矩阵是全幺模的，因此最小费用最大流给出的
最优解天然是整数解，无需额外的整数规划。

实现：s -> 旧地类（容量=像元数），旧地类 -> 新地类（容量=总数，
查询边费用取 +1/-1，其余 0），新地类 -> t（已复核：容量=复核数、
费用=-M；未复核：容量=总数、费用 0）。M = 图幅总数 + 1，保证
"满足全部复核总数" 在字典序上优先于 "优化查询边"。
"""
from __future__ import annotations

from dataclasses import dataclass, field

INF = float("inf")


class InfeasibleStateError(RuntimeError):
    """已提交状态被判定为不可解（正常情况下不应发生，因为写入前都会校验）。"""


class MinCostFlow:
    """连续最短路（SPFA）最小费用最大流，面向小规模整数网络。"""

    def __init__(self, num_nodes: int):
        self.graph: list[list[list]] = [[] for _ in range(num_nodes)]

    def add_edge(self, fr: int, to: int, cap: int, cost: int) -> tuple[int, int]:
        """添加一条边，返回可用于回读流量的引用 (fr, index)。"""
        fwd = [to, cap, cost, len(self.graph[to])]
        rev = [fr, 0, -cost, len(self.graph[fr])]
        self.graph[fr].append(fwd)
        self.graph[to].append(rev)
        return fr, len(self.graph[fr]) - 1

    def edge_flow(self, ref: tuple[int, int]) -> int:
        """读取某条边当前的流量（即其反向边的残余容量）。"""
        fr, idx = ref
        edge = self.graph[fr][idx]
        return self.graph[edge[0]][edge[3]][1]

    def min_cost_max_flow(self, s: int, t: int) -> tuple[int, int]:
        """返回 (最大流量, 该流量下的最小费用)。"""
        n = len(self.graph)
        flow = 0
        cost = 0
        while True:
            dist = [INF] * n
            prev_v = [-1] * n
            prev_e = [-1] * n
            in_queue = [False] * n
            dist[s] = 0
            queue = [s]
            in_queue[s] = True
            while queue:
                v = queue.pop(0)
                in_queue[v] = False
                for i, e in enumerate(self.graph[v]):
                    if e[1] > 0 and dist[v] + e[2] < dist[e[0]]:
                        dist[e[0]] = dist[v] + e[2]
                        prev_v[e[0]] = v
                        prev_e[e[0]] = i
                        if not in_queue[e[0]]:
                            queue.append(e[0])
                            in_queue[e[0]] = True
            if dist[t] == INF:
                return flow, cost
            d = INF
            v = t
            while v != s:
                d = min(d, self.graph[prev_v[v]][prev_e[v]][1])
                v = prev_v[v]
            flow += d
            cost += d * dist[t]
            v = t
            while v != s:
                e = self.graph[prev_v[v]][prev_e[v]]
                e[1] -= d
                self.graph[v][e[3]][1] += d
                v = prev_v[v]


@dataclass
class SheetProblem:
    """单个图幅的拆分问题。"""

    old_counts: dict[str, int] = field(default_factory=dict)   # 旧地类 -> 像元数
    review_totals: dict[str, int] = field(default_factory=dict)  # 新地类 -> 复核整幅总数
    mapping: dict[str, set[str]] = field(default_factory=dict)  # 旧地类 -> 可对应新地类集合

    @property
    def total_pixels(self) -> int:
        return sum(self.old_counts.values())

    @property
    def reviewed_pixels(self) -> int:
        return sum(self.review_totals.values())


def _build_network(prob: SheetProblem, query: tuple[str, str] | None = None,
                   query_cost: int = 0):
    """把拆分问题建成最小费用流网络。

    返回 (mcf, S, T, query_ref, big_m)；query_ref 为查询边的引用（无查询时为 None）。
    """
    old_codes = sorted(prob.old_counts)
    new_codes = sorted(
        {n for targets in prob.mapping.values() for n in targets}
        | set(prob.review_totals)
    )
    s, t = 0, 1
    o_base = 2
    n_base = o_base + len(old_codes)
    o_idx = {o: o_base + i for i, o in enumerate(old_codes)}
    n_idx = {n: n_base + i for i, n in enumerate(new_codes)}
    mcf = MinCostFlow(n_base + len(new_codes))
    total = prob.total_pixels
    big_m = total + 1
    for o, c in prob.old_counts.items():
        if c > 0:
            mcf.add_edge(s, o_idx[o], c, 0)
    query_ref = None
    for o, targets in prob.mapping.items():
        if o not in o_idx:
            continue
        for n in targets:
            cost = query_cost if query == (o, n) else 0
            ref = mcf.add_edge(o_idx[o], n_idx[n], total, cost)
            if query == (o, n):
                query_ref = ref
    for n in new_codes:
        if n in prob.review_totals:
            # 已复核新地类：列和必须恰好等于复核数，用大 M 费用强制优先满足
            mcf.add_edge(n_idx[n], t, prob.review_totals[n], -big_m)
        else:
            mcf.add_edge(n_idx[n], t, total, 0)
    return mcf, s, t, query_ref, big_m


def check_feasible(prob: SheetProblem) -> list[str]:
    """校验图幅是否存在合法拆分，返回问题描述列表（空列表 = 可行）。"""
    problems: list[str] = []
    total = prob.total_pixels
    reviewed = prob.reviewed_pixels
    for o, c in prob.old_counts.items():
        if c > 0 and not prob.mapping.get(o):
            problems.append(
                f"旧地类[{o}]有 {c} 像元，但对照表中它不能对应任何新地类")
    for n, v in prob.review_totals.items():
        if v > 0 and not any(n in targets for targets in prob.mapping.values()):
            problems.append(
                f"复核新地类[{n}]有 {v} 像元，但对照表中没有任何旧地类能划入它")
    if reviewed > total:
        problems.append(f"复核像元总数 {reviewed} 超过图幅像元总数 {total}")
    if problems or total == 0:
        return problems
    mcf, s, t, _, big_m = _build_network(prob)
    flow, cost = mcf.min_cost_max_flow(s, t)
    if flow < total:
        problems.append(
            f"按对照表最多只能分配 {flow} 像元，少于图幅像元总数 {total}")
        return problems
    reviewed_flow = (-cost) // big_m
    if reviewed_flow < reviewed:
        problems.append(
            f"全部复核总数无法同时满足，缺口 {reviewed - reviewed_flow} 像元")
    return problems


def overlap_bounds(prob: SheetProblem, old_code: str, new_code: str) -> tuple[int, int]:
    """返回该图幅中 (old_code, new_code) 重合像元数的 (最小值, 最大值)。

    调用前要求图幅状态可行（写入路径已保证）。不在对照表中的地类对恒为 0。
    """
    if new_code not in prob.mapping.get(old_code, set()):
        return 0, 0
    if prob.old_counts.get(old_code, 0) <= 0 or prob.total_pixels == 0:
        return 0, 0
    results = []
    for sign in (+1, -1):  # +1 求最小，-1 求最大
        mcf, s, t, qref, _ = _build_network(prob, query=(old_code, new_code),
                                            query_cost=sign)
        flow, _ = mcf.min_cost_max_flow(s, t)
        if flow != prob.total_pixels:
            raise InfeasibleStateError("已提交状态不可解，数据不一致")
        results.append(mcf.edge_flow(qref))
    return results[0], results[1]
