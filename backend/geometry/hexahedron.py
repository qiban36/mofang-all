"""正方体（六面体）11 种展开图 + 折叠动画参数。

公考"空间几何"里的立体折叠题，本质就是一句话：
**把 6 个正方形摊平在桌面上（展开），再沿公共棱一片片折起 90°，看它能不能合成一个正方体。**

本模块把这句话变成了可计算的数据结构：

1. 每种展开图用"网格坐标"描述：6 个格子 (col, row) 表示 6 个面片摊平后的位置，
   格子边长 = 1，全部躺在 z = 0 平面上。
2. 相邻两个格子共用一条棱（铰链 / 折痕），子面片绕着这条棱转 90° 就"立起来"。
3. 折叠方向用一个统一的几何规则确定：让面片的伸展方向转到 +z（桌面朝上），
   并且沿父子关系逐级复合——这样一整条 4 连片就能像卷纸一样绕成一圈。
4. 折完以后每个面片的 4 个角点必然落在单位正方体 [0,1]³ 的某个面上，
   模块在 import 时对 11 种展开图全部做一次落面校验，校验不过直接抛错。

为什么折叠方向要"逐级复合"？
---------------------------
一条 4 连的展开图（如一四一型的中间横排）要绕成一圈：第 2 片绕第 1 片的棱折 90°，
第 3 片要绕"已经被折起来的第 2 片"再折 90°，第 4 片同理。
所以每个面片的最终位置 = 父面片变换 ∘ 自己绕棱转 90°，
代码里用嵌套函数（闭包）实现这种"父子复合"，比手写 4x4 矩阵更好读。

坐标约定
--------
* 展开图落在 z = 0 平面，基准面（第一片，不动的那个面）占据 [0,1] x [0,1]。
* 折叠完成后，正方体固定为 [0,1]³，因此 11 种展开图折出来的 target_pos
  可以互相比较，也方便和 section_cut 的截面结果对应。
"""

from __future__ import annotations

import copy
import logging
import math
from functools import lru_cache
from typing import Callable, Dict, List, Optional, Sequence, Tuple, TypedDict

from . import vector_utils as vu

_LOGGER = logging.getLogger(__name__)

# 面片边长（格子边长）
EDGE_LENGTH: float = 1.0

# 每个面片相对父面片的折叠角度（度）。正方体每个面互相垂直，所以恒为 90°
FOLD_ANGLE: float = 90.0

# 上方向：折叠时面片朝它立起来
UP: vu.Vec3 = (0.0, 0.0, 1.0)

# 折叠后的 6 个面身份 → (英文名, 中文名, 颜色编号, 颜色值)
# 颜色按"折完之后是哪一面"分配，这样 11 种展开图里"同一面同色"，便于对照讲解
FACE_STYLE: Dict[Tuple[int, int], Tuple[str, str, int, str]] = {
    (2, 0): ("bottom", "底面", 1, "#FF6B6B"),
    (2, 1): ("top", "顶面", 2, "#4D96FF"),
    (1, 0): ("front", "前面", 3, "#6BCB77"),
    (1, 1): ("back", "后面", 4, "#FFD93D"),
    (0, 0): ("left", "左面", 5, "#C780E8"),
    (0, 1): ("right", "右面", 6, "#FF9645"),
}


# ---------------------------------------------------------------------------
# 数据结构（TypedDict）
# ---------------------------------------------------------------------------
# 这些结构同时也是接口出参的形状，写清楚字段类型后，构建过程里就不需要
# 到处 `# type: ignore[index]` 了，IDE 也能直接补全。
class NetEntry(TypedDict):
    """NET_TABLE 里的一条展开图记录。"""

    code: str
    variant: int
    cells: List[Tuple[int, int]]
    note: str


class FoldInfo(TypedDict):
    """一个子面片相对父面片的折叠参数。"""

    hinge_mid: vu.Vec3
    hinge: Tuple[vu.Vec3, vu.Vec3]
    axis: vu.Vec3
    angle: float
    parent: Tuple[int, int]
    depth: int


class FaceOut(TypedDict):
    """接口里一个面片的完整数据。"""

    face_index: int
    cell: List[int]
    color_index: int
    color: str
    target_face: str
    target_face_label: str
    start_pos: List[vu.Vec3]
    target_pos: List[vu.Vec3]
    hinge_edge: Optional[List[vu.Vec3]]
    hinge_edge_folded: Optional[List[vu.Vec3]]
    rotate_axis: Optional[vu.Vec3]
    rotate_angle: float
    target_normal: vu.Vec3
    parent_id: Optional[int]
    depth: int
    fold_order: int
    is_base: bool


class AnimationStep(TypedDict):
    """折叠动画的单个步骤。"""

    face_index: int
    fold_order: int
    start_time: float
    duration: float
    rotate_axis: Optional[vu.Vec3]
    rotate_angle: float
    pivot: Optional[vu.Vec3]
    parent_id: Optional[int]


class FoldAnimation(TypedDict):
    """整段折叠动画的时间轴。"""

    easing: str
    step_duration: float
    overlap: float
    total_duration: float
    fps: int
    play_order: List[int]
    steps: List[AnimationStep]
    note: str


class NetBounds(TypedDict):
    """展开状态的整体包围盒。"""

    min: List[float]
    max: List[float]
    width: float
    height: float


class HexahedronData(TypedDict):
    """POST /api/hexahedron/get_data 的 data。"""

    unfold_type: str
    variant: int
    net_id: str
    label: str
    note: str
    edge_length: float
    face_count: int
    cells: List[List[int]]
    base_face_index: int
    faces: List[FaceOut]
    net_bounds: NetBounds
    fold_sequence: List[int]
    animation: FoldAnimation


class UnfoldVariant(TypedDict):
    variant: int
    net_id: str
    label: str
    note: str
    cells: List[List[int]]


class UnfoldGroup(TypedDict):
    code: str
    label: str
    count: int
    variants: List[UnfoldVariant]


class UnfoldTypes(TypedDict):
    total_unfold_types: int
    groups: List[UnfoldGroup]
    codes: List[str]


class ValidateReport(TypedDict):
    """import 时自检的报告（自测脚本会打印它）。"""

    net_id: str
    faces: Dict[Tuple[int, int], Tuple[int, int]]
    fold_order: List[Tuple[int, int]]
    ok: bool


# ---------------------------------------------------------------------------
# 一、11 种展开图的静态布局
# ---------------------------------------------------------------------------
# 每条记录的 cells 是 6 个格子的 (col, row) 坐标，**第一个格子恒为基准面 (0,0)**。
# 基准面在折叠过程中保持不动，其余 5 片依次绕着公共棱折起来。
#
# 分类沿用公考教材的叫法（按"摊平后每行的格子数"分型）：
#   一四一型 6 种 / 二三一型 3 种 / 二二二型 1 种 / 三三型 1 种 = 11 种
# 这些坐标不是手抄的，而是用 6 格连通多联骨牌穷举 + 折叠校验筛出来的：
# 216 个固定六联骨牌中，能折成正方体的恰好 11 类（去掉旋转/镜像重复）。
# 朝向约定（2026-11 统一）：一律采用公考教材的横排画法——
# 一四一型的"四"横着摆（不是竖着），上下翻盖挂在横排两侧，
# 这样前端渲染出的摊平图与教材原图、与 prototype 版完全同向。
# 每种展开图的"形状"未变，只是整体旋转/镜像到了教材朝向。
NET_TABLE: Tuple[NetEntry, ...] = (
    # ---- 一四一型：中间一排 4 个连片绕成一圈，上下各挂 1 片（共 6 种）----
    {"code": "141", "variant": 1, "cells": [(0, 0), (0, -1), (0, 1), (1, 0), (2, 0), (3, 0)],
     "note": "十字形：横排 4 片，上下翻盖挂在最左一格"},
    {"code": "141", "variant": 2, "cells": [(0, 0), (-1, -1), (-1, 0), (1, 0), (2, 0), (2, 1)],
     "note": "上下翻盖分挂横排两端（左端上、右端下）"},
    {"code": "141", "variant": 3, "cells": [(0, 0), (-1, 0), (0, -1), (1, 0), (1, 1), (2, 0)],
     "note": "上下翻盖交错：上翻盖在第 2 格，下翻盖在第 3 格"},
    {"code": "141", "variant": 4, "cells": [(0, 0), (-2, -1), (-2, 0), (-1, 0), (0, 1), (1, 0)],
     "note": "上翻盖在最左端，下翻盖在横排第 3 格"},
    {"code": "141", "variant": 5, "cells": [(0, 0), (-1, 0), (0, -1), (0, 1), (1, 0), (2, 0)],
     "note": "十字形：横排 4 片，上下翻盖挂在第 2 格"},
    {"code": "141", "variant": 6, "cells": [(0, 0), (-1, -1), (-1, 0), (0, 1), (1, 0), (2, 0)],
     "note": "上翻盖在最左端，下翻盖在横排第 2 格"},
    # ---- 二三一型：行格子数为 2 / 3 / 1 的三种（共 3 种）----
    {"code": "231", "variant": 1, "cells": [(0, 0), (-1, -1), (-1, 0), (1, 0), (1, 1), (2, 1)],
     "note": "1 / 3 / 2 阶梯式：左上 1 片、中排 3 片、右下 2 片"},
    {"code": "231", "variant": 2, "cells": [(0, 0), (-1, 0), (0, -1), (1, 0), (1, 1), (2, 1)],
     "note": "上 1 片、中排 3 片、右下 2 片，错开一格"},
    {"code": "231", "variant": 3, "cells": [(0, 0), (-2, 0), (-1, 0), (0, -1), (0, 1), (1, 1)],
     "note": "二三一对角错位：上翻盖在横排第 3 格"},
    # ---- 二二二型：三段 2 连台阶（共 1 种）----
    {"code": "222", "variant": 1, "cells": [(0, 0), (-1, -1), (0, -1), (1, 0), (1, 1), (2, 1)],
     "note": "三级台阶：上 2 片、中 2 片、下 2 片依次右移"},
    # ---- 三三型：两排各 3 个连片，错开两列（共 1 种）----
    {"code": "33", "variant": 1, "cells": [(0, 0), (-2, 0), (-1, 0), (0, 1), (1, 1), (2, 1)],
     "note": "上排 3 片、下排 3 片，错开两格由一条公共棱相连"},
)

# 每个分型对应的中文名
CODE_LABELS: Dict[str, str] = {
    "141": "一四一型",
    "231": "二三一型",
    "222": "二二二型",
    "33": "三三型",
}


# ---------------------------------------------------------------------------
# 二、展开图的基本几何：格子角点、邻接、铰链棱
# ---------------------------------------------------------------------------
def cell_corners(cell: Tuple[int, int], z: float = 0.0) -> List[vu.Vec3]:
    """返回一个格子的 4 个角点（逆时针，从 +z 方向看）。

    格子 (col, row) 占据 x∈[col, col+1]、y∈[row, row+1]。
    角点顺序固定为：左下 → 右下 → 右上 → 左上，
    这样折叠变换后 4 个点的顺序也不会乱，前端可以直接按顺序连成四边形。
    """
    c, r = cell
    e = EDGE_LENGTH
    return [
        (c * e, r * e, z),
        ((c + 1) * e, r * e, z),
        ((c + 1) * e, (r + 1) * e, z),
        (c * e, (r + 1) * e, z),
    ]


def cell_center(cell: Tuple[int, int]) -> vu.Vec3:
    """格子中心点（折叠方向上用来判断"面片朝哪边伸展"）。"""
    c, r = cell
    return (c * EDGE_LENGTH + EDGE_LENGTH / 2.0, r * EDGE_LENGTH + EDGE_LENGTH / 2.0, 0.0)


def neighbors(cell: Tuple[int, int]) -> List[Tuple[int, int]]:
    """上下左右 4 个相邻格子的固定顺序（保证 BFS 建树结果稳定可复现）。"""
    c, r = cell
    return [(c + 1, r), (c - 1, r), (c, r + 1), (c, r - 1)]


def shared_edge(parent: Tuple[int, int], child: Tuple[int, int]) -> Tuple[vu.Vec3, vu.Vec3]:
    """求两个相邻格子共用的那条棱（铰链 / 折痕）的两个端点。

    * 同一行左右相邻：公共棱是竖线 x = 两者较大的列号，y 覆盖这一行；
    * 同一列上下相邻：公共棱是横线 y = 两者较大的行号，x 覆盖这一列。
    """
    (c0, r0), (c1, r1) = parent, child
    e = EDGE_LENGTH
    if r0 == r1:  # 左右相邻 → 竖直的公共棱
        x = max(c0, c1) * e
        return (x, r0 * e, 0.0), (x, (r0 + 1) * e, 0.0)
    else:  # 上下相邻 → 水平的公共棱
        y = max(r0, r1) * e
        return (c0 * e, y, 0.0), ((c0 + 1) * e, y, 0.0)


def fold_axis(parent: Tuple[int, int], child: Tuple[int, int]) -> Tuple[vu.Vec3, vu.Vec3]:
    """求子面片折叠时的旋转轴（同时返回铰链中点作为轴上的一个点）。

    推导：面片折叠 = 让它的"伸展方向" d 转到 +z。
    能完成 d → +z 的旋转轴是 d × z（右手定则：绕该轴正向转 90° 就把 d 转向 z）。
    d 取"铰链中点 → 子格子中心"并去掉沿铰链方向的分量（因为绕铰链转，沿铰链的分量不变）。
    """
    h1, h2 = shared_edge(parent, child)
    hinge_mid = vu.midpoint(h1, h2)
    hinge_dir = vu.normalize(vu.sub(h2, h1))

    # 子格子中心相对铰链中点的位移
    offset = vu.sub(cell_center(child), hinge_mid)
    # 去掉沿铰链方向的分量，得到"垂直于铰链、指向子面片"的伸展方向
    along = vu.dot(offset, hinge_dir)
    stretch = vu.sub(offset, vu.scale(hinge_dir, along))

    # 旋转轴 = 伸展方向 × 上方向，单位化
    axis = vu.axis_from_direction_and_up(stretch, UP)
    return hinge_mid, axis


# ---------------------------------------------------------------------------
# 三、折叠：用父子复合求出每个面片折完后的位置
# ---------------------------------------------------------------------------
def build_tree(cells: Sequence[Tuple[int, int]], base: Tuple[int, int] = (0, 0)) -> Tuple[Dict, List[Tuple[int, int]]]:
    """以基准面为根，按"广度优先"把 6 个格子连成一棵折叠树。

    返回 (parent_map, order)：
        parent_map[格子] = 父格子（基准面为 None）
        order = 折叠顺序（父在前、子在后，正好是"从桌面往外一片片折起来"的顺序）
    """
    cell_set = set(cells)
    parent: Dict[Tuple[int, int], Optional[Tuple[int, int]]] = {base: None}
    order: List[Tuple[int, int]] = [base]
    queue: List[Tuple[int, int]] = [base]
    while queue:
        current = queue.pop(0)
        for nb in neighbors(current):
            if nb in cell_set and nb not in parent:
                parent[nb] = current
                order.append(nb)
                queue.append(nb)
    if len(order) != len(cell_set):
        raise ValueError(f"展开图不连通，无法折叠: {sorted(cell_set)}")
    return parent, order


def build_transforms(
    cells: Sequence[Tuple[int, int]], base: Tuple[int, int] = (0, 0)
) -> Tuple[
    Dict[Tuple[int, int], Callable[[vu.Vec3], vu.Vec3]],
    Dict[Tuple[int, int], Optional[FoldInfo]],
    List[Tuple[int, int]],
]:
    """构造每个面片的折叠变换（闭包函数）、折叠参数和折叠顺序。

    变换的定义（父子复合）：
        T(base)  = 恒等变换
        T(child) = T(parent) ∘ 绕铰链转 90°
    也就是说：先把点绕"摊平状态下的那条铰链"转 90°，
    再交给父面片的变换去处理（父面片自己也是被它的父面片折过来的）。
    """
    parent, order = build_tree(cells, base)
    transforms: Dict[Tuple[int, int], Callable[[vu.Vec3], vu.Vec3]] = {base: lambda p: p}
    params: Dict[Tuple[int, int], Optional[FoldInfo]] = {base: None}

    for cell in order:
        p = parent[cell]
        if p is None:
            continue
        hinge_mid, axis = fold_axis(p, cell)
        hinge_a, hinge_b = shared_edge(p, cell)
        parent_transform = transforms[p]

        # 用默认参数把当前面片的铰链 / 轴"钉"进闭包，避免循环变量被后续覆盖
        def make_transform(mid=hinge_mid, ax=axis, outer=parent_transform):
            def transform(point: vu.Vec3) -> vu.Vec3:
                # 第一步：绕自己与父面片之间的公共棱转 90°（在摊平坐标系里算）
                rotated = vu.rotate_point_about_axis(point, mid, ax, FOLD_ANGLE)
                # 第二步：叠加父面片的折叠变换（父面片也许已经立起来了）
                return outer(rotated)

            return transform

        transforms[cell] = make_transform()
        parent_info = params[p]
        params[cell] = {
            "hinge_mid": hinge_mid,
            "hinge": (hinge_a, hinge_b),
            "axis": axis,
            "angle": FOLD_ANGLE,
            "parent": p,
            "depth": parent_info["depth"] + 1 if parent_info else 1,
        }
    return transforms, params, order


def folded_face_identity(corners: Sequence[vu.Vec3], tol: float = 1e-6) -> Optional[Tuple[int, int]]:
    """判断折完后的面片贴在正方体的哪一面，返回 (坐标轴, 侧别)。

    例如 4 个角点的 z 都等于 1 → (2, 1) 顶面；x 都等于 0 → (0, 0) 左面。
    判断不出来（不在 [0,1]³ 边界上）则返回 None，说明这个展开图折不成正方体。
    """
    for axis in range(3):
        values = [point[axis] for point in corners]
        if max(values) - min(values) > tol:
            continue  # 该坐标不固定，说明不平行于这个坐标平面
        value = values[0]
        upper = EDGE_LENGTH
        if abs(value) <= tol:
            side = 0
        elif abs(value - upper) <= tol:
            side = 1
        else:
            return None  # 贴在别的平面上，不是单位正方体的面
        for point in corners:
            for k in range(3):
                if point[k] < -tol or point[k] > upper + tol:
                    return None
        return (axis, side)
    return None


def validate_net(entry: NetEntry) -> ValidateReport:
    """校验一种展开图：折完后 6 个面片是否恰好落在单位正方体的 6 个面上。

    返回校验报告（自测脚本会打印它），不通过时 raise。
    """
    cells = list(entry["cells"])
    base = cells[0]  # 基准面约定是第一个格子
    transforms, params, order = build_transforms(cells, base)

    faces: Dict[Tuple[int, int], List[vu.Vec3]] = {}
    for cell in cells:
        transform = transforms[cell]
        faces[cell] = [transform(p) for p in cell_corners(cell)]

    identities = {}
    for cell, corners in faces.items():
        ident = folded_face_identity(corners)
        if ident is None:
            raise ValueError(f"展开图 {entry['code']}-{entry['variant']} 的面片 {cell} 没有落在单位正方体表面: {corners}")
        identities[cell] = ident

    if len(set(identities.values())) != 6:
        raise ValueError(f"展开图 {entry['code']}-{entry['variant']} 折叠后出现面片重叠: {identities}")

    return {
        "net_id": f"{entry['code']}-{entry['variant']}",
        "faces": identities,
        "fold_order": order,
        "ok": True,
    }


# ---------------------------------------------------------------------------
# 四、对外数据：展开状态 + 折叠动画参数
# ---------------------------------------------------------------------------
def _log(debug: bool, message: str) -> None:
    """调试日志开关：debug=False 时完全静默（接口默认就是这个状态）。

    为什么把"打印中间量"放在后端而不是前端：
    铰链端点、旋转轴、旋转角度、折后坐标全是**后端算出来的几何量**，
    在前端打印只能看到"渲染用了什么"，看不到"为什么是这个值"。

    走 logging 而不是 print：接口层有统一的日志格式和处理，debug 输出能和
    请求日志落到同一处；命令行脚本在入口处 basicConfig 后照样能在终端看到。
    """
    if debug:
        _LOGGER.info(message)


def _fmt_point(p: Sequence[float], ndigits: int = 4) -> str:
    """把一个三维点格式化成 (x, y, z)，方便肉眼比对。"""
    return "(" + ", ".join(f"{float(v):.{ndigits}f}" for v in p) + ")"


def _log_fold_tree(
    debug: bool,
    code: str,
    variant: int,
    cells: Sequence[Tuple[int, int]],
    order: Sequence[Tuple[int, int]],
    params: Dict[Tuple[int, int], Optional[FoldInfo]],
) -> None:
    """打印折叠树：谁是谁的父面片、折几层、按什么顺序折。

    一条 4 连片要像卷纸一样绕成一圈，所以父面片必须先折、子面片后折；
    这个顺序错了，第 3 片就会飞出去。这里把树结构打印出来方便核对。
    """
    if not debug:
        return
    _log(True, "=" * 78)
    _log(True, f"[折叠计算] 展开图 {code}-{variant}  基准面(不折) = 格子 {cells[0]}  共 {len(cells)} 片")
    _log(True, f"[折叠计算] 折叠顺序 = {[cells.index(c) for c in order]}")
    for depth_cell in order:
        info = params.get(depth_cell)
        if info is None:
            _log(True, f"  面片#{cells.index(depth_cell)}  格子{depth_cell}  ★基准面（深度 0，不参与旋转）")
        else:
            _log(
                True,
                f"  面片#{cells.index(depth_cell)}  格子{depth_cell}  父面片#{cells.index(info['parent'])}"
                f"  深度 {info['depth']}",
            )
    _log(True, "-" * 78)


def _log_fold_face(debug: bool, face: FaceOut) -> None:
    """打印单个面片的折叠中间量：铰链、旋转轴、角度、折后角点、落面与对齐度校验。"""
    if not debug:
        return

    idx = face["face_index"]
    if face["is_base"]:
        _log(True, f"[面片#{idx}] 基准面：不折、不转，保持 start_pos（z 恒为 0）")
        return

    hinge = face["hinge_edge"]
    axis = face["rotate_axis"]
    if hinge is None or axis is None:
        raise ValueError(f"面片#{idx} 缺少铰链或旋转轴，折叠参数不完整")
    hinge_dir = vu.normalize(vu.sub(hinge[1], hinge[0]))
    alignment = abs(vu.dot(axis, hinge_dir))

    _log(True, f"[面片#{idx}] 父面片 #{face['parent_id']}  深度 {face['depth']}  折叠顺序 {face['fold_order']}")
    _log(True, f"    铰链公共边   {_fmt_point(hinge[0])} → {_fmt_point(hinge[1])}")
    _log(True, f"    铰链方向 e   {_fmt_point(hinge_dir)}")
    _log(True, f"    旋转轴 axis  {_fmt_point(axis)}   旋转角 {face['rotate_angle']}°")
    _log(True, f"    校验 |axis·e| = {alignment:.12f}  （=1 说明轴严格沿公共边，不是随便给的欧拉角）")
    _log(True, f"    折后角点     " + "  ".join(_fmt_point(p) for p in face["target_pos"]))
    _log(True, f"    折后落在      {face['target_face_label']}（{face['target_face']}）")


def _find_entry(unfold_type: str, variant: Optional[int]) -> NetEntry:
    """按 "141" / "141-3" 这样的写法定位展开图，并确定变体序号。"""
    raw = str(unfold_type).strip()
    code = raw
    parsed_variant: Optional[int] = None

    # 支持 "141-3" 这种把变体号写在后面的写法
    for sep in ("-", "_", "."):
        if sep in raw:
            head, tail = raw.split(sep, 1)
            if tail.strip().isdigit():
                code = head.strip()
                parsed_variant = int(tail.strip())
            break

    code = code.strip()
    if code not in CODE_LABELS:
        raise ValueError(
            f"不支持的展开图类型: {unfold_type}，可用类型: {', '.join(CODE_LABELS.keys())}"
        )

    candidates = [e for e in NET_TABLE if e["code"] == code]
    chosen_variant = variant if variant is not None else (parsed_variant or 1)
    if chosen_variant < 1 or chosen_variant > len(candidates):
        raise ValueError(
            f"{code} 型只有 {len(candidates)} 种展开图，变体号 {chosen_variant} 越界"
        )
    return candidates[chosen_variant - 1]


def build_net_data(
    unfold_type: str, variant: Optional[int] = None, debug: bool = False
) -> HexahedronData:
    """构造某一种展开图的完整数据（展开状态 + 折叠目标 + 动画参数）。

    参数
    ----
    debug : True 时打印折叠树、每片的铰链 / 旋转轴 / 角度 / 折后角点等中间几何量，
            用于核对"到底是不是沿铰链翻折"（接口传 debug=true 即可打开）。
    """
    entry = _find_entry(unfold_type, variant)
    cells = list(entry["cells"])
    code = entry["code"]
    variant_no = entry["variant"]

    base = cells[0]
    transforms, params, order = build_transforms(cells, base)

    # 折叠顺序编号：父面片先折，子面片后折，正好对应"从桌面一片片折起来"
    order_index = {cell: i for i, cell in enumerate(order)}

    # 打印折叠树（谁是谁的父面片、折几层、什么顺序）
    _log_fold_tree(debug, code, variant_no, cells, order, params)

    faces_out: List[FaceOut] = []
    for index, cell in enumerate(cells):
        start_pos = cell_corners(cell)
        transform = transforms[cell]
        target_pos = [vu.round_point(transform(p), 9) for p in start_pos]

        ident = folded_face_identity(target_pos)
        if ident is None:  # 正常不会发生（import 时已全量校验），留作兜底
            raise ValueError(f"展开图 {code}-{variant_no} 的面片 {cell} 未能折叠到位")
        face_name, face_label, color_index, color_hex = FACE_STYLE[ident]

        info = params[cell]
        hinge_edge: Optional[List[vu.Vec3]] = None
        hinge_edge_folded: Optional[List[vu.Vec3]] = None
        axis: Optional[vu.Vec3] = None
        angle = 0.0
        parent_id: Optional[int] = None
        depth = 0
        if info is not None:
            hinge_edge = [vu.round_point(info["hinge"][0], 9), vu.round_point(info["hinge"][1], 9)]
            hinge_edge_folded = [
                vu.round_point(transform(info["hinge"][0]), 9),
                vu.round_point(transform(info["hinge"][1]), 9),
            ]
            axis = vu.round_point(info["axis"], 9)
            angle = float(info["angle"])
            parent_id = cells.index(info["parent"])
            depth = int(info["depth"])

        # 折完后的面法向量（由 4 个角点直接叉乘得到，便于前端做光照 / 剔除）
        edge1 = vu.sub(target_pos[1], target_pos[0])
        edge2 = vu.sub(target_pos[2], target_pos[1])
        target_normal = vu.round_point(vu.normalize(vu.cross(edge1, edge2)), 9)

        faces_out.append(
            {
                "face_index": index,
                "cell": [cell[0], cell[1]],
                "color_index": color_index,
                "color": color_hex,
                "target_face": face_name,
                "target_face_label": face_label,
                "start_pos": [vu.round_point(p, 9) for p in start_pos],
                "target_pos": target_pos,
                "hinge_edge": hinge_edge,
                "hinge_edge_folded": hinge_edge_folded,
                "rotate_axis": axis,
                "rotate_angle": angle,
                "target_normal": target_normal,
                "parent_id": parent_id,
                "depth": depth,
                "fold_order": order_index[cell],
                "is_base": info is None,
            }
        )

        # 打印这一片的折叠中间量（铰链、轴、角度、折后角点）
        _log_fold_face(debug, faces_out[-1])

    # 展开状态的整体包围盒（前端用来把镜头摆到合适位置）
    xs = [p[0] for f in faces_out for p in f["start_pos"]]
    ys = [p[1] for f in faces_out for p in f["start_pos"]]
    net_bounds: NetBounds = {
        "min": [min(xs), min(ys), 0.0],
        "max": [max(xs), max(ys), 0.0],
        "width": max(xs) - min(xs),
        "height": max(ys) - min(ys),
    }

    # 折叠动画：按折叠顺序播放，父面片先动，子面片跟着父面片的姿态继续转
    step_duration = 0.45
    overlap = 0.12
    steps: List[AnimationStep] = []
    for i, cell in enumerate(order):
        idx = cells.index(cell)
        face = faces_out[idx]
        hinge = face["hinge_edge"]
        steps.append(
            {
                "face_index": idx,
                "fold_order": i,
                "start_time": round(i * (step_duration - overlap), 4),
                "duration": step_duration,
                "rotate_axis": face["rotate_axis"],
                "rotate_angle": face["rotate_angle"],
                "pivot": hinge[0] if hinge else None,
                "parent_id": face["parent_id"],
            }
        )

    animation: FoldAnimation = {
        "easing": "easeInOutCubic",
        "step_duration": step_duration,
        "overlap": overlap,
        "total_duration": round((len(order) - 1) * (step_duration - overlap) + step_duration, 4),
        "fps": 60,
        "play_order": [cells.index(c) for c in order],
        "steps": steps,
        "note": "子面片必须在父面片折完之后再折：先应用父面片旋转，再应用自己的轴角",
    }

    if debug:
        bbox = [
            min(p[k] for f in faces_out for p in f["target_pos"]) for k in range(3)
        ]
        bbox_max = [
            max(p[k] for f in faces_out for p in f["target_pos"]) for k in range(3)
        ]
        _log(True, "-" * 78)
        _log(True, f"[折叠计算] 折完后整体包围盒 min={_fmt_point(bbox)} max={_fmt_point(bbox_max)}")
        _log(
            True,
            "[折叠计算] 覆盖的面："
            + "、".join(sorted({str(f["target_face"]) for f in faces_out})),
        )
        _log(True, "=" * 78)

    return {
        "unfold_type": code,
        "variant": variant_no,
        "net_id": f"{code}-{variant_no}",
        "label": f"{CODE_LABELS[code]}·第{variant_no}种",
        "note": entry.get("note", ""),
        "edge_length": EDGE_LENGTH,
        "face_count": len(faces_out),
        "cells": [[c[0], c[1]] for c in cells],
        "base_face_index": 0,
        "faces": faces_out,
        "net_bounds": net_bounds,
        "fold_sequence": [cells.index(c) for c in order],
        "animation": animation,
    }


@lru_cache(maxsize=32)
def _build_net_data_cached(unfold_type: str, variant: Optional[int]) -> HexahedronData:
    """缓存版构建：11 种展开图是静态数据，算一次即可。

    只缓存 debug=False 的结果；debug 请求不走这里，见 get_unfold_data。
    """
    return build_net_data(unfold_type, variant, debug=False)


def get_unfold_data(
    unfold_type: str, variant: Optional[int] = None, debug: bool = False
) -> HexahedronData:
    """接口层调用入口：按展开图类型（可选变体号）取展开数据。

    普通请求走 lru_cache，同一展开图只算一次；返回深拷贝，避免调用方改坏缓存对象。
    debug=True 时不走缓存，保证每次请求都能重新打印折叠中间几何量。
    """
    if debug:
        return build_net_data(unfold_type, variant, debug=True)
    return copy.deepcopy(_build_net_data_cached(unfold_type, variant))


@lru_cache(maxsize=1)
def _list_unfold_types_cached() -> UnfoldTypes:
    """构造展开图清单（进程内只构造一次，外部拿副本）。"""
    groups: List[UnfoldGroup] = []
    for code, label in CODE_LABELS.items():
        variants: List[UnfoldVariant] = [
            {
                "variant": e["variant"],
                "net_id": f"{code}-{e['variant']}",
                "label": f"{label}·第{e['variant']}种",
                "note": e["note"],
                "cells": [[c[0], c[1]] for c in e["cells"]],
            }
            for e in NET_TABLE
            if e["code"] == code
        ]
        groups.append({"code": code, "label": label, "count": len(variants), "variants": variants})
    return {
        "total_unfold_types": len(NET_TABLE),
        "groups": groups,
        "codes": list(CODE_LABELS.keys()),
    }


def list_unfold_types() -> UnfoldTypes:
    """列出全部展开图类型与变体，供 /api/shape/list 使用。"""
    return copy.deepcopy(_list_unfold_types_cached())


def render_net_ascii(cells: Sequence[Sequence[int]], base: Sequence[int] = (0, 0)) -> str:
    """把展开图渲染成字符画，方便在终端里肉眼检查布局。

    '#' = 普通面片，'B' = 基准面（不动的那片），'.' = 空位。
    """
    cell_set = {(int(c[0]), int(c[1])) for c in cells}
    base_cell = (int(base[0]), int(base[1]))
    xs = [c[0] for c in cell_set]
    ys = [c[1] for c in cell_set]
    lines = []
    for row in range(max(ys), min(ys) - 1, -1):
        line = ""
        for col in range(min(xs), max(xs) + 1):
            if (col, row) == base_cell:
                line += "B"
            elif (col, row) in cell_set:
                line += "#"
            else:
                line += "."
        lines.append(line)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 五、import 时自检：11 种展开图必须全部折得成正方体
# ---------------------------------------------------------------------------
VALIDATION_REPORT: List[ValidateReport] = []
for _entry in NET_TABLE:
    VALIDATION_REPORT.append(validate_net(_entry))

if len(VALIDATION_REPORT) != 11:
    raise RuntimeError(f"展开图数量异常，应为 11 种，实际 {len(VALIDATION_REPORT)} 种")