import { onScopeDispose, ref, shallowRef } from 'vue'
import { OpenAPI, TriggerUiState, type ComponentHint, type FrontendSurfaceMount } from '@/api'
import type { SettingsValues } from '@/views/plugins/settings/usePluginSettingsDraft'

export interface PluginUiTarget {
  kind: 'script' | 'setup' | 'user' | 'plan'
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
export interface PluginUiEditor {
  locale: string
  locked: boolean
  busy: boolean
  groups: { name: string; hints: ComponentHint[] }[]
  values: SettingsValues
  save: (changes: PluginUiChange[], commit: boolean) => Promise<boolean>
  runAction: (
    group: string,
    hint: ComponentHint,
    value: unknown,
    canRun: () => boolean
  ) => Promise<'success' | 'cancelled' | 'error'>
  notify: (severity: PluginUiSeverity, message: string) => void
}

const source = 'auto-mas-wheel'
const targetKeys = ['kind', 'scriptId', 'userId', 'planId', 'configUid'] as const
const isRecord = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === 'object' && Object.getPrototypeOf(value) === Object.prototype
const matchesTarget = (value: unknown, target: PluginUiTarget) =>
  isRecord(value) &&
  Object.keys(value).length === targetKeys.length &&
  targetKeys.every(
    key => Object.prototype.hasOwnProperty.call(value, key) && value[key] === target[key]
  )

function isConfigValue(value: unknown, depth = 0): boolean {
  if (value === null || typeof value === 'boolean' || typeof value === 'string') return true
  if (typeof value === 'number') return Number.isFinite(value)
  // 拒绝循环对象和非 JSON 值，避免污染宿主的配置草稿。
  if (depth >= 32) return false
  if (Array.isArray(value)) return value.every(item => isConfigValue(item, depth + 1))
  return isRecord(value) && Object.values(value).every(item => isConfigValue(item, depth + 1))
}

const visible = (hint: ComponentHint) => hint.field && !hint.secret && !hint.masked
const pathSegment = (value: string) =>
  encodeURIComponent(value).replace(
    /[!'()*]/g,
    char => '%' + char.charCodeAt(0).toString(16).toUpperCase()
  )

export function usePluginUiBridge(
  frame: () => HTMLIFrameElement | null,
  editor: () => PluginUiEditor
) {
  const iframeUrl = ref('')
  const frameHeight = ref(320)
  const status = shallowRef<'loading' | 'ready' | 'error'>('loading')
  let revoke: (() => void) | undefined

  function stop() {
    revoke?.()
    revoke = undefined
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
    const envelope = { v: 1, mountToken, pluginName, target }
    const valid = (data: unknown): data is Record<string, unknown> =>
      isRecord(data) &&
      data.source === source &&
      data.v === envelope.v &&
      data.mountToken === mountToken &&
      data.pluginName === pluginName &&
      matchesTarget(data.target, target)

    let port: MessagePort | undefined
    let active = true
    const seen = new Set<string | number>()

    function hintFor(group: string, field: string) {
      return editor()
        .groups.find(item => item.name === group)
        ?.hints.find(hint => hint.field === field && visible(hint))
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
      const reply = (result: unknown) => {
        if (active) port?.postMessage({ requestId, result })
      }
      const reject = (error: string) => {
        if (active) port?.postMessage({ requestId, error })
      }
      const current = editor()

      if (action === 'getContext' || action === 'readConfig') {
        const config = Object.fromEntries(
          current.groups.map(({ name, hints }) => [
            name,
            Object.fromEntries(
              hints.flatMap(hint => {
                const field = hint.field
                const fields = current.values[name]
                return field &&
                  visible(hint) &&
                  hint.state === undefined &&
                  fields &&
                  Object.prototype.hasOwnProperty.call(fields, field)
                  ? [[field, fields[field]]]
                  : []
              })
            ),
          ])
        )
        reply({
          target,
          surface: target.kind,
          locale: current.locale,
          locked: current.locked,
          config: JSON.parse(JSON.stringify(config)),
        })
        return
      }

      if (!isRecord(params)) return reject('invalid_params')
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
            const hint = hintFor(change.group, change.field)
            return (
              hint?.editable === true && hint.state === undefined && isConfigValue(change.value)
            )
          })
        )
          return reject('invalid_changes')
        if (await current.save(changes, phase === 'commit')) reply(true)
        else reject('save_failed')
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
