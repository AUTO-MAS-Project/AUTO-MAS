import { translate as t } from '@/i18n'
import type { OnlineAppearanceErrorCode } from '@/types/appearance'
import type { AppearanceCategory, ResourcePackageFailureCode } from '@/types/mascotPack'

const ERROR_KEYS: Record<OnlineAppearanceErrorCode | ResourcePackageFailureCode, string> = {
  NETWORK: 'core.themeStore.error.network',
  NOT_FOUND: 'core.themeStore.error.notFound',
  BAD_RESPONSE: 'core.themeStore.error.badResponse',
  TOO_LARGE: 'core.themeStore.error.tooLarge',
  CHECKSUM_MISMATCH: 'core.setting.basic.resourcePackageChecksum',
  NO_SPACE: 'core.setting.basic.resourcePackageNoSpace',
  EXTRACTION_LIMIT: 'core.setting.basic.resourcePackageLimit',
  PROCESS_FAILED: 'core.setting.basic.resourcePackageProcessFailed',
  INVALID_MANIFEST: 'core.setting.basic.resourcePackageManifestInvalid',
  PACKAGE_CHANGED: 'core.setting.basic.resourcePackageChanged',
  EXPIRED: 'core.themeStore.error.expired',
  UNSUPPORTED: 'core.themeStore.error.unsupported',
}

/** 下载和桌宠包错误使用本地文案；旧主题包校验保留具体诊断。 */
export function describePackageError(
  result: { code?: string; error?: string } | undefined,
  fallbackKey: string,
  category?: AppearanceCategory
): string {
  const code = result?.code
  if (code === 'INVALID_ANIMATION') return t('core.setting.basic.appearanceAnimationInvalid')
  if (code === 'INVALID_PACKAGE' && category === 'mascot')
    return t('core.setting.basic.mascotImportFailed')
  if (code && Object.prototype.hasOwnProperty.call(ERROR_KEYS, code)) {
    return t(ERROR_KEYS[code as keyof typeof ERROR_KEYS])
  }
  return result?.error || t(fallbackKey)
}
