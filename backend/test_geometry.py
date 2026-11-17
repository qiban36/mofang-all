"""纯几何逻辑自测脚本 —— 不需要前端、不需要启动服务。

用法
----
    python test_geometry.py          # 跑全部用例，打印一屏结论
    python test_geometry.py --quiet  # 只打印每条用例的结果行
    pytest test_geometry.py -q       # 也可以直接用 pytest 跑

覆盖内容
--------
1. 向量工具：点积 / 叉积 / 单位化 / 线段与平面求交的 4 种情形 / 绕轴旋转
2. 11 种展开图：面片数量、颜色编号、展开坐标是否在 z=0、折叠目标是否落在单位正方体 6 个面上、
   铰链是否真的与父面片共用、父面片是否先折（依赖顺序）
3. 截面切割：闭合多边形（正方形 / 三角形 / 六边形 / 长方形）、单点、线段、无交点、平面与面共面
4. 交点顺序：必须是绕一圈的闭合顺序（凸性 + 有向面积为正）
5. 接口冒烟（fastapi 装了就测）：三个接口各一次真实调用
"""

from __future__ import annotations

import math
import os
import sys
from typing import List, Tuple

from geometry import hexahedron, section_cut, shape_data
from geometry import vector_utils as vu

FAILURES: List[str] = []
SKIPS: List[str] = []
QUIET = "--quiet" in sys.argv

# 是否由 pytest 启动：pytest 下 check() 必须变成真正的断言，
# 否则收集到 test_* 函数后只会打印结果、永远不会失败（假通过）。
# 注意不能只在 import 时判断 PYTEST_CURRENT_TEST —— 那个变量要到用例执行时才存在，
# 模块导入（collection 阶段）时还没有。
def _running_under_pytest() -> bool:
    return "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ


def note(message: str) -> None:
    """普通过程信息（--quiet 时静默）。"""
    if not QUIET:
        print(message)


def skip(message: str) -> None:
    """显式标记一组用例被跳过：打印、计数，pytest 下转成正式 skip。"""
    print(f"  ⏭ {message}")
    SKIPS.append(message)
    if _running_under_pytest():
        import pytest

        pytest.skip(message)


def check(condition: bool, message: str) -> None:
    """断言式检查：失败时记录到 FAILURES，pytest 下同时抛出断言让用例变红。"""
    if condition:
        print(f"  ✅ {message}")
        return
    print(f"  ❌ {message}")
    FAILURES.append(message)
    if _running_under_pytest():
        raise AssertionError(message)


def close(a: float, b: float, tol: float = 1e-7) -> bool:
    return abs(a - b) <= tol


def point_close(p: Tuple[float, float, float], q, tol: float = 1e-6) -> bool:
    return vu.distance(tuple(p), tuple(q)) <= tol


# ---------------------------------------------------------------------------
# 1. 向量工具
# ---------------------------------------------------------------------------
def test_vector_utils() -> None:
    print("\n[1] 向量工具")
    check(close(vu.dot((1, 2, 3), (4, 5, 6)), 32.0), "点积 (1,2,3)·(4,5,6) = 32")
    check(vu.round_point(vu.cross((1, 0, 0), (0, 1, 0))) == (0.0, 0.0, 1.0), "叉积 x × y = z（右手定则）")
    check(vu.round_point(vu.normalize((3, 4, 0))) == (0.6, 0.8, 0.0), "单位化 (3,4,0) = (0.6,0.8,0)")

    # 线段与平面求交：4 种情形
    plane = ((0.0, 0.0, 0.5), (0.0, 0.0, 1.0))  # 平面 z = 0.5
    hit = vu.segment_plane_intersection((0, 0, 0), (0, 0, 1), *plane)
    check(hit["status"] == "point" and point_close(hit["point"], (0, 0, 0.5)), "竖棱穿过 z=0.5 → 交点 (0,0,0.5)")
    check(close(float(hit["t"]), 0.5), "交点参数 t = 0.5")

    same = vu.segment_plane_intersection((0, 0, 0), (1, 0, 0), *plane)
    check(same["status"] == "none", "两端同侧 → 无交点")

    endpoint = vu.segment_plane_intersection((0, 0, 0.5), (0, 0, 1), *plane)
    check(endpoint["status"] == "endpoint" and point_close(endpoint["point"], (0, 0, 0.5)), "端点落在平面上 → 交点为该端点")

    coplanar = vu.segment_plane_intersection((0, 0, 0.5), (1, 0, 0.5), *plane)
    check(coplanar["status"] == "segment", "整条棱躺在平面上 → segment")

    # 折叠轴：把 +x 方向转到 +z
    axis = vu.axis_from_direction_and_up((1, 0, 0))
    rotated = vu.round_point(vu.rotate_point_about_axis((1, 0, 0), (0, 0, 0), axis, 90))
    check(rotated == (0.0, 0.0, 1.0), "绕轴转 90°：+x → +z（面片立起来）")
    back = vu.round_point(vu.rotate_point_about_axis((1, 0, 0), (0, 0, 0), axis, -90))
    check(back == (0.0, 0.0, -1.0), "反向转 90°：+x → -z（展开回去）")

    # 平面极角排序：乱序输入必须排成绕一圈的顺序
    scrambled = [(1, 1, 0), (0, 0, 0), (1, 0, 0), (0, 1, 0)]
    ordered = vu.sort_points_on_plane(scrambled, (0, 0, 0), (0, 0, 1))
    check(ordered == [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], "乱序四点 → 排序成逆时针闭合顺序")
    check(vu.is_convex_polygon(ordered, (0, 0, 1)), "排序后是凸多边形")
    check(close(vu.polygon_area(ordered, (0, 0, 1)), 1.0), "排序后面积 = 1")


# ---------------------------------------------------------------------------
# 2. 11 种展开图
# ---------------------------------------------------------------------------
def test_hexahedron() -> None:
    print("\n[2] 正方体 11 种展开图")

    # 2.1 分类数量：一四一型 6 种 + 二三一型 3 种 + 二二二型 1 种 + 三三型 1 种
    summary = hexahedron.list_unfold_types()
    counts = {group["code"]: group["count"] for group in summary["groups"]}
    check(counts.get("141") == 6, f"一四一型 6 种（实际 {counts.get('141')}）")
    check(counts.get("231") == 3, f"二三一型 3 种（实际 {counts.get('231')}）")
    check(counts.get("222") == 1, f"二二二型 1 种（实际 {counts.get('222')}）")
    check(counts.get("33") == 1, f"三三型 1 种（实际 {counts.get('33')}）")
    check(summary["total_unfold_types"] == 11, f"展开图总数 11（实际 {summary['total_unfold_types']}）")

    # 2.2 逐种校验数据完整性
    total_checked = 0
    for entry in hexahedron.NET_TABLE:
        code = entry["code"]
        variant = entry["variant"]
        data = hexahedron.get_unfold_data(code, variant)
        net_id = data["net_id"]

        ok_faces = data["face_count"] == 6 and len(data["faces"]) == 6
        cells = [tuple(c) for c in data["cells"]]
        ok_cells = len(set(cells)) == 6
        ok_colors = sorted(f["color_index"] for f in data["faces"]) == [1, 2, 3, 4, 5, 6]

        ok_start_flat = all(close(p[2], 0.0) for f in data["faces"] for p in f["start_pos"])
        ok_target_inside = all(
            -1e-6 <= p[k] <= 1 + 1e-6 for f in data["faces"] for p in f["target_pos"] for k in range(3)
        )
        target_faces = {f["target_face"] for f in data["faces"]}
        ok_six_faces = len(target_faces) == 6

        # 每个非基准面片都要有铰链、轴、90°，且父面片先折
        order_of = {f["face_index"]: f["fold_order"] for f in data["faces"]}
        ok_fold_params = True
        ok_hinge = True
        for f in data["faces"]:
            if f["is_base"]:
                ok_fold_params &= f["rotate_angle"] == 0.0 and f["parent_id"] is None
                continue
            ok_fold_params &= (
                close(f["rotate_angle"], 90.0)
                and f["rotate_axis"] is not None
                and close(vu.length(tuple(f["rotate_axis"])), 1.0)
                and len(f["hinge_edge"]) == 2
                and order_of[f["parent_id"]] < f["fold_order"]
            )
            # 折叠后这条公共棱必须和父面片的某条边重合（真正共用一条棱）
            parent = next(x for x in data["faces"] if x["face_index"] == f["parent_id"])
            ok_hinge &= all(
                any(point_close(hp, pp) for pp in parent["target_pos"]) for hp in f["hinge_edge_folded"]
            )

        ok_order = data["fold_sequence"][0] == 0 and len(data["fold_sequence"]) == 6
        ok_anim = len(data["animation"]["steps"]) == 6 and data["animation"]["total_duration"] > 0

        passed = all(
            [ok_faces, ok_cells, ok_colors, ok_start_flat, ok_target_inside, ok_six_faces,
             ok_fold_params, ok_hinge, ok_order, ok_anim]
        )
        check(passed, f"{net_id}（{data['label']}）6 面 / 6 色 / 展开在 z=0 / 折后落 6 个不同面 / 铰链共用 / 90° / 父先折")
        if not passed:
            print("     明细:", dict(ok_faces=ok_faces, ok_cells=ok_cells, ok_colors=ok_colors,
                                   ok_start_flat=ok_start_flat, ok_target_inside=ok_target_inside,
                                   ok_six_faces=ok_six_faces, ok_fold_params=ok_fold_params,
                                   ok_hinge=ok_hinge, ok_order=ok_order, ok_anim=ok_anim))
        total_checked += 1

    check(total_checked == 11, f"逐种遍历 11 种展开图（实际 {total_checked}）")

    # 2.3 import 时的落面自检结果
    check(all(item["ok"] for item in hexahedron.VALIDATION_REPORT), "11 种展开图全部通过折叠落面校验")

    # 2.4 展开图布局的自洽性：格子必须连通，且允许 141-3 这种写法
    data = hexahedron.get_unfold_data("141-3")
    check(data["net_id"] == "141-3" and data["variant"] == 3, "支持 141-3 写法，解析到一四一型第 3 种")
    data_v = hexahedron.get_unfold_data("231", 2)
    check(data_v["net_id"] == "231-2", "字段 variant=2 生效，解析到二三一型第 2 种")

    # 2.5 非法输入
    for bad, desc in [("999", "不存在的分型"), ("141-9", "变体号越界")]:
        try:
            hexahedron.get_unfold_data(bad)
            check(False, f"非法输入 {desc} 应报错")
        except ValueError:
            check(True, f"非法输入 {desc}（{bad}）正确报错")

    note("\n  展开图字符画（'B' 为基准面）：")
    for entry in hexahedron.NET_TABLE[:2]:
        data = hexahedron.get_unfold_data(entry["code"], entry["variant"])
        note(f"  {data['net_id']}")
        for line in hexahedron.render_net_ascii(data["cells"]).splitlines():
            note("    " + line)


# ---------------------------------------------------------------------------
# 3. 截面切割
# ---------------------------------------------------------------------------
def assert_polygon(result: dict, expected_points: int, expected_area: float, desc: str) -> None:
    """多边形场景的通用校验：点数、面积、凸性、点在平面上、点在棱上、闭合。"""
    ok = result["status"] == "polygon"
    check(ok, f"{desc} → status=polygon（实际 {result['status']}）")
    if not ok:
        return
    points = [tuple(p) for p in result["points"]]
    normal = tuple(result["plane"]["normal"])
    origin = tuple(result["plane"]["origin"])

    check(len(points) == expected_points, f"{desc} → {expected_points} 个顶点（实际 {len(points)}）")
    check(close(result["area"], expected_area, 1e-6), f"{desc} → 面积 {expected_area:.6f}（实际 {result['area']}）")
    check(vu.is_convex_polygon(points, normal), f"{desc} → 顶点顺序构成凸多边形")

    ok_on_plane = all(abs(vu.signed_distance(p, origin, normal)) <= 1e-6 for p in points)
    check(ok_on_plane, f"{desc} → 所有顶点都落在平面上")

    solid = shape_data.get_shape(result["shape"], result["dims"])
    vertices = solid["vertices"]
    ok_on_edge = True
    for p in points:
        hit_edge = False
        for i, j in solid["edges"]:
            a, b = tuple(vertices[i]), tuple(vertices[j])
            direction = vu.sub(b, a)
            length_sq = vu.length_sq(direction)
            t = 0.0 if length_sq < 1e-12 else vu.dot(vu.sub(p, a), direction) / length_sq
            t = min(1.0, max(0.0, t))
            if vu.distance(p, vu.lerp(a, b, t)) <= 1e-6:
                hit_edge = True
                break
        ok_on_edge &= hit_edge
    check(ok_on_edge, f"{desc} → 每个顶点都落在几何体的某条棱上（端点必然是棱与平面的交点）")

    closed = result["closed_polygon"]
    check(closed is not None and len(closed) == len(points) + 1, f"{desc} → 输出首尾相连的闭合折线")
    if closed:
        check(point_close(closed[0], closed[-1]), f"{desc} → 闭合折线首尾重合")
    check(vu.signed_area_3d(points, normal) > 0, f"{desc} → 顶点按法向量正向逆时针排列")


def test_section_cut() -> None:
    print("\n[3] 截面切割（正方体 / 长方体）")

    # 3.1 竖直切：正方形
    square = section_cut.cut("cube", (0.5, 0.0, 0.5), (1.0, 0.0, 0.0), verbose=False)
    assert_polygon(square, 4, 1.0, "x=0.5 竖直切正方体")

    # 3.2 过三个顶点的斜切：等边三角形，面积 √3/2
    triangle = section_cut.cut("cube", (1.0, 0.0, 0.0), (1.0, 1.0, 1.0), verbose=False)
    assert_polygon(triangle, 3, math.sqrt(3) / 2, "过 B/D/E 三个顶点的斜切")

    # 3.3 过体心斜切：正六边形，面积 3√3/4
    hexagon = section_cut.cut("cube", (0.5, 0.5, 0.5), (1.0, 1.0, 1.0), verbose=False)
    assert_polygon(hexagon, 6, 3 * math.sqrt(3) / 4, "过体心的斜切")

    # 3.4 水平切长方体：长方形 2 x 1.5
    rectangle = section_cut.cut("cuboid", (0.0, 0.0, 0.5), (0.0, 0.0, 1.0), verbose=False)
    assert_polygon(rectangle, 4, 3.0, "长方体 z=0.5 水平切")

    # 3.5 单点：平面只碰到一个顶点
    point = section_cut.cut("cube", (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), verbose=False)
    check(point["status"] == "point" and point["point_count"] == 1, "过顶点 (0,0,0) → 单点")
    check("一个点" in point["message"], "单点场景带中文提示")

    # 3.6 线段：平面沿一条棱擦过
    segment = section_cut.cut("cube", (0.0, 0.0, 0.0), (1.0, 1.0, 0.0), verbose=False)
    check(segment["status"] == "segment" and segment["point_count"] == 2, "沿棱 AE 擦过 → 线段")
    check("线段" in segment["message"], "线段场景带中文提示")

    # 3.7 无交点：平面在体外
    empty = section_cut.cut("cube", (0.0, 0.0, 5.0), (0.0, 0.0, 1.0), verbose=False)
    check(empty["status"] == "none" and empty["point_count"] == 0, "平面在体外 → 无交点")
    check("没有交点" in empty["message"], "无交点场景带中文提示")

    # 3.8 平面与底面共面：直接取该面的四边形
    coplanar = section_cut.cut("cube", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0), verbose=False)
    check(coplanar["status"] == "polygon" and coplanar["point_count"] == 4, "平面与底面共面 → 返回底面四边形")
    check(close(coplanar["area"], 1.0), "共面场景面积 = 1")
    check(any("共面" in w for w in coplanar["warnings"]), "共面场景给出 warning 提醒")

    # 3.9 法向量不归一也能用（内部单位化）
    scaled = section_cut.cut("cube", (0.5, 0.0, 0.5), (7.0, 0.0, 0.0), verbose=False)
    check(scaled["status"] == "polygon" and close(scaled["area"], 1.0), "法向量 (7,0,0) 自动单位化，结果一致")

    # 3.10 12 条棱必须全部被遍历并留下记录
    detail = section_cut.cut("cube", (0.5, 0.5, 0.5), (1.0, 1.0, 1.0), verbose=False, eps=1e-7)
    check(detail["edges_total"] == 12 and len(detail["edge_intersections"]) == 12, "12 条棱全部参与求交并保留明细")
    check(detail["edges_crossed"] == 6, f"过体心斜切有 6 条棱被穿过（实际 {detail['edges_crossed']}）")

    # 3.11 长方体自定义尺寸
    custom = section_cut.cut("cuboid", (0.0, 0.0, 0.5), (0.0, 0.0, 1.0), dims=(4.0, 2.0, 1.0), verbose=False)
    assert_polygon(custom, 4, 8.0, "长方体 4x2x1 水平切")

    # 3.12 退化多边形：平面正好切过一个顶点和它对面的一条棱，交点数 3 但共线的情况不会误判
    edge_case = section_cut.cut("cube", (0.5, 0.5, 0.0), (1.0, 0.0, 0.0), verbose=False)
    check(edge_case["status"] in ("polygon", "segment"), "边界退化用例不崩溃，返回合法场景")


# ---------------------------------------------------------------------------
# 4. 接口冒烟（可选：装了 fastapi 才跑）
# ---------------------------------------------------------------------------
def test_api() -> None:
    print("\n[4] 接口冒烟测试")
    try:
        from fastapi.testclient import TestClient
        from main import app
    except Exception as exc:  # pragma: no cover - 依赖未安装时显式跳过
        skip(f"接口冒烟测试：缺少依赖（{exc}），先运行 python -m pip install -r requirements.txt")
        return

    client = TestClient(app)

    resp = client.get("/api/shape/list")
    check(resp.status_code == 200 and resp.json()["data"]["unfold_types"]["total_unfold_types"] == 11,
          "GET /api/shape/list 返回 11 种展开图")

    resp = client.post("/api/hexahedron/get_data", json={"unfold_type": "141"})
    body = resp.json()
    check(resp.status_code == 200 and len(body["data"]["faces"]) == 6, "POST /api/hexahedron/get_data 返回 6 个面片")
    first = body["data"]["faces"][1]
    check(all(key in first for key in ("start_pos", "target_pos", "rotate_axis", "rotate_angle", "color_index")),
          "面片字段齐全：start_pos / target_pos / rotate_axis / rotate_angle / color_index")

    resp = client.post("/api/section/cut", json={"shape": "cube", "plane_origin": [0, 0, 0.5], "plane_normal": [0, 0, 1]})
    check(resp.status_code == 200 and len(resp.json()["data"]["points"]) == 4, "POST /api/section/cut 竖直切返回 4 个点")

    resp = client.post("/api/section/cut", json={"shape": "cube", "plane_origin": [0, 0, 0], "plane_normal": [1, 1, 0]})
    check(resp.status_code == 200 and resp.json()["data"]["status"] == "segment", "POST /api/section/cut 擦棱返回线段提示")

    resp = client.post("/api/section/cut", json={"shape": "cube", "plane_origin": [0, 0, 0], "plane_normal": [0, 0, 0]})
    check(resp.status_code == 422, "零法向量被 pydantic 拦下（422）")

    resp = client.options(
        "/api/section/cut",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    check(resp.status_code == 200 and resp.headers.get("access-control-allow-origin") == "http://localhost:5173",
          "CORS 预检允许 http://localhost:5173")


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main() -> int:
    print("=" * 72)
    print("空间几何 · 几何逻辑自测")
    print("=" * 72)
    test_vector_utils()
    test_hexahedron()
    test_section_cut()
    test_api()

    print("\n" + "=" * 72)
    if SKIPS:
        print(f"跳过：{len(SKIPS)} 组")
        for item in SKIPS:
            print("  -", item)
    if FAILURES:
        print(f"结果：{len(FAILURES)} 项失败")
        for item in FAILURES:
            print("  -", item)
        return 1
    print(f"结果：全部通过 ✅{'（有跳过项，见上）' if SKIPS else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())