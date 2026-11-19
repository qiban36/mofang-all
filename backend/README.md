# 空间几何 · 几何计算后端（FastAPI）

空间几何模拟器的**计算服务**：正方体 11 种展开图的折叠参数、任意平面与正方体/长方体的截面多边形。
本项目**只输出数据，不含任何前端渲染逻辑**——坐标、旋转轴、角度、颜色编号都由前端自己画。

---

## 1. 目录结构

```
backend/
├── main.py                     # FastAPI 入口：三个接口 + pydantic 校验 + CORS
├── requirements.txt            # 依赖清单
├── test_geometry.py            # 纯几何自测脚本（不需要前端、不需要起服务）
├── debug_geometry.py           # 命令行放大镜：nets / fold / section / all 四个子命令
├── README.md                   # 本文件
└── geometry/                   # 纯计算模块包（无 Web 依赖）
    ├── __init__.py
    ├── vector_utils.py         # 手写向量工具：点积 / 叉积 / 线段与平面求交 / 点在平面 / 绕轴旋转
    ├── shape_data.py           # 正方体、长方体的顶点 / 棱 / 面数据
    ├── hexahedron.py           # 正方体 11 种展开图 + 折叠动画参数
    └── section_cut.py          # 平面切割求截面多边形（含逐棱调试打印）
```

几何计算全部手写，**没有引入 numpy**：点积、叉积、线段与平面求交、绕轴旋转都是几个函数，
配合逐行注释和打印语句，能把"一刀切"的原理一步步看清。

---

## 2. 开发顺序（建议照这个顺序看代码）

空间几何模拟器最容易出的问题是"前端看着能转，但数学是错的"。所以这套工程严格按三层往下做：

1. **后端几何模块自测**（不碰网络、不碰浏览器）
   先写向量工具 → 几何体数据 → 11 种展开图铰链 → 截面求交，
   用 `python test_geometry.py`、`python debug_geometry.py all` 把数学验对。
2. **后端接口**（只做数据搬运 + 参数校验）
   `uvicorn main:app --reload --port 8000` 起服务后，用 `/docs` 或 curl 确认三个接口的
   入参、出参、错误码都符合预期。
3. **前端对接**（只管渲染与动画）
   前端调用接口拿坐标 / 铰链 / 旋转轴 / 角度，用 Three.js 画 6 个独立面片、用 Tween.js 播放折叠、
   用红色粗线画截面轮廓。**前端不做任何几何计算。**

对应到文件就是：`geometry/*` → `main.py` → 前端 `src/api.js` + `src/three/*` + `App.vue`。

---

## 2. 环境要求

* Python **3.9+**（开发验证环境为 3.13）
* 依赖：FastAPI / Uvicorn / pydantic v2（见 `requirements.txt`）

---

## 3. 安装依赖

```bash
# 建议先建虚拟环境
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate

python -m pip install -r requirements.txt
```

---

## 4. 启动服务

```bash
# 方式一：uvicorn（推荐，带热重载）
uvicorn main:app --reload --port 8000

# 方式二：直接跑入口文件（内部调用 uvicorn，固定 127.0.0.1:8000）
python main.py
```

启动后：

| 地址 | 说明 |
| --- | --- |
| `http://127.0.0.1:8000/` | 服务自检，返回接口清单 |
| `http://127.0.0.1:8000/docs` | Swagger 交互文档，可直接点"Try it out"调试 |
| `http://127.0.0.1:8000/api/shape/list` | 支持的几何体与 11 种展开图 |

CORS 已放行前端 Vite 开发地址：`http://localhost:5173` 与 `http://127.0.0.1:5173`。

---

## 5. 不起前端、不起服务，直接测几何逻辑

```bash
python test_geometry.py          # 全量自测，逐条打印 ✅/❌，最后给总结
python test_geometry.py --quiet  # 只打结论行
pytest test_geometry.py -q       # 也可以用 pytest 跑
```

自测覆盖：

1. 向量工具：点积、叉积、单位化、线段与平面求交的 4 种情形、绕轴旋转、乱序点排序；
2. 11 种展开图：每种都检查 6 个面片、6 个颜色编号、展开坐标都在 `z=0`、
   折叠目标都落在单位正方体 6 个不同的面上、铰链确实与父面片共用、父子折叠顺序正确；
3. 截面：正方形 / 三角形 / 正六边形 / 长方形 / 单点 / 线段 / 无交点 / 平面与面共面，
   并检查顶点确实落在平面上、落在棱上、顺序构成凸多边形；
4. 接口冒烟：三个接口各真实调用一次（装了 FastAPI 才跑）。

单独看截面模块的调试打印：

```bash
python -m geometry.section_cut
```

---

## 6. 接口说明

### 6.1 `POST /api/hexahedron/get_data` —— 正方体展开图数据

请求：

```json
{ "unfold_type": "141" }
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `unfold_type` | string | 是 | `141` / `231` / `222` / `33`；也支持 `141-3` 这种"分型-变体"写法 |
| `variant` | int | 否 | 同分型的第几种（1 起）。不传默认 1；`unfold_type` 写成 `141-3` 时以 `variant` 字段为准 |

返回结构（`data` 内）：

| 字段 | 说明 |
| --- | --- |
| `unfold_type` / `variant` / `net_id` | 分型、变体号、唯一标识（如 `141-3`） |
| `label` | 中文名，如"一四一型·第3种" |
| `face_count` | 固定 6 |
| `cells` | 6 个格子坐标 `[col, row]`，`[0,0]` 恒为基准面 |
| `faces[]` | 6 个面片，字段见下表 |
| `net_bounds` | 展开状态包围盒，前端用来摆镜头 |
| `fold_sequence` | 面片序号数组，即折叠顺序（父面片在前） |
| `animation` | 折叠动画参数：`step_duration` / `overlap` / `total_duration` / `fps` / `easing` / `steps[]` |

`faces[]` 每个面片：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `face_index` | int | 面片序号 0~5（0 为基准面） |
| `cell` | [int,int] | 展开图里的格子坐标 |
| `color_index` / `color` | int / string | 颜色编号 1~6 与颜色值；**按"折完是哪一面"固定分配**，同色即同一面 |
| `target_face` / `target_face_label` | string | 折叠后对应的面：`bottom/top/front/back/left/right` |
| `start_pos` | 4×[x,y,z] | 展开状态 4 个角点，全部在 `z=0`，顺序为左下→右下→右上→左上 |
| `target_pos` | 4×[x,y,z] | 折叠到位后的 4 个角点，落在单位正方体 `[0,1]³` 上，角点顺序与 `start_pos` 一一对应 |
| `hinge_edge` | 2×[x,y,z] | 与**父面片**共用的公共棱（折痕），展开状态；基准面为 `null` |
| `hinge_edge_folded` | 2×[x,y,z] | 同一条公共棱折叠后的位置 |
| `rotate_axis` | [x,y,z] | 折叠旋转轴（单位向量，位于展开坐标系）。基准面为 `null` |
| `rotate_angle` | float | 绕轴旋转角度，非基准面固定 `90.0`，基准面 `0.0` |
| `target_normal` | [x,y,z] | 折完后的面法向量（由角点叉乘得到，指向正方体**内部**） |
| `parent_id` / `depth` / `fold_order` | int | 父面片序号（基准面 `null`）、折叠层级、折叠顺序 |
| `is_base` | bool | 是否基准面（不动的那片） |

> 折叠动画怎么用：面片是**父子链**关系（`parent_id`），子面片必须在父面片折完之后再折。
> 每个面片的旋转轴与铰链都定义在"摊平坐标系"里，因此前端按 `parent_id` 做嵌套 Group，
> 每帧对 Group 施加 `quaternion.setFromAxisAngle(rotate_axis, rotate_angle × 进度)`、
> 支点取 `hinge_edge`，就能 1:1 复现本模块算出的 `target_pos`。`animation.steps[]` 已给出
> 每个面片的 `start_time`、`duration`、`axis`、`pivot`，可直接当时间轴用。

---

### 6.2 `POST /api/section/cut` —— 平面切割求截面

请求：

```json
{
  "shape": "cube",
  "plane_origin": [0.5, 0.5, 0.5],
  "plane_normal": [1, 1, 1]
}
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `shape` | string | 是 | `cube`（正方体）/ `cuboid`（长方体） |
| `plane_origin` | [x,y,z] | 是 | 平面上的一个点 |
| `plane_normal` | [nx,ny,nz] | 是 | 平面法向量，不必归一（内部会单位化），但不能是零向量 |
| `dims` | [a,b,c] | 否 | 长方体三边；长方体默认 `[2,1.5,1]`，正方体默认边长 1（传了必须三边相等） |
| `debug` | bool | 否 | `true` 时服务端打印逐棱求交过程，并在响应里附带 `edge_intersections` 明细 |

返回（`data` 内）：

| 字段 | 说明 |
| --- | --- |
| `status` | `none` 无交点 / `point` 单点 / `segment` 线段 / `polygon` 闭合多边形 |
| `message` | 中文提示，可直接展示给用户 |
| `points` | 顶点数组。`polygon` 时**已按边界顺序排好**（绕法向量正向逆时针） |
| `closed_polygon` | `points` 首尾相接（末端重复首点），前端可直接连成闭合折线；非多边形场景为 `null` |
| `point_count` / `area` / `centroid` | 顶点数、面积、重心 |
| `vertices_on_plane` | 恰好落在平面上的原始顶点 |
| `edges_total` / `edges_crossed` | 12 条棱中实际被穿过的条数 |
| `coplanar_edges` | 完全躺在平面上的棱（平面与某个面共面时出现） |
| `edge_intersections` | 逐棱调试明细：`d1` / `d2` / `status` / `t` / 交点（仅 `debug=true` 返回） |
| `warnings` | 退化情形提醒 |

四种场景示例：

| 平面 | 结果 |
| --- | --- |
| `origin=[0.5,0,0.5] normal=[1,0,0]` | `polygon`，4 点正方形，面积 1 |
| `origin=[1,0,0] normal=[1,1,1]` | `polygon`，3 点等边三角形，面积 0.866 |
| `origin=[0.5,0.5,0.5] normal=[1,1,1]` | `polygon`，6 点正六边形，面积 1.299 |
| `origin=[0,0,0] normal=[1,1,1]` | `point`，切在顶点 (0,0,0) |
| `origin=[0,0,0] normal=[1,1,0]` | `segment`，沿棱 AE 擦过 |
| `origin=[0,0,5] normal=[0,0,1]` | `none`，平面在体外 |

---

### 6.3 `GET /api/shape/list` —— 支持的几何体与展开图清单

返回 `shapes`（正方体 / 长方体，含顶点数、棱数、面数、默认尺寸）与
`unfold_types`（4 个分型、各自变体数、11 种展开图的格子布局），共 11 种展开图。

---

## 7. 几何约定（前端对接必看）

* 右手坐标系，`x` 向右、`y` 向后（深度）、`z` 向上。
* 正方体 / 长方体底面固定在 `z = 0`，边长 1（正方体），占据 `[0,1]³` 或 `[0,a]×[0,b]×[0,c]`。
* 顶点固定编号 `A~H`：底面 `A(0,0,0) B(a,0,0) C(a,b,0) D(0,b,0)`，顶面 `E F G H` 对应同样的 x/y。
* 12 条棱 = 底面 4 + 顶面 4 + 竖棱 4；6 个面 = bottom / top / front / back / left / right。
* 展开图整体摊在 `z = 0` 平面，基准面（`[0,0]` 格子）占 `[0,1]×[0,1]`，
  折叠完成后正方体恒为 `[0,1]³`——**11 种展开图折出来的 `target_pos` 可以互相比较**，
  也能直接和 `section/cut` 的截面坐标对齐。
* `target_normal` 指向正方体内部；若前端用它做光照，取反即为外法向。

### 11 种展开图的分类

| 分型 | 名称 | 数量 | 说明 |
| --- | --- | --- | --- |
| `141` | 一四一型 | 6 | 中间一排 4 个连片绕成一圈，上下各挂 1 片 |
| `231` | 二三一型 | 3 | 行格子数 2 / 3 / 1 |
| `222` | 二二二型 | 1 | 三级台阶 |
| `33` | 三三型 | 1 | 两排各 3 个，错开两列 |

这 11 组格子坐标不是手抄的：程序穷举了全部 216 个固定六联骨牌，
用折叠模拟筛选"能折成正方体"的布局，去掉旋转/镜像重复后恰好得到这 11 类；
每种展开图在 `geometry/hexahedron.py` 被 import 时都会再做一次落面校验，
折不成正方体或出现面片重叠会直接抛错，不会把错数据发给前端。

---

## 8. 调试技巧

**先跑一遍命令行体检**（推荐的第一步，11 种展开图折叠 + 6 类截面场景一次验证）：

```bash
python debug_geometry.py all          # 一键体检
python debug_geometry.py nets         # 只看 11 种展开图的字符画
python debug_geometry.py fold 141-1   # 只看某一种展开图的铰链参数并校验
python debug_geometry.py section --shape cube --origin 0.5 0.5 0.5 --normal 1 1 1
```

**看"一刀切"的完整推导**（打印每个顶点的带符号距离、每条棱是否穿过、参数 t、交点坐标）：

```bash
python -m geometry.section_cut                 # 内置用例直接打印
python -c "from geometry.section_cut import cut; cut('cube',[0.5,0.5,0.5],[1,1,1])"
```

**让接口也打印**：两个接口都支持 `"debug": true`。

```bash
# 折叠：打印折叠树（父子/深度/顺序）+ 每片铰链、旋转轴、角度、折后角点、落面
curl -X POST http://127.0.0.1:8000/api/hexahedron/get_data   -H "Content-Type: application/json"   -d '{"unfold_type":"141-1","debug":true}'

# 截面：打印逐棱求交 + 排序前后对照 + 闭合校验（边长、首尾距离、周长、凸性）
curl -X POST http://127.0.0.1:8000/api/section/cut   -H "Content-Type: application/json"   -d '{"shape":"cube","plane_origin":[0.5,0.5,0.5],"plane_normal":[1,1,1],"debug":true}'
```

折叠打印里带一行校验 `|axis·e| = 1.000000000000`——它证明旋转轴严格沿公共边，
而不是随手给的角度；`debug` 默认关闭，避免每请求都刷控制台。

**看某一种展开图的折叠细节**：

```bash
python -c "
from geometry import hexahedron as hx
d = hx.get_unfold_data('141', 3)
print(hx.render_net_ascii(d['cells']))
for f in d['faces']:
    print(f['face_index'], f['target_face'], f['start_pos'], '->', f['target_pos'], f['rotate_axis'], f['rotate_angle'])
"
```

`render_net_ascii` 会把展开图渲染成字符画，`B` 是基准面，`#` 是其它面片。

---

## 9. 常见问题

**端口被占用**：换端口 `uvicorn main:app --reload --port 8001`，同时把前端请求地址一起改。

**前端拿不到数据 / 控制台报 CORS**：确认前端跑在 `http://localhost:5173` 或 `http://127.0.0.1:5173`；
换了端口就在 `main.py` 的 `ALLOWED_ORIGINS` 里加上。

**接口返回 422**：pydantic 校验没过，常见原因有坐标不是 3 个数、法向量是零向量、
`shape=cube` 却传了不相等 `dims`、`dims` 超出 `[1e-6, 1e6]`。响应体的 `message`
会指出具体字段，格式与其它错误一致：`{"code": 422, "message": "...", "data": null, "request_id": "..."}`。

**接口返回 400**：请求合法但几何上不成立，例如展开图分型写错（`999`）、变体号越界（`141-9`）。

**接口返回 500**：未预期异常，响应体只给一句通用提示，具体堆栈在后端日志里，
拿响应体里的 `request_id` 搜日志即可定位。

**多边形顶点看着"乱"**：`points` 是排过序的边界顺序（绕 `plane.normal` 逆时针）；
如果按顺时针画，说明渲染坐标系把 z 翻了——按 `closed_polygon` 正序画即可，
或对 `points` 做 `reverse()`。