import type { ElectronAPI } from '../src/types/electron'
import { expect, test } from './fixtures'

test.describe('@resource-store', () => {
  test('resource details show the cover before downloading and allow installation', async ({
    app,
    page,
  }) => {
    await page.addInitScript(() => {
      let bridge: ElectronAPI | undefined
      let downloads = 0
      const item = {
        fileKey: 'example',
        displayName: 'Resource example',
        description: 'Resource details',
        ownerUsername: 'author',
        publishedVersionNo: 1,
        publishedAt: '',
        updatedAt: '',
        installed: null,
        hasCover: true,
      }
      Object.defineProperty(window, 'electronAPI', {
        configurable: true,
        get: () => bridge,
        set: (base: ElectronAPI) => {
          bridge = {
            ...base,
            listOnlineAppearances: async () => ({
              success: true,
              items: [item],
              pagination: { page: 1, pageSize: 12, total: 1, hasNext: false },
            }),
            getOnlineAppearance: async () => ({
              success: true,
              item,
              versions: [
                {
                  versionNo: 1,
                  fileSize: 100,
                  sha256: 'a'.repeat(64),
                  createdAt: '',
                  changeNote: '',
                  hasCover: true,
                },
              ],
            }),
            getOnlineAppearanceCover: async () => ({
              success: true,
              dataUrl:
                'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGD4DwABBAEAX+XDSwAAAABJRU5ErkJggg==',
            }),
            prepareOnlineAppearance: async () => {
              downloads++
              return { success: false, code: 'NETWORK' }
            },
          }
          Object.defineProperty(window, 'resourceDownloads', {
            configurable: true,
            get: () => downloads,
          })
        },
      })
    })
    await app.goto('/theme-store')
    await page.locator('.online-card').filter({ hasText: 'Resource example' }).click()
    await expect(page.locator('.online-description')).toHaveText('Resource details')
    await expect(page.locator('.online-preview-image')).toBeVisible()
    expect(await page.evaluate(() => Reflect.get(window, 'resourceDownloads'))).toBe(0)
    const install = page.locator('.online-actions .ant-btn-primary')
    await expect(install).toBeEnabled()
    await app.evidence('resource-detail-without-package-download')
    await install.click()
    await expect.poll(() => page.evaluate(() => Reflect.get(window, 'resourceDownloads'))).toBe(1)
    await expect(install).toBeEnabled()
  })
})
