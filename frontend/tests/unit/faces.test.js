// faces.js 单元测试：不碰 WebGL，只验证"6 片独立网格 + parent_id 父子嵌套 + 资源释放"这三件核心事。
import { describe, expect, it, vi } from 'vitest'
import * as THREE from 'three'
import { clearFaceMeshes, createFaceMeshes, foldFaces } from '../../src/three/faces.js'

/** 两片面片的最小数据：0 号是基准面，1 号是它的子面片 */
function buildFaces() {
  return [
    {
      face_index: 0,
      cell: [0, 0],
      color: '#ff6b6b',
      is_base: true,
      parent_id: null,
      fold_order: 0,
      target_pos: [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]]
    },
    {
      face_index: 1,
      cell: [1, 0],
      color: '#4dabf7',
      is_base: false,
      parent_id: 0,
      fold_order: 1,
      hinge_edge: [[1, 0, 0], [1, 1, 0]],
      rotate_axis: [0, 1, 0],
      rotate_angle: 90,
      // 绕铰链 (1,0,0)-(1,1,0)、轴 +y 转 90° 后应有的角点
      target_pos: [[1, 0, 0], [1, 0, -1], [1, 1, -1], [1, 1, 0]]
    }
  ]
}

describe('createFaceMeshes', () => {
  it('每片面片一个独立 Mesh，且共用同一份 PlaneGeometry', () => {
    const root = new THREE.Group()
    const entries = createFaceMeshes(root, buildFaces())

    expect(entries).toHaveLength(2)
    expect(entries.map(entry => entry.mesh.geometry.type)).toEqual(['PlaneGeometry', 'PlaneGeometry'])
    expect(entries[0].mesh.geometry).toBe(entries[1].mesh.geometry)
    // 格子中心 = (cell + 0.5) × 边长
    expect(entries[0].mesh.position.toArray()).toEqual([0.5, 0.5, 0])
    expect(entries[1].mesh.position.toArray()).toEqual([1.5, 0.5, 0])
  })

  it('按 parent_id 建父子 Group，初始进度为 0 时变换清零（平铺）', () => {
    const root = new THREE.Group()
    const entries = createFaceMeshes(root, buildFaces())

    expect(entries[0].group.parent).toBe(root)
    expect(entries[1].group.parent).toBe(entries[0].group)
    // 进度 0 时 h − R(0)·h = 0，四元数为单位四元数
    expect(entries[1].group.position.length()).toBeCloseTo(0)
    expect(entries[1].group.quaternion.angleTo(new THREE.Quaternion())).toBeCloseTo(0)
  })

  it('数据里父面片不存在时兜底挂到根组，而不是丢掉', () => {
    const root = new THREE.Group()
    const faces = buildFaces()
    faces[1].parent_id = 99

    const entries = createFaceMeshes(root, faces)

    expect(entries[1].group.parent).toBe(root)
  })
})

describe('foldFaces（减少动态效果）', () => {
  it('系统开启减少动态效果时不做补间，直接折到位并回调', () => {
    const root = new THREE.Group()
    const entries = createFaceMeshes(root, buildFaces())
    const original = window.matchMedia
    window.matchMedia = () => ({ matches: true })

    const onComplete = vi.fn()
    foldFaces(entries, { onComplete })

    window.matchMedia = original

    expect(onComplete).toHaveBeenCalledTimes(1)
    // 基准面不参与变换：进度被写成 1，但 Group 变换保持身份
    expect(entries[0].group.quaternion.angleTo(new THREE.Quaternion())).toBeCloseTo(0)
    expect(entries[0].group.position.length()).toBeCloseTo(0)
    expect(entries[1].state.v).toBe(1)
    // 折 90° 后四元数不再是单位四元数
    expect(entries[1].group.quaternion.angleTo(new THREE.Quaternion())).toBeCloseTo(Math.PI / 2)
  })
})

describe('clearFaceMeshes', () => {
  it('把面片从场景摘掉，且共用几何体只 dispose 一次', () => {
    const root = new THREE.Group()
    const entries = createFaceMeshes(root, buildFaces())
    const dispose = vi.spyOn(entries[0].mesh.geometry, 'dispose')

    clearFaceMeshes(entries)

    expect(root.children).toHaveLength(0)
    expect(entries[0].group.parent).toBeNull()
    expect(dispose).toHaveBeenCalledTimes(1)
  })

  it('空数组 / 非数组入参直接返回，不抛错', () => {
    expect(() => clearFaceMeshes([])).not.toThrow()
    expect(() => clearFaceMeshes(undefined)).not.toThrow()
  })
})
