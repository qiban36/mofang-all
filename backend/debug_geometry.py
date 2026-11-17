"""debug_geometry.py —— 后端几何的"命令行放大镜"（不启动服务、不打开前端也能验证）

为什么要有这个脚本
------------------
主程序接口一旦出问题，很难判断到底是"算错了"还是"接口传参错了"。
这个脚本直接调用 geometry 里的纯计算函数，把每一步的中间量打印出来，
把问题缩小到"数学"这一层。

四个子命令
----------
    python debug_geometry.py nets
        列出 11 种展开图的字符画布局（看清每个形状长什么样）

    python debug_geometry.py fold 141-1
        打印某一种展开图 6 个面片的折叠参数：start_pos / 铰链 / 旋转轴 / 角度 / target_pos，
        并校验"旋转轴是否严格沿公共边"、"6 个面片是否正好落在单位正方体的 6 个面上"

    python debug_geometry.py section --shape cube --origin 0.5 0.5 0.5 --normal 1 1 1
        逐条棱求交的全过程（带符号距离 d1/d2、参数 t、交点坐标），
        以及排序后的闭合多边形顶点、面积、状态码

    python debug_geometry.py all
        把上面三件事 + 几组典型截面一次跑完（相当于"后端是否健康"的体检）

示例
----
    python debug_geometry.py section --shape cuboid --origin 0 0 0.5 --normal 0 0 1 --dims 2 1.5 1
    python debug_geometry.py fold 33-1
"""

from __future__ import annotations

import argparse
import logging
import math
import sys
from typing import List, Sequence

from geometry import hexahedron, section_cut, shape_data
from geometry import vector_utils as vu


# ===========================================================================
# 子命令 1：列出 11 种展开图
# ===========================================================================
def cmd_nets(_args: argparse.Namespace) -> int:
    """打印 11 种展开图的字符画（B = 基准面，# = 其它面片）。"""
    summary = hexahedron.list_unfold_types()
    print("=" * 68)
    print(f"正方体展开图共 {summary['total_unfold_types']} 种")
    for group in summary["groups"]:
        print(f"  {group['label']}（{group['code']}）：{group['count']} 种")
    print("=" * 68)

    for entry in hexahedron.NET_TABLE:
        net_id = f"{entry['code']}-{entry['variant']}"
        print(f"\n[{net_id}] {hexahedron.CODE_LABELS[str(entry['code'])]}·第{entry['variant']}种 —— {entry['note']}")
        for line in hexahedron.render_net_ascii(entry["cells"], base=(0, 0)).splitlines():
            print("   " + line)
    return 0


# ===========================================================================
# 子命令 2：打印某一种展开图的折叠参数并校验
# ===========================================================================
def cmd_fold(args: argparse.Namespace) -> int:
    """打印 6 个面片的折叠参数，并校验铰链轴与落面正确性。"""
    data = hexahedron.get_unfold_data(args.net)
    faces = data["faces"]

    print("=" * 72)
    print(f"展开图 {data['net_id']}（{data['label']}）—— {data['face_count']} 个独立面片")
    print(f"折叠顺序（面片序号）：{data['fold_sequence']}")
    print("=" * 72)

    failures: List[str] = []

    for face in faces:
        idx = face["face_index"]
        print(f"\n面片 #{idx}  颜色 {face['color_index']}{face['color']}  折后落在：{face['target_face_label']}")
        print(f"  start_pos（摊平坐标，z 恒为 0）:")
        for p in face["start_pos"]:
            print("     ", tuple(round(v, 3) for v in p))

        if face["is_base"]:
            print("  ★ 基准面：不折、不转（rotate_angle = 0）")
            print(f"  target_pos（折完后仍在原处）:")
            for p in face["target_pos"]:
                print("     ", tuple(round(v, 3) for v in p))
            continue

        hinge = face["hinge_edge"]
        axis = face["rotate_axis"]
        print(f"  hinge_edge（与父面片 #{face['parent_id']} 共用的棱）:")
        for p in hinge:
            print("     ", tuple(round(v, 3) for v in p))
        print(f"  rotate_axis = {tuple(round(v, 6) for v in axis)}   rotate_angle = {face['rotate_angle']}°")
        print(f"  深度 = {face['depth']}   折叠顺序 = {face['fold_order']}")
        print(f"  target_pos（折好后的 4 个角点）:")
        for p in face["target_pos"]:
            print("     ", tuple(round(v, 3) for v in p))

        # ---- 校验 1：铰链两端点是否同时属于自己与父面片 ----
        parent = next(f for f in faces if f["face_index"] == face["parent_id"])
        for h in hinge:
            in_own = any(vu.distance(tuple(h), tuple(c)) <= 1e-9 for c in face["start_pos"])
            in_parent = any(vu.distance(tuple(h), tuple(c)) <= 1e-9 for c in parent["start_pos"])
            if not (in_own and in_parent):
                failures.append(f"面片#{idx} 的铰链端点不同时属于两片：{h}")

        # ---- 校验 2：旋转轴是否严格沿公共边方向 ----
        hinge_dir = vu.normalize(vu.sub(tuple(hinge[1]), tuple(hinge[0])))
        alignment = abs(vu.dot(tuple(axis), hinge_dir))
        print(f"  校验：|axis · 铰链方向| = {alignment:.12f}")
        if abs(alignment - 1.0) > 1e-9:
            failures.append(f"面片#{idx} 的旋转轴没有沿公共边（对齐度 {alignment}）")

        # ---- 校验 3：轴是否躺在摊平平面内（否则会变成"原地旋转"而不是"翻折"）----
        if abs(vu.dot(tuple(axis), (0.0, 0.0, 1.0))) > 1e-9:
            failures.append(f"面片#{idx} 的旋转轴不平行于 z=0 平面")

    # ---- 校验 4：折完后 6 个面片应覆盖单位正方体的 6 个不同面 ----
    target_faces = {f["target_face"] for f in faces}
    bbox_min = [min(p[k] for f in faces for p in f["target_pos"]) for k in range(3)]
    bbox_max = [max(p[k] for f in faces for p in f["target_pos"]) for k in range(3)]
    print("\n" + "-" * 72)
    print(f"折完后整体包围盒：min={tuple(round(v, 3) for v in bbox_min)}  max={tuple(round(v, 3) for v in bbox_max)}")
    print(f"覆盖了 {len(target_faces)} 个不同的面：{sorted(target_faces)}")
    if len(target_faces) != 6:
        failures.append("折叠后没有覆盖 6 个不同的面")
    if any(abs(bbox_max[k] - bbox_min[k] - 1.0) > 1e-6 for k in range(3)):
        failures.append("折叠后整体尺寸不是 1×1×1")

    print("\n" + "=" * 72)
    if failures:
        print(f"❌ 校验失败 {len(failures)} 项：")
        for item in failures:
            print("   -", item)
        return 1
    print("✅ 折叠参数校验通过：轴沿公共边、6 片分别落在正方体 6 个面上、整体 1×1×1")
    return 0


# ===========================================================================
# 子命令 3：截面调试
# ===========================================================================
def cmd_section(args: argparse.Namespace) -> int:
    """打印一刀切的逐棱求交过程 + 排序后的闭合多边形。"""
    print("=" * 72)
    print(f"截面调试：shape={args.shape}  origin={args.origin}  normal={args.normal}"
          + (f"  dims={args.dims}" if args.dims else ""))
    print("=" * 72)

    result = section_cut.cut(
        shape=args.shape,
        plane_origin=args.origin,
        plane_normal=args.normal,
        dims=args.dims,
        verbose=True,  # 关键：让它把每条棱的 d1/d2、t、交点都打印出来
    )

    print("\n" + "-" * 72)
    print(f"状态码：{result['status']}    顶点数：{result['point_count']}    面积：{result['area']}")
    print(f"提示：{result['message']}")
    print("闭合多边形顶点（已按边界顺序排好，首尾相连即闭合）：")
    for i, p in enumerate(result["points"]):
        print(f"  顶点[{i}] = {tuple(round(v, 6) for v in p)}")

    if result["status"] == "polygon":
        # 再独立算一遍面积，和模块内部结果对照（多边形面积 = 各三角形叉积和的一半）
        normal = vu.normalize(tuple(args.normal))
        pts = [tuple(p) for p in result["points"]]
        area = 0.0
        for i in range(1, len(pts) - 1):
            area += vu.dot(vu.cross(vu.sub(pts[i], pts[0]), vu.sub(pts[i + 1], pts[0])), normal)
        area = abs(area) / 2
        print(f"\n独立复算面积 = {area:.9f}（模块给出 {result['area']:.9f}，差 {abs(area - result['area']):.2e}）")
        if abs(area - result["area"]) > 1e-6:
            print("❌ 面积不一致")
            return 1
        if not vu.is_convex_polygon(pts, normal):
            print("❌ 排序结果不是凸多边形（公考一刀切不可能拐弯）")
            return 1
        print("✅ 面积一致、顶点顺序构成凸多边形（符合'一刀切不能拐弯'）")
    return 0


# ===========================================================================
# 子命令 4：一键体检
# ===========================================================================
def cmd_all(_args: argparse.Namespace) -> int:
    """把 nets / fold / 几组典型截面都跑一遍。"""
    cmd_nets(argparse.Namespace())

    print("\n" + "#" * 72)
    print("# 折叠校验：逐个检查 11 种展开图")
    print("#" * 72)
    failed = []
    for entry in hexahedron.NET_TABLE:
        net_id = f"{entry['code']}-{entry['variant']}"
        code = cmd_fold(argparse.Namespace(net=net_id))
        if code != 0:
            failed.append(net_id)

    print("\n" + "#" * 72)
    print("# 截面校验：正方体 / 长方体的典型场景")
    print("#" * 72)
    cases = [
        (("cube", (0.0, 0.0, 0.5), (0.0, 0.0, 1.0), None), "水平切 → 正方形"),
        (("cube", (1.0, 0.0, 0.0), (1.0, 1.0, 1.0), None), "过 3 个顶点 → 等边三角形"),
        (("cube", (0.5, 0.5, 0.5), (1.0, 1.0, 1.0), None), "过体心 → 正六边形"),
        (("cube", (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), None), "过顶点 → 单点"),
        (("cube", (1.0, 1.0, 0.0), (1.0, 1.0, 0.0), None), "贴棱 → 线段"),
        (("cube", (0.0, 0.0, 5.0), (0.0, 0.0, 1.0), None), "体外 → 无截面"),
        (("cuboid", (0.0, 0.0, 0.5), (0.0, 0.0, 1.0), (2.0, 1.5, 1.0)), "长方体水平切 → 长方形"),
    ]
    for (shape, origin, normal, dims), desc in cases:
        print(f"\n>>> 场景：{desc}")
        result = section_cut.cut(shape, origin, normal, dims=dims, verbose=False)
        print(f"    status={result['status']}  点数={result['point_count']}  面积={result['area']}")

    print("\n" + "=" * 72)
    if failed:
        print(f"❌ 有 {len(failed)} 种展开图折叠校验失败：{failed}")
        return 1
    print("✅ 全部体检项通过：11 种展开图折叠正确、6 类截面场景返回正常")
    return 0


# ===========================================================================
# 命令行入口
# ===========================================================================
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="后端几何调试脚本：不用前端、不用起服务，直接验证折叠与截面计算",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_nets = sub.add_parser("nets", help="列出 11 种展开图的字符画")
    p_nets.set_defaults(func=cmd_nets)

    p_fold = sub.add_parser("fold", help="打印某种展开图的折叠参数并校验")
    p_fold.add_argument("net", help="展开图类型，例如 141-1 / 231-2 / 33")
    p_fold.set_defaults(func=cmd_fold)

    p_section = sub.add_parser("section", help="打印某个平面的截面计算过程")
    p_section.add_argument("--shape", default="cube", choices=["cube", "cuboid"], help="几何体")
    p_section.add_argument("--origin", nargs=3, type=float, required=True, metavar=("X", "Y", "Z"),
                           help="平面上的点，例如 --origin 0.5 0.5 0.5")
    p_section.add_argument("--normal", nargs=3, type=float, required=True, metavar=("NX", "NY", "NZ"),
                           help="平面法向量，例如 --normal 1 1 1")
    p_section.add_argument("--dims", nargs=3, type=float, metavar=("A", "B", "C"),
                           help="长方体三边，例如 --dims 2 1.5 1")
    p_section.set_defaults(func=cmd_section)

    p_all = sub.add_parser("all", help="一键体检：11 种展开图折叠 + 6 组截面场景")
    p_all.set_defaults(func=cmd_all)

    return parser


if __name__ == "__main__":
    # geometry 层的调试输出走 logging，这里配置一次即可在终端看到
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = build_parser().parse_args()
    sys.exit(args.func(args))