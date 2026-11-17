"""vector_utils.py —— 手写向量与平面工具（立体几何截面 / 面片铰链）

设计目标
--------
1. **只用基础数学公式**：点积、叉积、参数化直线、平面方程、极角排序。
   不调用 numpy / shapely / trimesh 里的"求交""切片""凸包"封装，
   每一步都能在纸上重新推导一遍。
2. **纯函数**：所有函数不改入参、没有隐藏状态，三维向量就是 (x, y, z) 三元组，
   方便单独测试、也方便直接打印调试。
3. **容差显式化**：浮点数不能用 ``==`` 比较。所有"是否在平面上""交点是否落在线段内"
   的判断都留一个 ``eps`` 口子，默认 1e-9（对应棱长为 1 的几何体足够安全）。

为什么用 tuple 而不是 Vector3 类？
---------------------------------
向量在数学上就是三个数。tuple 最轻、最快、可以直接打印成 ``(0.5, 0.0, 1.0)``；
加 / 减 / 数乘用几个一行小函数（见下面的内部工具）就够了，
比运算符重载更贴近公式，也更容易在断点里看清楚每一步的值。

三个约定
--------
* 右手坐标系：x 向右、y 向后、z 向上。
* 平面用「平面上一点 plane_point + 法向量 plane_normal」表示；法向量**不必是单位向量**，
  函数内部需要时自己单位化（初学最容易踩的坑：忘了归一化，
  算出来的"距离"其实是法向量的倍数）。
* 角度用弧度（``math.atan2`` 的返回值），本模块只在内部用到。

公开函数一览
------------
    dot(a, b)                       点积
    cross(a, b)                     叉积
    normalize(v)                    单位化
    point_on_plane(...)             点是否在平面上（带容差）
    segment_plane_intersect(...)    线段与平面求交点（带区间判断与容差）
    distance_point_plane(...)       点到平面距离
    sort_intersection_points(...)   共面交点排序成闭合多边形

直接运行本文件会执行 ``_self_test()``，逐条打印 ✅/❌：
    python vector_utils.py
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

# 三维点 / 向量的类型别名（运行时就是普通 tuple，标注只是为了可读）
Vec3 = Tuple[float, float, float]

# 默认几何容差。单位棱长的几何体上，1e-9 远小于任何真实特征尺寸，
# 又足以吸收 double 的舍入误差（double 有效位约 1e-16，运算几次后放大到 1e-15 量级）。
EPS: float = 1e-9


# ===========================================================================
# 0. 内部小工具：加、减、数乘、模长、线性插值
#    这些不算"公开 API"，但公式里要用，写出来比到处内联更清楚。
# ===========================================================================
def _sub(a: Sequence[float], b: Sequence[float]) -> Vec3:
    """向量减法 a - b：得到"从 b 指向 a"的位移向量。"""
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a: Sequence[float], b: Sequence[float]) -> Vec3:
    """向量加法：逐分量相加。"""
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _scale(a: Sequence[float], k: float) -> Vec3:
    """数乘：把向量拉长（k > 1）、缩短（0 < k < 1）或反向（k < 0）。"""
    return (a[0] * k, a[1] * k, a[2] * k)


def _length_sq(a: Sequence[float]) -> float:
    """模长平方 x² + y² + z²。比较距离时用它可以少开一次方，也避免误差被开方放大。"""
    return a[0] * a[0] + a[1] * a[1] + a[2] * a[2]


def _length(a: Sequence[float]) -> float:
    """模长 |a| = √(x² + y² + z²)。"""
    return math.sqrt(_length_sq(a))


def _lerp(a: Sequence[float], b: Sequence[float], t: float) -> Vec3:
    """线性插值 P(t) = a + t·(b - a)。

    t = 0 得起点 a，t = 1 得终点 b，t ∈ (0, 1) 是线段内部的点——
    这正是"线段与平面求交"最后一步要用的公式。
    """
    return (
        a[0] + (b[0] - a[0]) * t,
        a[1] + (b[1] - a[1]) * t,
        a[2] + (b[2] - a[2]) * t,
    )


# ===========================================================================
# 1. 点积
# ===========================================================================
def dot(a: Sequence[float], b: Sequence[float]) -> float:
    """点积（内积）：a·b = ax·bx + ay·by + az·bz = |a|·|b|·cosθ

    三个高频用途（本模块全都会用到）：

    1. **判断垂直**：a·b = 0 ⇔ 两向量垂直（夹角 90°）；
    2. **投影长度**：b 在 a 方向上的投影长度 = (a·b) / |a|；
    3. **平面方程**：把平面写成 n·(P - P0) = 0，
       那么 n·(P - P0) 的**符号**告诉你 P 在法向量的哪一侧，**绝对值**（n 为单位向量时）
       就是 P 到平面的垂直距离。

    注意：结果是一个标量，不是向量。
    """
    # 逐分量相乘再相加（三维固定展开，比循环更快也更好读）
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


# ===========================================================================
# 2. 叉积
# ===========================================================================
def cross(a: Sequence[float], b: Sequence[float]) -> Vec3:
    """叉积（外积）：结果同时垂直于 a 和 b，方向服从右手定则。

    模长 |a × b| = |a|·|b|·sinθ，等于 a、b 张成的平行四边形面积。

    按三阶行列式展开：

        | i    j    k  |
        | ax   ay   az |  =  (ay·bz − az·by,  az·bx − ax·bz,  ax·by − ay·bx)
        | bx   by   bz |

    两个用途：
    * 已知平面内两条不共线边，叉积就是该平面的法向量；
    * 面片折叠时，"伸展方向 × 上方向"就是让面片立起来的旋转轴。
    """
    return (
        a[1] * b[2] - a[2] * b[1],  # i 分量
        a[2] * b[0] - a[0] * b[2],  # j 分量
        a[0] * b[1] - a[1] * b[0],  # k 分量
    )


# ===========================================================================
# 3. 归一化
# ===========================================================================
def normalize(v: Sequence[float], eps: float = EPS) -> Vec3:
    """单位化：v / |v|，返回与 v 同方向、长度为 1 的向量。

    为什么必须归一化：平面方程里的法向量如果长度是 5，
    那么 n·(P − P0) 算出来是真实距离的 5 倍，判断"是否在平面上"就会漏判。
    本模块所有对外函数内部都会自己归一化，调用方传任意长度法向量都安全。

    零向量（长度 ≤ eps）没有方向，无法归一化 —— 直接抛 ValueError，
    而不是返回 (0, 0, 0) 或 NaN 让错误在几十行之后才爆炸。
    """
    length = _length(v)
    if length <= eps:
        raise ValueError(f"零向量（或长度 {length:.3e} 小于容差 {eps}）无法归一化: {tuple(v)}")
    # 三个分量同时除以模长，方向不变、模长变成 1
    return (v[0] / length, v[1] / length, v[2] / length)


# ===========================================================================
# 4. 点到平面的距离
# ===========================================================================
def distance_point_plane(
    point: Sequence[float],
    plane_point: Sequence[float],
    plane_normal: Sequence[float],
    eps: float = EPS,
) -> float:
    """点到平面的**垂直距离**（非负）。

    推导（就是"投影"两个字）：

        平面：n·(P − P0) = 0
        点 P 到平面的距离 = |P − P0| · |cosθ|，其中 θ 是 (P − P0) 与 n 的夹角
        而 n·(P − P0) = |n| · |P − P0| · cosθ
        所以  d = |n·(P − P0)| / |n|

    分母除以 |n| 是关键：这样即使调用方传了未归一化的法向量，结果仍是真实距离。

    需要知道点在哪一侧时，直接看 n·(P − P0) 的符号（正 = 法向量指向的一侧）。
    """
    n = normalize(plane_normal, eps)  # 先单位化，下面点积的绝对值就是真实距离
    offsets = _sub(point, plane_point)  # P − P0
    signed = dot(offsets, n)  # 带符号距离：正负表示在平面哪一侧
    return abs(signed)  # 距离本身没有方向，取绝对值


# ===========================================================================
# 5. 点是否在平面上
# ===========================================================================
def point_on_plane(
    point: Sequence[float],
    plane_point: Sequence[float],
    plane_normal: Sequence[float],
    eps: float = EPS,
) -> bool:
    """判断点是否落在平面上，用 ``eps`` 吸收浮点误差。

    判据：点到平面的距离 ≤ eps。
    eps 的取法要跟场景匹配：棱长为 1 的正方体用 1e-9 很稳；
    如果几何体尺度是 1e6（比如经纬度投影后的坐标），eps 就该放大到 1e-3 量级，
    否则"本该在平面上"的点会被判成不在。

    等价写法是 ``abs(n·(P − P0)) <= eps``（n 已单位化），
    这里调用 ``distance_point_plane`` 复用同一套推导，避免两处逻辑不一致。
    """
    # 距离已经在函数内部单位化了法向量，不需要重复归一化
    return distance_point_plane(point, plane_point, plane_normal, eps) <= eps


# ===========================================================================
# 6. 线段与平面求交（截面计算的核心一步）
# ===========================================================================
def segment_plane_intersect(
    p0: Sequence[float],
    p1: Sequence[float],
    plane_point: Sequence[float],
    plane_normal: Sequence[float],
    eps: float = EPS,
) -> Optional[Vec3]:
    """求线段 p0→p1 与平面的交点，落在坐标系里的三维点，或 None。

    推导过程（"一刀切"的全部数学）
    -----------------------------
    线段参数方程：

        P(t) = p0 + t·(p1 − p0),   t ∈ [0, 1]

    代入平面方程 n·(P − P0) = 0：

        n·(p0 − P0) + t·(n·(p1 − p0)) = 0

    记 d0 = n·(p0 − P0)，d1 = n·(p1 − P0)，则 n·(p1 − p0) = d1 − d0，于是

        d0 + t·(d1 − d0) = 0   ⟹   t = d0 / (d0 − d1)

    关键结论：只有 d0 与 d1 **异号**时，t 才落在 (0, 1) 内，线段才真的被平面穿过。
    d0、d1 同号说明两个端点都在平面同一侧，整条线段碰不到平面。

    五种情形
    --------
    1. d0、d1 同号                        → 无交点，返回 None
    2. p0 恰在平面上（|d0| ≤ eps）         → 交点是 p0
    3. p1 恰在平面上（|d1| ≤ eps）         → 交点是 p1
    4. 两端都在平面上                      → 整条线段躺在平面里，没有**唯一**交点，返回 None
       （需要"整条边共面"的信息时，请调用方自己判断两端点的 ``point_on_plane``）
    5. 异号                                → 算出 t，插值得到交点

    容差处理
    --------
    即使理论上有 t ∈ (0, 1)，浮点误差也可能给出 t = -2e-16 或 1 + 2e-16；
    所以判断区间时用 ``-eps <= t <= 1 + eps``，并通过 clamp 把 t 收回 [0, 1]，
    避免交点跑到线段外面一点点。
    """
    n = normalize(plane_normal, eps)  # 单位法向量：保证 t 与距离的量纲一致

    # 第一步：算出两个端点"代入平面方程"的值（带符号距离）
    d0 = dot(_sub(p0, plane_point), n)
    d1 = dot(_sub(p1, plane_point), n)

    # 第二步：两端都贴在平面上 —— 线段与平面重合，交点不唯一
    if abs(d0) <= eps and abs(d1) <= eps:
        return None

    # 第三步：端点恰好落在平面上 —— 交点就是这个端点
    #（先判 p0 再判 p1，两者都可能在平面上，此时上面已返回 None）
    if abs(d0) <= eps:
        return (float(p0[0]), float(p0[1]), float(p0[2]))
    if abs(d1) <= eps:
        return (float(p1[0]), float(p1[1]), float(p1[2]))

    # 第四步：同号 —— 两端在同一侧，整条线段不穿过平面
    if (d0 > 0 and d1 > 0) or (d0 < 0 and d1 < 0):
        return None

    # 第五步：异号 —— 真的穿过，用 t = d0 / (d0 − d1) 定位
    #（d0、d1 异号 ⇒ 分母 |d0| + |d1| 一定非零，不会除零）
    t = d0 / (d0 - d1)

    # 区间判断：浮点误差可能让 t 略微越界，用 eps 放宽后再 clamp 回 [0, 1]
    if t < -eps or t > 1.0 + eps:
        return None
    t = min(1.0, max(0.0, t))

    # 插值得到交点坐标
    return _lerp(p0, p1, t)


# ===========================================================================
# 7. 共面交点排序 → 闭合多边形
# ===========================================================================
def sort_intersection_points(
    points: Sequence[Sequence[float]],
    plane_point: Sequence[float],
    plane_normal: Sequence[float],
    eps: float = EPS,
) -> List[Vec3]:
    """把一堆"落在同一平面上的散乱交点"排成绕一圈的顺序，形成闭合多边形。

    为什么需要排序
    --------------
    遍历棱求交时，交点顺序取决于棱的遍历顺序，天然是乱的
    （先算到的可能是多边形对边的两个点）。要连成闭合图形，
    必须知道"沿边界走一圈"的顺序。

    算法（凸多边形严格成立，截面必为凸）
    ------------------------------------
    1. **去重**：两条棱在同一个顶点相交时，会算出同一个交点，先按容差合并；
    2. **求重心** C：凸多边形的重心一定在内部，可以作为极坐标的极点；
    3. **建平面局部坐标系** (u, v)：法向量 n 与任意不平行参考向量叉乘得到 u，再用 n × u 得到 v，
       于是点在平面内的坐标就是 (d·u, d·v)，其中 d = P − plane_point；
    4. **算极角** θ = atan2(d·v, d·u)，按 θ 从小到大排序 —— 这就是沿边界走一圈的顺序；
    5. **统一旋向**：用叉积求有向面积，若为负（顺时针）则整体反转，
       保证输出相对法向量 n 是**逆时针**，前端三角化时不用担心绕序。

    返回
    ----
    排好序的顶点列表（不含重复的首点）。列表首尾两点之间再接一条边，即为闭合多边形。

    约定与异常
    ----------
    * 点数 ≤ 2 时没有"环绕顺序"可言，原样返回；
    * 传入的点若明显不在该平面上（偏离超过 max(eps, 1e-6)），说明调用方搞错了平面，
      直接抛 ValueError，而不是默默排出一个错误的顺序。
    """
    # ---------- 步骤 1：去重 ----------
    unique: List[Vec3] = []
    for p in points:
        candidate = (float(p[0]), float(p[1]), float(p[2]))
        # 与已保留的每个点比较；距离平方 ≤ eps² 视为同一点（不开方，避免误差放大）
        duplicate = False
        for q in unique:
            if _length_sq(_sub(candidate, q)) <= eps * eps:
                duplicate = True
                break
        if not duplicate:
            unique.append(candidate)

    # 少于 3 个点构不成多边形，直接返回（保持"输入顺序"这一个稳定约定）
    if len(unique) <= 2:
        return unique

    # ---------- 步骤 2：平面局部坐标系 ----------
    n = normalize(plane_normal, eps)  # 单位法向量，后面算距离、算面积都要用

    # 共面校验：任何一个点离平面太远，都说明这批点根本不在同一平面上
    tolerance = max(eps, 1e-6)
    for p in unique:
        if abs(dot(_sub(p, plane_point), n)) > tolerance:
            raise ValueError(f"输入的点不在指定平面上，无法排序: {p}")

    # 选一个与 n 不平行的参考向量：优先用 z 轴；若 n 几乎平行 z 轴则换 y 轴
    #（|n.z| < 0.9 时 z 轴与 n 的夹角至少 25°，叉积不会退化成零向量）
    helper: Vec3 = (0.0, 0.0, 1.0) if abs(n[2]) < 0.9 else (0.0, 1.0, 0.0)
    u = normalize(cross(helper, n), eps)  # 平面内第一个基向量
    v = normalize(cross(n, u), eps)  # 平面内第二个基向量，且与 u 垂直

    # ---------- 步骤 3：重心 ----------
    count = len(unique)
    centroid: Vec3 = (
        sum(p[0] for p in unique) / count,
        sum(p[1] for p in unique) / count,
        sum(p[2] for p in unique) / count,
    )  # 凸多边形的顶点算术平均一定落在多边形内部，做极点最稳

    # ---------- 步骤 4：算极角并排序 ----------
    # 每个点相对重心的位移，投影到 (u, v) 上得到平面内二维坐标，
    # 再用 atan2(vy, vx) 求极角，范围 (−π, π]
    with_angle: List[Tuple[float, Vec3]] = []
    for p in unique:
        d = _sub(p, centroid)  # 从重心指向该点
        angle = math.atan2(dot(d, v), dot(d, u))  # 极角：先算 v 分量（y），再算 u 分量（x）
        with_angle.append((angle, p))

    # 按极角升序排列：极角单调递增 = 沿边界逆时针走一圈
    with_angle.sort(key=lambda item: item[0])
    ordered = [item[1] for item in with_angle]

    # ---------- 步骤 5：统一成相对 n 的逆时针 ----------
    # 有向面积：把多边形拆成以首点为顶点的三角形，累加 (Pi−P0) × (Pi+1−P0) 在 n 上的投影。
    # 逆时针为正、顺时针为负（右手定则）；为负就整体反转。
    total = 0.0
    p0 = ordered[0]
    for i in range(1, len(ordered) - 1):
        total += dot(cross(_sub(ordered[i], p0), _sub(ordered[i + 1], p0)), n)
    if total < 0:  # 负面积 ⇒ 当前是顺时针，反转成逆时针
        ordered.reverse()

    return ordered


# ===========================================================================
# 自测：直接 python vector_utils.py 即可运行
# ===========================================================================
def _approx(a: float, b: float, tol: float = 1e-9) -> bool:
    """浮点近似比较，自测里代替 == 。"""
    return abs(a - b) <= tol


def _point_approx(p: Sequence[float], q: Sequence[float], tol: float = 1e-9) -> bool:
    """三维点近似比较。"""
    return _length(_sub(p, q)) <= tol


def _print_case(name: str, ok: bool) -> None:
    """统一打印单条自测结果。"""
    print(f"  {'✅' if ok else '❌'} {name}")
    if not ok:
        raise AssertionError(name)


def _self_test() -> None:
    """逐条验证 7 个公开函数。每条都是「给输入 → 比对期望值」。"""
    print("=" * 70)
    print("vector_utils 自测")
    print("=" * 70)

    # ---------------- 1. dot ----------------
    print("\n[1] dot 点积")
    _print_case("(1,2,3)·(4,5,6) = 32", _approx(dot((1, 2, 3), (4, 5, 6)), 32.0))
    _print_case("垂直向量点积为 0：x·y = 0", _approx(dot((1, 0, 0), (0, 1, 0)), 0.0))
    _print_case("自点积等于模长平方：|(3,4,0)|² = 25", _approx(dot((3, 4, 0), (3, 4, 0)), 25.0))

    # ---------------- 2. cross ----------------
    print("\n[2] cross 叉积")
    _print_case("x × y = z（右手定则）", _point_approx(cross((1, 0, 0), (0, 1, 0)), (0, 0, 1)))
    _print_case("y × x = −z（反交换律）", _point_approx(cross((0, 1, 0), (1, 0, 0)), (0, 0, -1)))
    _print_case("平行向量叉积为零向量", _point_approx(cross((2, 0, 0), (5, 0, 0)), (0, 0, 0)))
    # 叉积结果长度 = 两向量张成的平行四边形面积：x、y 单位向量张成 1×1 正方形
    _print_case("|x × y| = 1（平行四边形面积）", _approx(_length(cross((1, 0, 0), (0, 1, 0))), 1.0))
    # 由平面上两条边求法向量：z=1 平面上 (1,0,0)、(0,1,0) 张成平面，法向量应为 ±z
    normal = normalize(cross((1, 0, 0), (0, 1, 0)))
    _print_case("平面内两边叉积 → 单位法向量 (0,0,1)", _point_approx(normal, (0, 0, 1)))

    # ---------------- 3. normalize ----------------
    print("\n[3] normalize 归一化")
    _print_case("(3,4,0) → (0.6,0.8,0)", _point_approx(normalize((3, 4, 0)), (0.6, 0.8, 0.0)))
    _print_case("归一化后模长为 1", _approx(_length(normalize((1, 2, 3))), 1.0))
    try:
        normalize((0, 0, 0))
        _print_case("零向量归一化必须报错", False)
    except ValueError:
        _print_case("零向量归一化抛 ValueError", True)

    # ---------------- 4. point_on_plane ----------------
    print("\n[4] point_on_plane 点在平面上（带容差）")
    plane_p = (0.0, 0.0, 0.0)
    plane_n = (0.0, 0.0, 1.0)  # 平面 z = 0
    _print_case("原点在 z=0 平面上", point_on_plane((0.0, 0.0, 0.0), plane_p, plane_n))
    _print_case("(5,6,0) 在 z=0 平面上", point_on_plane((5.0, 6.0, 0.0), plane_p, plane_n))
    _print_case("z=1e-12 的点算在平面上（容差生效）", point_on_plane((0.0, 0.0, 1e-12), plane_p, plane_n))
    _print_case("z=1e-3 的点不在平面上", not point_on_plane((0.0, 0.0, 1e-3), plane_p, plane_n))
    # 法向量不归一化也必须正确：(0,0,7) 长度是 7，判定不能因此失效
    _print_case("法向量 (0,0,7) 未归一化，判定依然正确", point_on_plane((1.0, 1.0, 0.0), plane_p, (0.0, 0.0, 7.0)))
    # 斜平面：x + y + z = 1.5，点 (0.5,0.5,0.5) 在平面上
    _print_case("斜平面 x+y+z=1.5 上的点 (0.5,0.5,0.5)",
               point_on_plane((0.5, 0.5, 0.5), (0.5, 0.5, 0.5), (1.0, 1.0, 1.0)))

    # ---------------- 5. distance_point_plane ----------------
    print("\n[5] distance_point_plane 点到平面距离")
    _print_case("点 (0,0,3) 到 z=0 的距离 = 3", _approx(distance_point_plane((0, 0, 3), (0, 0, 0), (0, 0, 1)), 3.0))
    _print_case("法向量 (0,0,-2) 时距离仍为 3（自动归一化）",
               _approx(distance_point_plane((0, 0, 3), (0, 0, 0), (0, 0, -2)), 3.0))
    _print_case("平面上的点距离为 0", _approx(distance_point_plane((2, 2, 0), (0, 0, 0), (0, 0, 1)), 0.0))
    # 斜平面 x+y+z=1.5：(0,0,0) 到平面的距离 = |0+0+0−1.5| / √3 = 0.8660254
    _print_case("原点到斜平面 x+y+z=1.5 的距离 = 1.5/√3 ≈ 0.8660",
               _approx(distance_point_plane((0, 0, 0), (0.5, 0.5, 0.5), (1, 1, 1)), 1.5 / math.sqrt(3)))

    # ---------------- 6. segment_plane_intersect ----------------
    print("\n[6] segment_plane_intersect 线段与平面求交")
    # 竖直棱 (0,0,0)→(0,0,1) 与 z=0.5 平面：应在中点相交
    hit = segment_plane_intersect((0, 0, 0), (0, 0, 1), (0, 0, 0.5), (0, 0, 1))
    _print_case("竖棱穿过 z=0.5 → 交点 (0,0,0.5)", hit is not None and _point_approx(hit, (0, 0, 0.5)))
    # 同侧：整条线段在 z=0.5 平面下方
    _print_case("两端同侧 → None", segment_plane_intersect((0, 0, 0), (1, 0, 0), (0, 0, 0.5), (0, 0, 1)) is None)
    # 端点恰好落在平面上
    hit_end = segment_plane_intersect((0, 0, 0.5), (0, 0, 1), (0, 0, 0.5), (0, 0, 1))
    _print_case("起点在平面上 → 交点为该端点", hit_end is not None and _point_approx(hit_end, (0, 0, 0.5)))
    hit_end2 = segment_plane_intersect((0, 0, 1), (0, 0, 0.5), (0, 0, 0.5), (0, 0, 1))
    _print_case("终点在平面上 → 交点为该端点", hit_end2 is not None and _point_approx(hit_end2, (0, 0, 0.5)))
    # 整条线段躺在平面上：没有唯一交点
    _print_case("整条线段与平面重合 → None（交点不唯一）",
               segment_plane_intersect((0, 0, 0.5), (1, 0, 0.5), (0, 0, 0.5), (0, 0, 1)) is None)
    # 法向量未归一化：t 的计算不受影响
    hit_scaled = segment_plane_intersect((0, 0, 0), (0, 0, 1), (0, 0, 0.5), (0, 0, 4))
    _print_case("法向量 (0,0,4) 未归一化 → 交点仍是 (0,0,0.5)",
               hit_scaled is not None and _point_approx(hit_scaled, (0, 0, 0.5)))
    # 1/3 处穿过的斜棱：从 (0,0,0) 到 (3,0,3) 与 z=1 平面交于 t=1/3 → (1,0,1)
    hit_third = segment_plane_intersect((0, 0, 0), (3, 0, 3), (0, 0, 1), (0, 0, 1))
    _print_case("t = 1/3 的斜棱交点 = (1,0,1)", hit_third is not None and _point_approx(hit_third, (1, 0, 1)))
    # 反向线段（p0 在上、p1 在下）也要能算出来
    hit_rev = segment_plane_intersect((0, 0, 1), (0, 0, 0), (0, 0, 0.5), (0, 0, 1))
    _print_case("线段方向反过来 → 交点相同", hit_rev is not None and _point_approx(hit_rev, (0, 0, 0.5)))
    # 浮点误差：交点几乎落在线段端点（t ≈ 1），不能被误判为越界
    hit_edge = segment_plane_intersect((0, 0, 0), (0, 0, 1), (0, 0, 1 - 1e-12), (0, 0, 1))
    _print_case("t ≈ 1 的浮点边界不误判为越界", hit_edge is not None)
    # 平面与线段平行且不在同一平面：无交点
    _print_case("线段平行于平面 → None",
               segment_plane_intersect((0, 0, 1), (1, 0, 1), (0, 0, 0), (0, 0, 1)) is None)

    # ---------------- 7. sort_intersection_points ----------------
    print("\n[7] sort_intersection_points 共面交点排序")

    # 7.1 正方形：4 个点乱序喂进去，应排成逆时针闭合顺序
    square = [(1.0, 1.0, 0.5), (0.0, 0.0, 0.5), (1.0, 0.0, 0.5), (0.0, 1.0, 0.5)]
    ordered_square = sort_intersection_points(square, (0.0, 0.0, 0.5), (0.0, 0.0, 1.0))
    _print_case("乱序 4 点排成闭合顺序（从 (0,0,0.5) 出发逆时针）",
               [tuple(round(c, 9) for c in p) for p in ordered_square]
               == [(0.0, 0.0, 0.5), (1.0, 0.0, 0.5), (1.0, 1.0, 0.5), (0.0, 1.0, 0.5)])
    # 相邻点连成边，四条边长都应为 1（证明顺序没有跳点）
    edges = [_length(_sub(ordered_square[(i + 1) % 4], ordered_square[i])) for i in range(4)]
    _print_case("四条边长均为 1（相邻点正确相连）", all(_approx(e, 1.0) for e in edges))

    # 7.2 正方体过体心的正六边形截面：6 个点乱序，排完应两两相邻、边长 √2/2、面积 3√3/4
    hexagon = [
        (0.5, 0.0, 1.0), (1.0, 0.5, 0.0), (0.0, 0.5, 1.0),
        (0.5, 1.0, 0.0), (1.0, 0.0, 0.5), (0.0, 1.0, 0.5),
    ]
    plane_center = (0.5, 0.5, 0.5)
    plane_normal = (1.0, 1.0, 1.0)
    ordered_hex = sort_intersection_points(hexagon, plane_center, plane_normal)
    _print_case("6 点排序后仍是 6 点", len(ordered_hex) == 6)
    hex_edges = [_length(_sub(ordered_hex[(i + 1) % 6], ordered_hex[i])) for i in range(6)]
    _print_case("正六边形六条边长均为 √2/2 ≈ 0.7071", all(_approx(e, math.sqrt(2) / 2, 1e-9) for e in hex_edges))
    # 面积：叉积求和 / 2；正六边形面积应为 (3√3/2)·s²，s = √2/2
    area = 0.0
    n_unit = normalize(plane_normal)
    p0 = ordered_hex[0]
    for i in range(1, len(ordered_hex) - 1):
        area += dot(cross(_sub(ordered_hex[i], p0), _sub(ordered_hex[i + 1], p0)), n_unit)
    area = abs(area / 2.0)
    _print_case("六边形面积 = 3√3/4 ≈ 1.2990", _approx(area, 3 * math.sqrt(3) / 4, 1e-9))

    # 7.3 去重：重复点（含 1e-12 级别的微小偏差）应被合并
    dup = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (1.0, 1.0, 0.0 + 1e-12)]
    _print_case("重复点被去重（4 个点 → 3 个）",
               len(sort_intersection_points(dup, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0))) == 3)

    # 7.4 退化输入：0 / 1 / 2 个点原样返回
    _print_case("0 个点 → 空列表", sort_intersection_points([], (0, 0, 0), (0, 0, 1)) == [])
    _print_case("1 个点 → 原样返回", sort_intersection_points([(1, 2, 0)], (0, 0, 0), (0, 0, 1)) == [(1.0, 2.0, 0.0)])
    _print_case("2 个点 → 原样返回",
               sort_intersection_points([(0, 0, 0), (1, 0, 0)], (0, 0, 0), (0, 0, 1))
               == [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)])

    # 7.5 传错平面（点不在该平面上）应报错，而不是排出一个错误顺序
    try:
        sort_intersection_points([(0, 0, 0), (1, 0, 0), (0, 1, 5)], (0, 0, 0), (0, 0, 1))
        _print_case("不共面点必须报错", False)
    except ValueError:
        _print_case("不共面的点抛 ValueError", True)

    # 7.6 与"截面求交"串起来跑一遍：正方体被 z=0.5 切开，遍历 12 条棱求交 + 排序
    print("\n[8] 组合场景：正方体被 z=0.5 平面切开")
    cube_vertices = [
        (0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
        (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1),
    ]
    # 12 条棱：底面 4 + 顶面 4 + 竖棱 4
    cube_edges = [
        (0, 1), (1, 2), (2, 3), (3, 0),
        (4, 5), (5, 6), (6, 7), (7, 4),
        (0, 4), (1, 5), (2, 6), (3, 7),
    ]
    hits: List[Vec3] = []
    for i, j in cube_edges:
        point = segment_plane_intersect(cube_vertices[i], cube_vertices[j], (0, 0, 0.5), (0, 0, 1))
        if point is not None:
            hits.append(point)
    _print_case("12 条棱共得到 4 个交点", len(hits) == 4)
    section = sort_intersection_points(hits, (0.0, 0.0, 0.5), (0.0, 0.0, 1.0))
    _print_case("排序后是 4 边形（正方形截面）", len(section) == 4)
    _print_case("截面顶点都在 z=0.5 平面上",
               all(point_on_plane(p, (0, 0, 0.5), (0, 0, 1)) for p in section))
    side_lengths = [_length(_sub(section[(i + 1) % 4], section[i])) for i in range(4)]
    _print_case("截面四条边长均为 1", all(_approx(s, 1.0) for s in side_lengths))

    print("\n" + "=" * 70)
    print("全部自测通过 ✅")


if __name__ == "__main__":
    _self_test()