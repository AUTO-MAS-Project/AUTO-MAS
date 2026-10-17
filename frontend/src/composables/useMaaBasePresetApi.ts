import { ref } from 'vue'

import { ApiError } from '@/api'
import { DeveloperService } from '@/api/services/DeveloperService'
import type { MaaBasePresetOut } from '@/api/models/MaaBasePresetOut'

type JsonObject = Record<string, unknown>

const getErrorMessage = (error: unknown, fallback: string): string => {
  if (error instanceof ApiError) {
    const body = error.body
    if (body && typeof body === 'object' && 'message' in body && typeof body.message === 'string') {
      return body.message
    }
  }
  return error instanceof Error && error.message ? error.message : fallback
}

const unwrap = (response: MaaBasePresetOut, fallback: string): MaaBasePresetOut => {
  if (response.code !== 200 || !response.data || typeof response.data !== 'object') {
    throw new Error(response.message || fallback)
  }
  return response
}

export function useMaaBasePresetApi() {
  const loading = ref(false)
  const saving = ref(false)

  const getBasePreset = async (): Promise<MaaBasePresetOut> => {
    loading.value = true
    try {
      return unwrap(
        await DeveloperService.getMaaBasePresetApiApiDeveloperMaaBasePresetGet(),
        '读取 MAA 预设失败'
      )
    } catch (error) {
      throw new Error(getErrorMessage(error, '读取 MAA 预设失败'))
    } finally {
      loading.value = false
    }
  }

  const saveBasePreset = async (data: JsonObject): Promise<MaaBasePresetOut> => {
    saving.value = true
    try {
      return unwrap(
        await DeveloperService.updateMaaBasePresetApiApiDeveloperMaaBasePresetPost({ data }),
        '保存 MAA 预设失败'
      )
    } catch (error) {
      throw new Error(getErrorMessage(error, '保存 MAA 预设失败'))
    } finally {
      saving.value = false
    }
  }

  return { loading, saving, getBasePreset, saveBasePreset }
}
