// =============================================================================
// three/section.js —— 截面渲染（半透明填充 + 双层描边）
//
// 后端 /api/section/cut 返回的 points 已经按边界顺序排好（逆时针），
// 这里只需要把点连成闭合多边形，再补一层同形状的半透明填充。
//
// ★ 为什么不用 THREE.LineLoop 直接画粗线？
//   WebGL 的 LineBasicMaterial.linewidth 在大多数浏览器/显卡上会被忽略（始终 1 像素），
//   想要"红色粗线"必须用 Three.js 提供的粗线扩展 Line2（基于挤出四边形实现）。
//   Line2 本身是折线，不是自动闭合的 LineLoop，所以这里把**首点再追加一次**，
//   效果与 LineLoop 完全一致（首尾相连），同时线宽真实可调。
//
// ★ 渲染层级（透明列表内的 renderOrder，越大越后画、越在上层）
//   -1  截面填充：垫在面片描边下面，避免红色半透明盖住立方体的黑色轮廓
//    0  面片描边（faces.js）
//    1  参考线框（scene.js）
//    2  截面的深色描边（光晕层，让红线在浅色填充/蓝色面片上都清晰）
//    3  截面的亮红主描边（永远最后画，确保边界线不被遮挡）
//    4  顶点标记的深色底圈
//    5  顶点标记的亮色芯（拐点永远压在线上，方便数清"几边形"）
//   所有截面元素都关掉 depthTest：截面是"切开看内部"的教学视图，
//   被实体面挡住的那半边轮廓也应该完整可见，否则就会出现半截断线。
// =============================================================================

import * as THREE from 'three'
import { Line2 } from 'three/examples/jsm/lines/Line2.js'
import { LineGeometry } from 'three/examples/jsm/lines/LineGeometry.js'
import { LineMaterial } from 'three/examples/jsm/lines/LineMaterial.js'

// 截面样式：一层半透明填充 + 深色光晕描边 + 亮红主描边 + 顶点标记
const FILL_COLOR = 0xff2d55
const FILL_OPACITY = 0.24
const HALO_COLOR = 0x7a1029
const HALO_WIDTH = 8
const OUTLINE_COLOR = 0xff2d55
const OUTLINE_WIDTH = 5
const MARKER_HALO_COLOR = 0x5c0a1c
const MARKER_COLOR = 0xfff1f4

// 顶点标记半径相对"截面包围盒对角线"的比例：
// 截面大就跟着大、截面小就跟着小，屏幕上看起来永远是同一颗珠子的大小。
const MARKER_SIZE_RATIO = 0.012

// 渲染层级常量：供 scene.js / faces.js 的注释与调参对照
export const SECTION_LAYERS = Object.freeze({
  fill: -1,
  halo: 2,
  outline: 3,
  markerHalo: 4,
  marker: 5
})

// 调试开关：开发模式（npm run dev）自动打开，生产构建自动关闭
const DEBUG = Boolean(import.meta.env.DEV)

/**
 * 创建截面渲染状态。
 * 用一个 Group 统一挂载填充与两层描边，清除时只处理这一个组即可。
 * @param {THREE.Group} root 场景根组（与面片同一坐标系，直接用后端坐标）
 */
export function createSectionState(root) {
  const group = new THREE.Group()
  group.name = 'section-group'
  root.add(group)

  return {
    root,
    group,
    materials: [], // LineMaterial 列表：窗口尺寸变化时要逐个更新 resolution
    resolution: new THREE.Vector2(1, 1)
  }
}

/**
 * 【渲染截面】把多边形顶点画成"填充 + 双层描边"。
 *
 * @param {Object} state createSectionState 的返回值
 * @param {Array<[number,number,number]>} points 后端返回的顶点（按边界顺序）
 * @param {{width:number, height:number}} size 画布尺寸（粗线需要它把像素宽度换算成屏幕线宽）
 * @returns {boolean} 是否成功渲染（点数不足 3 时返回 false，并清掉旧截面）
 */
export function renderSection(state, points, size) {
  // 每次都先清掉旧截面，避免多条线叠在一起
  clearSection(state)

  // 少于 3 个点构不成多边形（单点 / 线段 / 无截面），直接返回
  if (!Array.isArray(points) || points.length < 3) {
    return false
  }

  // 把三维点拉平成 [x1,y1,z1, x2,y2,z2, ...]，并在末尾重复首点 → 首尾闭合
  const flat = []
  points.forEach(p => flat.push(p[0], p[1], p[2]))
  flat.push(points[0][0], points[0][1], points[0][2])

  // ---- 1. 半透明填充 ----
  // 盒体截面一定是凸多边形，所以可以直接以第 0 个点为扇心三角剖分
  const fillGeometry = new THREE.BufferGeometry()
  fillGeometry.setAttribute('position', new THREE.Float32BufferAttribute(flat.slice(0, points.length * 3), 3))
  const indices = []
  for (let i = 1; i < points.length - 1; i += 1) {
    indices.push(0, i, i + 1)
  }
  fillGeometry.setIndex(indices)

  const fillMaterial = new THREE.MeshBasicMaterial({
    color: FILL_COLOR,
    transparent: true,
    opacity: FILL_OPACITY,
    side: THREE.DoubleSide,
    depthTest: false, // 截面要"透过实体"完整可见
    depthWrite: false
  })
  const fill = new THREE.Mesh(fillGeometry, fillMaterial)
  fill.name = 'section-fill'
  fill.renderOrder = SECTION_LAYERS.fill
  state.group.add(fill)

  // ---- 2. 两层描边：深色光晕 + 亮红主线 ----
  state.materials = []
  const halo = createOutline(flat, {
    color: HALO_COLOR,
    linewidth: HALO_WIDTH,
    opacity: 0.45,
    renderOrder: SECTION_LAYERS.halo,
    size
  })
  const outline = createOutline(flat, {
    color: OUTLINE_COLOR,
    linewidth: OUTLINE_WIDTH,
    opacity: 1,
    renderOrder: SECTION_LAYERS.outline,
    size
  })
  state.group.add(halo, outline)
  state.materials.push(halo.material, outline.material)

  // ---- 3. 顶点标记：深色底圈 + 亮色芯 ----
  // 截面最容易被看错的地方是"到底几条边"：拐点上各放一颗珠子，
  // 数点的个数就等于数多边形的边数。半径按截面包围盒对角线缩放。
  const markerRadius = boundingDiagonal(points) * MARKER_SIZE_RATIO
  const markerGeometry = new THREE.SphereGeometry(1, 10, 8)
  const markerHaloMaterial = new THREE.MeshBasicMaterial({
    color: MARKER_HALO_COLOR,
    transparent: true,
    opacity: 0.85,
    depthTest: false,
    depthWrite: false
  })
  const markerMaterial = new THREE.MeshBasicMaterial({
    color: MARKER_COLOR,
    depthTest: false,
    depthWrite: false
  })

  points.forEach(point => {
    const markerHalo = new THREE.Mesh(markerGeometry, markerHaloMaterial)
    markerHalo.name = 'section-marker-halo'
    markerHalo.position.set(point[0], point[1], point[2])
    markerHalo.scale.setScalar(markerRadius * 1.9)
    markerHalo.renderOrder = SECTION_LAYERS.markerHalo
    state.group.add(markerHalo)

    const marker = new THREE.Mesh(markerGeometry, markerMaterial)
    marker.name = 'section-marker'
    marker.position.set(point[0], point[1], point[2])
    marker.scale.setScalar(markerRadius)
    marker.renderOrder = SECTION_LAYERS.marker
    state.group.add(marker)
  })

  state.resolution.set(size.width, size.height)

  if (DEBUG) {
    // 后端已经排好序，前端"原样使用"它的顺序，只在末尾补一个首点让折线闭合。
    // 打印出来是为了证明：这里没有前端自己排序/求交，纯粹按后端给的顺序连线。
    const first = points[0]
    const last = points[points.length - 1]
    const closing = Math.hypot(first[0] - last[0], first[1] - last[1], first[2] - last[2])
    console.log(
      `[截面渲染] 顶点数 ${points.length}，顺序 = 后端返回顺序（前端未排序）\n` +
        `  首点 (${first.map(v => v.toFixed(4)).join(', ')})  末点 (${last.map(v => v.toFixed(4)).join(', ')})\n` +
        `  首尾闭合距离 = ${closing.toFixed(6)}（已补一层填充 + 双层描边 + ${points.length} 个顶点标记）`
    )
  }

  return true
}

/**
 * 截面包围盒的空间对角线长度（顶点标记的大小以它为基准）。
 * 全部顶点重合时返回 1，避免缩放为 0 导致标记消失。
 */
function boundingDiagonal(points) {
  let minX = Infinity
  let minY = Infinity
  let minZ = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  let maxZ = -Infinity

  points.forEach(point => {
    minX = Math.min(minX, point[0])
    minY = Math.min(minY, point[1])
    minZ = Math.min(minZ, point[2])
    maxX = Math.max(maxX, point[0])
    maxY = Math.max(maxY, point[1])
    maxZ = Math.max(maxZ, point[2])
  })

  return Math.hypot(maxX - minX, maxY - minY, maxZ - minZ) || 1
}

/**
 * 创建一条闭合粗线（Line2）。
 * @param {number[]} flat 已闭合的顶点坐标
 * @param {Object} options 颜色 / 线宽 / 透明度 / 层级 / 画布尺寸
 */
function createOutline(flat, options) {
  const geometry = new LineGeometry()
  geometry.setPositions(flat)

  const material = new LineMaterial({
    color: options.color,
    linewidth: options.linewidth, // 单位：像素（worldUnits = false 时）
    worldUnits: false,
    dashed: false,
    alphaToCoverage: false,
    transparent: true,
    opacity: options.opacity,
    depthTest: false, // 同上：切开看内部，避免轮廓被实体面截断
    depthWrite: false
  })
  // 粗线的宽度依赖"屏幕分辨率"，窗口变化时必须同步更新，否则线会被拉变形
  material.resolution.set(options.size.width, options.size.height)

  const line = new Line2(geometry, material)
  line.name = 'section-outline'
  line.renderOrder = options.renderOrder
  return line
}

/**
 * 【清除截面】移除旧的填充与描边并释放显存。
 * 后端返回"无截面 / 单点 / 线段"时都要调用它，避免留着上一次的旧截面误导用户。
 */
export function clearSection(state) {
  if (!state || !state.group) return

  // 从后往前删，避免遍历时数组变化
  for (let i = state.group.children.length - 1; i >= 0; i -= 1) {
    const child = state.group.children[i]
    state.group.remove(child)
    if (child.geometry) child.geometry.dispose()
    if (child.material) child.material.dispose()
  }

  state.materials = []
}

/**
 * 【同步分辨率】窗口大小或投影方式变化时调用，保证粗线宽度不变形。
 */
export function updateSectionResolution(state, size) {
  if (!state) return
  state.materials.forEach(material => material.resolution.set(size.width, size.height))
  state.resolution.set(size.width, size.height)
}
