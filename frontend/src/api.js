/**
 * api.js —— 空间几何后端接口封装
 *
 * 生产环境：前后端同源部署在 Vercel，请求用相对路径 /api/*（零 CORS）
 * 开发环境：Vite dev server 通过 vite.config.js 的 proxy 把 /api/* 转发到 localhost:8000
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
// 一、基础配置：统一用相对路径，让 Vite proxy（开发）或同源（生产）来路由
// ---------------------------------------------------------------------------

/**
 * 生产部署时前后端同源，VITE_API_BASE_URL 留空即可。
 * 如果以后后端独立部署（Render/Railway 等），把环境变量改成那个公网域名。
 */
export const BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

/** 请求超时（毫秒）。几何计算很快，10 秒还没回来通常是后端没启动 */
const TIMEOUT = 10000

/** 调试开关：只在开发模式打印请求/响应，生产构建自动关闭 */
const DEBUG = Boolean(import.meta.env.DEV)

/** 统一的 axios 实例 */
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

function logRequest(config) {
  if (!DEBUG) return
  const method = (config.method || 'get').toUpperCase()
  const url = config.url
  const payload = config.data ? safeParse(config.data) : config.params
  console.log(`%c[API →] ${method} ${url}`, 'color:#1e88e5;font-weight:bold', payload ?? '')
}

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
        const field = Array.isArray(item.loc) ? item.loc.slice(1).join('.') : ''
        return field ? `${field}: ${item.msg}` : item.msg
      })
      .join('；')
  }
  return ''
}

function normalizeError(error) {
  let message = '请求失败，请稍后重试'

  if (error.code === 'ECONNABORTED' || /timeout/i.test(error.message || '')) {
    message = `请求超时（${TIMEOUT / 1000} 秒），请确认后端已启动`
  } else if (error.response) {
    const status = error.response.status
    message = formatErrorBody(error.response.data) || `请求失败（HTTP ${status}）`
  } else if (error.request) {
    message = '无法连接后端，请确认服务已启动（或检查开发代理配置）'
  } else {
    message = error.message || message
  }

  const friendly = new Error(message)
  friendly.cause = error
  friendly.originalError = error
  return friendly
}

// ---------------------------------------------------------------------------
// 四、拦截器
// ---------------------------------------------------------------------------

http.interceptors.request.use(
  config => {
    config.__startTime = Date.now()
    logRequest(config)
    return config
  },
  error => {
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
    logError(error)
    return Promise.reject(normalizeError(error))
  }
)

// ---------------------------------------------------------------------------
// 五、剥掉后端统一外壳 { code, message, data, request_id }
// ---------------------------------------------------------------------------

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

export async function getUnfoldData(unfoldType) {
  const response = await http.post('/api/hexahedron/get_data', { unfold_type: unfoldType })
  return unwrap(response.data)
}

export async function cutSection({ shape, planeOrigin, planeNormal, dims }) {
  const payload = {
    shape,
    plane_origin: planeOrigin,
    plane_normal: planeNormal
  }
  if (dims) payload.dims = dims

  const response = await http.post('/api/section/cut', payload)
  return unwrap(response.data)
}

export async function getShapeList() {
  const response = await http.get('/api/shape/list')
  return unwrap(response.data)
}

export default http
