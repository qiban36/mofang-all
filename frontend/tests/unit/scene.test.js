import { describe, it, expect } from 'vitest'
import { REFERENCE_BOX_STYLE } from '@/three/scene.js'
import { SECTION_LAYERS } from '@/three/section.js'

// 说明：jsdom 没有 WebGL，createViewer 无法在这里实例化（会创建 WebGLRenderer），
// 所以 scene.js 只测"跨模块共享的样式契约"——它正是参考线框与截面层级不打架的关键。
describe('REFERENCE_BOX_STYLE', () => {
  it('是冻结的唯一样式源，颜色与透明度符合设计', () => {
    expect(Object.isFrozen(REFERENCE_BOX_STYLE)).toBe(true)
    expect(REFERENCE_BOX_STYLE.color).toBe('#475569')
    expect(REFERENCE_BOX_STYLE.opacity).toBeCloseTo(0.55)
  })

  it('线框层级在截面填充之上、截面描边之下', () => {
    expect(REFERENCE_BOX_STYLE.renderOrder).toBeGreaterThan(SECTION_LAYERS.fill)
    expect(REFERENCE_BOX_STYLE.renderOrder).toBeLessThan(SECTION_LAYERS.halo)
  })
})
