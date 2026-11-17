/**
 * api.js —— 立体几何后端接口封装（axios 版）
 *
 * 作用：把"跟后端打交道"这件事集中到这一个文件里。
 *   1. 统一基础地址：http://127.0.0.1:8000
 *   2. 统一超时与请求头
 *   3. 统一错误捕获：网络不通 / 超时 / 400 / 422 都转成一句能看懂的中文
 *   4. 开发模式下自动打印请求体与返回体，方便在浏览器控制台调试
 *
 * 后端三个接口（FastAPI）
 *   GET  /api/shape/list            支持的几何体 + 11 种展开图清单
 *   POST /api/hexahedron/get_data   入参 { unfold_type }        → 6 个面片参数
 *   POST /api/section/cut           入参 { shape, plane_origin, plane_normal } → 截面多边形
 *
 * 后端统一返回外壳：{ code: 0, message: 'ok', data: {...}, request_id: '...' }
 * 下面的每个函数都会自动剥掉外壳，直接返回 data，调用处不用再掏一层。
 */

import axios from 'axios'

// ---------------------------------------------------------------------------
// 一、基础配置
// ---------------------------------------------------------------------------

/** 后端基础地址：改端口/换机器只改这一行（或改用环境变量 VITE_API_BASE_URL） */
export const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

/** 请求超时（毫秒）。几何计算很快，10 秒还没回来通常是后端没启动 */
const TIMEOUT = 10000

/** 调试开关：只在开发模式（npm run dev）打印请求/响应，生产构建自动关闭 */
const DEBUG = Boolean(import.meta.env.DEV)

/** 统一的 axios 实例：所有请求都走它，配置只写一次 */
const http = axios.create({
  baseURL: BASE_URL,
  timeout: TIMEOUT,
  headers: {
    'Content-Type': 'application/json'
  }
})

// ---------------------------------------------------------------------------
// 二、调试日志：请求前打印入参，响应后打印结果
// ---------------------------------------------------------------------------

/** 打印请求信息（方法、地址、请求体） */
function logRequest(config) {
  if (!DEBUG) return
  const method = (config.method || 'get').toUpperCase()
  const url = config.url
  const payload = config.data ? safeParse(config.data) : config.params
  console.log(`%c[API →] ${method} ${url}`, 'color:#1e88e5;font-weight:bold', payload ?? '')
}

/** 打印响应信息（状态码、耗时、返回体） */
function logResponse(response) {
  if (!DEBUG) return
  const { config, status, data } = response
  const cost = Date.now() - (config.__startTime || Date.now())
  console.log(
    `%c[API ←] ${status} ${(config.method || 'get').toUpperCase()} ${config.url} (${cost}ms)`,
    'color:#43a047;font-weight:bold',
    data
  )
}

/** 打印错误信息（含请求体，方便对照哪个参数把后端惹毛了） */
function logError(error) {
  if (!DEBUG) return
  const config = error.config || {}
  console.warn(
    `%c[API ✗] ${(config.method || 'get').toUpperCase()} ${config.url || '?'} 失败`,
    'color:#e53935;font-weight:bold',
    {
      请求参数: config.data ? safeParse(config.data) : config.params,
      错误详情: error.friendlyMessage || error.message,
      后端返回: error.response?.data
    }
  )
}

/** 请求体是 JSON 字符串，打印时转成对象看得更清楚（转不了就原样输出） */
function safeParse(text) {
  if (typeof text !== 'string') return text
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

// ---------------------------------------------------------------------------
// 三、统一异常处理：把 axios 的各种错误形态统一成一句中文
// ---------------------------------------------------------------------------

/**
 * 把后端错误响应转成一句可读文本。
 *
 * 后端现在统一返回信封 { code, message, data, request_id }，
 * 所以优先读 message，并把 request_id 一并带上（排查问题时拿它去找后端日志）。
 * 仍然兼容旧版 FastAPI 的 detail（400 是字符串，422 是数组）。
 */
function formatErrorBody(body) {
  if (!body) return ''
  if (typeof body === 'string') return body

  if (typeof body.message === 'string' && body.message) {
    return body.request_id ? `${body.message}（request_id: ${body.request_id}）` : body.message
  }

  const detail = body.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map(item => {
        // loc 形如 ['body', 'plane_normal']，去掉第一个 body 只留字段名
        const field = Array.isArray(item.loc) ? item.loc.slice(1).join('.') : ''
        return field ? `${field}: ${item.msg}` : item.msg
      })
      .join('；')
  }
  return ''
}

/**
 * 错误归一化：返回一个带 friendlyMessage 的 Error，抛给调用方。
 * 覆盖四种常见情况：超时、没连上后端、后端返回 4xx/5xx、其它未知错误。
 */
function normalizeError(error) {
  let message = '请求失败，请稍后重试'

  if (error.code === 'ECONNABORTED' || /timeout/i.test(error.message || '')) {
    // 超时：axios 用 ECONNABORTED 表示超时
    message = `请求超时（${TIMEOUT / 1000} 秒），请确认后端已启动：${BASE_URL}`
  } else if (error.response) {
    // 后端有响应，但状态码不是 2xx：新信封在 message 里，旧格式在 detail 里
    const status = error.response.status
    message = formatErrorBody(error.response.data) || `请求失败（HTTP ${status}）`
  } else if (error.request) {
    // 请求发出去了但没有任何响应：后端没启动 / 端口不对 / 被 CORS 拦下
    message = `无法连接后端 ${BASE_URL}，请先启动 FastAPI 服务（uvicorn main:app --port 8000）`
  } else {
    message = error.message || message
  }

  const friendly = new Error(message)
  friendly.cause = error
  friendly.originalError = error
  return friendly
}

// ---------------------------------------------------------------------------
// 四、拦截器：请求开始 / 响应回来 / 出错，三个时机各做一件事
// ---------------------------------------------------------------------------

http.interceptors.request.use(
  config => {
    config.__startTime = Date.now() // 记开始时间，用于算耗时
    logRequest(config)
    return config
  },
  error => {
    // 请求还没发出去就出错（比如参数序列化失败）
    logError(error)
    return Promise.reject(normalizeError(error))
  }
)

http.interceptors.response.use(
  response => {
    logResponse(response)
    return response
  },
  error => {
    // 所有失败（超时 / 网络 / 4xx / 5xx）都在这里统一转成中文 Error
    logError(error)
    return Promise.reject(normalizeError(error))
  }
)

// ---------------------------------------------------------------------------
// 五、工具：剥掉后端统一外壳 { code, message, data, request_id }
// ---------------------------------------------------------------------------

/**
 * 后端返回 { code: 0, message: 'ok', data: {...} }，
 * 调用方通常只关心 data，这里统一取出来；没有外壳就原样返回。
 * 若 HTTP 200 但 code != 0（理论上不会出现），也按错误处理，避免静默拿到空数据。
 */
function unwrap(body) {
  if (body && typeof body === 'object' && Object.prototype.hasOwnProperty.call(body, 'data')) {
    if (typeof body.code === 'number' && body.code !== 0) {
      const requestId = body.request_id ? `（request_id: ${body.request_id}）` : ''
      throw new Error(`${body.message || '接口返回错误'}${requestId}`)
    }
    return body.data
  }
  return body
}

// ---------------------------------------------------------------------------
// 六、三个对外接口
// ---------------------------------------------------------------------------

/**
 * 1. 取正方体展开图的 6 个面片参数
 *    POST /api/hexahedron/get_data
 *
 * @param {string} unfoldType 展开图类型：'141' / '141-3' / '231-2' / '222' / '33'
 * @returns {Promise<Object>} { net_id, label, faces: [6 个面片], fold_sequence, animation, ... }
 *   每个面片含：start_pos / target_pos / hinge_edge / rotate_axis / rotate_angle /
 *              parent_id / depth / fold_order / color_index / target_face
 */
export async function getUnfoldData(unfoldType) {
  const response = await http.post('/api/hexahedron/get_data', { unfold_type: unfoldType })
  return unwrap(response.data)
}

/**
 * 2. 平面切割求截面
 *    POST /api/section/cut
 *
 * @param {{shape:string, planeOrigin:number[], planeNormal:number[], dims?:number[]}} params
 *   shape        'cube' | 'cuboid'
 *   planeOrigin  切面原点 [x, y, z]
 *   planeNormal  切面法向量 [nx, ny, nz]（不必归一化，但不能是零向量）
 *   dims         长方体三边 [a, b, c]；正方体不传
 * @returns {Promise<Object>} { status: 'none'|'point'|'segment'|'polygon', points, message, area, ... }
 */
export async function cutSection({ shape, planeOrigin, planeNormal, dims }) {
  const payload = {
    shape,
    plane_origin: planeOrigin,
    plane_normal: planeNormal
  }
  // 只有长方体才需要尺寸；正方体传了必须三边相等，所以默认不传
  if (dims) payload.dims = dims

  const response = await http.post('/api/section/cut', payload)
  return unwrap(response.data)
}

/**
 * 3. 取支持的几何体列表 + 11 种展开图清单（页面初始化时用来填下拉框）
 *    GET /api/shape/list
 *
 * @returns {Promise<Object>} { shapes: [...], unfold_types: { total_unfold_types, groups: [...] } }
 */
export async function getShapeList() {
  const response = await http.get('/api/shape/list')
  return unwrap(response.data)
}

// 方便在控制台或别处直接拿到原始 axios 实例（需要自定义请求时用）
export default http