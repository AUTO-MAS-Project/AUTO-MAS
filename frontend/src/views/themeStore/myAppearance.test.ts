import { describe, expect, it } from 'vitest'

import type { AppearanceUploadRecord, MyAppearanceItem } from '@/composables/useShareApi'
import {
  getCoverModes,
  getMyAppearanceState,
  isCoverReady,
  isInStore,
  pickUploadTarget,
  toStoreItem,
} from './myAppearance'

const mine = (overrides: Partial<MyAppearanceItem> = {}): MyAppearanceItem => ({
  fileId: 1,
  fileKey: 'sakura',
  displayName: '樱花',
  description: '',
  status: 'active',
  publishedVersionNo: 2,
  latestVersionNo: 2,
  latestReviewStatus: 'approved',
  latestReviewComment: '',
  latestHasCover: true,
  updatedAt: '2026-10-07T00:00:00Z',
  ...overrides,
})

const record = (appearanceId: string, fileId: number): AppearanceUploadRecord => ({
  appearanceId,
  fileId,
  fileKey: '',
  displayName: '',
  updatedAt: '',
})

describe('getMyAppearanceState', () => {
  it('shows the published version when it is the latest', () => {
    expect(getMyAppearanceState(mine())).toEqual({ kind: 'published', published: 2 })
  })

  it('shows both versions when a newer one is in review', () => {
    expect(
      getMyAppearanceState(mine({ latestVersionNo: 3, latestReviewStatus: 'pending' }))
    ).toEqual({ kind: 'publishedPending', published: 2, latest: 3 })
  })

  it('shows only the pending version when nothing is published yet', () => {
    expect(
      getMyAppearanceState(
        mine({ publishedVersionNo: null, latestVersionNo: 1, latestReviewStatus: 'pending' })
      )
    ).toEqual({ kind: 'pending', latest: 1 })
  })

  it('shows a rejected latest version with its reason, published or not', () => {
    expect(
      getMyAppearanceState(
        mine({
          latestVersionNo: 3,
          latestReviewStatus: 'rejected',
          latestReviewComment: '  封面糊了 ',
        })
      )
    ).toEqual({ kind: 'rejected', published: 2, latest: 3, comment: '封面糊了' })
    expect(
      getMyAppearanceState(mine({ publishedVersionNo: null, latestReviewStatus: 'rejected' }))
    ).toEqual({ kind: 'rejected', published: null, latest: 2, comment: '' })
  })
})

describe('isInStore', () => {
  it('needs an active file with a published version', () => {
    expect(isInStore(mine())).toBe(true)
    expect(isInStore(mine({ publishedVersionNo: null }))).toBe(false)
    expect(isInStore(mine({ status: 'archived' }))).toBe(false)
    expect(isInStore(mine({ status: 'disabled' }))).toBe(false)
  })
})

describe('pickUploadTarget', () => {
  const list = [mine({ fileId: 1 }), mine({ fileId: 2 })]

  it('keeps an externally chosen target', () => {
    expect(pickUploadTarget({ lockedFileId: 9, appearanceId: 'a', records: [], mine: list })).toBe(
      9
    )
  })

  it('uses the local record only when the file is still on the share site', () => {
    expect(
      pickUploadTarget({
        lockedFileId: null,
        appearanceId: 'a',
        records: [record('a', 2)],
        mine: list,
      })
    ).toBe(2)
    expect(
      pickUploadTarget({
        lockedFileId: null,
        appearanceId: 'a',
        records: [record('a', 5)],
        mine: list,
      })
    ).toBeNull()
  })

  it('creates a new theme without a package or a matching record', () => {
    expect(
      pickUploadTarget({ lockedFileId: null, appearanceId: null, records: [], mine: list })
    ).toBeNull()
    expect(
      pickUploadTarget({
        lockedFileId: null,
        appearanceId: 'b',
        records: [record('a', 1)],
        mine: list,
      })
    ).toBeNull()
  })
})

describe('cover modes', () => {
  it('defaults to keeping the current cover when updating a theme that has one', () => {
    expect(
      getCoverModes({ updating: true, targetHasCover: true, packageHasPreview: true })
    ).toEqual(['inherit', 'package', 'custom'])
  })

  it('offers only what exists', () => {
    expect(
      getCoverModes({ updating: true, targetHasCover: false, packageHasPreview: true })
    ).toEqual(['package', 'custom'])
    expect(
      getCoverModes({ updating: true, targetHasCover: false, packageHasPreview: false })
    ).toEqual(['custom'])
  })

  it('never inherits when creating a new theme', () => {
    expect(
      getCoverModes({ updating: false, targetHasCover: true, packageHasPreview: true })
    ).toEqual(['package', 'custom'])
    expect(
      getCoverModes({ updating: false, targetHasCover: true, packageHasPreview: false })
    ).toEqual(['custom'])
  })

  it('needs a picked image for a custom cover and an available mode', () => {
    expect(isCoverReady('custom', ['custom'], false)).toBe(false)
    expect(isCoverReady('custom', ['custom'], true)).toBe(true)
    expect(isCoverReady('inherit', ['inherit', 'custom'], false)).toBe(true)
    expect(isCoverReady('inherit', ['package', 'custom'], false)).toBe(false)
    expect(isCoverReady('package', ['package', 'custom'], false)).toBe(true)
  })
})

describe('toStoreItem', () => {
  it('seeds the store detail from my own item', () => {
    expect(toStoreItem(mine({ description: '粉' }), 'alice')).toEqual({
      fileKey: 'sakura',
      displayName: '樱花',
      description: '粉',
      ownerUsername: 'alice',
      publishedVersionNo: 2,
      publishedAt: '',
      updatedAt: '2026-10-07T00:00:00Z',
      installed: null,
      hasCover: false,
    })
  })
})
