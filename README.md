# 空间几何模拟器 · 合并工程

演示「正方体 11 种展开图折叠」与「平面一刀切截面」的教学系统。原先分散在 `mofang`、`mofang-web`、`vector_lab` 三个目录，2026-11-16 合并为本工程，分三层，职责不混。

## 目录结构

```
mofang-all/
├── backend/        FastAPI 计算服务（:8000）—— 原 mofang
│   ├── main.py                 三个接口 + pydantic 校验 + CORS
│   ├── geometry/               纯计算包（无 Web 依赖）
│   │   ├── vector_utils.py     手写向量 / 平面求交 / 极角排序
│   │   ├── shape_data.py       正方体、长方体的顶点 / 棱 / 面
│   │   ├── hexahedron.py       11 种展开图 + 折叠参数
│   │   ├── section_cut.py      平面切割求截面多边形
│   ├── docs/
│   │   └── hexahedron.py.orig  改朝向前后的原始备份（改 2026-11-16 之前，不参与运行）
│   ├── test_geometry.py        几何自测（不需要网络、不需要前端）
│   ├── debug_geometry.py       命令行放大镜：nets / fold / section / all
│   └── requirements.txt
├── frontend/       Vue3 + Three.js 前端（:5173）—— 原 mofang-web
│   ├── src/api.js              接口封装（baseURL 默认 http://127.0.0.1:8000）
│   ├── src/three/scene.js      场景初始化
│   ├── src/three/faces.js      面片渲染 + 折叠动画
│   ├── src/three/section.js    截面轮廓渲染
│   └── src/App.vue             控制面板 + 画布 + 流程编排
├── prototype/      独立自包含原型 —— 原 vector_lab
│   ├── hexahedron.py           单文件版展开图（含 592 项自测）
│   ├── section_cut.py          单文件版截面
│   ├── test_section_cut.py     命令行 / 交互 / 内置用例
│   └── vector_utils.py
└── README.md       本文件
```

## 快速启动

两个终端，先后顺序不能反。

```bash
# 终端 1：后端
cd backend
python -m pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# 终端 2：前端
cd frontend
npm install
npm run dev
```

浏览器打开 <http://localhost:5173>。后端接口文档在 <http://127.0.0.1:8000/docs>。

## 三层职责

| 层 | 目录 | 负责 | 不负责 |
|---|---|---|---|
| 渲染 | `frontend/` | Three.js 画面、折叠动画、截面红线、参数面板 | 任何几何计算 |
| 接口 | `backend/main.py` | HTTP 接口、参数校验、错误码、CORS | 几何算法 |
| 计算 | `backend/geometry/` | 向量数学、折叠变换、截面求交与排序 | 网络、渲染、IO |

前端只消费后端给的坐标 / 旋转轴 / 角度，不自己算——这是刻意的，避免"画面能动但数学错了"。

## 展开图朝向约定

`geometry/hexahedron.py` 的 `NET_TABLE` 在 2026-11-16 统一改成**公考教材的横排画法**：

- 一四一型的"四"横向摆放，上下翻盖挂在横排两侧；
- 11 种形状本身没有变（与原版逐一比对，形状集合 0 差异），只是整体旋转/镜像到了教材朝向；
- 每种展开图折完仍恰好覆盖正方体 6 个不同面（自测已验证）。

改动前只有竖排朝向，与教材原图方向不一致。原始文件保留在 `backend/docs/hexahedron.py.orig`（不参与运行、不会被当成 Python 包内容），需要对比时直接 diff。

## prototype 是干什么的

`prototype/` 不属于运行链路，后端和前端都不会 import 它。它是同一套算法的**单文件自包含版本**：

- 每个文件可单独拷走运行，零第三方依赖；
- 自带大量自测打印（`python hexahedron.py` 一次跑 592 项校验）；
- 讲题时可用来输出教材同款字符画，或对照 `backend` 的工程化实现。

不要把它当第二套生产代码维护——改算法只改 `backend/geometry/`。

## 自测与验证

```bash
cd backend
python test_geometry.py        # 几何全量断言（接口部分需先装 fastapi）
python debug_geometry.py all   # 打印 11 种展开图 / 折叠过程 / 截面明细

cd ../prototype
python hexahedron.py           # 592 项自测
python test_section_cut.py     # 8 组内置用例
python test_section_cut.py -i  # 交互式输入平面参数
```

前端构建验证：`cd frontend && npm run build`（产物在 `dist/`）。
