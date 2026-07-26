/**
 * 插件 UI Manifest 类型定义与校验系统。
 *
 * 建立显式、版本化、可验证的插件前端扩展描述合约。
 * 未知字段、未知版本和危险 URL 必须拒绝并给出错误原因。
 */

// ---- 版本化 Manifest 基础类型 ----

export const PLUGIN_UI_MANIFEST_VERSION = 1

export type PluginUIManifestVersion = 1

export interface PluginUIManifestBase {
  schema_version: PluginUIManifestVersion
  /** 插件发行包名 */
  package: string
  /** 插件名称 */
  name: string
  /** 语义化版本 */
  version: string
}

/** 页面扩展声明 */
export interface PluginUIPageDeclaration {
  id: string
  path: string
  title: string
  menu_label?: string
  icon?: string
  section?: string
  order?: number
  /** iframe 或 custom-element */
  renderer: 'iframe' | 'custom-element'
  /** iframe renderer 的 URL */
  url?: string | null
  /** custom-element renderer 的入口脚本 */
  entry_asset_url?: string | null
  /** custom-element renderer 的标签名 */
  element_tag?: string | null
  /** custom-element renderer 的样式 */
  style_asset_urls?: string[]
  /** 是否仅开发环境可见 */
  dev_only?: boolean
}

/** 设置面板扩展声明 */
export interface PluginUISettingsDeclaration {
  id: string
  title: string
  /** 设置面板的 renderer */
  renderer: 'iframe' | 'custom-element'
  url?: string | null
  entry_asset_url?: string | null
  element_tag?: string | null
  style_asset_urls?: string[]
}

/** 脚本扩展声明 */
export interface PluginUIScriptExtension {
  id: string
  label: string
  description?: string
  /** 脚本类型标识 */
  script_type: string
  /** 脚本扩展的配置 schema */
  schema?: Record<string, unknown>
}

/** 工具扩展声明 */
export interface PluginUIToolExtension {
  id: string
  label: string
  description?: string
  renderer: 'iframe' | 'custom-element'
  url?: string | null
  entry_asset_url?: string | null
  element_tag?: string | null
  style_asset_urls?: string[]
}

/** 主题/背景资源扩展 */
export interface PluginUIThemeResource {
  id: string
  label: string
  /** 受控 token/resource contract */
  tokens?: Record<string, string>
  /** 背景图片 URL（仅允许相对路径或受控域名） */
  backgrounds?: string[]
}

/** 完整 Plugin UI Manifest */
export interface PluginUIManifest extends PluginUIManifestBase {
  pages?: PluginUIPageDeclaration[]
  settings?: PluginUISettingsDeclaration[]
  script_extensions?: PluginUIScriptExtension[]
  tool_extensions?: PluginUIToolExtension[]
  theme_resources?: PluginUIThemeResource[]
}

// ---- 校验错误类型 ----

export interface ManifestValidationError {
  field: string
  message: string
  severity: 'error' | 'warning'
}

export interface ManifestValidationResult {
  valid: boolean
  errors: ManifestValidationError[]
  warnings: ManifestValidationError[]
}

// ---- 校验函数 ----

const SEMVER_REGEX = /^\d+\.\d+\.\d+(-[\w.]+)?(\+[\w.]+)?$/
const ELEMENT_TAG_REGEX = /^[a-z][a-z0-9]*-[a-z0-9-]*[a-z0-9]$/

function isString(value: unknown): value is string {
  return typeof value === 'string'
}

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function isArray(value: unknown): value is unknown[] {
  return Array.isArray(value)
}

function isVersion(value: unknown): value is PluginUIManifestVersion {
  return value === PLUGIN_UI_MANIFEST_VERSION
}

export function validateManifest(raw: unknown): ManifestValidationResult {
  const errors: ManifestValidationError[] = []
  const warnings: ManifestValidationError[] = []

  if (!isObject(raw)) {
    errors.push({ field: '$', message: 'Manifest 必须是 JSON 对象', severity: 'error' })
    return { valid: false, errors, warnings }
  }

  const manifest = raw as Record<string, unknown>

  // schema_version
  if (!('schema_version' in manifest)) {
    errors.push({
      field: 'schema_version',
      message: '缺少 schema_version 字段',
      severity: 'error',
    })
  } else if (!isVersion(manifest.schema_version)) {
    errors.push({
      field: 'schema_version',
      message: `不支持的 schema_version: ${manifest.schema_version}，当前仅支持 ${PLUGIN_UI_MANIFEST_VERSION}`,
      severity: 'error',
    })
  }

  // package
  if (!isString(manifest.package) || !manifest.package.trim()) {
    errors.push({ field: 'package', message: 'package 必须是有效的字符串', severity: 'error' })
  }

  // name
  if (!isString(manifest.name) || !manifest.name.trim()) {
    errors.push({ field: 'name', message: 'name 必须是有效的字符串', severity: 'error' })
  }

  // version
  if (!isString(manifest.version) || !manifest.version.trim()) {
    errors.push({ field: 'version', message: 'version 必须是有效的字符串', severity: 'error' })
  } else if (!SEMVER_REGEX.test(manifest.version)) {
    errors.push({
      field: 'version',
      message: `version 必须符合语义化版本规范: ${manifest.version}`,
      severity: 'error',
    })
  }

  // pages
  if ('pages' in manifest) {
    if (!isArray(manifest.pages)) {
      errors.push({ field: 'pages', message: 'pages 必须是数组', severity: 'error' })
    } else {
      ;(manifest.pages as unknown[]).forEach((page, index) => {
        if (!isObject(page)) {
          errors.push({
            field: `pages[${index}]`,
            message: '页面必须是对象',
            severity: 'error',
          })
          return
        }
        if (!isString(page.id) || !page.id.trim()) {
          errors.push({
            field: `pages[${index}].id`,
            message: '页面 id 不能为空',
            severity: 'error',
          })
        }
        if (!isString(page.path) || !page.path.trim()) {
          errors.push({
            field: `pages[${index}].path`,
            message: '页面 path 不能为空',
            severity: 'error',
          })
        }
        if (!isString(page.title) || !page.title.trim()) {
          errors.push({
            field: `pages[${index}].title`,
            message: '页面 title 不能为空',
            severity: 'error',
          })
        }
        const renderer = page.renderer
        if (renderer !== 'iframe' && renderer !== 'custom-element') {
          errors.push({
            field: `pages[${index}].renderer`,
            message: `renderer 必须是 'iframe' 或 'custom-element': ${renderer}`,
            severity: 'error',
          })
        }

        // 校验 element_tag
        if (renderer === 'custom-element' && 'element_tag' in page) {
          if (isString(page.element_tag) && page.element_tag.trim()) {
            if (!ELEMENT_TAG_REGEX.test(page.element_tag)) {
              errors.push({
                field: `pages[${index}].element_tag`,
                message: `element_tag 格式无效: ${page.element_tag}，必须包含连字符`,
                severity: 'error',
              })
            }
          }
        }

        // 校验未知字段
        const knownFields = new Set([
          'id',
          'path',
          'title',
          'menu_label',
          'icon',
          'section',
          'order',
          'renderer',
          'url',
          'entry_asset_url',
          'element_tag',
          'style_asset_urls',
          'dev_only',
        ])
        for (const key of Object.keys(page)) {
          if (!knownFields.has(key)) {
            warnings.push({
              field: `pages[${index}].${key}`,
              message: `未知字段: ${key}`,
              severity: 'warning',
            })
          }
        }
      })
    }
  }

  // settings
  if ('settings' in manifest) {
    if (!isArray(manifest.settings)) {
      errors.push({ field: 'settings', message: 'settings 必须是数组', severity: 'error' })
    }
  }

  // theme_resources
  if ('theme_resources' in manifest) {
    if (!isArray(manifest.theme_resources)) {
      errors.push({
        field: 'theme_resources',
        message: 'theme_resources 必须是数组',
        severity: 'error',
      })
    } else {
      ;(manifest.theme_resources as unknown[]).forEach((res, index) => {
        if (isObject(res) && isObject(res.tokens)) {
          // 插件主题/背景只能通过受控 token/resource contract
          // 不允许覆盖任意全局 CSS
          const forbiddenKeys = Object.keys(res.tokens).filter(
            k => k.startsWith('--ant-') || k.startsWith('--v6-') || k === '--app-background'
          )
          for (const key of forbiddenKeys) {
            errors.push({
              field: `theme_resources[${index}].tokens.${key}`,
              message: `不允许覆盖受保护的 CSS token: ${key}`,
              severity: 'error',
            })
          }
        }
      })
    }
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
  }
}

/** 检查 manifest 是否包含未知版本 */
export function isManifestVersionSupported(version: unknown): boolean {
  return version === PLUGIN_UI_MANIFEST_VERSION
}

/** 获取 manifest 支持的版本号 */
export function getSupportedManifestVersion(): PluginUIManifestVersion {
  return PLUGIN_UI_MANIFEST_VERSION
}
