"""魔方几何计算后端 · 纯计算模块包。

模块划分
--------
* vector_utils  —— 手写向量 / 平面工具（点积、叉积、线段与平面求交……）
* shape_data    —— 正方体 / 长方体的顶点、棱、面基础数据
* hexahedron    —— 正方体 11 种展开图与折叠动画参数
* section_cut   —— 平面切割几何体求截面多边形

本包不含任何前端渲染逻辑，所有输出都是纯数据（点坐标 / 轴 / 角度）。
这里不预先 import 子模块：`from geometry import hexahedron, section_cut` 时按需加载，
既避免导入顺序耦合，也让单个模块可以独立调试。
"""

__all__ = ["vector_utils", "shape_data", "hexahedron", "section_cut"]

__version__ = "1.0.0"