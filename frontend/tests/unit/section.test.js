import { describe, it, expect, vi } from 'vitest'
import * as THREE from 'three'
import {
  SECTION_LAYERS,
  clearSection,
  createSectionState,
  renderSection,
  updateSectionResolution
} from '@/three/section.js'

const SIZE = { width: 800, height: 600 }

// 一个躺在地面上的单位正方形（后端坐标），4 个顶点足够覆盖凸多边形剖分
const SQUARE = [
  [0, 0, 0],
  [1, 0, 0],
  [1, 0, 1],
  [0, 0, 1]
]

function setup() {
  const root = new THREE.Group()
  return { root, state: createSectionState(root) }
}

describe('createSectionState', () => {
  it('在根组下创建截面组，初始没有材质', () => {
    const { root, state } = setup()
    expect(state.group.name).toBe('section-group')
    expect(root.children).toContain(state.group)
    expect(state.materials).toEqual([])
  })
})

describe('renderSection', () => {
  it('生成 1 层填充 + 2 层描边 + 每顶点 2 层标记，层级依次为 -1 / 2 / 3 / 4 / 5', () => {
    const { state } = setup()
    expect(renderSection(state, SQUARE, SIZE)).toBe(true)

    const fill = state.group.getObjectByName('section-fill')
    expect(fill).toBeTruthy()
    expect(fill.renderOrder).toBe(SECTION_LAYERS.fill)
    // 凸 n 边形扇心剖分后是 n-2 个三角形
    expect(fill.geometry.index.count).toBe((SQUARE.length - 2) * 3)
    expect(fill.material.opacity).toBeGreaterThan(0)
    expect(fill.material.depthTest).toBe(false)

    const outlines = state.group.children.filter(child => child.name === 'section-outline')
    expect(outlines).toHaveLength(2)
    expect(outlines.map(line => line.renderOrder).sort()).toEqual([SECTION_LAYERS.halo, SECTION_LAYERS.outline])

    const [halo, outline] = outlines
    // 光晕线更粗、主描边更细：主线始终盖在光晕上
    expect(halo.material.linewidth).toBeGreaterThan(outline.material.linewidth)
    outlines.forEach(line => {
      expect(line.material.depthTest).toBe(false)
      expect(line.material.depthWrite).toBe(false)
      expect(line.material.resolution.x).toBe(SIZE.width)
      expect(line.material.resolution.y).toBe(SIZE.height)
    })
    expect(state.materials).toHaveLength(2)
  })

  it('每个顶点各有一个深色底圈和一个亮色芯，且都压在描边之上', () => {
    const { state } = setup()
    renderSection(state, SQUARE, SIZE)

    const halos = state.group.children.filter(child => child.name === 'section-marker-halo')
    const cores = state.group.children.filter(child => child.name === 'section-marker')
    expect(halos).toHaveLength(SQUARE.length)
    expect(cores).toHaveLength(SQUARE.length)

    halos.forEach(marker => {
      expect(marker.renderOrder).toBe(SECTION_LAYERS.markerHalo)
      expect(marker.material.depthTest).toBe(false)
    })
    cores.forEach((marker, index) => {
      expect(marker.renderOrder).toBe(SECTION_LAYERS.marker)
      expect(marker.material.depthTest).toBe(false)
      // 标记位置必须与后端返回的顶点完全一致，不许自己挪位
      expect([marker.position.x, marker.position.y, marker.position.z]).toEqual(SQUARE[index])
      expect(marker.scale.x).toBeGreaterThan(0)
    })
    // 底圈比芯大，才能描出深色轮廓
    expect(halos[0].scale.x).toBeGreaterThan(cores[0].scale.x)
    // 标记在最上层：层级高于主线
    expect(SECTION_LAYERS.marker).toBeGreaterThan(SECTION_LAYERS.outline)
  })

  it('点数不足 3 时返回 false，并清掉旧截面', () => {
    const { state } = setup()
    renderSection(state, SQUARE, SIZE)
    expect(state.group.children.length).toBeGreaterThan(0)

    expect(renderSection(state, [[0, 0, 0], [1, 0, 0]], SIZE)).toBe(false)
    expect(state.group.children).toHaveLength(0)
    expect(state.materials).toHaveLength(0)
  })

  it('重复渲染不会叠加旧截面', () => {
    const { state } = setup()
    renderSection(state, SQUARE, SIZE)
    renderSection(state, SQUARE, SIZE)
    // 填充 1 + 描边 2 + 顶点标记 2 × 4
    expect(state.group.children).toHaveLength(1 + 2 + SQUARE.length * 2)
  })

  it('非法入参不抛错，并保持空状态', () => {
    const { state } = setup()
    expect(() => renderSection(state, null, SIZE)).not.toThrow()
    expect(state.group.children).toHaveLength(0)
  })
})

describe('clearSection', () => {
  it('移除全部子对象，并释放几何体与材质', () => {
    const { state } = setup()
    renderSection(state, SQUARE, SIZE)

    const fill = state.group.getObjectByName('section-fill')
    const geometrySpy = vi.spyOn(fill.geometry, 'dispose')
    const materialSpy = vi.spyOn(fill.material, 'dispose')

    clearSection(state)

    expect(state.group.children).toHaveLength(0)
    expect(state.materials).toHaveLength(0)
    expect(geometrySpy).toHaveBeenCalledTimes(1)
    expect(materialSpy).toHaveBeenCalledTimes(1)
  })

  it('state 为空时不抛错', () => {
    expect(() => clearSection(null)).not.toThrow()
    expect(() => clearSection(undefined)).not.toThrow()
  })
})

describe('updateSectionResolution', () => {
  it('窗口尺寸变化后同步所有描边材质的分辨率', () => {
    const { state } = setup()
    renderSection(state, SQUARE, SIZE)

    const next = { width: 1280, height: 720 }
    updateSectionResolution(state, next)

    state.materials.forEach(material => {
      expect(material.resolution.x).toBe(next.width)
      expect(material.resolution.y).toBe(next.height)
    })
    expect(state.resolution.x).toBe(next.width)
  })

  it('state 为空时不抛错', () => {
    expect(() => updateSectionResolution(null, SIZE)).not.toThrow()
  })
})
