import { describe, it, expect } from 'vitest'
import { SECTION_PRESETS, getSectionPresets, matchPreset } from '@/sectionPresets.js'

const SHAPES = [
  { name: 'cube', dims: [1, 1, 1] },
  { name: 'cuboid', dims: [2, 1.5, 1] }
]

describe('SECTION_PRESETS', () => {
  it.each(SHAPES)('$name 有 12 组预设且 id 唯一', ({ name }) => {
    const presets = getSectionPresets(name)
    expect(presets).toHaveLength(12)
    expect(new Set(presets.map(preset => preset.id)).size).toBe(presets.length)
  })

  it.each(SHAPES)('$name 的 origin 落在盒子内，normal 非零且分量在 [-1,1]', ({ name, dims }) => {
    getSectionPresets(name).forEach(preset => {
      expect(preset.origin).toHaveLength(3)
      expect(preset.normal).toHaveLength(3)

      preset.origin.forEach((value, index) => {
        expect(Number.isFinite(value)).toBe(true)
        expect(value).toBeGreaterThanOrEqual(0)
        expect(value).toBeLessThanOrEqual(dims[index])
      })

      preset.normal.forEach(value => {
        expect(Number.isFinite(value)).toBe(true)
        expect(Math.abs(value)).toBeLessThanOrEqual(1)
      })
      expect(preset.normal.some(value => value !== 0)).toBe(true)
    })
  })

  it.each(SHAPES)('$name 的参数都落在滑块刻度上（原点 0.05 / 法向 0.01）', ({ name }) => {
    const onGrid = (value, step) => Math.abs(value / step - Math.round(value / step)) < 1e-9

    getSectionPresets(name).forEach(preset => {
      preset.origin.forEach(value => {
        expect(onGrid(value, 0.05)).toBe(true)
      })
      preset.normal.forEach(value => {
        expect(onGrid(value, 0.01)).toBe(true)
      })
    })
  })

  it('未知几何体返回空数组', () => {
    expect(getSectionPresets('cylinder')).toEqual([])
    expect(SECTION_PRESETS.cube).toBeDefined()
    expect(SECTION_PRESETS.cuboid).toBeDefined()
  })
})

describe('matchPreset', () => {
  it('滑块值与预设完全一致时返回该预设', () => {
    const presets = getSectionPresets('cube')
    const target = presets[0]
    const origin = { x: target.origin[0], y: target.origin[1], z: target.origin[2] }
    const normal = { x: target.normal[0], y: target.normal[1], z: target.normal[2] }

    expect(matchPreset(presets, origin, normal)?.id).toBe(target.id)
  })

  it('任一分量不同则返回 null', () => {
    const presets = getSectionPresets('cube')
    const target = presets[0]
    const origin = { x: target.origin[0], y: target.origin[1], z: target.origin[2] }
    const normal = { x: target.normal[0], y: target.normal[1], z: target.normal[2] + 0.05 }

    expect(matchPreset(presets, origin, normal)).toBeNull()
  })

  it('预设列表为空时返回 null', () => {
    expect(matchPreset([], { x: 0, y: 0, z: 0 }, { x: 1, y: 1, z: 1 })).toBeNull()
  })
})
