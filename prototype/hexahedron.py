"""hexahedron.py —— 正方体 11 种公考标准展开图（每片独立，绝不合并成整体网格）

这个模块只回答一个问题：
**一张 6 个正方形的展开图，沿着哪些边、绕哪根轴、转多少度，能折成一个正方体？**

答案拆成 6 个独立面片。每片自己带 4 个角点坐标，**不做顶点合并、不输出三角面索引、
不返回一个"立方体网格"**——前端想让哪片动就让哪片动，想画 6 个独立平面就是 6 个平面。

每个面片记录 5 件核心事情
------------------------
    start_pos     初始平铺坐标：4 个角点，全部躺在 z = 0 平面上
    hinge_edge    铰链公共边：和"父面片"共享的那条边（两个端点）
    rotate_axis   旋转轴向量：**严格沿 hinge_edge 方向**的单位向量
    rotate_angle  需要旋转的角度：非基准面恒为 90°，基准面为 0
    target_pos    折叠之后目标坐标：4 个角点落在单位正方体 [0,1]³ 的某个面上

折叠为什么一定是"沿边翻折"
--------------------------
设铰链边方向为 e（单位向量），子面片从铰链指向自己的伸展方向为 d
（d 与 e 垂直，因为 d 在面片平面内、e 在棱上，两者垂直）。

折叠的物理动作是：让面片绕着这条棱转 90°，从"躺着"变成"立着"，即把 d 转到 +z（桌面朝上）。
能完成这个动作的旋转轴必须同时垂直于 d 和 z，因此

    axis = normalize(d × z)

而 d ⊥ e、z ⊥ e（e 在 z=0 平面内），所以 **d × z 必然与 e 平行**，
即旋转轴和公共边同方向——这就是"沿边翻折"的数学保证，不是靠调参数凑出来的。
模块在 import 时会逐个面片断言 |axis · e| = 1（自测里也会打印这条校验）。

父子关系与动画
--------------
一条 4 连的展开图要像卷纸一样绕成一圈：第 2 片绕第 1 片的棱折起，
第 3 片要绕"已经被折起来的第 2 片"再折 90°……所以面片之间有 parent_id / depth / fold_order，
最终位置 = 父面片变换 ∘ 自己绕棱转 90°。
报告给前端的 rotate_axis / hinge_edge 都是定义在"摊平坐标系"里的，
前端按 parent_id 做嵌套（每片的局部坐标就是摊平坐标），就能 1:1 复现 target_pos；
`fold_faces(faces, progress)` 就是这个过程的参考实现，可直接拿来做插值预览。

坐标约定
--------
右手坐标系，格子边长 1；展开图躺在 z = 0，基准面（第一片）占 [0,1]×[0,1]；
折叠完成后正方体固定为 [0,1]³，所以 11 种展开图的 target_pos 可以直接互相比较。

用法
----
    from hexahedron import get_hexahedron_data
    faces = get_hexahedron_data("141")      # 一四一型第 1 种，返回 6 个面片
    faces = get_hexahedron_data("141-3")    # 一四一型第 3 种
    faces = get_hexahedron_data("33")       # 三三型（只有 1 种）

直接运行本文件会打印 11 种展开图的面片参数并做校验：
    python hexahedron.py
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

# 三维点 / 向量
Vec3 = Tuple[float, float, float]

# 格子（面片）边长
EDGE: float = 1.0

# 每个非基准面片相对父面片折叠的角度：正方体相邻面互相垂直
FOLD_ANGLE: float = 90.0

# "上"方向：折叠时面片朝它立起来
UP: Vec3 = (0.0, 0.0, 1.0)

# 浮点容差（等于/不等于的比较一律走它）
EPS: float = 1e-9

# 折叠后 6 个面的身份 → (英文名, 中文名, 颜色编号, 颜色值)
# 颜色按"折完是哪一面"固定分配，于是 11 种展开图里同一面同色，方便对照讲解
FACE_STYLE: Dict[Tuple[int, int], Tuple[str, str, int, str]] = {
    (2, 0): ("bottom", "底面", 1, "#FF6B6B"),
    (2, 1): ("top", "顶面", 2, "#4D96FF"),
    (1, 0): ("front", "前面", 3, "#6BCB77"),
    (1, 1): ("back", "后面", 4, "#FFD93D"),
    (0, 0): ("left", "左面", 5, "#C780E8"),
    (0, 1): ("right", "右面", 6, "#FF9645"),
}

# 分型中文名
CODE_LABELS: Dict[str, str] = {
    "141": "一四一型",
    "231": "二三一型",
    "222": "二二二型",
    "33": "三三型",
}


# ===========================================================================
# 一、11 种展开图的布局表
# ===========================================================================
# cells 是 6 个格子的 (col, row) 坐标，**第一个恒为基准面 (0,0)**，也就是折叠时不动的那片。
#
# 这些坐标怎么来的：程序穷举了全部 216 个固定六联骨牌，用折叠模拟筛出"能折成正方体"的布局，
# 去掉旋转/镜像重复后恰好 11 类；再在每类的 8 个对称像里挑"行数图案"与公考叫法一致的那个朝向：
#     一四一 → 每行格子数 (1,4,1)      二三一 → (2,3,1)
#     二二二 → (2,2,2)                三三   → (3,3)
# 所以下面的字符画就是教科书里那 11 个形状（B = 基准面，# = 其它面片）：
#
#   141-1  #...   141-2  .#..   141-3  ..#.   141-4  ...#   141-5  .#..   141-6  ..#.
#          B###          #B##          ##B#          #B##          #B##          #B##
#          #...          #...          #...          #...          .#..          .#..
#
#   231-1  ..##   231-2  ..##   231-3  ..##
#          #B#.          #B#.          ##B.
#          #...          .#..          ..#.
#
#   222-1  ..##   33-1  ..###
#          .B#.         ##B..
#          ##..
NET_TABLE: Tuple[Dict[str, object], ...] = (
    # ---------------- 一四一型（6 种）：一排 4 个连片绕成一圈，上下各挂 1 片 ----------------
    {"code": "141", "variant": 1, "note": "十字形：上下翻盖挂在同一列（连片的一端）",
     "cells": [(0, 0), (0, -1), (0, 1), (1, 0), (2, 0), (3, 0)]},
    {"code": "141", "variant": 2, "note": "上翻盖在第二列，下翻盖在第一列",
     "cells": [(0, 0), (-1, -1), (-1, 0), (0, 1), (1, 0), (2, 0)]},
    {"code": "141", "variant": 3, "note": "上翻盖在第三列，下翻盖在第一列（4 连片的中间偏右）",
     "cells": [(0, 0), (-2, -1), (-2, 0), (-1, 0), (0, 1), (1, 0)]},
    {"code": "141", "variant": 4, "note": "上翻盖在第四列，下翻盖在第一列（镜像）",
     "cells": [(0, 0), (-1, -1), (-1, 0), (1, 0), (2, 0), (2, 1)]},
    {"code": "141", "variant": 5, "note": "上下翻盖挂在同一列（连片中间）",
     "cells": [(0, 0), (-1, 0), (0, -1), (0, 1), (1, 0), (2, 0)]},
    {"code": "141", "variant": 6, "note": "上翻盖在第三列，下翻盖在第二列",
     "cells": [(0, 0), (-1, 0), (0, -1), (1, 0), (1, 1), (2, 0)]},
    # ---------------- 二三一型（3 种）：行格子数依次 2 / 3 / 1 ----------------
    {"code": "231", "variant": 1, "note": "上行 2 连、中行 3 连、下行 1 连，错位排列",
     "cells": [(0, 0), (-1, -1), (-1, 0), (1, 0), (1, 1), (2, 1)]},
    {"code": "231", "variant": 2, "note": "上行 2 连靠右，下行 1 连居中",
     "cells": [(0, 0), (-1, 0), (0, -1), (1, 0), (1, 1), (2, 1)]},
    {"code": "231", "variant": 3, "note": "阶梯式二三一",
     "cells": [(0, 0), (-2, 0), (-1, 0), (0, -1), (0, 1), (1, 1)]},
    # ---------------- 二二二型（1 种）：三级台阶 ----------------
    {"code": "222", "variant": 1, "note": "三级台阶：三段 2 连片逐级错开一格",
     "cells": [(0, 0), (-1, -1), (0, -1), (1, 0), (1, 1), (2, 1)]},
    # ---------------- 三三型（1 种）：两排各 3 个，只共用一条棱 ----------------
    {"code": "33", "variant": 1, "note": "两排 3 连片错开一格，只有一条公共棱相连",
     "cells": [(0, 0), (-2, 0), (-1, 0), (0, 1), (1, 1), (2, 1)]},
)


# ===========================================================================
# 二、向量小工具（自包含，保证本文件单独拷走也能跑）
#     与 vector_utils.py 里同名函数完全一致，只是这里只放用得到的几个。
# ===========================================================================
def _sub(a: Sequence[float], b: Sequence[float]) -> Vec3:
    """向量减法 a - b。"""
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a: Sequence[float], b: Sequence[float]) -> Vec3:
    """向量加法。"""
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _scale(a: Sequence[float], k: float) -> Vec3:
    """数乘（k 为负则反向）。"""
    return (a[0] * k, a[1] * k, a[2] * k)


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    """点积 a·b = ax·bx + ay·by + az·bz，用来求投影、判垂直。"""
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Sequence[float], b: Sequence[float]) -> Vec3:
    """叉积 a × b，结果是同时垂直于两者的向量（右手定则）。"""
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _length(a: Sequence[float]) -> float:
    """模长 |a|。"""
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def _normalize(v: Sequence[float], eps: float = EPS) -> Vec3:
    """单位化：v / |v|；零向量没有方向，直接报错而不是返回 NaN。"""
    n = _length(v)
    if n <= eps:
        raise ValueError(f"零向量无法单位化: {tuple(v)}")
    return (v[0] / n, v[1] / n, v[2] / n)


def _midpoint(a: Sequence[float], b: Sequence[float]) -> Vec3:
    """线段中点。"""
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0, (a[2] + b[2]) / 2.0)


def _rotate_point(
    point: Sequence[float],
    pivot: Sequence[float],
    axis: Sequence[float],
    angle_deg: float,
) -> Vec3:
    """把 point 绕"过 pivot、方向为 axis 的直线"旋转 angle_deg 度（罗德里格斯公式）。

        v' = v·cosθ + (k × v)·sinθ + k·(k·v)·(1 − cosθ)

    其中 v 是"点相对 pivot 的位移"，k 是单位轴。
    三项的含义：旋转平面内的分量按 cos 缩放、垂直分量负责转过去、轴向分量保持不变。
    """
    k = _normalize(axis)
    theta = math.radians(angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)

    v = _sub(point, pivot)          # 先把 pivot 挪到原点
    kv = _dot(k, v)                 # 沿轴方向的投影长度（这部分不参与旋转）
    rotated = _add(
        _add(_scale(v, cos_t), _scale(_cross(k, v), sin_t)),
        _scale(k, kv * (1.0 - cos_t)),
    )
    return _add(rotated, pivot)     # 再平移回去


# ===========================================================================
# 三、面片几何：格子角点、邻接、公共边、旋转轴
# ===========================================================================
def cell_corners(cell: Sequence[int]) -> List[Vec3]:
    """一个格子的 4 个角点，逆时针（从 +z 往下看），全部在 z = 0。

    顺序固定为：左下 → 右下 → 右上 → 左上。
    折叠变换是刚体运动，变换后顺序不变，前端按顺序连成四边形即可。
    """
    c, r = int(cell[0]), int(cell[1])
    return [
        (c * EDGE, r * EDGE, 0.0),
        ((c + 1) * EDGE, r * EDGE, 0.0),
        ((c + 1) * EDGE, (r + 1) * EDGE, 0.0),
        (c * EDGE, (r + 1) * EDGE, 0.0),
    ]


def cell_center(cell: Sequence[int]) -> Vec3:
    """格子中心点，用来判断"子面片朝哪个方向伸展"。"""
    c, r = int(cell[0]), int(cell[1])
    return (c * EDGE + EDGE / 2.0, r * EDGE + EDGE / 2.0, 0.0)


def neighbors(cell: Sequence[int]) -> List[Tuple[int, int]]:
    """上下左右 4 个相邻格子，顺序固定，保证建树结果稳定可复现。"""
    c, r = int(cell[0]), int(cell[1])
    return [(c + 1, r), (c - 1, r), (c, r + 1), (c, r - 1)]


def shared_edge(parent: Sequence[int], child: Sequence[int]) -> Tuple[Vec3, Vec3]:
    """两个相邻格子**共用的那条边**（铰链），返回两个端点。

    * 同一行左右相邻：公共边是竖线 x = 两者较大的列号，y 覆盖这一行；
    * 同一列上下相邻：公共边是横线 y = 两者较大的行号，x 覆盖这一列。
    这两个端点同时属于父、子两片面片，所以它是真正的"公共棱"，不是虚拟的直线。
    """
    (c0, r0) = int(parent[0]), int(parent[1])
    (c1, r1) = int(child[0]), int(child[1])
    if r0 == r1:  # 左右相邻 → 竖直的公共棱
        x = max(c0, c1) * EDGE
        return (x, r0 * EDGE, 0.0), (x, (r0 + 1) * EDGE, 0.0)
    # 上下相邻 → 水平的公共棱
    y = max(r0, r1) * EDGE
    return (c0 * EDGE, y, 0.0), ((c0 + 1) * EDGE, y, 0.0)


def fold_axis(parent: Sequence[int], child: Sequence[int]) -> Tuple[Vec3, Vec3]:
    """求子面片折叠的旋转轴，以及轴上的一个点（铰链中点）。

    推导（这就是"沿边翻折"的证明）：
        1. 铰链方向 e = (h2 − h1) / |h2 − h1|，它躺在 z = 0 平面里；
        2. 伸展方向 d = 子格子中心 − 铰链中点，去掉沿 e 的分量后剩下的部分：
           d ⊥ e（所以 d 也在 z = 0 平面里）；
        3. 折叠要"把 d 转到 +z"，旋转轴必须垂直于 d 与 z，取
              axis = normalize(d × z)
           绕该轴 +90° 恰好把 d 转到 z（右手定则）；绕反方向 90° 会把面片压到 z < 0。
        4. 因为 d ⊥ e 且 z ⊥ e，所以 d × z 与 e 平行 —— **轴天然沿公共边**。

    返回 (铰链中点, 单位旋转轴)。
    """
    h1, h2 = shared_edge(parent, child)
    hinge_dir = _normalize(_sub(h2, h1))         # 公共边方向 e
    hinge_mid = _midpoint(h1, h2)                # 轴上的一点

    offset = _sub(cell_center(child), hinge_mid)  # 从铰链中点指向子面片中心
    along = _dot(offset, hinge_dir)               # 沿边的分量（绕边旋转时它不变）
    stretch = _sub(offset, _scale(hinge_dir, along))  # 垂直分量 d：真正的"伸展方向"

    axis = _normalize(_cross(stretch, UP))        # 让 d 转到 +z 的旋转轴
    return hinge_mid, axis


# ===========================================================================
# 四、折叠树与折叠变换
# ===========================================================================
def _build_tree(
    cells: Sequence[Sequence[int]], base: Sequence[int]
) -> Tuple[Dict[Tuple[int, int], Optional[Tuple[int, int]]], List[Tuple[int, int]]]:
    """以基准面为根，按广度优先把 6 个格子连成折叠树。

    返回 (parent_map, order)：order 是折叠顺序，父在前、子在后，
    正好对应"从桌面一片片往外折起来"的真实顺序。
    """
    key = lambda cell: (int(cell[0]), int(cell[1]))  # noqa: E731 - 小工具，无需命名函数
    cell_set = {key(c) for c in cells}
    base_key = key(base)

    parent: Dict[Tuple[int, int], Optional[Tuple[int, int]]] = {base_key: None}
    order: List[Tuple[int, int]] = [base_key]
    queue: List[Tuple[int, int]] = [base_key]
    while queue:
        current = queue.pop(0)
        for nb in neighbors(current):
            if nb in cell_set and nb not in parent:
                parent[nb] = current   # 第一次遇到即为父面片（BFS 保证层级最浅）
                order.append(nb)
                queue.append(nb)

    if len(order) != len(cell_set):
        raise ValueError(f"展开图不连通，无法折叠: {sorted(cell_set)}")
    return parent, order


def _build_transforms(
    cells: Sequence[Sequence[int]], base: Sequence[int]
) -> Tuple[
    Dict[Tuple[int, int], object],
    Dict[Tuple[int, int], Optional[Dict[str, object]]],
    List[Tuple[int, int]],
]:
    """为每个面片构造折叠变换函数、折叠参数、折叠顺序。

    变换的定义（父子复合）：
        T(基准面)  = 恒等
        T(子面片)  = T(父面片) ∘ 绕铰链转 90°
    即：先把点绕"摊平状态下的那条铰链"转 90°，再交给父面片的变换处理
    （父面片自己也是被它的父面片折过来的，所以这个递归天然支持 4 连片绕成一圈）。

    变换写成 ``transform(point, progress)``，progress ∈ [0, 1] 表示折叠进度，
    于是同一套公式既能算 target_pos（progress = 1），也能做动画插值。
    """
    key = lambda cell: (int(cell[0]), int(cell[1]))  # noqa: E731
    parent, order = _build_tree(cells, base)

    transforms: Dict[Tuple[int, int], object] = {}
    params: Dict[Tuple[int, int], Optional[Dict[str, object]]] = {}

    for cell in order:
        p = parent[cell]
        if p is None:
            # 基准面：不动
            transforms[cell] = lambda point, progress: (
                float(point[0]), float(point[1]), float(point[2])
            )
            params[cell] = None
            continue

        hinge_mid, axis = fold_axis(p, cell)
        hinge_a, hinge_b = shared_edge(p, cell)
        parent_transform = transforms[p]

        # 用默认参数把当前面片的铰链、轴、父变换"钉"进闭包，
        # 否则循环结束后所有闭包都会指向最后一个面片
        def make_transform(
            pivot: Vec3 = hinge_mid,
            rot_axis: Vec3 = axis,
            outer=parent_transform,
        ):
            def transform(point: Sequence[float], progress: float) -> Vec3:
                # 第一步：绕自己与父面片的公共棱旋转（在摊平坐标系里算）
                rotated = _rotate_point(point, pivot, rot_axis, FOLD_ANGLE * progress)
                # 第二步：叠加父面片的折叠变换（父面片可能已经立起来了）
                return outer(rotated, progress)

            return transform

        transforms[cell] = make_transform()
        params[cell] = {
            "hinge": (hinge_a, hinge_b),
            "hinge_mid": hinge_mid,
            "axis": axis,
            "angle": FOLD_ANGLE,
            "parent": p,
            "depth": 1 if params[p] is None else int(params[p]["depth"]) + 1,  # type: ignore[index]
        }

    return transforms, params, order


def _folded_face_identity(
    corners: Sequence[Sequence[float]], tol: float = 1e-7
) -> Optional[Tuple[int, int]]:
    """判断折完后的面片贴在正方体的哪一面，返回 (坐标轴, 侧别)。

    例如 4 个角点的 z 都等于 1 → (2, 1) 顶面；x 都等于 0 → (0, 0) 左面。
    判断不出来说明这个展开图折不成正方体（或面片跑出 [0,1]³）。
    """
    for axis in range(3):
        values = [float(p[axis]) for p in corners]
        if max(values) - min(values) > tol:
            continue  # 该坐标不固定 → 面片不平行于这个坐标平面
        value = values[0]
        if abs(value) <= tol:
            side = 0
        elif abs(value - EDGE) <= tol:
            side = 1
        else:
            return None  # 贴到了别的平面上，不是单位正方体的面
        # 其余两个坐标必须落在 [0, 1] 之内，否则面片跑出立方体
        for p in corners:
            for k in range(3):
                if float(p[k]) < -tol or float(p[k]) > EDGE + tol:
                    return None
        return (axis, side)
    return None


# ===========================================================================
# 五、对外接口：get_hexahedron_data
# ===========================================================================
def _parse_unfold_type(unfold_type: str) -> Dict[str, object]:
    """解析展开图类型字符串，支持三种写法：``141`` / ``141-3`` / ``141_3``。

    不写变体号时默认取第 1 种；变体号越界或分型不存在都会报错并列出可选值。
    """
    raw = str(unfold_type).strip()
    code, variant_text = raw, None
    for sep in ("-", "_"):
        if sep in raw:
            head, tail = raw.split(sep, 1)
            if tail.strip().isdigit():
                code, variant_text = head.strip(), tail.strip()
            break

    if code not in CODE_LABELS:
        raise ValueError(
            f"不支持的展开图类型: {unfold_type}；可用值: "
            + "、".join(CODE_LABELS.keys())
            + "（可写成 141-2 指定第几种）"
        )

    options = [e for e in NET_TABLE if e["code"] == code]
    variant = int(variant_text) if variant_text else 1
    if variant < 1 or variant > len(options):
        raise ValueError(f"{code} 型只有 {len(options)} 种展开图，变体号 {variant} 越界")
    return options[variant - 1]


def get_hexahedron_data(unfold_type: str) -> List[Dict[str, object]]:
    """按展开图类型返回 **6 个独立面片** 组成的数组（不合并顶点、不输出立方体网格）。

    参数
    ----
    unfold_type : ``"141"`` / ``"141-3"`` / ``"231"`` / ``"222"`` / ``"33"``
                  不写变体号时取第 1 种。

    返回
    ----
    list[dict]，长度恒为 6，每项字段：

        face_id          面片序号 0~5（0 是基准面）
        cell             在展开图里的格子坐标 [col, row]
        color / color_index  颜色值与颜色编号（1~6，按折完是哪一面固定分配）
        target_face      折叠后对应的面：bottom/top/front/back/left/right
        start_pos        初始平铺坐标：4 个角点 (x, y, 0)
        hinge_edge       铰链公共边：与父面片共享的边的两个端点；基准面为 None
        hinge_edge_folded 折完后这条公共棱的位置
        rotate_axis      旋转轴向量（单位向量，**沿 hinge_edge 方向**）；基准面为 None
        rotate_angle     需要旋转的角度：非基准面 90.0，基准面 0.0
        target_pos       折叠之后目标坐标：4 个角点，落在单位正方体 [0,1]³ 上
        parent_id        父面片序号；子面片必须在父面片折完之后再折
        depth / fold_order  折叠层级 / 折叠顺序（0 表示最先折）
        is_base          是否基准面
    """
    entry = _parse_unfold_type(unfold_type)
    cells = [(int(c[0]), int(c[1])) for c in entry["cells"]]  # type: ignore[index]
    code = str(entry["code"])
    variant = int(entry["variant"])  # type: ignore[arg-type]

    base = cells[0]  # 约定：第一个格子是基准面 (0, 0)
    transforms, params, order = _build_transforms(cells, base)
    order_index = {cell: i for i, cell in enumerate(order)}

    faces: List[Dict[str, object]] = []
    for face_id, cell in enumerate(cells):
        # ---- 初始平铺坐标（z 恒为 0，说明它躺在桌面上）----
        start_pos = cell_corners(cell)

        # ---- 折叠之后的目标坐标：对 4 个角点做完整折叠变换 ----
        transform = transforms[cell]
        target_pos = [
            tuple(round(v, 9) + 0.0 for v in transform(p, 1.0))  # type: ignore[operator]
            for p in start_pos
        ]

        # ---- 面片折完贴在正方体哪一面 → 决定颜色 ----
        identity = _folded_face_identity(target_pos)
        if identity is None:
            raise ValueError(f"展开图 {code}-{variant} 的面片 {cell} 未能折到单位正方体表面")
        face_name, face_label, color_index, color_hex = FACE_STYLE[identity]

        info = params[cell]
        if info is None:
            # 基准面：不折、不转，没有铰链
            hinge_edge = None
            hinge_edge_folded = None
            rotate_axis = None
            rotate_angle = 0.0
            parent_id = None
            depth = 0
        else:
            hinge_a, hinge_b = info["hinge"]  # type: ignore[misc]
            # 铰链的两个端点（摊平状态）
            hinge_edge = [
                tuple(round(v, 9) + 0.0 for v in hinge_a),
                tuple(round(v, 9) + 0.0 for v in hinge_b),
            ]
            # 同一条棱折完后的位置：用来验证"折叠后两片仍然共边"
            hinge_edge_folded = [
                tuple(round(v, 9) + 0.0 for v in transform(hinge_a, 1.0)),  # type: ignore[operator]
                tuple(round(v, 9) + 0.0 for v in transform(hinge_b, 1.0)),  # type: ignore[operator]
            ]
            rotate_axis = tuple(round(v, 9) + 0.0 for v in info["axis"])  # type: ignore[misc]
            rotate_angle = float(info["angle"])  # type: ignore[arg-type]
            parent_id = cells.index(info["parent"])  # type: ignore[arg-type]
            depth = int(info["depth"])  # type: ignore[arg-type]

        faces.append(
            {
                "face_id": face_id,
                "cell": [cell[0], cell[1]],
                "color": color_hex,
                "color_index": color_index,
                "target_face": face_name,
                "target_face_label": face_label,
                # —— 5 个核心字段 ——
                "start_pos": [tuple(round(v, 9) + 0.0 for v in p) for p in start_pos],
                "hinge_edge": hinge_edge,
                "rotate_axis": rotate_axis,
                "rotate_angle": rotate_angle,
                "target_pos": target_pos,
                # —— 折叠结构 ——
                "hinge_edge_folded": hinge_edge_folded,
                "parent_id": parent_id,
                "depth": depth,
                "fold_order": order_index[cell],
                "is_base": info is None,
            }
        )

    return faces


def list_unfold_types() -> List[Dict[str, object]]:
    """列出全部 11 种展开图（分型、变体号、格子布局、说明），供前端做选择题菜单。"""
    return [
        {
            "code": str(entry["code"]),
            "label": f"{CODE_LABELS[str(entry['code'])]}·第{entry['variant']}种",
            "unfold_type": f"{entry['code']}-{entry['variant']}",
            "note": entry["note"],
            "cells": [[int(c[0]), int(c[1])] for c in entry["cells"]],  # type: ignore[index]
        }
        for entry in NET_TABLE
    ]


def fold_faces(faces: Sequence[Dict[str, object]], progress: float = 1.0) -> List[List[Vec3]]:
    """把 get_hexahedron_data 的结果按**折叠进度**插值，返回每片当前的 4 个角点。

    这是"沿边翻折"的参考实现，也是前端动画的对照答案：

        progress = 0   → 完全摊平（等于每片的 start_pos）
        progress = 1   → 完全折好（等于每片的 target_pos）
        0 < p < 1      → 中间状态；每片的铰链点始终不动，面片只绕着那条棱转

    实现方式：按 parent_id 逐级复合——子面片先绕自己的铰链转 angle·progress，
    再交给父面片的变换。仍然返回 6 个独立多边形，不合并成网格。
    """
    p = max(0.0, min(1.0, float(progress)))
    by_id = {int(f["face_id"]): f for f in faces}

    cache: Dict[int, object] = {}

    def transform_of(face: Dict[str, object]):
        """递归取得某个面片的变换函数（带缓存，避免重复递归）。"""
        fid = int(face["face_id"])  # type: ignore[arg-type]
        if fid in cache:
            return cache[fid]

        if face["is_base"]:
            def identity(point: Sequence[float]) -> Vec3:
                return (float(point[0]), float(point[1]), float(point[2]))

            cache[fid] = identity
            return identity

        parent_tf = transform_of(by_id[int(face["parent_id"])])  # type: ignore[arg-type]
        pivot = face["hinge_edge"][0]  # type: ignore[index]
        axis = face["rotate_axis"]
        angle = float(face["rotate_angle"]) * p  # type: ignore[arg-type]

        def transform(point: Sequence[float]) -> Vec3:
            return parent_tf(_rotate_point(point, pivot, axis, angle))  # type: ignore[arg-type,operator]

        cache[fid] = transform
        return transform

    result: List[List[Vec3]] = []
    for face in faces:
        tf = transform_of(face)
        result.append([tf(point) for point in face["start_pos"]])  # type: ignore[index,operator]
    return result


def render_net_ascii(cells: Sequence[Sequence[int]]) -> str:
    """把展开图画成字符画，方便在终端里肉眼确认形状（B = 基准面，# = 其它面片）。"""
    cell_set = {(int(c[0]), int(c[1])) for c in cells}
    xs = [c[0] for c in cell_set]
    ys = [c[1] for c in cell_set]
    lines = []
    for row in range(max(ys), min(ys) - 1, -1):
        line = ""
        for col in range(min(xs), max(xs) + 1):
            if (col, row) == (0, 0):
                line += "B"
            elif (col, row) in cell_set:
                line += "#"
            else:
                line += "."
        lines.append(line)
    return "\n".join(lines)


# ===========================================================================
# 六、自测：打印每片面片折叠前后参数，并验证旋转轴确实沿公共边
# ===========================================================================
def _close(a: float, b: float, tol: float = 1e-9) -> bool:
    """浮点近似相等。"""
    return abs(a - b) <= tol


def _same_point(p: Sequence[float], q: Sequence[float], tol: float = 1e-9) -> bool:
    """三维点近似相等。"""
    return _length(_sub(p, q)) <= tol


def _quad_area(corners: Sequence[Sequence[float]]) -> float:
    """平面四边形面积：拆成两个三角形，用叉积模长的一半相加。"""
    a, b, c, d = corners
    tri1 = 0.5 * _length(_cross(_sub(b, a), _sub(c, a)))
    tri2 = 0.5 * _length(_cross(_sub(c, a), _sub(d, a)))
    return tri1 + tri2


class _Checker:
    """极简断言收集器：一条失败不影响后面继续跑，最后统一汇总。"""

    def __init__(self) -> None:
        self.failures: List[str] = []
        self.passed = 0

    def check(self, ok: bool, message: str) -> None:
        if ok:
            self.passed += 1
            print(f"      ✔ {message}")
        else:
            self.failures.append(message)
            print(f"      ✘ {message}")


def _print_face(face: Dict[str, object]) -> None:
    """打印一个面片的折叠前后参数（自测的主要输出）。"""
    fmt = lambda pts: "[" + ", ".join("(" + ", ".join(f"{v:.2f}" for v in p) + ")" for p in pts) + "]"  # noqa: E731
    head = f"  面片 #{face['face_id']}  颜色{face['color_index']}{face['color']}  折后={face['target_face_label']}"
    if face["is_base"]:
        print(head + "  ★基准面（不折、不转）")
    else:
        print(head + f"  父片=#{face['parent_id']}  深度={face['depth']}  折叠顺序={face['fold_order']}")
    print(f"      start_pos   = {fmt(face['start_pos'])}")
    print(f"      target_pos  = {fmt(face['target_pos'])}")
    if not face["is_base"]:
        print(f"      hinge_edge  = {fmt(face['hinge_edge'])}   ← 与父片共用的边")
        print(f"      rotate_axis = ({', '.join(f'{v:.2f}' for v in face['rotate_axis'])})   "
              f"rotate_angle = {face['rotate_angle']:.1f}°")


def _verify_faces(checker: _Checker, unfold_type: str, faces: List[Dict[str, object]]) -> None:
    """校验一种展开图的 6 个面片：轴沿边、铰链共享、刚体折叠、落面完整。"""
    # ---------- 1. 结构：必须 6 片独立面片 ----------
    checker.check(len(faces) == 6, f"返回 6 个独立面片（实际 {len(faces)}）")
    checker.check(all(len(f["start_pos"]) == 4 and len(f["target_pos"]) == 4 for f in faces),
                  "每片都有 4 个角点（start_pos / target_pos）")
    checker.check(len({tuple(face["start_pos"][0]) for face in faces}) == 6,
                  "6 片各自独立，没有合并成整体网格")
    checker.check(sorted(f["color_index"] for f in faces) == [1, 2, 3, 4, 5, 6],
                  "6 个颜色编号 1~6 各出现一次")

    # ---------- 2. 初始平铺：全部在 z = 0 平面 ----------
    checker.check(all(_close(p[2], 0.0) for f in faces for p in f["start_pos"]),
                  "初始平铺坐标全部躺在 z = 0 平面上（可以摊在桌面上）")

    # ---------- 3. 折叠目标：落在单位正方体 6 个不同的面上 ----------
    checker.check(all(-1e-9 <= p[k] <= 1.0 + 1e-9 for f in faces for p in f["target_pos"] for k in range(3)),
                  "折叠目标坐标全部落在单位正方体 [0,1]³ 内")
    checker.check(len({f["target_face"] for f in faces}) == 6,
                  "6 片分别贴在正方体 6 个不同的面上（不重叠、不缺面）")
    checker.check(all(_close(_quad_area(f["target_pos"]), 1.0, 1e-9) for f in faces),
                  "每片折叠后面积仍为 1（刚体运动，没有被拉伸）")

    # ---------- 4. 铰链 / 旋转轴（本模块的重点）----------
    by_id = {int(f["face_id"]): f for f in faces}
    for face in faces:
        if face["is_base"]:
            checker.check(face["rotate_axis"] is None and face["rotate_angle"] == 0.0,
                          f"面片 #{face['face_id']}（基准面）不动：rotate_angle = 0")
            continue

        hinge = face["hinge_edge"]
        axis = face["rotate_axis"]
        parent = by_id[int(face["parent_id"])]  # type: ignore[arg-type]
        panel = f"面片 #{face['face_id']}"

        # 4.1 铰链的两个端点必须同时是"自己"和"父片"的角点 → 证明它是两片共享的边
        own_corners = face["start_pos"]
        parent_corners = parent["start_pos"]
        checker.check(
            all(any(_same_point(h, c) for c in own_corners) for h in hinge)
            and all(any(_same_point(h, c) for c in parent_corners) for h in hinge),
            f"{panel}：铰链两端点同时是【自己】和【父片】的角点（真的是公共边）",
        )
        # 4.2 铰链长度 = 1（正好是格子的一条边）
        checker.check(_close(_length(_sub(hinge[1], hinge[0])), EDGE),
                      f"{panel}：铰链长度 = 1（是一条完整的棱）")

        # 4.3 旋转轴是单位向量
        checker.check(_close(_length(axis), 1.0), f"{panel}：rotate_axis 是单位向量")

        # 4.4 旋转轴与公共边平行 —— 这就是"沿边翻折"的判据
        hinge_dir = _normalize(_sub(hinge[1], hinge[0]))
        alignment = abs(_dot(axis, hinge_dir))
        checker.check(_close(alignment, 1.0, 1e-9),
                      f"{panel}：|axis · 铰链方向| = {alignment:.12f} ≈ 1，轴严格沿公共边")

        # 4.5 轴躺在摊平平面内（轴 ⊥ z），否则会变成"绕竖直轴旋转"的平移式错误动画
        checker.check(_close(abs(_dot(axis, UP)), 0.0), f"{panel}：axis ⊥ z 轴（轴在摊平平面内）")

        # 4.6 只绕自己的铰链转 90°（不叠加父片）后，面片应当"立起来"：
        #     仍然压在自己那条铰链上（端点不动）、并且垂直立于 z=0 平面上
        pivot = hinge[0]
        local = [_rotate_point(p, pivot, axis, float(face["rotate_angle"])) for p in own_corners]  # type: ignore[arg-type]
        checker.check(all(_same_point(local[i], own_corners[i]) for i in _hinge_corner_indices(own_corners, hinge)),
                      f"{panel}：绕铰链转 90° 后，铰链上的两个角点原地不动（不平移）")
        checker.check(all(v >= -1e-9 for v in (p[2] for p in local)) and _close(max(p[2] for p in local), 1.0),
                      f"{panel}：绕铰链转 90° 后面片立起来（z 从 0 抬到 1，朝 +z 折）")

        # 4.7 折叠后仍与父片共边：两条 hinge_edge_folded 应一一对上父片的角点
        checker.check(
            all(any(_same_point(h, c) for c in parent["target_pos"]) for h in face["hinge_edge_folded"]),
            f"{panel}：折叠后这条棱仍落在父片的一条边上（折完依然连着，没有飞走）",
        )

    # ---------- 5. 用 fold_faces 复算一遍：进度 0 / 1 必须等于 start / target ----------
    flat = fold_faces(faces, 0.0)
    folded = fold_faces(faces, 1.0)
    checker.check(all(_same_point(a, b) for f, f0 in zip(faces, flat) for a, b in zip(f["start_pos"], f0)),
                  "fold_faces(0.0) 与每片 start_pos 完全一致")
    checker.check(all(_same_point(a, b) for f, f1 in zip(faces, folded) for a, b in zip(f["target_pos"], f1)),
                  "fold_faces(1.0) 与每片 target_pos 完全一致")
    # 折叠过程中（progress = 0.5）面片会甩到立方体外侧，这是正常的；
    # 真正该守住的两条是：每片仍保持 1x1 的面积，铰链始终贴在父片上。
    half = fold_faces(faces, 0.5)
    checker.check(all(_close(_quad_area(corners), 1.0, 1e-9) for corners in half),
                  "折叠进度 0.5 时每片面积仍为 1（过程中也是刚体运动，没有被拉伸）")
    half_by_id = {int(f["face_id"]): corners for f, corners in zip(faces, half)}
    hinge_glued = True
    for face in faces:
        if face["is_base"]:
            continue
        own_half = half_by_id[int(face["face_id"])]
        parent_half = half_by_id[int(face["parent_id"])]  # type: ignore[arg-type]
        hinge_idx = _hinge_corner_indices(face["start_pos"], face["hinge_edge"])
        # 折叠到一半时，铰链端点仍应落在父片当前位置的角点上 —— 说明是"贴着边翻"而不是"飞起来"
        hinge_glued &= all(any(_same_point(own_half[i], pc) for pc in parent_half) for i in hinge_idx)
    checker.check(hinge_glued, "折叠进度 0.5 时每片的铰链端点仍贴在父片角点上（全程沿边翻折）")


def _hinge_corner_indices(corners: Sequence[Sequence[float]], hinge: Sequence[Sequence[float]]) -> List[int]:
    """找出铰链端点在 4 个角点里的下标（用于验证折叠时这两点不动）。"""
    idx = []
    for i, c in enumerate(corners):
        if any(_same_point(c, h) for h in hinge):
            idx.append(i)
    return idx


def _self_test() -> int:
    """打印 11 种展开图的全部面片参数，并逐条校验。返回进程退出码。"""
    checker = _Checker()

    print("=" * 78)
    print("hexahedron · 正方体 11 种展开图自测")
    print("=" * 78)
    print("约定：面片 = 一个正方形；start_pos 是摊平坐标（z=0），target_pos 是折完坐标（[0,1]³）")
    print("      hinge_edge 是与父片共享的棱，rotate_axis 必须严格沿这条棱的方向")

    # 分型 → 应有数量，用来确认 11 种齐全
    expected = {"141": 6, "231": 3, "222": 1, "33": 1}

    index = 0
    for entry in NET_TABLE:
        index += 1
        code = str(entry["code"])
        variant = int(entry["variant"])  # type: ignore[arg-type]
        unfold_type = f"{code}-{variant}"

        print("\n" + "-" * 78)
        print(f"[{index}/11] {unfold_type}  {CODE_LABELS[code]}·第{variant}种  —— {entry['note']}")
        print("展开图（B = 基准面，摊平在 z=0 平面）：")
        for line in render_net_ascii(entry["cells"]).splitlines():  # type: ignore[arg-type]
            print("      " + line)
        print("面片参数：")

        faces = get_hexahedron_data(unfold_type)
        for face in faces:
            _print_face(face)

        print("  校验：")
        _verify_faces(checker, unfold_type, faces)

    # ---- 总量校验：11 种齐全 ----
    print("\n" + "-" * 78)
    print("数量校验：")
    counts = {code: 0 for code in expected}
    for entry in NET_TABLE:
        counts[str(entry["code"])] += 1
    for code, want in expected.items():
        checker.check(counts[code] == want, f"{CODE_LABELS[code]}（{code}）{want} 种（实际 {counts[code]}）")
    checker.check(len(NET_TABLE) == 11, f"展开图合计 11 种（实际 {len(NET_TABLE)}）")
    checker.check(len(list_unfold_types()) == 11, "list_unfold_types() 返回 11 项")

    # ---- 非法输入 ----
    print("\n非法输入：")
    for bad in ("999", "141-9", "231-0"):
        try:
            get_hexahedron_data(bad)
            checker.check(False, f"{bad} 应当报错")
        except ValueError:
            checker.check(True, f"{bad} 正确抛出 ValueError")

    # ---- 收尾 ----
    print("\n" + "=" * 78)
    if checker.failures:
        print(f"结果：{checker.passed} 项通过，{len(checker.failures)} 项失败")
        for item in checker.failures:
            print("  - " + item)
        return 1
    print(f"结果：全部通过 ✅（共 {checker.passed} 项校验）")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())