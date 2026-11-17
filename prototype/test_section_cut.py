"""test_section_cut.py —— 截面切割的独立调试 / 自测脚本（不需要任何前端）

三种用法
--------
1) 直接命令行传平面参数，打印截面点：

    python test_section_cut.py --shape cube --origin 0.5 0.5 0.5 --normal 1 1 1

2) 交互式输入（脚本会一步步问你要参数）：

    python test_section_cut.py -i

3) 不带参数直接运行 → 跑内置的 8 组典型用例（含断言）：

    python test_section_cut.py

输出内容
--------
* 状态码（none / point / segment / polygon）与中文提示；
* 截面顶点列表：每行一个点，并标出它是多边形的第几个顶点；
* 多边形边数与面积、是否首尾闭合；
* 逐棱求交明细（12 条棱各自是否被穿过、交点在哪）；
* 内置用例会额外打印 ✔ / ✘ 校验结果。

为什么这个脚本值得留
--------------------
行测图推里最容易错的地方是"截面看起来拐弯了"——那其实是把无序交点按棱的顺序连起来了。
本脚本会把「原始收集顺序」和「排序后顺序」都打印出来，对照一眼就能看出排序的价值。
"""

from __future__ import annotations

import argparse
import math
import sys
from typing import List, Sequence

from section_cut import (
    EPS,
    SECTION_RULE_NOTE,
    STATUS_CODES,
    STATUS_NONE,
    STATUS_POINT,
    STATUS_POLYGON,
    STATUS_SEGMENT,
    cut_shape_by_plane,
    get_shape_data,
)


# ---------------------------------------------------------------------------
# 打印
# ---------------------------------------------------------------------------
def print_result(result: dict, show_edges: bool = False) -> None:
    """把 cut_shape_by_plane 的返回值打印成人能读的格式。"""
    print()
    print("=" * 70)
    print(f"几何体：{result['shape']}   尺寸：{result['dims']}")
    origin = result["plane"]["origin"]
    normal = result["plane"]["normal"]
    print(f"平面：过点 ({origin[0]:g}, {origin[1]:g}, {origin[2]:g})，"
          f"法向量 ({normal[0]:.4f}, {normal[1]:.4f}, {normal[2]:.4f})")
    print(f"容差：{EPS:g}")
    print("-" * 70)

    status = result["status"]
    print(f"状态码：{status}（{result['status_code']}）")
    print(f"提示文字：{result['message']}")

    points: List[Sequence[float]] = result["points"]
    if points:
        label = "截面顶点（已按边界顺序排列）" if status == STATUS_POLYGON else "截面点"
        print(f"{label}，共 {len(points)} 个：")
        for i, p in enumerate(points):
            print(f"    顶点[{i}]  ({p[0]:+.6f}, {p[1]:+.6f}, {p[2]:+.6f})")
    else:
        print("截面点：无")

    if status == STATUS_POLYGON:
        closed = result["closed_polygon"]
        print(f"边数：{result['side_count']}    面积：{result['area']:.6f}")
        print(f"闭合折线：{'已闭合（首尾重复首点）' if closed else '未生成'}")
        if closed:
            print("    闭合顺序：" + " → ".join(f"#{i}" for i in range(len(points))) + " → #0")

    if show_edges:
        print("-" * 70)
        print("逐棱求交明细：")
        for item in result["edge_details"]:
            hit = item["hit"]
            if hit is None:
                print(f"    棱 {item['edge']:<3} 未穿过")
            else:
                print(f"    棱 {item['edge']:<3} 穿过 → 交点 "
                      f"({hit[0]:+.4f}, {hit[1]:+.4f}, {hit[2]:+.4f})")

    print("-" * 70)
    print("公考规则：" + result["rule_note"])
    print("=" * 70)


# ---------------------------------------------------------------------------
# 命令行 / 交互式参数
# ---------------------------------------------------------------------------
def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="凸多面体一刀切：输入平面参数，打印截面点（不带参数则跑内置用例）",
    )
    parser.add_argument("--shape", default="cube", help="几何体：cube（正方体）/ cuboid（长方体）")
    parser.add_argument("--origin", nargs=3, type=float, metavar=("X", "Y", "Z"),
                        help="平面上的一个点，例如 --origin 0.5 0.5 0.5")
    parser.add_argument("--normal", nargs=3, type=float, metavar=("NX", "NY", "NZ"),
                        help="平面法向量，例如 --normal 1 1 1（不必归一化）")
    parser.add_argument("--dims", nargs=3, type=float, metavar=("A", "B", "C"),
                        help="长方体三边长度，例如 --dims 2 1.5 1")
    parser.add_argument("--edges", action="store_true", help="额外打印 12 条棱的求交明细")
    parser.add_argument("-i", "--interactive", action="store_true", help="交互式输入平面参数")
    return parser.parse_args(list(argv))


def ask_float_list(prompt: str, count: int = 3) -> List[float]:
    """交互式读入 count 个浮点数，容忍逗号 / 空格分隔。"""
    while True:
        raw = input(prompt).strip().replace(",", " ")
        parts = raw.split()
        if len(parts) != count:
            print(f"  需要 {count} 个数，收到 {len(parts)} 个，请重按格式输入")
            continue
        try:
            return [float(x) for x in parts]
        except ValueError:
            print("  存在无法解析的数字，请重新输入")


def interactive() -> None:
    """手动输入参数 → 打印截面。"""
    print("交互式截面调试（Ctrl+C 退出）")
    shape = input("几何体（cube / cuboid，默认 cube）: ").strip() or "cube"

    dims = None
    if shape.lower().startswith(("cuboid", "长方体")):
        dims = ask_float_list("长方体三边 a b c（默认 2 1.5 1，直接回车用默认值）: ", 3)

    origin = ask_float_list("平面上的点 x y z（例如 0.5 0.5 0.5）: ")
    normal = ask_float_list("平面法向量 nx ny nz（例如 1 1 1）: ")

    result = cut_shape_by_plane(shape, origin, normal, dims=dims, verbose=False)
    print_result(result, show_edges=True)


# ---------------------------------------------------------------------------
# 内置用例（带断言）
# ---------------------------------------------------------------------------
def _approx(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(a - b) <= tol


def _same_point(p: Sequence[float], q: Sequence[float], tol: float = 1e-6) -> bool:
    return math.dist(p, q) <= tol


def _point_count_ok(points: Sequence[Sequence[float]], want: int) -> bool:
    return len(points) == want


def run_demo() -> int:
    """跑 8 组典型用例：正方体的正方形/三角形/六边形/单点/线段/无截面、长方体、容差边界。"""
    failures: List[str] = []

    def check(ok: bool, message: str) -> None:
        print(f"    {'✔' if ok else '✘'} {message}")
        if not ok:
            failures.append(message)

    print("=" * 70)
    print("内置用例：正方体 / 长方体的典型截面")
    print("=" * 70)

    # ---- 用例 1：水平切正方体 → 正方形 ----
    print("\n[1] 正方体，平面 z = 0.5（水平切一刀）")
    r = cut_shape_by_plane("cube", (0.0, 0.0, 0.5), (0.0, 0.0, 1.0))
    print_result(r, show_edges=True)
    check(r["status"] == STATUS_POLYGON, "状态码 = polygon")
    check(_point_count_ok(r["points"], 4), "截面是 4 边形（正方形）")
    check(_approx(r["area"], 1.0), f"面积 = 1（实际 {r['area']:.6f}）")
    check(all(_approx(p[2], 0.5) for p in r["points"]), "4 个顶点都在 z = 0.5 平面上")
    check(r["closed_polygon"] is not None and len(r["closed_polygon"]) == 5,
          "输出了首尾相连的闭合折线（5 个点 = 4 顶点 + 重复首点）")

    # ---- 用例 2：过三个顶点的斜切 → 等边三角形 ----
    print("\n[2] 正方体，过 B(1,0,0)、D(0,1,0)、E(0,0,1) 的斜切")
    r = cut_shape_by_plane("cube", (1.0, 0.0, 0.0), (1.0, 1.0, 1.0))
    print_result(r)
    check(r["status"] == STATUS_POLYGON, "状态码 = polygon")
    check(_point_count_ok(r["points"], 3), "截面是三角形")
    check(_approx(r["area"], math.sqrt(3) / 2), "面积 = √3/2 ≈ 0.8660")

    # ---- 用例 3：过体心的斜切 → 正六边形（正方体截面的"最多 6 边"代表）----
    print("\n[3] 正方体，过体心 (0.5,0.5,0.5) 的斜切")
    r = cut_shape_by_plane("cube", (0.5, 0.5, 0.5), (1.0, 1.0, 1.0))
    print_result(r)
    check(r["status"] == STATUS_POLYGON, "状态码 = polygon")
    check(_point_count_ok(r["points"], 6), "截面是 6 边形（正方体截面最多 6 边）")
    check(_approx(r["area"], 3 * math.sqrt(3) / 4), "面积 = 3√3/4 ≈ 1.2990")
    # 正六边形：相邻顶点距离应完全相等
    pts = r["points"]
    edges = [math.dist(pts[i], pts[(i + 1) % 6]) for i in range(6)]
    check(all(_approx(e, edges[0]) for e in edges), "6 条边长完全相等（正六边形）")

    # ---- 用例 4：只擦过一个顶点 → 单点 ----
    print("\n[4] 正方体，平面过顶点 A(0,0,0)，法向量 (1,1,1)")
    r = cut_shape_by_plane("cube", (0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
    print_result(r)
    check(r["status"] == STATUS_POINT, "状态码 = point（单点）")
    check(_point_count_ok(r["points"], 1) and _same_point(r["points"][0], (0, 0, 0)),
          "退化成一个点，坐标 = (0,0,0)")

    # ---- 用例 5：只擦过一条棱 → 线段 ----
    print("\n[5] 正方体，平面 x + y = 2（正好贴着棱 C-G）")
    r = cut_shape_by_plane("cube", (1.0, 1.0, 0.0), (1.0, 1.0, 0.0))
    print_result(r)
    check(r["status"] == STATUS_SEGMENT, "状态码 = segment（线段）")
    check(_point_count_ok(r["points"], 2), "退化成 2 个点")
    if len(r["points"]) == 2:
        check(_approx(math.dist(r["points"][0], r["points"][1]), 1.0), "线段长度 = 1（正好是一条棱）")

    # ---- 用例 6：平面在体外 → 无截面 ----
    print("\n[6] 正方体，平面 z = 5（在几何体外侧）")
    r = cut_shape_by_plane("cube", (0.0, 0.0, 5.0), (0.0, 0.0, 1.0))
    print_result(r)
    check(r["status"] == STATUS_NONE, "状态码 = none（无截面）")
    check(_point_count_ok(r["points"], 0), "截面点列表为空")

    # ---- 用例 7：长方体水平切 → 长方形 ----
    print("\n[7] 长方体 2 x 1.5 x 1，平面 z = 0.5")
    r = cut_shape_by_plane("cuboid", (0.0, 0.0, 0.5), (0.0, 0.0, 1.0), dims=(2.0, 1.5, 1.0))
    print_result(r)
    check(r["status"] == STATUS_POLYGON, "状态码 = polygon")
    check(_point_count_ok(r["points"], 4), "截面是 4 边形（长方形）")
    check(_approx(r["area"], 3.0), "面积 = 2 × 1.5 = 3")

    # ---- 用例 8：容差边界（1e-6）----
    print("\n[8] 容差验证：平面 z = 0.0000005（小于 1e-6）与 z = 0.000005（大于 1e-6）")
    near = cut_shape_by_plane("cube", (0.0, 0.0, 5e-7), (0.0, 0.0, 1.0))
    far = cut_shape_by_plane("cube", (0.0, 0.0, 5e-6), (0.0, 0.0, 1.0))
    print(f"    z=5e-7 → {near['status']}，顶点 {len(near['points'])} 个，"
          f"顶点 z 值 = {[round(p[2], 9) for p in near['points']]}")
    print(f"    z=5e-6 → {far['status']}，顶点 {len(far['points'])} 个，"
          f"顶点 z 值 = {[round(p[2], 9) for p in far['points']]}")
    check(near["status"] == STATUS_POLYGON and all(_approx(p[2], 0.0, 1e-9) for p in near["points"]),
          "z=5e-7 被容差吸收：当作与底面共面，顶点落在 z=0 上")
    check(far["status"] == STATUS_POLYGON and all(_approx(p[2], 5e-6, 1e-9) for p in far["points"]),
          "z=5e-6 超出容差：正常切开，顶点落在 z=5e-6 上")

    # ---- 汇总 ----
    print("\n" + "=" * 70)
    if failures:
        print(f"结果：{len(failures)} 项失败")
        for item in failures:
            print("  - " + item)
        return 1
    print("结果：内置用例全部通过 ✅")
    return 0


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)

    if args.interactive:
        interactive()
        return 0

    # 命令行给了平面参数 → 按参数算一次
    if args.origin and args.normal:
        result = cut_shape_by_plane(
            args.shape,
            args.origin,
            args.normal,
            dims=args.dims,
            verbose=False,
        )
        print_result(result, show_edges=args.edges)
        return 0

    # 只给了一个（比如只给 --pagerange）→ 提示用法
    if args.origin or args.normal:
        print("需要同时提供 --origin 与 --normal；或加 -i 进入交互式输入", file=sys.stderr)
        return 2

    # 什么都没给 → 跑内置用例
    return run_demo()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))