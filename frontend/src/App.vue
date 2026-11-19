<template>
  <!-- 整体布局：左侧控制面板 + 右侧全屏 3D 画布 -->
  <div class="app-shell">
    <!-- ===================== 左侧控制面板 ===================== -->
    <aside class="control-panel">
      <div class="panel-header">
        <h1 class="h5 mb-1">空间几何模拟器</h1>
      </div>

      <div class="panel-body">
        <!-- 错误提示：接口失败 / 后端未启动时显示 -->
        <div v-if="errorText" class="alert alert-danger d-flex align-items-start gap-2 py-2 px-3 small" role="alert">
          <div class="flex-grow-1">{{ errorText }}</div>
          <button type="button" class="btn-close btn-sm mt-1" aria-label="关闭" @click="errorText = ''"></button>
        </div>

        <!-- ===================== 分组 1：六面体 ===================== -->
        <div class="card mb-3 shadow-sm">
          <div class="card-header fw-semibold py-2">① 六面体</div>
          <div class="card-body py-3">
            <label class="form-label small text-secondary mb-1" for="unfold-select">正方体展开图（11 种）</label>
            <p v-if="isCuboidMode" class="form-text text-secondary mb-2">
              当前是长方体：长方体没有展开图，可直接用「② 截面切割」的预设观察截面。
            </p>
            <select
              id="unfold-select"
              v-model="selectedUnfold"
              class="form-select form-select-sm mb-2"
              :disabled="loading || isCuboidMode"
            >
              <option v-for="opt in unfoldOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>

            <div class="d-grid gap-2">
              <button class="btn btn-primary btn-sm" :disabled="loading || !selectedUnfold || isCuboidMode" @click="loadUnfold">
                加载展开
              </button>
              <button
                class="btn btn-success btn-sm"
                :disabled="loading || !hasFaces || folding || folded || isCuboidMode"
                @click="foldUnfold"
              >
                {{ folded ? '已折叠' : '折叠' }}
              </button>
              <button class="btn btn-outline-secondary btn-sm" :disabled="loading || !hasFaces || isCuboidMode" @click="resetUnfold">
                平铺（重置）
              </button>
            </div>

            <div class="form-text mt-2">
              「折叠」= 6 个面片沿各自铰链立起来拼成正方体；「平铺」= 摊回桌面上的展开图（同时清除截面线）。
            </div>

            <div v-if="netLabel" class="form-text mt-1">{{ netLabel }}</div>
          </div>
        </div>

        <!-- ===================== 分组 2：截面切割 ===================== -->
        <div class="card mb-3 shadow-sm">
          <div class="card-header fw-semibold py-2">② 截面切割</div>
          <div class="card-body py-3">
            <label class="form-label small text-secondary mb-1" for="shape-select">几何体</label>
            <select id="shape-select" v-model="selectedShape" class="form-select form-select-sm mb-3" :disabled="loading">
              <option v-for="shape in shapes" :key="shape.name" :value="shape.name">{{ shape.label }}</option>
            </select>

            <!-- 截面类型预设：点一下自动填好 origin / normal 并请求后端渲染 -->
            <div class="d-flex justify-content-between align-items-baseline mb-1">
              <span class="small text-secondary">截面类型</span>
              <span class="small text-secondary">{{ activePresetLabel }}</span>
            </div>
            <div v-for="group in presetGroups" :key="group.name" class="mb-2">
              <div class="preset-group-label">{{ group.name }}</div>
              <div class="section-preset-grid">
                <button
                  v-for="preset in group.items"
                  :key="preset.id"
                  type="button"
                  class="btn btn-sm"
                  :class="preset.id === activePresetId ? 'btn-danger' : 'btn-outline-secondary'"
                  :disabled="loading || !canCutSection"
                  @click="applyPreset(preset)"
                >
                  {{ preset.label }}
                </button>
              </div>
            </div>

            <!-- 切面原点：三个滑块分别控制 x / y / z -->
            <div class="d-flex justify-content-between align-items-baseline mb-1">
              <span class="small text-secondary">切面原点 origin</span>
              <span class="small text-secondary font-monospace">
                ({{ origin.x.toFixed(2) }}, {{ origin.y.toFixed(2) }}, {{ origin.z.toFixed(2) }})
              </span>
            </div>
            <div v-for="(axis, index) in axes" :key="'origin-' + axis" class="mb-2">
              <label class="form-label small mb-0" :for="'origin-' + axis">原点 {{ axis.toUpperCase() }}</label>
              <input
                :id="'origin-' + axis"
                v-model.number="origin[axis]"
                type="range"
                class="form-range"
                min="0"
                :max="shapeDims[index]"
                step="0.05"
                :disabled="loading"
              />
            </div>

            <!-- 切面法向量：三个滑块分别控制 nx / ny / nz -->
            <div class="d-flex justify-content-between align-items-baseline mt-3 mb-1">
              <span class="small text-secondary">切面法向量 normal</span>
              <span class="small text-secondary font-monospace">
                ({{ normal.x.toFixed(2) }}, {{ normal.y.toFixed(2) }}, {{ normal.z.toFixed(2) }})
              </span>
            </div>
            <div v-for="axis in axes" :key="'normal-' + axis" class="mb-2">
              <label class="form-label small mb-0" :for="'normal-' + axis">法向 {{ axis.toUpperCase() }}</label>
              <input
                :id="'normal-' + axis"
                v-model.number="normal[axis]"
                type="range"
                class="form-range"
                min="-1"
                max="1"
                step="0.01"
                :disabled="loading"
              />
            </div>

            <!-- 后端要求法向量非零：全 0 时直接拦住，不发注定 422 的请求 -->
            <p v-if="normalIsZero" class="form-text text-danger mb-0">法向量不能全为 0，请至少调整一个分量</p>

            <button
              class="btn btn-danger btn-sm w-100 mt-2"
              :disabled="loading || normalIsZero || !canCutSection"
              @click="generateSection"
            >
              生成截面
            </button>

            <!-- 截面必须切在折好的几何体上：未折叠时按钮禁用，这里说明原因 -->
            <p v-if="!canCutSection" class="form-text mb-0">
              请先在①中「加载展开」并「折叠」成正方体，再切割截面
            </p>

            <!-- 后端返回的提示文字（无截面 / 截面线段 / 闭合多边形） -->
            <div v-if="sectionText" class="alert alert-secondary small mt-3 mb-0 py-2" role="status" aria-live="polite">
              <span class="badge text-bg-secondary me-2">{{ sectionStatusLabel }}</span>{{ sectionText }}
            </div>
          </div>
        </div>

        <!-- ===================== 分组 3：视图控制 ===================== -->
        <div class="card mb-3 shadow-sm">
          <div class="card-header fw-semibold py-2">③ 视图控制</div>
          <div class="card-body py-3">
            <div class="small text-secondary mb-1">投影方式</div>
            <div class="btn-group w-100 mb-3" role="group">
              <button
                type="button"
                class="btn btn-sm"
                :class="projection === 'perspective' ? 'btn-primary' : 'btn-outline-primary'"
                @click="switchProjection('perspective')"
              >
                透视
              </button>
              <button
                type="button"
                class="btn btn-sm"
                :class="projection === 'orthographic' ? 'btn-primary' : 'btn-outline-primary'"
                @click="switchProjection('orthographic')"
              >
                正交
              </button>
            </div>

            <div class="small text-secondary mb-1">视角</div>
            <div class="btn-group w-100 mb-2" role="group">
              <button
                type="button"
                class="btn btn-sm"
                :class="activeView === 'front' ? 'btn-primary' : 'btn-outline-primary'"
                @click="switchView('front')"
              >
                主视图
              </button>
              <button
                type="button"
                class="btn btn-sm"
                :class="activeView === 'top' ? 'btn-primary' : 'btn-outline-primary'"
                @click="switchView('top')"
              >
                俯视图
              </button>
              <button
                type="button"
                class="btn btn-sm"
                :class="activeView === 'left' ? 'btn-primary' : 'btn-outline-primary'"
                @click="switchView('left')"
              >
                左视图
              </button>
            </div>
            <button
              type="button"
              class="btn btn-sm w-100"
              :class="activeView === 'iso' ? 'btn-primary' : 'btn-outline-secondary'"
              @click="switchView('iso')"
            >
              立体视角
            </button>
          </div>
        </div>

        <p class="small text-secondary mb-0">
          后端：<span class="font-monospace">{{ baseUrl }}</span>
        </p>
      </div>
    </aside>

    <!-- ===================== 右侧 3D 画布 ===================== -->
    <main ref="canvasHost" class="canvas-host">
      <div class="canvas-caption">
        <span class="badge text-bg-light border">拖拽旋转</span>
        <span class="badge text-bg-light border">滚轮缩放</span>
        <span class="badge text-bg-light border">{{ projectionLabel }}</span>
        <span class="badge text-bg-light border">{{ hasSection ? '已显示截面' : '无截面线' }}</span>
        <span v-if="selectedShape === 'cuboid'" class="badge text-bg-light border">
          <span
            class="refbox-swatch"
            :style="{ backgroundColor: refboxStyle.color, opacity: refboxStyle.opacity }"
            aria-hidden="true"
          ></span>
          参考线框 {{ shapeDims.join(' × ') }}
        </span>
      </div>

      <!-- 截面面积标注：由渲染循环每帧投影到截面中心，位置不参与 Vue 响应式更新 -->
      <div v-if="sectionLabel" ref="sectionLabel" class="section-label">{{ sectionLabel }}</div>

      <!-- 加载提示遮罩 -->
      <div v-if="loading" class="loading-mask">
        <div class="spinner-border text-primary" role="status" aria-hidden="true"></div>
        <div class="mt-2 small text-secondary" role="status" aria-live="polite">{{ loadingText }}</div>
      </div>
    </main>
  </div>
</template>

<script>
// =============================================================================
// App.vue —— 空间几何模拟器（选项式 API）
//
// 组件只做三件事：
//   1. 管界面状态（下拉框、滑块、加载中、错误提示）；
//   2. 调接口（api.js 里封装好的三个函数）；
//   3. 把结果交给 Three.js 的三个模块去画（scene.js / faces.js / section.js）。
// 几何计算全部在后端 FastAPI 完成，前端不做任何数学推导。
// =============================================================================

import { BASE_URL, cutSection, getShapeList, getUnfoldData } from './api.js'
import { createViewer, REFERENCE_BOX_STYLE } from './three/scene.js'
import {
  clearFaceMeshes,
  createFaceMeshes,
  foldFaces,
  resetFaces,
  updateFoldAnimations
} from './three/faces.js'
import { clearSection, createSectionState, renderSection, updateSectionResolution } from './three/section.js'
import { getSectionPresets, matchPreset } from './sectionPresets.js'

// 内置的 11 种展开图清单：后端没启动时下拉框也能用（启动后会自动用接口返回的清单覆盖）
const FALLBACK_UNFOLD_OPTIONS = [
  { value: '141-1', label: '一四一型 · 第1种' },
  { value: '141-2', label: '一四一型 · 第2种' },
  { value: '141-3', label: '一四一型 · 第3种' },
  { value: '141-4', label: '一四一型 · 第4种' },
  { value: '141-5', label: '一四一型 · 第5种' },
  { value: '141-6', label: '一四一型 · 第6种' },
  { value: '231-1', label: '二三一型 · 第1种' },
  { value: '231-2', label: '二三一型 · 第2种' },
  { value: '231-3', label: '二三一型 · 第3种' },
  { value: '222-1', label: '二二二型 · 第1种' },
  { value: '33-1', label: '三三型 · 第1种' }
]

// 截面状态码 → 中文标签（后端 status 字段）
const SECTION_STATUS_LABELS = {
  none: '无截面',
  point: '截面：单点',
  segment: '截面：线段',
  polygon: '截面：多边形'
}

export default {
  name: 'App',

  data() {
    return {
      // ---- 全局状态 ----
      loading: false,
      loadingText: '加载中…',
      errorText: '',
      baseUrl: BASE_URL,

      // ---- 分组 1：六面体 ----
      unfoldOptions: FALLBACK_UNFOLD_OPTIONS,
      selectedUnfold: '141-1',
      netLabel: '',
      hasFaces: false,
      folding: false,
      folded: false, // 是否已经折成正方体（用于按钮状态，避免重复点“折叠”没反应）

      // ---- 分组 2：截面切割 ----
      shapes: [
        { name: 'cube', label: '正方体', dims: [1, 1, 1] },
        { name: 'cuboid', label: '长方体', dims: [2, 1.5, 1] }
      ],
      selectedShape: 'cube',
      axes: ['x', 'y', 'z'],
      origin: { x: 0.5, y: 0.5, z: 0.5 },
      normal: { x: 1, y: 1, z: 1 },
      sectionText: '',
      sectionStatus: '',
      hasSection: false,
      // 截面标注：points 是后端返回的顶点（只用来看"标签该放哪"），label 是文案
      sectionPoints: [],
      sectionLabel: '',
      // 参考线框的颜色 / 透明度：直接取自 scene.js 的唯一样式源，画布徽标色块不会和线框跑偏
      refboxStyle: REFERENCE_BOX_STYLE,

      // ---- 分组 3：视图控制 ----
      projection: 'perspective',
      activeView: 'iso'
    }
  },

  computed: {
    projectionLabel() {
      return this.projection === 'orthographic' ? '正交投影' : '透视投影'
    },
    sectionStatusLabel() {
      return SECTION_STATUS_LABELS[this.sectionStatus] || '提示'
    },
    /** 当前几何体的三边长度：原点滑块上限跟着它走（正方体 1，长方体各轴不同） */
    shapeDims() {
      const shape = this.shapes.find(item => item.name === this.selectedShape)
      const dims = shape?.dims
      return Array.isArray(dims) && dims.length === 3 ? dims : [1, 1, 1]
    },
    /** 当前几何体可用的截面类型预设 */
    sectionPresets() {
      return getSectionPresets(this.selectedShape)
    },
    /** 把预设按「三角形 / 四边形 / 五边形 / 六边形」分组，模板直接遍历 */
    presetGroups() {
      const groups = []
      this.sectionPresets.forEach(preset => {
        let group = groups.find(item => item.name === preset.group)
        if (!group) {
          group = { name: preset.group, items: [] }
          groups.push(group)
        }
        group.items.push(preset)
      })
      return groups
    },
    /**
     * 当前滑块值命中的预设 id。
     * 只有"确实生成了截面"才允许高亮：否则首屏默认参数恰好命中正六边形，
     * 会让用户误以为已经切好了一个截面（体验报告 P1-3）。
     */
    activePresetId() {
      if (!this.hasSection) return ''
      const preset = matchPreset(this.sectionPresets, this.origin, this.normal)
      return preset ? preset.id : ''
    },
    activePresetLabel() {
      if (!this.hasSection) return '未生成'
      const preset = this.sectionPresets.find(item => item.id === this.activePresetId)
      return preset ? preset.label : '自定义平面'
    },
    /** 长方体没有展开图：①里的加载 / 折叠按钮要禁用，避免与②的实体打架 */
    isCuboidMode() {
      return this.selectedShape === 'cuboid'
    },
    /**
     * 截面能不能切：长方体本身就是一个现成实体（不需要折正方体）；
     * 正方体则必须先折叠完成，否则红线会浮在平面展开图上。
     */
    canCutSection() {
      if (this.isCuboidMode) return true
      return this.hasFaces && this.folded && !this.folding
    },
    /** 法向量全 0 时后端会返回 422，前端提前拦住 */
    normalIsZero() {
      return this.normal.x === 0 && this.normal.y === 0 && this.normal.z === 0
    }
  },

  watch: {
    /** 切换几何体后，旧截面线不再对应当前几何体：清掉，并把越界的原点收回来 */
    selectedShape() {
      this.clampOrigin()
      this.clearSectionFeedback()
      this.syncReferenceBox()
      this.syncShapeVisibility()
    }
  },

  mounted() {
    // 页面就绪后：搭 3D 场景 → 拉清单 → 监听窗口尺寸变化
    this.initScene()
    this.loadShapeList()
    window.addEventListener('resize', this.handleResize)
  },

  beforeUnmount() {
    // 卸载时把动画帧、事件监听、GPU 资源都清掉，避免内存泄漏
    if (this.animateId) cancelAnimationFrame(this.animateId)
    window.removeEventListener('resize', this.handleResize)
    clearFaceMeshes(this.faceEntries || [])
    clearSection(this.sectionState)
    if (this.viewer) this.viewer.dispose()
  },

  methods: {
    // =========================================================================
    // 一、场景初始化
    // =========================================================================
    /**
     * 初始化 Three.js 场景，并启动渲染循环。
     * 注意：viewer / faceEntries / sectionState 故意不放进 data——
     * 它们是 Three.js 对象，不需要 Vue 做响应式代理（代理反而会影响性能）。
     */
    initScene() {
      this.viewer = createViewer(this.$refs.canvasHost)       // 场景、相机、灯光、控制器
      this.sectionState = createSectionState(this.viewer.root) // 截面线的容器
      this.faceEntries = []                                    // 当前 6 个面片
      this.animateId = null

      // 渲染循环：折叠动画的补间要每帧推进，所以和渲染放在同一循环里
      const tick = () => {
        updateFoldAnimations()  // 推进折叠 / 展开补间
        this.viewer.render()    // 渲染一帧（内部会更新 OrbitControls 阻尼）
        this.syncSectionLabel() // 截面标注跟着相机走
        this.animateId = requestAnimationFrame(tick)
      }
      this.animateId = requestAnimationFrame(tick)
    },

    /** 窗口尺寸变化：同步相机与渲染器，并修正截面粗线的分辨率 */
    handleResize() {
      if (!this.viewer) return
      const size = this.viewer.resize()
      updateSectionResolution(this.sectionState, size)
    },

    /** 把原点滑块的旧值收进当前几何体的尺寸范围（切到更小的几何体时防止越界） */
    clampOrigin() {
      this.axes.forEach((axis, index) => {
        if (this.origin[axis] > this.shapeDims[index]) {
          this.origin[axis] = this.shapeDims[index]
        }
      })
    },

    /** 清掉截面线与提示（切换几何体 / 重新加载展开 / 平铺时复用） */
    clearSectionFeedback() {
      clearSection(this.sectionState)
      this.clearSectionLabel()
      this.hasSection = false
      this.sectionText = ''
      this.sectionStatus = ''
    },

    /** 清掉画布上的截面标注 */
    clearSectionLabel() {
      this.sectionPoints = []
      this.sectionLabel = ''
    },

    /**
     * 同步参考线框：长方体是按 dims 算截面的，场景里必须有一个同尺寸的盒子，
     * 否则红色截面线会跑到 1×1×1 立方体外面，看起来像算错了。
     * 正方体折叠后本身就是 1³，不需要额外线框。
     */
    syncReferenceBox() {
      if (!this.viewer) return
      this.viewer.setReferenceBox(this.selectedShape === 'cuboid' ? this.shapeDims : null)
    },

    /**
     * 画面里只允许存在一个"当前几何体"：
     * 长方体模式下隐藏彩色折叠方块（它属于正方体流程），只保留半透明长方体实体。
     * 切回正方体时恢复显示，之前的折叠状态不丢。
     */
    syncShapeVisibility() {
      const showFaces = !this.isCuboidMode
      ;(this.faceEntries || []).forEach(entry => {
        entry.group.visible = showFaces
      })
    },

    // =========================================================================
    // 二、接口请求（初始化清单）
    // =========================================================================
    /**
     * 读取后端支持的几何体与 11 种展开图，填充下拉框。
     * 后端没启动时不算致命错误：保留内置清单，并提示用户启动后端。
     */
    async loadShapeList() {
      this.loading = true
      this.loadingText = '正在读取几何体与展开图清单…'
      try {
        const data = await getShapeList()

        // 几何体列表（正方体 / 长方体）
        if (Array.isArray(data?.shapes) && data.shapes.length) {
          this.shapes = data.shapes.map(item => ({
            name: item.name,
            label: item.label || item.name,
            dims: item.dims
          }))
          // 后端给的尺寸可能和内置默认值不同，原点滑块上限要跟着更新
          this.clampOrigin()
          this.syncReferenceBox()
        }

        // 展开图：把 groups[].variants[] 拍平成一维下拉选项
        const groups = data?.unfold_types?.groups || []
        const options = []
        groups.forEach(group => {
          ;(group.variants || []).forEach(variant => {
            options.push({
              value: variant.net_id,
              label: variant.label || `${group.label}·第${variant.variant}种`
            })
          })
        })
        if (options.length) this.unfoldOptions = options

        // 保证下拉框当前值一定在选项里
        if (!this.unfoldOptions.some(opt => opt.value === this.selectedUnfold)) {
          this.selectedUnfold = this.unfoldOptions[0]?.value || ''
        }
      } catch (error) {
        this.errorText = `${error.message}（下拉框已用内置清单兜底）`
      } finally {
        this.loading = false
      }
    },

    // =========================================================================
    // 三、加载展开图 + 渲染 6 个面片
    // =========================================================================
    /**
     * 【加载展开】调用 /api/hexahedron/get_data，拿 6 个面片的
     * start_pos / hinge_edge / rotate_axis / rotate_angle / target_pos 等参数，
     * 交给 faces.js 生成 6 个独立的 PlaneGeometry 网格（不合并！）。
     */
    async loadUnfold() {
      // 长方体没有展开图，按钮本来就禁用，这里再拦一次防止程序化调用
      if (this.isCuboidMode || !this.selectedUnfold) return

      this.loading = true
      this.loadingText = '正在获取展开图面片数据…'
      this.errorText = ''

      try {
        const data = await getUnfoldData(this.selectedUnfold)

        // 先清掉旧面片和旧截面，避免叠加
        clearFaceMeshes(this.faceEntries)
        this.faceEntries = []
        this.clearSectionFeedback()
        this.folded = false

        // 生成新的 6 个面片（边长用后端给的 edge_length，不写死 1）
        this.faceEntries = createFaceMeshes(this.viewer.root, data.faces, {
          edgeLength: data.edge_length
        })
        this.hasFaces = true
        this.netLabel = `${data.label || data.net_id} · ${data.faces.length} 个面片 · 边长 ${data.edge_length}`
        this.syncShapeVisibility()

        // 加载后自动切回立体视角 + 自适应取景：
        // 横排展开图（一四一型等）不再被画布右边界裁切，主/俯视下也不会被压成一条线（体验报告 P1-2 / P2-5）
        this.activeView = 'iso'
        this.viewer.setView('iso')
        this.viewer.fitToObjects((this.faceEntries || []).map(entry => entry.group))
      } catch (error) {
        this.errorText = error.message
        this.hasFaces = (this.faceEntries || []).length > 0
      } finally {
        this.loading = false
      }
    },

    /**
     * 【折叠】用 Tween.js 播放翻折动画：
     * 每片面片读取后端给的 rotate_axis / rotate_angle，沿铰链轴转 90°，
     * 并按 fold_order 依次错开（父面片先折，子面片后折）。
     */
    foldUnfold() {
      if (this.isCuboidMode) return
      if (!(this.faceEntries || []).length) {
        this.errorText = '请先点击「加载展开」获取面片数据'
        return
      }
      if (this.folding) return

      this.folding = true
      foldFaces(this.faceEntries, {
        duration: 620,
        stagger: 170,
        onComplete: () => {
          this.folding = false
          this.folded = true
        }
      })
    },

    /**
     * 【重置】把面片平滑转回平铺展开状态，同时清掉截面线。
     */
    resetUnfold() {
      if (this.isCuboidMode) return
      if (!(this.faceEntries || []).length) return

      this.folding = false
      this.folded = false
      resetFaces(this.faceEntries, { duration: 480 })

      // 平铺后立方体已经不存在，截面线没有意义，一并清除
      this.clearSectionFeedback()
    },

    // =========================================================================
    // 四、生成截面
    // =========================================================================
    /**
     * 【应用预设】点「截面类型」按钮：把预设的 origin / normal 写回滑块，
     * 然后立刻请求后端计算并渲染，和后端结果完全一致（前端不做任何几何推导）。
     */
    applyPreset(preset) {
      this.axes.forEach((axis, index) => {
        this.origin[axis] = preset.origin[index]
        this.normal[axis] = preset.normal[index]
      })
      this.generateSection()
    },

    /**
     * 【生成截面】把滑块的平面参数发给 /api/section/cut，
     * 拿到闭合多边形后用红色粗线画出来；没有点时清掉旧线。
     */
    async generateSection() {
      // 双保险：按钮已禁用，这里再拦一次，避免自动折叠动画途中或平铺状态下发出无意义的请求
      if (!this.canCutSection) return

      this.loading = true
      this.loadingText = '正在计算截面…'
      this.errorText = ''

      try {
        const data = await cutSection({
          shape: this.selectedShape,
          planeOrigin: [this.origin.x, this.origin.y, this.origin.z],
          planeNormal: [this.normal.x, this.normal.y, this.normal.z],
          // 长方体才需要三边尺寸；正方体传了必须三边相等，所以不传
          dims: this.selectedShape === 'cuboid' ? this.shapeDims : undefined
        })

        // 提示文字直接展示后端给的中文说明（无截面 / 线段 / 多边形）
        this.sectionStatus = data.status
        this.sectionText = data.message || ''

        if (data.status === 'polygon' && Array.isArray(data.points) && data.points.length >= 3) {
          renderSection(this.sectionState, data.points, this.viewer.size())
          this.setSectionLabel(data.points, data.area)
          this.hasSection = true
        } else {
          // 后端没有返回可用的截面点：清除旧截面线，避免误导
          clearSection(this.sectionState)
          this.clearSectionLabel()
          this.hasSection = false
        }
      } catch (error) {
        this.errorText = error.message
        clearSection(this.sectionState)
        this.clearSectionLabel()
        this.hasSection = false
      } finally {
        this.loading = false
      }
    },

    /**
     * 记录截面标注：只保存后端给的顶点（用于算标签位置），
     * 文案形如「6 边形 · 面积 1.29904」，与状态栏保持同一精度。
     */
    setSectionLabel(points, area) {
      this.sectionPoints = points.map(point => [point[0], point[1], point[2]])

      const areaValue = Number(area)
      const areaText = Number.isFinite(areaValue) ? ` · 面积 ${areaValue.toFixed(5)}` : ''
      this.sectionLabel = `${points.length} 边形${areaText}`
    },

    /**
     * 把截面顶点投影到画布，标签固定在"屏幕包围盒上边缘之外"，
     * 这样六边形等多边形永远不会被标签压住（体验报告 P2-6）。
     * 每帧直接改 DOM 的 transform / opacity，不触发 Vue 响应式更新。
     */
    syncSectionLabel() {
      if (!this.sectionLabel || !this.sectionPoints.length || !this.viewer) return
      const element = this.$refs.sectionLabel
      if (!element) return

      let minX = Infinity
      let minY = Infinity
      let maxX = -Infinity
      for (const point of this.sectionPoints) {
        const projected = this.viewer.project(point)
        if (!projected.visible) {
          element.style.opacity = '0'
          return
        }
        minX = Math.min(minX, projected.x)
        minY = Math.min(minY, projected.y)
        maxX = Math.max(maxX, projected.x)
      }

      element.style.opacity = '1'
      element.style.transform =
        `translate(${(minX + maxX) / 2}px, ${minY - 10}px) translate(-50%, -100%)`
    },

    // =========================================================================
    // 五、视图控制
    // =========================================================================
    /** 切换投影方式：正交 / 透视 */
    switchProjection(type) {
      if (!this.viewer) return
      this.viewer.setProjection(type)
      this.projection = type
      // 换相机后画布尺寸没变，但粗线材质要跟着重新算一次分辨率
      updateSectionResolution(this.sectionState, this.viewer.size())
    },

    /** 切换视角：front（主视图）/ top（俯视图）/ left（左视图）/ iso（立体视角） */
    switchView(name) {
      if (!this.viewer) return
      this.viewer.setView(name)
      this.activeView = name
    }
  }
}
</script>

<style scoped>
/* 左侧面板 + 右侧画布的整体布局 */
.app-shell {
  display: flex;
  height: 100vh;
  height: 100dvh; /* 移动端浏览器地址栏收起/展开时更稳定，老浏览器回退到 100vh */
  width: 100vw;
  overflow: hidden;
  background: #eef1f6;
}

/* 左侧控制面板：固定宽度、可滚动 */
.control-panel {
  width: 360px;
  min-width: 320px;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #ffffff;
  border-right: 1px solid #dde3ec;
  box-shadow: 2px 0 10px rgba(28, 45, 70, 0.06);
  z-index: 2;
}

.panel-header {
  padding: 16px 16px 12px;
  border-bottom: 1px solid #eef1f6;
}

.panel-body {
  padding: 12px 16px 20px;
  overflow-y: auto;
  flex: 1;
}

/* 右侧画布容器：Three.js 的 canvas 会被塞进来，占满剩余空间 */
.canvas-host {
  position: relative;
  flex: 1;
  height: 100%;
  overflow: hidden;
}

/* 左上角的操作提示 */
.canvas-caption {
  position: absolute;
  top: 12px;
  left: 16px;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  pointer-events: none;
  z-index: 1;
}

/* 截面面积标注：跟随截面中心，样式与截面主色一致 */
.section-label {
  position: absolute;
  top: 0;
  left: 0;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(122, 16, 41, 0.9);
  color: #fff;
  font-size: 12px;
  line-height: 1.5;
  white-space: nowrap;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.15s ease;
  will-change: transform;
  z-index: 1;
}

/* 加载遮罩：半透明覆盖整个画布 */
.loading-mask {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(247, 249, 252, 0.72);
  backdrop-filter: blur(1px);
  z-index: 3;
}

/* 截面类型按钮：三列网格，窄面板里也能点得动 */
.section-preset-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
}

.section-preset-grid .btn {
  padding: 3px 2px;
  font-size: 12px;
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.preset-group-label {
  font-size: 11px;
  color: #8a94a6;
  margin-bottom: 4px;
}

/* 参考线框色块：颜色 / 透明度都来自 REFERENCE_BOX_STYLE，和画布里的线框保持一致 */
.refbox-swatch {
  display: inline-block;
  width: 10px;
  height: 10px;
  margin-right: 5px;
  border-radius: 2px;
  vertical-align: -1px;
}

/* 让滑块在窄面板里更好点 */
.form-range {
  height: 1.1rem;
}

/* 窄屏（手机 / 竖屏平板）：控制面板在上、画布在下，避免固定 360px 面板把画布挤没 */
@media (max-width: 860px) {
  .app-shell {
    flex-direction: column;
  }

  .control-panel {
    width: 100%;
    min-width: 0;
    height: auto;
    max-height: 38vh;
    border-right: none;
    border-bottom: 1px solid #dde3ec;
    box-shadow: 0 2px 10px rgba(28, 45, 70, 0.06);
  }

  .canvas-host {
    flex: 1;
    min-height: 0;
  }
}
</style>