# 空间几何模拟器 · 前端（Vue3 + Three.js）

一个教学向的 3D 演示页面：左侧控制面板调参数，右侧全屏画布看立体图形。

* **正方体 11 种展开图**：一键加载摊平、一键沿铰链折成正方体、一键平铺（重置）
* **平面截面**：滑块调切面原点与法向量，实时调用后端算截面，用红色粗线画出闭合多边形
* **视图控制**：正交 / 透视切换，主视图 / 俯视图 / 左视图切换

> 前端只负责渲染与交互，**所有几何计算都在 FastAPI 后端完成**（见同级 `backend` 后端工程）。
> 技术栈：Vite + Vue3（选项式 API，无 TypeScript）+ Three.js + Tween.js + Bootstrap5 + axios。

---

## 1. 目录结构

```
frontend/
├── index.html              # HTML 入口（挂载 #app）
├── vite.config.js          # Vite 配置（固定 5173 端口）
├── package.json            # 依赖与脚本
└── src/
    ├── main.js             # 应用入口：挂载 Vue + 引入 Bootstrap CSS
    ├── style.css           # 全局样式（页面撑满、字体）
    ├── api.js              # ★ 接口请求封装（axios：统一地址 + 超时 + 请求/响应日志 + 错误转中文）
    ├── App.vue             # ★ 完整 Vue 单文件组件（左侧面板 + 右侧画布 + 全部交互）
    └── three/
        ├── scene.js        # ① 场景初始化函数：场景/相机/灯光/控制器/视角切换/尺寸自适应
        ├── faces.js        # ② 渲染面片函数：6 个独立 PlaneGeometry + 沿铰链折叠动画
        └── section.js      # ③ 渲染截面函数：红色粗线闭合轮廓 + 清除
```

三个 Three.js 模块分别对应题目要求的「场景初始化函数 / 渲染面片函数 / 渲染截面函数」，
`api.js` 对应「接口请求函数」，`App.vue` 只做状态管理与流程编排。

---

## 2. 开发顺序（本项目就是这么一步步做出来的）

> 空间几何模拟器最容易犯的错是"前端看起来能动，但数学是错的"。所以顺序固定为三层：

1. **后端几何模块自测**（不碰网络、不碰浏览器）
   先写好向量工具、几何体数据、11 种展开图铰链、截面求交，用 `python test_geometry.py`
   和 `python debug_geometry.py all` 把数学验对。数学错了，后面怎么调都是错的。
2. **后端接口**（只做数据搬运）
   用 `uvicorn main:app --reload --port 8000` 起服务，用 curl / 浏览器打开 `/docs` 确认
   三个接口的入参出参、错误码都对。
3. **前端对接**（只管渲染）
   先在 `src/api.js` 打通请求，再在 `three/*.js` 里一个模块一件事地渲染，最后用 `App.vue`
   串起来。前端**不做任何几何计算**，只消费后端给的坐标、轴向量和角度。

对应的验证命令在 [第 9 节](#9-交付时已做的验证) 有完整清单。

---

## 3. 启动

### 2.1 先启动后端（必须）

```bash
cd ../backend
python -m pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

后端启动后可访问 `http://127.0.0.1:8000/api/shape/list` 确认正常（应返回 11 种展开图）。

### 2.2 再启动前端

```bash
cd frontend
npm install
npm run dev
```

> 需要 Node.js 20.19+（Vite 8 的最低要求）。

浏览器打开 **http://localhost:5173**。

> 前端默认请求 `http://127.0.0.1:8000`。后端换端口时，二选一：
> 1. 改 `src/api.js` 里的默认值；
> 2. 在 `.env` 里写 `VITE_API_BASE_URL=http://127.0.0.1:8001`（推荐，不用改代码）。

其他命令：`npm run build`（打包到 dist/）、`npm run preview`（预览打包结果）。

---

## 4. 界面与操作

| 分组 | 控件 | 行为 |
| --- | --- | --- |
| ① 六面体 | 展开图下拉（11 种） | 选择一四一 / 二三一 / 二二二 / 三三型的任一变体 |
| | 加载展开 | 请求 `/api/hexahedron/get_data`，渲染 6 个平铺面片 |
| | 折叠 | 用 Tween.js 沿铰链把 6 片依次折起来，拼成正方体 |
| | 平铺（重置） | 平滑摊回平铺状态（即「平铺/折叠切换」中的平铺），并清除截面线 |
| ② 截面切割 | 几何体下拉 | 正方体 / 长方体 |
| | 截面类型预设 | 按参考截面图预置 12 组平面参数（三角形 / 四边形 / 五边形 / 六边形），点击即填好滑块并渲染；未折叠时按钮禁用 |
| | 原点滑块 ×3 | 切面原点 x / y / z（0 ~ 当前几何体对应边长） |
| | 法向量滑块 ×3 | 切面法向量 nx / ny / nz（-1 ~ 1；全 0 时「生成截面」禁用并提示） |
| | 生成截面 | 需先折叠成正方体；请求 `/api/section/cut`，半透明填充 + 双层红色描边 + 顶点标记，画布上浮出「n 边形 · 面积」标注，下方显示后端提示文字 |
| ③ 视图控制 | 透视 / 正交 | 切换相机投影方式 |
| | 主视图 / 俯视图 / 左视图 | 切到对应预设视角（另有「立体视角」回默认斜视） |

画布操作：**左键拖拽旋转、滚轮缩放、右键平移**（OrbitControls）。

选中「长方体」时，画布上会出现一个与后端 `dims` 完全一致的半透明长方实体（2 × 1.5 × 1）加深色棱线，红色截面线和它严格对齐；同时 ① 里的加载 / 折叠 / 平铺按钮会被禁用并提示「长方体没有展开图」，画面里不会再同时出现正方体的彩色折叠方块。正方体本身用折叠后的实体表示，不额外画盒子。

「截面类型」预设库在 `src/sectionPresets.js`：正方体 12 组、长方体 12 组，每组都用后端几何模块核对过顶点数与边长关系（等边 / 等腰 / 平行边），法向量只保留方向并收进 `[-1, 1]`。点击按钮 = 写回 `origin` / `normal` + 立即请求 `/api/section/cut`，前端依旧不做任何几何推导。

截面渲染分三层（`src/three/section.js`）：半透明填充 `renderOrder = -1`、深色光晕描边 `2`、亮红主描边 `3`，外加每个顶点的「深色底圈 4 + 亮色芯 5」标记；面片描边 0、参考线框 1。所有截面元素都在透明渲染列表里，且关闭 `depthTest`，所以轮廓不会被实体面截断、也不会被线框盖住。参考线框的颜色 / 透明度只有唯一数据源 `REFERENCE_BOX_STYLE`（`src/three/scene.js`），画布徽标色块读取同一份值。

---

## 5. 数据怎么流动

```
点【加载展开】 ──POST /api/hexahedron/get_data──▶ 6 个面片参数
      │                                          start_pos / hinge_edge / rotate_axis
      │                                          rotate_angle / target_pos / parent_id
      ▼
createFaceMeshes()  每片一个 PlaneGeometry + 一个 Group，按 parent_id 嵌套
      │
点【折叠】 ──▶ foldFaces() 用 Tween 把每片的进度 0→1，每帧按进度算四元数

点【生成截面】 ──POST /api/section/cut──▶ { status, points, message, area }
      │
      ├─ status = polygon 且有 ≥3 个点 → renderSection() 画红色粗线
      └─ 其它（none / point / segment） → clearSection() 清掉旧线 + 显示提示
```

后端返回的关键字段（面片）：

| 字段 | 含义 | 前端怎么用 |
| --- | --- | --- |
| `start_pos` | 平铺状态 4 个角点 | 决定面片初始位置（格子中心 = `cell + 0.5`） |
| `hinge_edge` | 与父面片共享的棱 | 折叠时的旋转轴位置（轴穿过这条棱） |
| `rotate_axis` | 沿铰链的单位向量 | 旋转轴方向 |
| `rotate_angle` | 90 | 旋转角度 |
| `target_pos` | 折好后的 4 个角点 | 用于验证动画结果（后端保证正确） |
| `parent_id` | 父面片编号 | 建父子 Group，子片跟着父片一起转 |

---

## 6. 三个关键实现细节（初学者最容易踩的坑）

### 5.1 后端的 z 轴向上，Three.js 的 y 轴向上

后端坐标是「z 向上、展开图躺在 z = 0」，Three.js 默认「y 向上」。与其把每个点都手动换算，
不如把整棵场景树挂到一个 root 组上，**只旋转一次**：

```js
root.rotation.x = -Math.PI / 2   // 后端 (x, y, z) → Three 世界 (x, z, -y)
```

于是展开图自动落在 Three 的地面（y = 0）上，「朝上折」正好是 +y 方向，
面片、截面点全部可以直接使用后端坐标。

### 5.2 折叠必须是「沿铰链绕轴旋转」，而且要父子嵌套

一条 4 连片折起来时，第 3 片是绕**已经折起来的第 2 片**的边再转 90°。
如果 6 片都按自己的轴独立转，第 3 片会飞出去。做法：

1. 按 `parent_id` 建父子 Group（子 Group 的局部坐标就是摊平坐标系）；
2. 每片绕「过铰链端点、方向 `rotate_axis` 的直线」旋转：
   `p' = R(p − h) + h`，在 Three.js 里就是
   ```js
   group.quaternion = R
   group.position  = h − R·h     // 注意不是 h！
   ```
3. 用 Tween.js 补间每片的进度 `v: 0 → 1`，按 `fold_order` 依次延迟，父片先折、子片后折。

> 实测：折叠完成后 6 片的 4 个角点与后端 `target_pos` **逐点一致**（误差 < 1e-6），
> 整体包围盒正好 1×1×1，6 片分别落在 6 个不同的面上。

### 5.3 「红色粗线」不能用 LineLoop

`THREE.LineLoop` 配 `LineBasicMaterial` 时，`linewidth` 在绝大多数浏览器/显卡上会被忽略（永远 1 像素）。
所以截面用 Three.js 的粗线扩展 **Line2 + LineGeometry + LineMaterial**：
把多边形顶点拉平成坐标数组，**末尾重复首点**实现首尾闭合（等价于 LineLoop），
`linewidth = 4.5` 是真实像素宽度；窗口尺寸变化时要同步 `material.resolution`，否则线宽会变形。

---

## 7. 调试输出（打开浏览器控制台就能看到）

前端各模块的 `DEBUG` 开关现在跟随构建模式：`npm run dev` 自动打开，`npm run build` 生产包自动关闭（`import.meta.env.DEV`）。打开后会打印它经手的中间几何量（数值全部来自后端）：

| 位置 | 打印内容 |
| --- | --- |
| `faces.js` 渲染后 | 每片的几何体类型、父面片、铰链两端点、旋转轴、角度、颜色（证明是 6 个 `PlaneGeometry`，不是 Box） |
| `faces.js` 折叠完成 | 把渲染出来的 4 个角点换算回后端坐标系，与 `target_pos` 逐点比对，打印每片最大偏差与总体结论 |
| `section.js` 绘制后 | 顶点数、首点/末点坐标、首尾闭合距离，并说明"顺序沿用后端，前端未排序" |
| `api.js` 请求前后 | 请求方法/路径/入参、响应状态码/耗时/返回体、失败时的请求参数与后端返回 |

折叠自检正常输出形如：

```
[折叠自检] 渲染角点 vs 后端 target_pos
  面片#0  最大偏差 0.00e+0  (后端落面: bottom)
  ...
  ✅ 全部角点与后端一致（<1e-6）
```

如果这里出现 ❌，说明"动画停的位置"和"后端算出的位置"不一致，优先查 `parent_id` 父子关系与 `rotate_axis`。

---

## 8. 常见问题

**页面打开后点按钮提示「无法连接后端」**
后端没启动，或端口不是 8000。先访问 `http://127.0.0.1:8000/api/shape/list` 验证，再检查 `src/api.js` 的 `BASE_URL`。

**浏览器控制台报 CORS**
后端已放行 `http://localhost:5173` 与 `http://127.0.0.1:5173`。若你把前端换到别的端口，
要到后端 `main.py` 的 `ALLOWED_ORIGINS` 里补一行。

**折叠后看起来是「散开的 6 片」而不是立方体**
通常是 `parent_id` 没被用上（父子 Group 没建立）。检查 `faces.js` 里第二轮建父子关系那段，
以及后端返回的面片编号字段是 `face_index`。

**截面线很细 / 看不到**
Line2 的线宽依赖 `material.resolution`，确认 `renderSection` 收到了正确的画布尺寸，并在 `resize` 时调了 `updateSectionResolution`。

**改完代码页面没更新**
Vite 自带热更新；若卡住，重启 `npm run dev`，或浏览器强制刷新（Ctrl+F5）。

---

## 9. 交付时已做的验证

* `npm install` 与 `npm run build` 均通过（产物 `dist/`，Vite 8 + Vue 3.5 + Three.js 0.187 + Tween.js 25）。
* 在 Node 中直接驱动 Three.js 对象验证几何逻辑：6 个独立 `PlaneGeometry`、父子嵌套正确、
  初始角点 = `start_pos`、折叠后角点 = `target_pos`、折叠后包围盒 = 1×1×1、重置回平铺、
  截面线颜色/线宽/闭合段数正确、无点时清线。
* 无头浏览器实测页面：加载展开 → 折叠 → 生成截面 → 正交/三视图切换 → 拖拽旋转 → 重置，
  截图逐张比对，控制台**无报错**；断开后端后点击「加载展开」能弹出中文错误提示。
* 依赖升级到 Vite 8 / Three.js 0.187 / Tween.js 25 后重新构建并在浏览器实测：
  加载展开 → 折叠（按钮变「已折叠」）→ 生成截面（6 边形，面积 1.29904）全流程通过。
* 浏览器实测「截面类型」预设：点「等边三角形」得 3 边形（面积 0.487139），点「正六边形」得 6 边形（面积 1.29904）；
  切到长方体后徽标显示「参考线框 2 × 1.5 × 1」并带同色色块。
* 预设的所有原点都落在原点滑块的 0.05 刻度、法向量落在法向滑块的 0.01 刻度上，点预设后滑块不会跳位；
  24 组预设逐条用后端几何模块复核过顶点数（三角形 / 四边形 / 五边形 / 六边形）与菱形边长关系。
* `npm run lint` 0 error / 0 warning，`npm test` 35 个用例全通过，`npm run build` 成功。
* `npm run test:coverage` 总语句覆盖率 52.28%：`section.js`、`sectionPresets.js` 100%，`faces.js` 70%；
  `scene.js` 因 jsdom 没有 WebGL（`createViewer` 会创建 `WebGLRenderer`），只覆盖样式契约与层级断言。
* 体验报告闭环：长方体改为半透明实体 + 棱线并隐藏折叠方块（P0-1）；加载展开后自动回立体视角 + 自适应取景（P1-2）；
  预设只在生成截面后高亮（P1-3）；长方体免折叠直接切割（P1-4）；手机端画布约 61vh（P2-5）；
  面积标签固定在截面屏幕包围盒上边缘之外（P2-6）；内联 favicon 后控制台无 404（P3-7）。
* E2E：8 个 Playwright 用例全通过（用法见 10.4）。

---

## 10. 代码检查与测试（ESLint 9 + Vitest）

### 10.1 命令

```bash
npm run lint          # ESLint 检查（扁平配置 eslint.config.js）
npm run lint:fix      # 自动修复格式类问题
npm test              # Vitest 单次运行
npm run test:watch    # 监听模式
npm run test:coverage # 生成覆盖率（text / html / lcov，输出到 coverage/）
```

* ESLint：`@eslint/js` + `eslint-plugin-vue` 的 `flat/recommended`，风格由 `@stylistic` 约束
  （单引号、无分号、2 空格、`comma-dangle: never`、`object-curly-spacing: always`、`arrow-parens: as-needed`）。
  `App.vue` 模板为人工排版，因此关闭了 `vue/max-attributes-per-line`、
  `vue/singleline-html-element-content-newline`、`vue/html-self-closing` 三条纯排版规则；
  `src/api.js` 与 `src/three/**` 是调试日志模块，单独放开 `no-console`。
* Vitest：`jsdom` 环境 + 全局 API，测试在 `tests/unit/`，`@` 别名指向 `src`
  （`vite.config.js` 与 `vitest.config.js` 保持一致）。

### 10.2 IDE 配置

仓库已提供 `frontend/.vscode/settings.json`（`eslint.useFlatConfig: true`、保存时
`source.fixAll.eslint: "explicit"`）与 `frontend/.vscode/extensions.json`
（推荐 `dbaeumer.vscode-eslint`、`Vue.volar`）。若你的编辑器没有读到这些配置，请手动：

1. 安装扩展 **ESLint** 与 **Vue - Official (Volar)**；
2. 设置 `eslint.useFlatConfig` 为 `true`（ESLint 9 扁平配置）；
3. 设置 `eslint.validate` 包含 `javascript`、`vue`；
4. 设置 `editor.codeActionsOnSave.source.fixAll.eslint` 为 `"explicit"`。

### 10.3 pre-commit（需要先初始化 git）

当前项目**不是 git 仓库**，所以没有安装 husky / simple-git-hooks，也未创建 `.git`。
`package.json` 里已备好 `precommit` 脚本与 `lint-staged` 配置（`*.{js,vue}` 走 `eslint --fix`）。

仓库根目录已放好版本化钩子 `.githooks/pre-commit`（零安装方案），初始化 git 后执行一次：

```bash
git init
git config core.hooksPath .githooks
git update-index --chmod=+x .githooks/pre-commit   # Windows 上补可执行位
```

之后每次提交会自动对暂存区的前端文件跑 `lint-staged`（只处理改动文件）。如果只在
`frontend/` 目录里初始化仓库，就把该钩子复制到 `frontend/.githooks/pre-commit`，
并把 `core.hooksPath` 配成 `.githooks`。

也可以改用 husky：

```bash
npm i -D husky && npx husky init && echo "npm run precommit" > .husky/pre-commit
# 或：npm i -D simple-git-hooks && npx simple-git-hooks
#     并在 package.json 里加 "simple-git-hooks": { "pre-commit": "npm run precommit" }
```

### 10.4 Playwright E2E（端到端回归）

```bash
npm run test:e2e        # 自动拉起后端（8000）与前端（5173），跑完自动收尾
```

* 用例在 `e2e/`，覆盖：首屏、未折叠时截面按钮禁用、加载展开 → 折叠 → 正六边形截面、
  长方体徽标、长方体免折叠直接切割、预设高亮时机、加载后自动回到立体视角。
* `playwright.config.js` 里配了两个 `webServer`（FastAPI + Vite），已启动的服务会被复用；
  端口被占用时也可以直接跑。
* 本机访问 `storage.googleapis.com` 超时，官方 Chromium 下载不下来，所以 `use.channel = 'chrome'`
  直接复用系统已安装的 Chrome；换机器时如已装 Playwright Chromium，删掉该行即可，
  或临时改成 `channel: 'msedge'`。
* `vitest.config.js` 已把 `e2e/**` 排除，`npm test` 不会误跑 Playwright 用例。