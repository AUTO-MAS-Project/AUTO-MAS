import { describe, expect, it } from 'vite-plus/test'
import type { OnlineAppearanceItem } from '@/types/appearance'
import {
  filterAndSortStoreItems,
  pickAutoFeaturedItem,
  shouldUseCompactBanner,
} from './storeFiltering'
import { evaluateUploadPrecheck } from './uploadPrecheck'

const makeItem = (overrides: Partial<OnlineAppearanceItem>): OnlineAppearanceItem => ({
  fileKey: 'item-a',
  categoryKey: 'theme',
  displayName: 'Theme A',
  description: '',
  ownerUsername: 'author',
  publishedVersionNo: 1,
  publishedAt: '2026-11-20T00:00:00Z',
  updatedAt: '2026-11-20T00:00:00Z',
  installed: null,
  hasCover: true,
  downloadCount: 10,
  ...overrides,
})

describe('uploadPrecheck', () => {
  it('带自定义菜单图标但缺少 menuIcons.default 时必须硬性阻止上传', () => {
    const result = evaluateUploadPrecheck({
      categoryKey: 'theme',
      fileSize: 4 * 1024 * 1024,
      precheck: {
        hasCustomMenuIcons: true,
        hasDefaultMenuIcon: false,
        menuIconCount: 10,
        hasBackground: true,
        hasCursors: false,
        hasMascot: false,
        previewDimensions: { width: 1600, height: 1000 },
      },
      coverMode: 'package',
      coverReady: true,
      inheritCoverState: 'none',
    })
    expect(result.hasBlockingError).toBe(true)
    const iconCheck = result.items.find(item => item.id === 'default-menu-icon')
    expect(iconCheck?.severity).toBe('error')
    expect(iconCheck?.blocking).toBe(true)
  })

  it('纯配色主题（无自定义菜单图标）且封面规范时全部通过', () => {
    const result = evaluateUploadPrecheck({
      categoryKey: 'theme',
      fileSize: 2 * 1024 * 1024,
      precheck: {
        hasCustomMenuIcons: false,
        hasDefaultMenuIcon: false,
        menuIconCount: 0,
        hasBackground: false,
        hasCursors: false,
        hasMascot: false,
        previewDimensions: { width: 1280, height: 800 },
      },
      coverMode: 'package',
      coverReady: true,
      inheritCoverState: 'none',
    })
    expect(result.hasBlockingError).toBe(false)
    expect(result.warningCount).toBe(0)
  })

  it('封面比例严重偏离 16:10 时给出告警但不硬性阻塞', () => {
    const result = evaluateUploadPrecheck({
      categoryKey: 'theme',
      fileSize: 3 * 1024 * 1024,
      precheck: {
        hasCustomMenuIcons: true,
        hasDefaultMenuIcon: true,
        menuIconCount: 12,
        hasBackground: true,
        hasCursors: true,
        hasMascot: false,
      },
      coverMode: 'custom',
      coverReady: true,
      inheritCoverState: 'none',
      customCoverDimensions: { width: 800, height: 1600 },
    })
    expect(result.hasBlockingError).toBe(false)
    expect(result.warningCount).toBe(1)
    expect(result.items.find(item => item.id === 'cover-aspect')?.severity).toBe('warning')
  })

  it('桌宠包超过 50 MB 上限时硬性阻止上传', () => {
    const result = evaluateUploadPrecheck({
      categoryKey: 'mascot',
      fileSize: 55 * 1024 * 1024,
      coverMode: 'package',
      coverReady: true,
      inheritCoverState: 'none',
    })
    expect(result.hasBlockingError).toBe(true)
    expect(result.items.find(item => item.id === 'archive-size')?.blocking).toBe(true)
  })
})

describe('storeFiltering', () => {
  it('自动精选排除已安装作品并优先选下载量最高者', () => {
    const items = [
      makeItem({
        fileKey: 'installed-hot',
        downloadCount: 2000,
        installed: { appearanceId: 'hot', versionNo: 1 },
      }),
      makeItem({ fileKey: 'uninstalled-top', downloadCount: 900 }),
      makeItem({ fileKey: 'uninstalled-low', downloadCount: 200 }),
    ]
    expect(pickAutoFeaturedItem(items)?.fileKey).toBe('uninstalled-top')
  })

  it('作品数少于 30 时启用紧凑横幅，达到阈值后放开', () => {
    expect(shouldUseCompactBanner(21)).toBe(true)
    expect(shouldUseCompactBanner(30)).toBe(false)
  })

  it('支持按热门排序与可更新过滤且不修改原数组顺序', () => {
    const original = [
      makeItem({ fileKey: 'a', downloadCount: 50 }),
      makeItem({
        fileKey: 'b',
        downloadCount: 500,
        publishedVersionNo: 2,
        installed: { appearanceId: 'b', versionNo: 1 },
      }),
    ]
    const popular = filterAndSortStoreItems(original, { filter: 'all', sort: 'popular' })
    expect(popular.map(i => i.fileKey)).toEqual(['b', 'a'])
    expect(original.map(i => i.fileKey)).toEqual(['a', 'b'])

    const outdated = filterAndSortStoreItems(original, { filter: 'outdated', sort: 'latest' })
    expect(outdated.map(i => i.fileKey)).toEqual(['b'])
  })
})
