// Vitest 全局初始化（所有测试文件执行前运行一次）
//
// 这里只做两件事：
//   1. 补一个最小可用的 window.matchMedia —— jsdom 没有实现它，
//      而 src/three/faces.js 会用它判断系统是否开启了"减少动态效果"；
//   2. 每个用例结束后清空 DOM，避免测试之间互相污染。

if (typeof window !== 'undefined' && typeof window.matchMedia !== 'function') {
  window.matchMedia = query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener() {},
    removeListener() {},
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent: () => false
  })
}

if (typeof globalThis.afterEach === 'function') {
  globalThis.afterEach(() => {
    document.body.innerHTML = ''
    window.localStorage.clear()
  })
}
