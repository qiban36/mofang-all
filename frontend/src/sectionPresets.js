// =============================================================================
// sectionPresets.js —— 正方体 / 长方体的"截面类型"预设
//
// 参考截面图（三角形 / 菱形 / 梯形 / 矩形 / 五边形 / 六边形…）整理而来：
// 每个预设就是一组切面参数（origin + normal），点击后由 App.vue 直接填进滑块
// 并请求后端 /api/section/cut —— 前端依旧不做任何几何推导。
//
// ★ 数据约定
//   1. 坐标是后端坐标系（盒子占 [0,a]×[0,b]×[0,c]），与界面滑块完全一致；
//   2. 法向量只关心方向，这里把所有分量都收进 [-1, 1] 并且落在滑块刻度上
//      （法向滑块 step = 0.01、原点滑块 step = 0.05），点预设后滑块不会跳位；
//   3. 每条预设都用后端几何模块核对过顶点数、边长与平行关系，lable 与真实截面一致；
//   4. 顺序按海报排版：三角形 → 四边形 → 五边形 → 六边形。
// =============================================================================

export const SECTION_PRESETS = {
  // ---------------- 正方体 [0,1]³ ----------------
  cube: [
    { id: 'triangle-equilateral', group: '三角形', label: '等边三角形', origin: [0.25, 0.25, 0.25], normal: [1, 1, 1] },
    { id: 'triangle-isosceles', group: '三角形', label: '等腰三角形', origin: [0.4, 0, 0], normal: [1, 0.5, 0.5] },
    { id: 'triangle-acute', group: '三角形', label: '锐角三角形', origin: [0.2, 0, 0], normal: [1, 0.67, 0.33] },

    { id: 'quad-rhombus', group: '四边形', label: '菱形', origin: [0.5, 0.5, 0.5], normal: [1, 0.5, 0.5] },
    { id: 'quad-trapezoid-isosceles', group: '四边形', label: '等腰梯形', origin: [0, 0.75, 0.9], normal: [1, 1, 0.25] },
    { id: 'quad-trapezoid', group: '四边形', label: '普通梯形', origin: [0, 0.7, 0.9], normal: [1, 0.75, 0.25] },
    { id: 'quad-square', group: '四边形', label: '正方形', origin: [0.5, 0, 0], normal: [1, 0, 0] },
    { id: 'quad-rectangle', group: '四边形', label: '矩形', origin: [0.5, 0.5, 0.5], normal: [1, 1, 0] },
    { id: 'quad-parallelogram', group: '四边形', label: '平行四边形', origin: [0.5, 0.5, 0.5], normal: [1, 0.67, 0.33] },

    { id: 'pentagon', group: '五边形', label: '五边形', origin: [0.4, 0.25, 0.5], normal: [1, 0.5, 0.5] },

    { id: 'hexagon-regular', group: '六边形', label: '正六边形', origin: [0.5, 0.5, 0.5], normal: [1, 1, 1] },
    { id: 'hexagon', group: '六边形', label: '普通六边形', origin: [0.45, 0.45, 0.5], normal: [1, 1, 1] }
  ],

  // ---------------- 长方体 [0,2]×[0,1.5]×[0,1] ----------------
  cuboid: [
    { id: 'triangle-equilateral', group: '三角形', label: '等边三角形', origin: [0.25, 0.25, 0.25], normal: [1, 1, 1] },
    { id: 'triangle-isosceles', group: '三角形', label: '等腰三角形', origin: [0.4, 0, 0], normal: [1, 0.5, 0.5] },
    { id: 'triangle-acute', group: '三角形', label: '锐角三角形', origin: [0.2, 0, 0], normal: [1, 0.67, 0.33] },

    { id: 'quad-rhombus', group: '四边形', label: '菱形', origin: [0.05, 0, 0], normal: [0.7, -0.28, -0.89] },
    { id: 'quad-trapezoid-isosceles', group: '四边形', label: '等腰梯形', origin: [0, 0.75, 0.9], normal: [1, 1, 0.25] },
    { id: 'quad-trapezoid', group: '四边形', label: '普通梯形', origin: [0, 0.9, 0.85], normal: [1, 0.6, 0.2] },
    { id: 'quad-square', group: '四边形', label: '正方形', origin: [0.6, 0, 0], normal: [0.8, 0.6, 0] },
    { id: 'quad-rectangle', group: '四边形', label: '矩形（纵切）', origin: [0.5, 0, 0], normal: [1, 0, 0] },
    { id: 'quad-rectangle-h', group: '四边形', label: '矩形（横切）', origin: [0, 0.5, 0], normal: [0, 1, 0] },
    { id: 'quad-parallelogram', group: '四边形', label: '平行四边形', origin: [1.25, 0, 0], normal: [1, 0.5, 0.5] },

    { id: 'pentagon', group: '五边形', label: '五边形', origin: [0.25, 0, 0], normal: [0.6, 0.2, -0.6] },

    { id: 'hexagon', group: '六边形', label: '六边形', origin: [0, 0.5, 0], normal: [0.3, 0.6, -0.9] }
  ]
}

/**
 * 取某个几何体的全部截面预设。
 * @param {string} shape 几何体名（cube / cuboid）
 * @returns {Array<{id:string, group:string, label:string, origin:number[], normal:number[]}>}
 */
export function getSectionPresets(shape) {
  return SECTION_PRESETS[shape] || []
}

const AXES = ['x', 'y', 'z']

/**
 * 找出与当前 origin / normal 完全一致的预设（用于按钮高亮），没有则返回 null。
 * 预设写入滑块的值与这里比较的是同一份数字，直接严格比较即可。
 * @param {Array} presets getSectionPresets 的返回值
 * @param {{x:number,y:number,z:number}} origin 当前原点
 * @param {{x:number,y:number,z:number}} normal 当前法向量
 */
export function matchPreset(presets, origin, normal) {
  const found = presets.find(preset =>
    preset.origin.every((value, index) => value === origin[AXES[index]]) &&
    preset.normal.every((value, index) => value === normal[AXES[index]])
  )
  return found || null
}
