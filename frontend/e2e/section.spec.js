import { expect, test } from '@playwright/test'

// 首屏会请求后端清单，loading 期间所有按钮都是 disabled：先等它结束再操作
async function gotoApp(page) {
  await page.goto('/')
  await expect(page.getByRole('button', { name: '加载展开' })).toBeEnabled()
}

// 「加载展开」→「折叠」→ 等折叠动画（含错峰，约 1.5s）走完，按钮文字变成「已折叠」
async function foldToCube(page) {
  await page.getByRole('button', { name: '加载展开' }).click()

  const foldButton = page.getByRole('button', { name: '折叠', exact: true })
  await expect(foldButton).toBeEnabled()
  await foldButton.click()

  await expect(page.getByRole('button', { name: '已折叠', exact: true })).toBeVisible()
}

test('页面加载后显示「① 六面体」与「② 截面切割」两张卡片', async ({ page }) => {
  await gotoApp(page)

  await expect(page.getByText('① 六面体')).toBeVisible()
  await expect(page.getByText('② 截面切割')).toBeVisible()
})

test('未折叠时「生成截面」禁用，并提示需要先加载展开再折叠', async ({ page }) => {
  await gotoApp(page)

  await expect(page.getByRole('button', { name: '生成截面' })).toBeDisabled()

  const hint = page.getByText(/请先在①中/)
  await expect(hint).toBeVisible()
  await expect(hint).toContainText('加载展开')
  await expect(hint).toContainText('折叠')
  await expect(hint).toContainText('成正方体')
})

test('点「加载展开」再点「折叠」后，按钮文字变成「已折叠」', async ({ page }) => {
  await gotoApp(page)
  await foldToCube(page)

  await expect(page.getByRole('button', { name: '已折叠', exact: true })).toBeVisible()
})

test('折叠后点「正六边形」，状态区域给出 6 边形与面积', async ({ page }) => {
  await gotoApp(page)
  await foldToCube(page)

  await page.getByRole('button', { name: '正六边形', exact: true }).click()

  const sectionStatus = page.getByRole('status').filter({ hasText: /边形/ })
  await expect(sectionStatus).toContainText('6 边形')
  await expect(sectionStatus).toContainText('面积')
})

test('切换几何体到「长方体」后，画布徽标显示参考线框 2 × 1.5 × 1', async ({ page }) => {
  await gotoApp(page)

  await page.getByLabel('几何体').selectOption({ label: '长方体' })

  await expect(page.getByText(/参考线框 2 × 1\.5 × 1/)).toBeVisible()
})

test('长方体不需要折叠，直接可以用预设切截面', async ({ page }) => {
  await gotoApp(page)
  await page.getByLabel('几何体').selectOption({ label: '长方体' })

  // 长方体本身就是一个现成实体，①的加载/折叠按钮被禁用，但②仍可直接切割
  await expect(page.getByRole('button', { name: '生成截面' })).toBeEnabled()
  await expect(page.getByRole('button', { name: '加载展开' })).toBeDisabled()

  await page.getByRole('button', { name: '矩形（纵切）', exact: true }).click()
  const sectionStatus = page.getByRole('status').filter({ hasText: /边形/ })
  await expect(sectionStatus).toContainText('4 边形')
})

test('未生成截面时预设不高亮，生成后命中项才高亮', async ({ page }) => {
  await gotoApp(page)
  await foldToCube(page)

  const hexagon = page.getByRole('button', { name: '正六边形', exact: true })
  await expect(hexagon).not.toHaveClass(/btn-danger/)
  await expect(page.getByText('未生成')).toBeVisible()

  await hexagon.click()
  await expect(hexagon).toHaveClass(/btn-danger/)
})

test('加载展开后自动回到立体视角（自适应取景）', async ({ page }) => {
  await gotoApp(page)

  await page.getByRole('button', { name: '加载展开' }).click()
  await expect(page.getByRole('button', { name: '立体视角' })).toHaveClass(/btn-primary/)
})
