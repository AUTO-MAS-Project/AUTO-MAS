import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import { useI18n } from 'vue-i18n'
import { Service, type GameCreateIn, type GameUpdateIn, type GameDeviceUpdateIn } from '@/api'
import type { GameRow } from '@/types/games'
import type { AnalyticsEventProps } from '@/types/analytics'
import { observeFeature, apiOutcome } from '@/utils/featureAnalytics'
import { queryRequest } from '@/utils/queryRequest'
import { useConfigQuery } from '@/services/configUiSync'

export const GAMES_QUERY_KEY = ['games'] as const
export function useGameBindingQuery(
  scriptId: MaybeRefOrGetter<string>,
  userId?: MaybeRefOrGetter<string | undefined>,
  enabled: MaybeRefOrGetter<boolean> = true
) {
  return useConfigQuery({
    queryKey: computed(() => ['game-binding', toValue(scriptId), toValue(userId)]),
    enabled: computed(() => toValue(enabled) && !!toValue(scriptId)),
    queryFn: async () => {
      const sid = toValue(scriptId),
        uid = toValue(userId)
      const scriptResponse = checkedGameResponse(
        await Service.getScriptApiScriptsGetPost({ scriptId: sid })
      )
      const userResponse = uid
        ? checkedGameResponse(
            await Service.getUserApiScriptsUserGetPost({ scriptId: sid, userId: uid })
          )
        : undefined
      const script = scriptResponse.data[sid]
      const account = uid ? userResponse?.data[uid] : undefined
      return {
        binding: account?.game ?? script?.game,
        inherited: script?.game,
        uiSources: [...(scriptResponse.uiSources ?? []), ...(userResponse?.uiSources ?? [])],
      }
    },
  })
}
export function checkedGameResponse<T extends { code?: number; message?: string }>(response: T): T {
  if (response.code !== 200) throw new Error(response.message || 'Game operation failed')
  return response
}
export function gameAdapter(value: string): AnalyticsEventProps['game_target_changed']['adapter'] {
  switch (value) {
    case 'mumu':
    case 'ldplayer':
    case 'avd':
    case 'general_emulator':
    case 'win_process':
      return value
    default:
      return 'unknown'
  }
}

export function useGamesApi() {
  const client = useQueryClient()
  const { t, te } = useI18n()
  const typesQuery = useConfigQuery({
    queryKey: ['game-types'],
    queryFn: async ({ signal }) =>
      checkedGameResponse(await queryRequest(signal, () => Service.gameTypesApiGamesTypesPost())),
  })
  const query = useConfigQuery({
    queryKey: GAMES_QUERY_KEY,
    queryFn: async ({ signal }) =>
      checkedGameResponse(await queryRequest(signal, () => Service.getGamesApiGamesGetPost())),
  })
  const types = computed(() =>
    (typesQuery.data.value?.data ?? []).map(type => {
      const plugin = type.type === 'avd' ? 'mod_avd' : type.type
      const key = `plugins.${plugin}_adapter.display_name`
      return { ...type, name: te(key) ? t(key) : type.name }
    })
  )
  const rows = computed<GameRow[]>(() =>
    (query.data.value?.order ?? []).flatMap(item => {
      const document = query.data.value?.data?.[item.uid]
      const type = types.value.find(type => type.configType === item.type)
      return document && type
        ? [{ uid: item.uid, document, type, runtime: query.data.value?.runtime?.[item.uid] ?? {} }]
        : []
    })
  )
  const refresh = () => client.invalidateQueries({ queryKey: GAMES_QUERY_KEY })
  async function change<T extends { code?: number; message?: string }>(
    type: string,
    action: AnalyticsEventProps['game_target_changed']['action'],
    run: () => Promise<T>
  ): Promise<T> {
    const response = await observeFeature(
      'game_target_changed',
      { adapter: gameAdapter(type), action },
      run,
      result => {
        const outcome = apiOutcome(result)
        if (
          outcome !== 'success' ||
          !('data' in result) ||
          !result.data ||
          typeof result.data !== 'object'
        )
          return outcome
        const results = Object.values(result.data).filter(
          (item): item is { ok: boolean } =>
            typeof item === 'object' &&
            item !== null &&
            'ok' in item &&
            typeof item.ok === 'boolean'
        )
        const failures = results.filter(item => !item.ok).length
        return failures ? (failures === results.length ? 'failure' : 'partial') : 'success'
      }
    )
    checkedGameResponse(response)
    await refresh()
    return response
  }
  return {
    rows,
    types,
    loading: computed(() => query.isPending.value || typesQuery.isPending.value),
    error: computed(() => query.error.value ?? typesQuery.error.value),
    refresh,
    prepare: () =>
      Promise.all([
        query.refetch({ cancelRefetch: false }),
        typesQuery.refetch({ cancelRefetch: false }),
      ]),
    change,
    create: (body: GameCreateIn) =>
      change(body.type, 'create', () => Service.createGameApiGamesCreatePost(body)),
    update: (row: GameRow, data: GameUpdateIn['data']) =>
      change(row.type.type, 'update', () =>
        Service.updateGameApiGamesUpdatePost({ gameId: row.uid, data })
      ),
    updateDevice: (row: GameRow, deviceId: string, data: GameDeviceUpdateIn['data']) =>
      change(row.type.type, 'update', () =>
        Service.updateGameDeviceApiGamesDeviceUpdatePost({ gameId: row.uid, deviceId, data })
      ),
    remove: (row: GameRow) =>
      change(row.type.type, 'delete', () =>
        Service.deleteGameApiGamesDeletePost({ gameId: row.uid })
      ),
    search: () => change('unknown', 'search', () => Service.searchGamesApiGamesSearchPost()),
    importFound: (uid: string) =>
      change('unknown', 'import', () => Service.importGameApiGamesImportPost({ gameId: uid })),
  }
}
