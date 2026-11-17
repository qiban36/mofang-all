// =============================================================================
// three/scene.js —— 场景初始化 / 相机 / 灯光 / 视角控制
//
// 这个文件只负责"把 3D 世界搭起来"：场景、相机、渲染器、控制器、灯光、地面网格。
// 具体画什么（面片、截面）交给 faces.js 和 section.js。
//
// ★ 坐标约定（很重要）
//   后端用的是"z 轴向上"的右手坐标系：展开图躺在 z = 0 平面，折起来朝 +z 立。
//   而 Three.js 默认是"y 轴向上"。为了不把每一份后端坐标都手动换算一遍，
//   这里创建一个 root 组并绕 X 轴旋转 -90°：
//       后端 (x, y, z)  →  Three 世界 (x, z, -y)
//   于是：展开图的 z=0 平面变成 Three 的地面（y=0），"朝上折"正好是 Three 的 +y。
//   后续所有面片、截面点都直接使用后端坐标，统一挂到 root 下面即可。
// =============================================================================

import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'

// 正方体折好后占据 [0,1]³（后端坐标），换算到 Three 世界后中心在这里：
//   x 中心 0.5；y 中心 0.5（原来是 z 中心）；z 中心 -0.5（原来是 y 中心）
export const SCENE_CENTER = new THREE.Vector3(0.5, 0.45, -0.5)

// 相机距离场景中心的默认距离（能完整看到 4 连片展开图，大约 5 格宽）
const VIEW_DISTANCE = 3.6

// 正交相机的默认半高；fitToObjects 会按内容大小改写它，resize 必须沿用同一个值
const ORTHO_HALF_HEIGHT = 2.3

// 参考线框样式：唯一数据源（App.vue 的画布徽标也引用这里，避免 CSS / JS 各写一套颜色）
export const REFERENCE_BOX_STYLE = Object.freeze({
  color: '#475569',
  opacity: 0.55,
  renderOrder: 1 // 透明列表内：-1 截面填充、0 面片描边、1 参考线框、2/3 截面描边、4/5 截面顶点标记
})

// 四个预设视角的方向（只需要方向，具体距离由 VIEW_DISTANCE 决定）
const VIEW_DIRECTIONS = {
  iso: [0.95, 0.85, 1.15],   // 立体视角（自定义斜视，方便同时看到展开图的纵横方向）
  front: [0, 0, 1],          // 主视图：从 +z 方向看过去（后端 y=0 的那一面）
  top: [0, 1, 0],            // 俯视图：从正上方往下看
  left: [-1, 0, 0]           // 左视图：从 -x 方向看过去
}

/**
 * 创建相机。
 * @param {'perspective'|'orthographic'} type 投影方式
 * @param {{width:number, height:number}} size 画布尺寸（宽高比要用）
 */
function createCamera(type, size, orthoHalfHeight = ORTHO_HALF_HEIGHT) {
  const aspect = size.width / Math.max(size.height, 1)

  if (type === 'orthographic') {
    // 正交相机：没有近大远小，工程图常用它，看起来更"平"
    const halfHeight = orthoHalfHeight
    const halfWidth = halfHeight * aspect
    return new THREE.OrthographicCamera(-halfWidth, halfWidth, halfHeight, -halfHeight, 0.1, 100)
  }

  // 透视相机：有近大远小，更接近人眼
  return new THREE.PerspectiveCamera(45, aspect, 0.1, 100)
}

/**
 * 创建轨道控制器（拖拽旋转 / 滚轮缩放）。
 * 透视与正交切换时相机会被整体替换，控制器也要重建，所以把配置收在这里，避免两处漂移。
 */
function createControls(camera, domElement) {
  const controls = new OrbitControls(camera, domElement)
  controls.target.copy(SCENE_CENTER)
  controls.enableDamping = true // 阻尼惯性，拖起来更顺滑
  controls.dampingFactor = 0.08
  controls.minDistance = 1.2 // 滚轮拉最近只能到 1.2
  controls.maxDistance = 12
  controls.update()
  return controls
}

/**
 * 初始化整个 3D 视图。
 * @param {HTMLElement} container 画布挂载的父容器（App.vue 里的 .canvas-host）
 * @returns 一个 viewer 对象，后续所有操作都通过它进行
 */
export function createViewer(container) {
  // ---------- 1. 场景 ----------
  const scene = new THREE.Scene()
  scene.background = new THREE.Color(0xf3f5f9) // 浅灰蓝背景，面片颜色更清楚

  // ---------- 2. 渲染器 ----------
  const renderer = new THREE.WebGLRenderer({ antialias: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2)) // 高分屏最多按 2 倍渲染，省性能
  renderer.setSize(container.clientWidth, container.clientHeight)
  renderer.domElement.setAttribute('role', 'img')
  renderer.domElement.setAttribute('aria-label', '三维几何演示画布：拖拽旋转、滚轮缩放、右键平移')
  container.appendChild(renderer.domElement)

  // ---------- 3. 相机 + 控制器 ----------
  const size = { width: container.clientWidth, height: container.clientHeight }
  let orthoHalfHeight = ORTHO_HALF_HEIGHT // 正交相机半高，fitToObjects 会按内容改写
  let camera = createCamera('perspective', size) // 用 let：切换正交/透视时要整体替换相机
  camera.position.set(
    SCENE_CENTER.x + VIEW_DIRECTIONS.iso[0] * VIEW_DISTANCE,
    SCENE_CENTER.y + VIEW_DIRECTIONS.iso[1] * VIEW_DISTANCE,
    SCENE_CENTER.z + VIEW_DIRECTIONS.iso[2] * VIEW_DISTANCE
  )
  camera.lookAt(SCENE_CENTER)

  // OrbitControls：鼠标拖拽旋转、滚轮缩放、右键平移（这个项目只用旋转 + 缩放）
  let controls = createControls(camera, renderer.domElement)

  // ---------- 4. 根组：把后端 z-up 坐标转成 Three 的 y-up ----------
  // 注意：这里旋转的是"整个坐标系"，只做一次坐标轴换算（z 向上 → y 向上），
  // 与面片折叠无关；面片折叠一律用"绕公共边的轴角旋转"，绝不用欧拉角凑。
  // 为了不让读者误以为用了欧拉角，这里同样写成四元数（绕世界 X 轴 -90°）。
  const root = new THREE.Group()
  root.quaternion.setFromAxisAngle(new THREE.Vector3(1, 0, 0), -Math.PI / 2)
  scene.add(root)

  // ---------- 5. 灯光 ----------
  // 环境光：均匀照亮所有面，避免背光面全黑（题目要求必须有环境光）
  scene.add(new THREE.AmbientLight(0xffffff, 0.95))
  // 主平行光：产生明暗变化，让立方体的三个面能区分开
  const keyLight = new THREE.DirectionalLight(0xffffff, 1.5)
  keyLight.position.set(4, 8, 6)
  scene.add(keyLight)
  // 补光：从背面补一点，避免背面死黑
  const fillLight = new THREE.DirectionalLight(0xffffff, 0.45)
  fillLight.position.set(-5, 4, -7)
  scene.add(fillLight)

  // ---------- 6. 地面参考网格 ----------
  // 网格画在 y = 0，正好对应展开图所在的 z = 0 平面，方便看清"平铺在桌面上"
  const grid = new THREE.GridHelper(8, 16, 0xc9d2df, 0xdfe5ee)
  grid.position.y = -0.002 // 往下挪一点点，避免和面片共面时闪烁（z-fighting）
  scene.add(grid)

  // ---------- 6.5 参考线框（截面用） ----------
  // 后端坐标是 z 向上、盒子占 [0,a] × [0,b] × [0,c]，
  // 所以线框挂在 root 下（跟着 root 一起换算到 y-up），截面红线才会和它对齐。
  // 正方体折叠后本身就是 1×1×1，不需要额外线框；只有长方体尺寸不同，才显示它。
  // 半透明"幽灵框"：不做深度测试，被面片挡住的边也能看到，方便对照截面。
  // 颜色 / 透明度统一从 REFERENCE_BOX_STYLE 读取，禁止在别处再写一份。
  const referenceBox = new THREE.LineSegments(
    new THREE.EdgesGeometry(new THREE.BoxGeometry(1, 1, 1)),
    new THREE.LineBasicMaterial({
      color: REFERENCE_BOX_STYLE.color,
      transparent: true,
      opacity: REFERENCE_BOX_STYLE.opacity,
      depthTest: false,
      depthWrite: false
    })
  )
  referenceBox.name = 'reference-box'
  referenceBox.renderOrder = REFERENCE_BOX_STYLE.renderOrder
  referenceBox.visible = false // 默认隐藏，由 setReferenceBox 控制
  root.add(referenceBox)

  // 长方体的半透明实体：只画线框会让人误以为"截面切在一个空盒子上"，
  // 补一层淡蓝半透明表面，才能让学员看到"截面切在哪个实体上"。
  // renderOrder 设为 -2：先于截面填充（-1）绘制，避免把红线染淡。
  const solidBox = new THREE.Mesh(
    new THREE.BoxGeometry(1, 1, 1),
    new THREE.MeshLambertMaterial({
      color: 0x9ec5e8,
      transparent: true,
      opacity: 0.34,
      depthWrite: false
    })
  )
  solidBox.name = 'solid-box'
  solidBox.renderOrder = -2
  solidBox.visible = false
  root.add(solidBox)

  // ---------- 7. 对外暴露的操作 ----------
  const viewer = {
    scene,
    root,
    renderer,
    // 用 getter：切换投影时 camera 会被整体替换，getter 保证外部拿到的永远是最新那台
    get camera() {
      return camera
    },
    get controls() {
      return controls
    },

    /** 当前画布尺寸（截面粗线需要它来算线宽） */
    size() {
      return { width: container.clientWidth, height: container.clientHeight }
    },

    /**
     * 把"后端坐标"里的点投影成画布像素坐标（给 HTML 截面标注定位用）。
     * 只做坐标换算，不参与几何计算。
     * @param {number[]} point [x, y, z]（后端坐标）
     * @returns {{x:number, y:number, visible:boolean}} 像素坐标；visible=false 表示在相机视锥外
     */
    project(point) {
      const vec = new THREE.Vector3(point[0], point[1], point[2])
      root.localToWorld(vec) // 后端 z-up → Three y-up
      vec.project(camera)
      return {
        x: (vec.x * 0.5 + 0.5) * container.clientWidth,
        y: (-vec.y * 0.5 + 0.5) * container.clientHeight,
        visible: vec.z > -1 && vec.z < 1
      }
    },

    /**
     * 显示 / 隐藏"当前几何体"示意框：长方体 = 半透明实体 + 深色棱线。
     * @param {number[]|null} dims 后端坐标下的三边 [a, b, c]（盒子占 [0,a]×[0,b]×[0,c]）；
     *   传 null 或非法值则隐藏
     */
    setReferenceBox(dims) {
      if (!Array.isArray(dims) || dims.length !== 3) {
        referenceBox.visible = false
        solidBox.visible = false
        return
      }

      const size = dims.map(value => Number(value))
      if (size.some(value => !Number.isFinite(value) || value <= 0)) {
        referenceBox.visible = false
        solidBox.visible = false
        return
      }

      // BoxGeometry 以自身中心为原点：先把 1×1×1 的盒子缩放到 a×b×c，再平移到盒子中心
      const center = [size[0] / 2, size[1] / 2, size[2] / 2]
      ;[referenceBox, solidBox].forEach(box => {
        box.scale.set(size[0], size[1], size[2])
        box.position.set(center[0], center[1], center[2])
        box.visible = true
      })
    },

    /**
     * 自动取景：把一组 Three 对象完整框进画面（展开图加载后调用）。
     * @param {THREE.Object3D[]} objects 需要完整可见的对象
     * @param {number} padding 留白系数（1.15 ≈ 上下左右各留约 15%）
     */
    fitToObjects(objects, padding = 1.15) {
      if (!Array.isArray(objects) || !objects.length) return

      root.updateMatrixWorld(true)
      const box = new THREE.Box3()
      objects.forEach(object => box.expandByObject(object))
      if (box.isEmpty()) return

      const sphere = box.getBoundingSphere(new THREE.Sphere())
      const direction = new THREE.Vector3().subVectors(camera.position, controls.target)
      if (direction.lengthSq() === 0) direction.set(1, 1, 1)
      direction.normalize()

      controls.target.copy(sphere.center)

      if (camera.isPerspectiveCamera) {
        const halfFov = THREE.MathUtils.degToRad(camera.fov) / 2
        // 竖屏 / 窄画布时水平视角更小，取两者中更"紧"的那个，保证左右也完整可见
        const aspect = Math.max(camera.aspect || 1, 1e-6)
        const halfAngle = Math.min(halfFov, Math.atan(Math.tan(halfFov) * aspect))
        const distance = (sphere.radius * padding) / Math.sin(halfAngle)
        camera.position.copy(sphere.center).addScaledVector(direction, distance)
      } else {
        // 正交相机靠改半高缩放，不动距离，避免穿过物体
        const aspect = Math.max(camera.right - camera.left, 1e-6) / Math.max(camera.top - camera.bottom, 1e-6)
        orthoHalfHeight = Math.max((sphere.radius * padding) / Math.min(1, aspect), 0.3)
        camera.top = orthoHalfHeight
        camera.bottom = -orthoHalfHeight
        camera.left = -orthoHalfHeight * aspect
        camera.right = orthoHalfHeight * aspect
        camera.updateProjectionMatrix()
        camera.position.copy(sphere.center).addScaledVector(direction, VIEW_DISTANCE)
      }
      controls.update()
    },

    /**
     * 切换投影方式（正交 / 透视）。
     * 做法：记住当前相机位置、朝向与观察点 → 换一台相机 → 把状态搬过去 → 重建控制器，
     * 这样切换投影时用户刚才拖到的角度和缩放位置不会跳回默认视角。
     */
    setProjection(type) {
      if (type !== 'perspective' && type !== 'orthographic') return
      if (type === 'perspective' && camera.isPerspectiveCamera) return
      if (type === 'orthographic' && camera.isOrthographicCamera) return

      const currentSize = viewer.size()
      const position = camera.position.clone()
      const up = camera.up.clone()
      const target = controls.target.clone() // 保留用户当前观察点

      const newCamera = createCamera(type, currentSize, orthoHalfHeight)
      newCamera.position.copy(position)
      newCamera.up.copy(up)
      newCamera.lookAt(target)

      camera = newCamera // 注意：camera 用 let 声明，就是为了这里能整体替换

      controls.dispose() // 旧控制器绑定的是旧相机，先销毁
      controls = createControls(camera, renderer.domElement)
      controls.target.copy(target)
      controls.update()
    },

    /**
     * 切换预设视角：iso（立体）/ front（主视）/ top（俯视）/ left（左视）。
     */
    setView(name) {
      const dir = VIEW_DIRECTIONS[name]
      if (!dir) return
      const length = Math.hypot(dir[0], dir[1], dir[2]) || 1
      camera.position.set(
        SCENE_CENTER.x + (dir[0] / length) * VIEW_DISTANCE,
        SCENE_CENTER.y + (dir[1] / length) * VIEW_DISTANCE,
        SCENE_CENTER.z + (dir[2] / length) * VIEW_DISTANCE
      )
      controls.target.copy(SCENE_CENTER)
      controls.update()
    },

    /** 窗口尺寸变化时同步相机与渲染器 */
    resize() {
      const s = viewer.size()
      const aspect = s.width / Math.max(s.height, 1)

      if (camera.isPerspectiveCamera) {
        camera.aspect = aspect
      } else {
        camera.left = -orthoHalfHeight * aspect
        camera.right = orthoHalfHeight * aspect
        camera.top = orthoHalfHeight
        camera.bottom = -orthoHalfHeight
      }
      camera.updateProjectionMatrix()
      // 窗口在不同 DPR 的显示器之间移动时，按新 DPR 重建绘制缓冲，避免画面发虚
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
      renderer.setSize(s.width, s.height)
      return s
    },

    /** 每帧渲染（由 App.vue 的 requestAnimationFrame 循环调用） */
    render() {
      controls.update()
      renderer.render(scene, camera)
    },

    /** 卸载时释放 GPU 资源 */
    dispose() {
      controls.dispose()

      // 面片与截面已由各自的模块 dispose，这里兜底清掉场景里剩下的资源（网格地面等）
      scene.traverse(obj => {
        if (obj.geometry) obj.geometry.dispose()
        if (obj.material) {
          if (Array.isArray(obj.material)) obj.material.forEach(m => m.dispose())
          else obj.material.dispose()
        }
      })

      renderer.dispose()
      renderer.forceContextLoss?.() // 主动交还 WebGL 上下文，避免 HMR 反复创建导致上下文泄漏
      if (renderer.domElement.parentNode === container) {
        container.removeChild(renderer.domElement)
      }
    }
  }

  return viewer
}