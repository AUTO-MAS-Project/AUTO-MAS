import { onScopeDispose, ref, shallowRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useConfirm } from './useConfirm'
import { createDeclarativeI18n } from '@/components/declarative/declarativeI18n'
import { i18nRevision } from '@/i18n'
import { isBrowserDevelopment } from '@/utils/environment'
import { OpenAPI, TriggerUiState, type ComponentHint, type FrontendSurfaceMount } from '@/api'
import type { SettingsValues } from '@/views/plugins/settings/usePluginSettingsDraft'
import type { PluginPanelTheme } from './pluginPanelTheme'

export interface PluginUiTarget {
  kind: 'script' | 'setup' | 'user' | 'plan' | 'settings' | 'notification'
  pluginId?: string | null
  channelId?: string | null
  scriptId: string | null
  userId: string | null
  planId: string | null
  configUid: string
}

export interface PluginUiChange {
  group: string
  field: string
  value: unknown
}

const severities = ['info', 'success', 'warning', 'error'] as const
export type PluginUiSeverity = (typeof severities)[number]
export type WheelMount = FrontendSurfaceMount & { entry: string }
export type PluginUiSaveResult =
  | { ok: true }
  | { ok: false; code: string; message: string; fieldErrors?: Record<string, string> }

export interface PluginUiEditor {
  locale: string
  locked: boolean
  busy: boolean
  groups: { name: string; hints: ComponentHint[] }[]
  panelData?: Record<string, unknown> | null
  values: SettingsValues
  fieldErrors?: Record<string, string>
  configRevision: number
  save: (changes: PluginUiChange[], commit: boolean) => Promise<PluginUiSaveResult>
  runAction: (
    group: string,
    hint: ComponentHint,
    value: unknown,
    canRun: () => boolean
  ) => Promise<'success' | 'cancelled' | 'error'>
  notify: (severity: PluginUiSeverity, message: string) => void
}

const source = 'auto-mas-wheel'
const shortText = (v: unknown, max: number): v is string => typeof v === 'string' && v.length <= max
const optionalText = (v: unknown, max: number): v is string | undefined =>
  v === undefined || shortText(v, max)
const isRecord = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === 'object' && Object.getPrototypeOf(value) === Object.prototype

type TranslationKey = string | { key: string; params?: Record<string, unknown> }

function isTranslationKey(value: unknown): value is TranslationKey {
  return (
    shortText(value, 256) ||
    (isRecord(value) &&
      shortText(value.key, 256) &&
      (value.params === undefined || isRecord(value.params)))
  )
}

function validFilters(value: unknown): value is Array<{ name: string; extensions: string[] }> {
  return (
    Array.isArray(value) &&
    value.length <= 32 &&
    value.every(
      filter =>
        isRecord(filter) &&
        Object.keys(filter).length === 2 &&
        shortText(filter.name, 100) &&
        filter.name.trim() &&
        Array.isArray(filter.extensions) &&
        filter.extensions.length > 0 &&
        filter.extensions.length <= 32 &&
        filter.extensions.every(
          extension => shortText(extension, 32) && /^(?:[a-z0-9][a-z0-9._+-]*|\*)$/i.test(extension)
        )
    )
  )
}

const matchesTarget = (value: unknown, target: PluginUiTarget) =>
  isRecord(value) &&
  Object.keys(value).length === Object.keys(target).length &&
  Object.entries(target).every(
    ([key, expected]) => Object.prototype.hasOwnProperty.call(value, key) && value[key] === expected
  )

function isConfigValue(value: unknown, depth = 0): boolean {
  if (value === null || typeof value === 'boolean' || typeof value === 'string') return true
  if (typeof value === 'number') return Number.isFinite(value)
  // 拒绝循环对象和非 JSON 值，避免污染宿主的配置草稿。
  if (depth >= 32) return false
  if (Array.isArray(value)) return value.every(item => isConfigValue(item, depth + 1))
  return isRecord(value) && Object.values(value).every(item => isConfigValue(item, depth + 1))
}

function panelConfig({ groups, values, panelData }: PluginUiEditor) {
  const configuredSecrets: string[] = []
  const config = Object.fromEntries(
    groups.map(({ name, hints }) => [
      name,
      Object.fromEntries(
        hints.flatMap(({ field, secret, masked, state }) => {
          if (!field) return []
          const fields = values[name]
          if (secret || masked) {
            if (masked || fields?.[field]) configuredSecrets.push(`${name}.${field}`)
            return []
          }
          return state === undefined &&
            fields &&
            Object.prototype.hasOwnProperty.call(fields, field)
            ? [[field, fields[field]]]
            : []
        })
      ),
    ])
  )
  return {
    config: JSON.parse(JSON.stringify(config)) as SettingsValues,
    configuredSecrets,
    ...(panelData && {
      panelData: JSON.parse(JSON.stringify(panelData)) as Record<string, unknown>,
    }),
  }
}

const pathSegment = (value: string) =>
  encodeURIComponent(value).replace(
    /[!'()*]/g,
    char => '%' + char.charCodeAt(0).toString(16).toUpperCase()
  )

export function usePluginUiBridge(
  frame: () => HTMLIFrameElement | null,
  editor: () => PluginUiEditor,
  theme: () => PluginPanelTheme
) {
  const { confirm } = useConfirm()
  const { t, te } = useI18n()
  const iframeUrl = ref('')
  const frameHeight = ref(320)
  const status = shallowRef<'loading' | 'ready' | 'error'>('loading')
  let revoke: (() => void) | undefined
  let port: MessagePort | undefined

  function state({ locked, busy, locale, fieldErrors }: PluginUiEditor) {
    return {
      locked,
      busy,
      locale,
      i18nRevision: i18nRevision.value,
      theme: theme(),
      ...(fieldErrors && { fieldErrors: { ...fieldErrors } }),
    }
  }

  watch(
    [
      () => editor().locked,
      () => editor().busy,
      () => editor().locale,
      i18nRevision,
      theme,
      () => editor().fieldErrors,
    ],
    () => port?.postMessage({ event: 'stateChanged', payload: state(editor()) }),
    { deep: true }
  )
  watch(
    () => editor().configRevision,
    () => port?.postMessage({ event: 'configReloaded', payload: panelConfig(editor()) })
  )

  function stop() {
    revoke?.()
    revoke = undefined
    port = undefined
    iframeUrl.value = ''
  }

  function fail() {
    stop()
    status.value = 'error'
  }

  function start(mount: WheelMount, target: PluginUiTarget) {
    stop()
    status.value = 'loading'
    frameHeight.value = 320
    const mountToken = Array.from(crypto.getRandomValues(new Uint8Array(16)), byte =>
      byte.toString(16).padStart(2, '0')
    ).join('')
    const { pluginName, revision, entry } = mount
    const scope =
      target.kind === 'setup' ? 'script' : target.kind === 'notification' ? 'settings' : target.kind
    const envelope = { v: 1, mountToken, pluginName, target }
    const valid = (data: unknown): data is Record<string, unknown> =>
      isRecord(data) &&
      data.source === source &&
      data.v === envelope.v &&
      data.mountToken === mountToken &&
      data.pluginName === pluginName &&
      matchesTarget(data.target, target)

    let active = true
    const seen = new Set<string | number>()

    function hintFor(group: string, field: string, allowSecret = false) {
      return editor()
        .groups.find(item => item.name === group)
        ?.hints.find(
          hint =>
            hint.field && hint.field === field && !hint.masked && (allowSecret || !hint.secret)
        )
    }

    async function onRequest({ data }: MessageEvent<unknown>) {
      if (!active || !valid(data)) return
      const { requestId, action, params } = data
      if (
        !(
          typeof requestId === 'string' ||
          (typeof requestId === 'number' && Number.isSafeInteger(requestId))
        ) ||
        seen.has(requestId)
      )
        return
      seen.add(requestId)
      if (seen.size > 512) seen.delete(seen.values().next().value!)
      const reply = (result: unknown) => {
        if (active) port?.postMessage({ requestId, result })
      }
      const reject = (error: string) => {
        if (active) port?.postMessage({ requestId, error })
      }
      const current = editor()

      if (action === 'getContext' || action === 'readConfig') {
        reply({
          target,
          surface: target.kind,
          ...state(current),
          ...panelConfig(current),
        })
        return
      }

      if (!isRecord(params)) return reject('invalid_params')
      if (action === 'translate') {
        const { keys } = params
        if (!Array.isArray(keys) || keys.length > 512 || !keys.every(isTranslationKey))
          return reject('invalid_params')
        const { locale } = current
        const resolver = createDeclarativeI18n(t, te, locale, `plugins.${pluginName}.config`, scope)
        const messages = Object.fromEntries(
          keys.flatMap((item: TranslationKey) => {
            const { key, params } = typeof item === 'string' ? { key: item } : item
            const message = key.startsWith('panel.')
              ? resolver.panel(key, params)
              : resolver.config(key, params)
            return message === undefined ? [] : [[key, message]]
          })
        )
        reply({ locale, revision: i18nRevision.value, messages })
        return
      }
      const writable = () => active && !editor().locked
      if (action === 'saveConfig') {
        const { phase, changes } = params
        if (!writable() || current.busy) return reject('read_only')
        if (
          (phase !== 'draft' && phase !== 'commit') ||
          !Array.isArray(changes) ||
          !changes.every((change): change is PluginUiChange => {
            if (
              !isRecord(change) ||
              typeof change.group !== 'string' ||
              typeof change.field !== 'string'
            )
              return false
            const hint = hintFor(change.group, change.field, true)
            return (
              hint?.editable === true &&
              hint.state === undefined &&
              (hint.secret ? typeof change.value === 'string' : isConfigValue(change.value))
            )
          })
        )
          return reject('invalid_changes')
        reply(await current.save(changes, phase === 'commit'))
      } else if (action === 'runAction') {
        const { group, field, value } = params
        if (!writable() || current.busy) return reject('read_only')
        if (typeof group !== 'string' || typeof field !== 'string') return reject('invalid_action')
        const hint = hintFor(group, field)
        if (hint?.editable !== true || hint.state !== TriggerUiState.IDLE)
          return reject('invalid_action')
        const canRun = () => {
          const latest = hintFor(group, field)
          return writable() && latest?.editable === true && latest.state === TriggerUiState.IDLE
        }
        reply(await current.runAction(group, hint, value, canRun))
      } else if (action === 'confirm' || action === 'pickPath') {
        if (!writable() || current.busy) return reject('read_only')
        const { title } = params
        if (!optionalText(title, 100)) return reject('invalid_params')
        try {
          if (action === 'confirm') {
            const { message, confirmText, cancelText, danger } = params
            if (
              !shortText(message, 500) ||
              !message.trim() ||
              !optionalText(confirmText, 100) ||
              !optionalText(cancelText, 100) ||
              (danger !== undefined && typeof danger !== 'boolean')
            )
              return reject('invalid_params')
            const confirmed = await confirm({
              title: title ?? pluginName,
              description: message,
              ...(confirmText !== undefined && { okText: confirmText }),
              ...(cancelText !== undefined && { cancelText }),
              tone: danger ? 'danger' : 'info',
            })
            reply({ confirmed: writable() && confirmed })
          } else {
            const { mode, defaultPath, filters } = params
            if (
              (mode !== 'file' && mode !== 'folder') ||
              !optionalText(defaultPath, 32767) ||
              (filters !== undefined && !validFilters(filters))
            )
              return reject('invalid_params')
            const api = window.electronAPI
            if (isBrowserDevelopment() || !(mode === 'file' ? api?.selectFile : api?.selectFolder))
              return reply({ ok: false, code: 'unavailable' })
            const options = { title, defaultPath }
            const path =
              mode === 'file'
                ? (await api.selectFile(filters, options))[0]
                : await api.selectFolder(options)
            if (!writable()) return reject('read_only')
            reply({ cancelled: !path, path: path ?? null })
          }
        } catch {
          reject('dialog_failed')
        }
      } else if (action === 'notify') {
        const { severity, message } = params
        if (typeof message !== 'string' || !message.trim() || message.length > 500)
          return reject('invalid_message')
        const level = severities.find(item => item === severity)
        if (!level) return reject('invalid_severity')
        current.notify(level, message)
        reply(true)
      } else if (action === 'resize') {
        const { height } = params
        if (typeof height !== 'number' || !Number.isFinite(height)) return reject('invalid_height')
        frameHeight.value = Math.min(4000, Math.max(160, Math.round(height)))
        reply(frameHeight.value)
      } else {
        reject('unknown_action')
      }
    }

    function onReady(event: MessageEvent<unknown>) {
      const child = frame()?.contentWindow
      if (
        !child ||
        event.source !== child ||
        event.origin !== 'null' ||
        !valid(event.data) ||
        event.data.type !== 'ready' ||
        !event.ports[0]
      )
        return
      port = event.ports[0]
      port.addEventListener('message', onRequest)
      port.addEventListener('messageerror', fail)
      port.start()
      clearTimeout(timer)
      window.removeEventListener('message', onReady)
      port.postMessage({ event: 'stateChanged', payload: state(editor()) })
      status.value = 'ready'
    }

    window.addEventListener('message', onReady)
    const timer = setTimeout(fail, 10_000)
    revoke = () => {
      active = false
      clearTimeout(timer)
      window.removeEventListener('message', onReady)
      if (port) {
        port.removeEventListener('message', onRequest)
        port.removeEventListener('messageerror', fail)
        port.close()
      }
    }

    const hash = new URLSearchParams({ ...envelope, v: '1', target: JSON.stringify(target) })
    const path = [pluginName, 'ui', revision, ...entry.split('/')].map(pathSegment).join('/')
    iframeUrl.value = `${OpenAPI.BASE.replace(/\/$/, '')}/api/plugin/${path}#${hash}`
  }
  onScopeDispose(stop)
  return { iframeUrl, frameHeight, status, start, stop, fail }
}
