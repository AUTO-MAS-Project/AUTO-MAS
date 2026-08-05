import { ref } from 'vue'
import axios from 'axios'
import { OpenAPI } from '@/api/core/OpenAPI'
import type { ScriptUserRecord } from '@/types/scriptRegistry'

export type MaaFWConfigurationSource = {
  sourceId: string
  label: string
  kind: string
  path: string
  selector?: Record<string, unknown>
  fingerprint: string
  modifiedAt: string
  summary?: {
    taskCount?: number
    controller?: string
    resource?: string
    hasGamePath?: boolean
    hasAdbDevice?: boolean
  }
}

export type MaaFWConfigurationPlan = {
  planId: string
  schemaVersion: number
  kind: string
  target: 'project-and-first-user' | 'new-user'
  sourceFingerprint?: string
  summary: {
    taskCount?: number
    enabledTaskCount?: number
    optionCount?: number
    scriptFieldCount?: number
    sourceUserName?: string
    targetUserName?: string
  }
  warnings: string[]
  manualActions: Array<{
    kind: string
    blocking?: boolean
    message: string
  }>
  orphans: Record<string, unknown>
  readyToApply: boolean
  preview: {
    sourceLabel: string
    format: string
    scriptFields: string[]
    userName: string
    taskCount: number
    optionCount: number
    gamePathPresent: boolean
    adbDevicePresent: boolean
  }
  expiresAt: string
}

export type MaaFWConfigurationApplyResult = {
  applied: boolean
  planId: string
  target: 'project-and-first-user' | 'new-user'
  createdUser: ScriptUserRecord
  scriptUpdated: boolean
}

type PluginResponse<T> = {
  code: number
  status: string
  message: string
  data: T | null
}

const post = async <T>(path: string, payload: Record<string, unknown>): Promise<T> => {
  const response = await axios.post<PluginResponse<T>>(
    `${OpenAPI.BASE}/plugin/maafw/config-reuse${path}`,
    payload
  )
  const body = response.data
  if (body.code !== 200 || body.data === null) {
    throw new Error(body.message || 'MaaFW 配置复用操作失败')
  }
  return body.data
}

export function useMaaFWConfigurationReuse() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  const run = async <T>(operation: () => Promise<T>): Promise<T> => {
    loading.value = true
    error.value = null
    try {
      return await operation()
    } catch (caught) {
      error.value = caught instanceof Error ? caught.message : String(caught)
      throw caught
    } finally {
      loading.value = false
    }
  }

  const discoverSources = (scriptId: string, sourcePath: string) =>
    run(async () => {
      const result = await post<{ sources: MaaFWConfigurationSource[]; count: number }>(
        '/sources',
        { scriptId, sourcePath }
      )
      return result.sources
    })

  const planExternal = (
    scriptId: string,
    source: MaaFWConfigurationSource,
    target: MaaFWConfigurationPlan['target']
  ) =>
    run(() =>
      post<MaaFWConfigurationPlan>('/plan/external', {
        scriptId,
        source,
        target,
      })
    )

  const planCopy = (scriptId: string, sourceUserId: string, targetName = '') =>
    run(() =>
      post<MaaFWConfigurationPlan>('/plan/copy', {
        scriptId,
        sourceUserId,
        targetName,
      })
    )

  const applyPlan = (scriptId: string, planId: string) =>
    run(() =>
      post<MaaFWConfigurationApplyResult>('/apply', {
        scriptId,
        planId,
      })
    )

  return {
    loading,
    error,
    discoverSources,
    planExternal,
    planCopy,
    applyPlan,
  }
}
