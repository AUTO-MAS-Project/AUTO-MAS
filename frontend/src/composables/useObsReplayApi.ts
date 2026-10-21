import { ref } from 'vue'
import { ActionService, ApiError, GetService } from '@/api'
import { translate } from '@/i18n'

const responseMessage = <T extends { message?: string; code?: number }>(
  response: T,
  fallback: string
): T => {
  if (response.code !== undefined && response.code !== 200) {
    throw new Error(response.message || fallback)
  }
  return response
}

const errorMessage = (error: unknown, fallback: string) => {
  if (error instanceof ApiError && typeof error.body?.message === 'string') {
    return error.body.message
  }
  return error instanceof Error && error.message ? error.message : fallback
}

export function useObsReplayApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  const run = async <T>(request: () => Promise<T>, fallback: string): Promise<T> => {
    loading.value = true
    error.value = null
    try {
      return await request()
    } catch (caught) {
      const message = errorMessage(caught, fallback)
      error.value = message
      throw new Error(message)
    } finally {
      loading.value = false
    }
  }

  const checkObsReplay = () =>
    run(
      async () =>
        responseMessage(
          await GetService.checkObsReplayApiSettingObsCheckPost(),
          translate('setting.replay.checkFailed')
        ),
      translate('setting.replay.checkFailed')
    )

  const saveObsReplay = () =>
    run(
      async () =>
        responseMessage(
          await ActionService.saveObsReplayApiSettingObsSavePost(),
          translate('setting.replay.saveFailed')
        ),
      translate('setting.replay.saveFailed')
    )

  const listObsReplays = () =>
    run(
      async () =>
        responseMessage(
          await GetService.getObsReplaysApiHistoryReplaysGet(),
          translate('history.replays.fetchFailed')
        ),
      translate('history.replays.fetchFailed')
    )

  return {
    loading,
    error,
    checkObsReplay,
    saveObsReplay,
    listObsReplays,
  }
}
