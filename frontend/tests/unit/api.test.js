// api.js 单元测试：验证后端统一信封 { code, message, data, request_id } 的解包与错误解析。
// axios 全部用假实现替换，不产生任何真实网络请求。
import { beforeEach, describe, expect, it, vi } from 'vitest'

const axiosMock = vi.hoisted(() => {
  // 直接保存拦截器回调：不依赖 mock.calls（测试框架可能在不同版本间清理调用记录）
  const handlers = { request: {}, response: {} }
  const instance = {
    post: vi.fn(),
    get: vi.fn(),
    interceptors: {
      request: {
        use(onFulfilled, onRejected) {
          handlers.request.onFulfilled = onFulfilled
          handlers.request.onRejected = onRejected
        }
      },
      response: {
        use(onFulfilled, onRejected) {
          handlers.response.onFulfilled = onFulfilled
          handlers.response.onRejected = onRejected
        }
      }
    }
  }
  return { instance, handlers, create: vi.fn(() => instance) }
})

vi.mock('axios', () => ({ default: { create: axiosMock.create } }))

const { cutSection, getShapeList, getUnfoldData } = await import('../../src/api.js')

const { post, get } = axiosMock.instance

beforeEach(() => {
  post.mockReset()
  get.mockReset()
})

describe('getUnfoldData', () => {
  it('成功时剥掉信封，只返回 data', async () => {
    post.mockResolvedValue({
      data: { code: 0, message: 'ok', data: { net_id: '141-1', faces: [] }, request_id: 'req-1' }
    })

    await expect(getUnfoldData('141-1')).resolves.toEqual({ net_id: '141-1', faces: [] })
    expect(post).toHaveBeenCalledWith('/api/hexahedron/get_data', { unfold_type: '141-1' })
  })

  it('HTTP 200 但 code != 0 时抛错，并带上 message 与 request_id', async () => {
    post.mockResolvedValue({
      data: { code: 1001, message: '展开图类型不存在', data: null, request_id: 'req-9' }
    })

    await expect(getUnfoldData('bad')).rejects.toThrow('展开图类型不存在（request_id: req-9）')
  })
})

describe('cutSection', () => {
  it('把驼峰入参映射成后端的下划线字段（正方体不传 dims）', async () => {
    post.mockResolvedValue({ data: { code: 0, data: { status: 'polygon', points: [[0, 0, 0], [1, 0, 0], [0, 1, 0]] } } })

    const result = await cutSection({
      shape: 'cube',
      planeOrigin: [0.5, 0.5, 0.5],
      planeNormal: [1, 1, 1]
    })

    expect(post).toHaveBeenCalledWith('/api/section/cut', {
      shape: 'cube',
      plane_origin: [0.5, 0.5, 0.5],
      plane_normal: [1, 1, 1]
    })
    expect(result.status).toBe('polygon')
  })

  it('长方体时才把 dims 一起发给后端', async () => {
    post.mockResolvedValue({ data: { code: 0, data: { status: 'none', points: [] } } })

    await cutSection({
      shape: 'cuboid',
      planeOrigin: [1, 0.75, 0.5],
      planeNormal: [0, 0, 1],
      dims: [2, 1.5, 1]
    })

    expect(post.mock.calls[0][1]).toEqual({
      shape: 'cuboid',
      plane_origin: [1, 0.75, 0.5],
      plane_normal: [0, 0, 1],
      dims: [2, 1.5, 1]
    })
  })
})

describe('getShapeList', () => {
  it('没有信封时原样返回', async () => {
    get.mockResolvedValue({ data: { shapes: [], unfold_types: { total_unfold_types: 11 } } })

    await expect(getShapeList()).resolves.toEqual({ shapes: [], unfold_types: { total_unfold_types: 11 } })
    expect(get).toHaveBeenCalledWith('/api/shape/list')
  })
})

describe('响应拦截器的错误归一化', () => {
  // 拦截器用 Promise.reject 把错误交给调用方，所以用 rejects 断言
  it('超时转成带后端地址的中文提示', async () => {
    const error = { code: 'ECONNABORTED', message: 'timeout of 10000ms exceeded' }

    await expect(axiosMock.handlers.response.onRejected(error)).rejects.toThrow(/请求超时（10 秒）/)
  })

  it('4xx/5xx 优先读信封里的 message 与 request_id', async () => {
    const error = {
      response: { status: 422, data: { code: 422, message: '法向量不能为零向量', request_id: 'req-422' } }
    }

    await expect(axiosMock.handlers.response.onRejected(error))
      .rejects.toThrow('法向量不能为零向量（request_id: req-422）')
  })
})
