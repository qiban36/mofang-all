// =============================================================================
// three/faces.js —— 6 个独立面片的渲染 + 沿铰链翻折动画
//
// 后端 /api/hexahedron/get_data 返回 6 个面片，每个面片给出：
//   start_pos     展开状态下 4 个角点（都在 z = 0 平面上）
//   hinge_edge    与父面片共享的那条边（折痕），两个端点
//   rotate_axis   折叠旋转轴（单位向量，方向严格沿 hinge_edge）
//   rotate_angle  旋转角度（90°）
//   parent_id     父面片编号；子面片要跟着父面片一起动
//   fold_order    折叠顺序（0 是基准面）
//
// ★ 为什么面片要"嵌套"而不是"各转各的"
//   一条 4 连片折起来时，第 3 片是绕"已经折起来的第 2 片"的边再转 90°。
//   如果 6 片都按自己的轴在世界坐标里独立旋转，第 3 片会飞出去。
//   所以按 parent_id 建父子 Group：子 Group 的局部坐标就是"摊平坐标系"，
//   它绕自己的铰链转 90° 后，父 Group 的旋转会自动叠加下来。
//
// ★ 绕任意直线旋转公式
//   绕"过点 h、方向 u 的直线"旋转 θ，等价于：先平移到 h → 旋转 → 再平移回去
//       p' = R(p − h) + h = R·p + (h − R·h)
//   在 Three.js 里就是把 Group 的 quaternion 设成 R，
//   把 Group 的 position 设成 h − R·h（而不是 h），这样旋转轴才真的穿过那条棱。
// =============================================================================

import * as THREE from 'three'
import * as TWEEN from '@tweenjs/tween.js'

// 调试开关：开发模式（npm run dev）自动打开，生产构建自动关闭。
// 打开后把每片的铰链、旋转轴、角度、折后角点打印到控制台，
// 并在折叠结束时"用实际渲染出的角点"和"后端给的 target_pos"逐个比对。
// 这些量全部来自后端（前端只做刚体变换），打印出来是为了证明"确实沿这条边走"。
const DEBUG = Boolean(import.meta.env.DEV)

// Tween.js v25 起不再把补间自动塞进全局组（全局 TWEEN 本身也已标记废弃），
// 所以自己建一个组统一管理折叠 / 展开动画，由渲染循环每帧推进。
const foldTweens = new TWEEN.Group()

/** 推进所有折叠 / 展开补间（渲染循环每帧调用一次） */
export function updateFoldAnimations(time) {
  foldTweens.update(time)
}

/** 用户是否开启了"减少动态效果"（系统级无障碍设置） */
function prefersReducedMotion() {
  return typeof window !== 'undefined' && window.matchMedia
    ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
    : false
}

/**
 * 根据后端返回的面片数据，在 root 下创建 6 个独立网格（每个面片 1 个 Mesh，绝不合并）。
 *
 * @param {THREE.Group} root 场景根组（已在 scene.js 里做过 z-up → y-up 的旋转）
 * @param {Array} facesData 后端返回的 faces 数组
 * @param {{edgeLength?: number}} [options] edgeLength 面片边长，取自后端 edge_length（默认 1）
 * @returns {Array} entries —— 每一项对应一个面片，供折叠 / 重置 / 清除使用
 */
export function createFaceMeshes(root, facesData, options = {}) {
  const edgeLength = Number(options.edgeLength) > 0 ? Number(options.edgeLength) : 1
  const entries = []
  const entryById = new Map()

  // 6 个面片形状完全相同：几何体与描边只建一份、6 个 Mesh 共用（省显存、省构建时间）。
  // 颜色随面片不同，所以 MeshStandardMaterial 仍按片创建。
  const sharedGeometry = new THREE.PlaneGeometry(edgeLength, edgeLength)
  const sharedOutlineGeometry = new THREE.EdgesGeometry(sharedGeometry)
  const sharedOutlineMaterial = new THREE.LineBasicMaterial({
    color: 0x2c3e50,
    transparent: true,
    opacity: 0.45
  })

  // ---------------- 第一轮：给每个面片建 Group + Mesh ----------------
  facesData.forEach(data => {
    // 后端面片编号字段叫 face_index（这里兼容 face_id 的写法，避免字段改名时静默出错）
    const faceId = data.face_index ?? data.face_id

    // 面片 Group：局部坐标 = 后端的"摊平坐标系"（z = 0 平面）
    const group = new THREE.Group()
    group.name = `face-${faceId}`

    // PlaneGeometry(edgeLength, edgeLength)：默认躺在自身 XY 平面上、法向量 +z
    // 这正好对得上后端的格子（躺在 z = 0 平面上），所以不需要再旋转网格。
    const material = new THREE.MeshStandardMaterial({
      color: new THREE.Color(data.color), // 颜色由后端按"折完是哪一面"分配
      roughness: 0.7,
      metalness: 0.05,
      side: THREE.DoubleSide // 双面可见：展开时可以翻到背面看
    })
    const mesh = new THREE.Mesh(sharedGeometry, material)
    mesh.name = `face-mesh-${faceId}`

    // 把网格放到它所在的格子上：格子 (col, row) 覆盖 [col, col+1] × [row, row+1] 个格宽，
    // 而 PlaneGeometry 以自身中心为原点，所以中心点 = (col + 0.5, row + 0.5) × 边长
    mesh.position.set((data.cell[0] + 0.5) * edgeLength, (data.cell[1] + 0.5) * edgeLength, 0)

    // 给面片加一圈淡淡的描边，边界更清楚（纯装饰，不影响几何计算）
    const outline = new THREE.LineSegments(sharedOutlineGeometry, sharedOutlineMaterial)
    mesh.add(outline)

    group.add(mesh)
    group.userData.faceData = data

    const entry = {
      data,          // 后端原始数据
      group,         // 折痕所在的 Group（负责旋转）
      mesh,          // 真正的面片网格
      isBase: !!data.is_base,
      state: { v: 0 }, // 折叠进度：0 = 完全摊平，1 = 完全折好（Tween.js 就补间这个值）
      tween: null,   // 当前正在播放的补间，切换时要先 stop

      // 折叠变换的复用对象：轴与铰链点只算一次，四元数 / 临时向量每帧复用。
      // 这样动画期间不会为 6 个面片每帧 new 一堆 THREE 对象，减少 GC 抖动。
      axis: data.rotate_axis
        ? new THREE.Vector3(data.rotate_axis[0], data.rotate_axis[1], data.rotate_axis[2]).normalize()
        : null,
      hinge: data.hinge_edge
        ? new THREE.Vector3(data.hinge_edge[0][0], data.hinge_edge[0][1], data.hinge_edge[0][2])
        : null,
      quaternion: new THREE.Quaternion(),
      rotatedHinge: new THREE.Vector3()
    }

    entries.push(entry)
    entryById.set(faceId, entry)
  })

  // ---------------- 第二轮：按 parent_id 建立父子关系 ----------------
  entries.forEach(entry => {
    if (entry.isBase) {
      // 基准面直接挂在根组上，永远不动
      root.add(entry.group)
      return
    }
    const parent = entryById.get(entry.data.parent_id)
    if (parent) {
      // 子 Group 挂到父 Group 下：父面片转多少，子面片就跟着转多少
      parent.group.add(entry.group)
    } else {
      // 数据异常时的兜底：直接挂根组，至少不会崩
      root.add(entry.group)
    }
  })

  // 初始状态是"平铺展开"，所以先把所有 Group 的变换清零
  entries.forEach(entry => applyFoldTransform(entry, 0))

  // 记住根组：折叠完成后要在"根组坐标系"（= 后端坐标系）里核对角点
  entries.forEach(entry => {
    entry.rootGroup = root
  })

  if (DEBUG) {
    const planeCount = entries.filter(e => e.mesh.geometry.type === 'PlaneGeometry').length
    console.groupCollapsed(`[面片渲染] 共 ${entries.length} 个独立网格（PlaneGeometry ${planeCount} 个）`)
    entries.forEach(e => {
      const d = e.data
      const hinge = d.hinge_edge ? d.hinge_edge.map(p => `(${p.join(', ')})`).join(' → ') : '无（基准面）'
      const axis = d.rotate_axis ? `(${d.rotate_axis.join(', ')})` : '无'
      console.log(
        `面片#${d.face_index}  ${e.mesh.geometry.type}  父面片=${d.parent_id ?? '无'}  ` +
          `铰链=${hinge}  轴=${axis}  角度=${d.rotate_angle}°  颜色=${d.color}`
      )
    })
    console.groupEnd()
  }

  return entries
}

/**
 * 按折叠进度更新一个面片的变换。
 *
 * @param {Object} entry createFaceMeshes 返回的条目
 * @param {number} progress 0 = 摊平，1 = 折好（0~1 之间是动画中间态）
 */
function applyFoldTransform(entry, progress) {
  if (entry.isBase) return // 基准面不动，留在桌面上

  // 当前应该转的角度：目标角度 × 进度
  const theta = THREE.MathUtils.degToRad(entry.data.rotate_angle) * progress

  // 四元数 = 绕铰链轴（后端已给成单位向量）转 theta；对象复用，避免每帧分配
  entry.quaternion.setFromAxisAngle(entry.axis, theta)

  // 关键：旋转轴要"穿过铰链"，所以位移量 = h − R·h（而不是直接把组移到 h）
  entry.rotatedHinge.copy(entry.hinge).applyQuaternion(entry.quaternion) // R·h
  entry.group.position.copy(entry.hinge).sub(entry.rotatedHinge)          // h − R·h
  entry.group.quaternion.copy(entry.quaternion)
}

/**
 * 【折叠】播放翻折动画：每片面片按 fold_order 依次绕自己的铰链转 90°。
 *
 * Tween.js 的用法：把 entry.state.v 从 0 补间到 1，每帧回调里用新的进度更新变换。
 * 这样动画曲线（缓动）由 Tween 控制，几何变换只关心"当前进度是多少"，两者解耦。
 *
 * @param {Array} entries createFaceMeshes 的返回值
 * @param {Object} options { duration: 单片面片时长(ms), stagger: 相邻面片延迟(ms), onComplete }
 */
export function foldFaces(entries, options = {}) {
  const { duration = 620, stagger = 170, onComplete = null } = options

  // 先把上一轮没播完的动画停掉，避免两个补间同时抢着改同一个 state
  entries.forEach(entry => {
    if (entry.tween) {
      entry.tween.stop()
      entry.tween = null
    }
  })

  // 所有面片折完时统一做一次收尾：先自检，再通知调用方
  let pending = 0
  const finish = () => {
    if (DEBUG) reportFoldResult(entries)
    if (typeof onComplete === 'function') onComplete()
  }

  // 系统开启"减少动态效果"时，直接折到位、不播放补间（无障碍）
  if (prefersReducedMotion()) {
    entries.forEach(entry => {
      entry.state.v = 1
      applyFoldTransform(entry, 1)
    })
    finish()
    return
  }

  entries.forEach(entry => {
    if (entry.isBase) return // 基准面不参与折叠动画

    pending += 1
    // 延迟按折叠顺序错开：父面片先折，子面片随后跟上，看起来才像"一片片折起来"
    const delay = entry.data.fold_order * stagger

    entry.tween = new TWEEN.Tween(entry.state, foldTweens)
      .to({ v: 1 }, duration)
      .delay(delay)
      .easing(TWEEN.Easing.Cubic.InOut) // 两头慢中间快，翻折更有"惯性"
      .onUpdate(() => applyFoldTransform(entry, entry.state.v))
      .onComplete(() => {
        pending -= 1
        if (pending === 0) finish()
      })
      .start()
  })

  // 只有基准面（理论上不会发生）时直接收尾，避免按钮一直转圈
  if (pending === 0) finish()
}

/**
 * 折叠完成后的自检：把每片面片在"根组坐标系"里的 4 个角点算出来，
 * 与后端返回的 target_pos 逐个比对，并打印最大偏差。
 *
 * 为什么要这么做：只有把渲染结果换算回后端坐标系比对，
 * 才能证明"动画确实沿铰链转到了后端算出的位置"，而不是靠肉眼看着像。
 */
function reportFoldResult(entries) {
  const rootGroup = entries[0]?.rootGroup
  if (!rootGroup) return

  rootGroup.updateMatrixWorld(true)
  const rootInverse = new THREE.Matrix4().copy(rootGroup.matrixWorld).invert()
  // 角点相对网格中心的偏移随边长走（默认 1 → ±0.5）
  const half = (entries[0]?.mesh.geometry.parameters?.width ?? 1) / 2
  const cornerOffsets = [
    [-half, -half],
    [half, -half],
    [half, half],
    [-half, half]
  ]

  let maxDeviation = 0
  console.groupCollapsed('[折叠自检] 渲染角点 vs 后端 target_pos')
  entries.forEach(e => {
    let worst = 0
    cornerOffsets.forEach(([dx, dy], i) => {
      // 面片局部坐标 → 世界坐标 → 根组（后端）坐标
      const v = new THREE.Vector3(dx, dy, 0).applyMatrix4(e.mesh.matrixWorld).applyMatrix4(rootInverse)
      const target = e.data.target_pos[i]
      const deviation = Math.hypot(v.x - target[0], v.y - target[1], v.z - target[2])
      worst = Math.max(worst, deviation)
    })
    maxDeviation = Math.max(maxDeviation, worst)
    console.log(`面片#${e.data.face_index}  最大偏差 ${worst.toExponential(2)}  (后端落面: ${e.data.target_face})`)
  })
  console.log(maxDeviation < 1e-6 ? '✅ 全部角点与后端一致（<1e-6）' : `❌ 存在偏差 ${maxDeviation}`)
  console.groupEnd()
}

/**
 * 【重置】把所有面片平滑地转回平铺展开状态（进度 1 → 0）。
 */
export function resetFaces(entries, options = {}) {
  const { duration = 480, onComplete = null } = options

  entries.forEach(entry => {
    if (entry.tween) {
      entry.tween.stop()
      entry.tween = null
    }
  })

  // 系统开启"减少动态效果"时，直接摊回平铺、不播放补间（无障碍）
  if (prefersReducedMotion()) {
    entries.forEach(entry => {
      entry.state.v = 0
      applyFoldTransform(entry, 0)
    })
    if (typeof onComplete === 'function') onComplete()
    return
  }

  let pending = 0
  entries.forEach(entry => {
    if (entry.isBase) {
      applyFoldTransform(entry, 0)
      return
    }
    pending += 1
    entry.tween = new TWEEN.Tween(entry.state, foldTweens)
      .to({ v: 0 }, duration)
      .easing(TWEEN.Easing.Cubic.Out)
      .onUpdate(() => applyFoldTransform(entry, entry.state.v))
      .onComplete(() => {
        pending -= 1
        if (pending === 0 && typeof onComplete === 'function') onComplete()
      })
      .start()
  })

  if (pending === 0 && typeof onComplete === 'function') onComplete()
}

/**
 * 【清除】销毁 6 个面片（重新加载展开图前调用，避免旧面片残留在场景里）。
 *
 * 6 个面片共用同一份 PlaneGeometry / EdgesGeometry / 描边材质，
 * 所以先用 Set 去重再 dispose，避免同一个资源被重复释放。
 */
export function clearFaceMeshes(entries) {
  if (!Array.isArray(entries) || !entries.length) return

  const geometries = new Set()
  const materials = new Set()

  entries.forEach(entry => {
    if (entry.tween) {
      entry.tween.stop()
      entry.tween = null
    }

    // 先从父节点上摘下来
    if (entry.group.parent) entry.group.parent.remove(entry.group)

    entry.group.traverse(obj => {
      if (obj.geometry) geometries.add(obj.geometry)
      if (obj.material) {
        if (Array.isArray(obj.material)) obj.material.forEach(m => materials.add(m))
        else materials.add(obj.material)
      }
    })
  })

  // Three.js 不会自动回收显存，几何体与材质都要手动 dispose
  geometries.forEach(geometry => geometry.dispose())
  materials.forEach(material => material.dispose())
}