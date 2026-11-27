import { computed, ref, toValue, watch, type MaybeRefOrGetter } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMutation, useQueryClient } from '@tanstack/vue-query'
import { useConfigQuery } from '@/services/configUiSync'
import { Service } from '@/api'
import { useGamesApi, checkedGameResponse, useGameBindingQuery } from '@/composables/useGamesApi'
import { useScriptApi } from '@/composables/useScriptApi'
import { useUserApi } from '@/composables/useUserApi'
import { useSaveQueue } from '@/composables/useSaveQueue'
import { useScriptConfigLock } from '@/composables/useScriptConfigLock'
import { gameDevices, visibleDevices, type GameBindingValue } from '@/types/games'

/**
 * 托管 / 账号的游戏目标绑定：读绑定与可选目标，保存时与脚本草稿同一个保存 scope。
 * 绑定卡片、账号覆写块和 MFW 控制配置里的内嵌控件共用这一份。
 */
export function useGameBinding(options: {
  scriptId: MaybeRefOrGetter<string>
  /** 账号页传账号 ID；托管本体不传 */
  userId?: MaybeRefOrGetter<string | undefined>
  enabled?: MaybeRefOrGetter<boolean>
}) {
  const { t } = useI18n()
  const client = useQueryClient()
  const games = useGamesApi()
  const { updateScript } = useScriptApi()
  const { updateUser } = useUserApi()
  const scriptId = computed(() => toValue(options.scriptId))
  const userId = computed(() => toValue(options.userId))
  const enabled = computed(() => toValue(options.enabled) ?? true)
  const { configLocked } = useScriptConfigLock(() =>
    userId.value ? { scriptId: scriptId.value, userId: userId.value } : scriptId.value
  )
  const binding = ref<GameBindingValue>({ game_id: '-', device_id: '-' })
  const overrideDraftOpen = ref(false)
  const queryKey = computed(() => ['game-binding', scriptId.value, userId.value])
  const query = useGameBindingQuery(scriptId, userId, enabled)
  const bindingOptions = useConfigQuery({
    queryKey: computed(() => ['game-binding-options', scriptId.value, userId.value]),
    enabled: computed(() => enabled.value && !!scriptId.value),
    queryFn: async () =>
      checkedGameResponse(
        await Service.gameBindingOptionsApiGamesBindingOptionsPost({
          scriptId: scriptId.value,
          userId: userId.value,
        })
      ),
  })
  const bindingSupported = computed(
    () =>
      bindingOptions.data.value?.supported !== false &&
      (!userId.value || bindingOptions.data.value?.accountOverrideSupported !== false)
  )
  const hasBinding = computed(
    () => binding.value.game_id !== '-' || !!binding.value.unavailable_reason
  )
  const selectedOptionWarning = computed(
    () =>
      bindingOptions.data.value?.data?.find(option => option.value === binding.value.game_id)
        ?.warning ?? ''
  )
  const selected = computed(() => games.rows.value.find(game => game.uid === binding.value.game_id))
  const devices = computed(() => (selected.value ? gameDevices(selected.value) : []))
  // 设备下拉：所绑设备已删除时仍列出（禁用并标「已删除」），不露出 uid
  const deviceOptions = computed(() =>
    visibleDevices(selected.value, binding.value.device_id).map(device => {
      const name = device.document?.info?.name ?? ''
      const deleted = t('core.games.deleted')
      return {
        value: device.uid,
        label: device.deleted ? (name ? `${name} (${deleted})` : deleted) : name,
        disabled: device.deleted,
      }
    })
  )
  // 删除实例时托管正旁挂或正在运行，恢复或下次启动规整之前绑定仍指向墓碑
  const deviceMissing = computed(
    () =>
      binding.value.device_id !== '-' &&
      !!selected.value &&
      !devices.value.some(device => device.uid === binding.value.device_id)
  )
  const bindingProblem = computed(
    () =>
      binding.value.unavailable_reason ||
      (!bindingSupported.value && hasBinding.value ? t('core.games.bindingUnsupported') : '') ||
      (deviceMissing.value ? t('core.games.deviceDeleted') : '')
  )
  // 类型不一致只是提示，绑定照常可用，不提供「清空」。
  const bindingWarning = computed(() => bindingProblem.value || selectedOptionWarning.value)
  const inheritedName = computed(
    () =>
      games.rows.value.find(game => game.uid === query.data.value?.inherited?.game_id)?.document
        .info?.name ?? t('core.games.noTarget')
  )
  const userSaveQueue = useSaveQueue()
  const save = useMutation({
    mutationKey: computed(() => ['game-binding-save', scriptId.value, userId.value]),
    scope: { id: `script-save:${scriptId.value}` },
    retry: false,
    mutationFn: async (value: GameBindingValue) => {
      const currentUserId = userId.value
      const ok = currentUserId
        ? await userSaveQueue.enqueue(
            () => updateUser(scriptId.value, currentUserId, { game: value }),
            'game'
          )
        : await updateScript(scriptId.value, { game: value })
      if (!ok) throw new Error(t('core.games.saveFailed'))
    },
    onSettled: () => client.invalidateQueries({ queryKey: queryKey.value }),
  })
  const saving = save.isPending
  const controlsDisabled = computed(
    () => configLocked.value || saving.value || query.isPending.value
  )
  const overrideEnabled = computed(() => overrideDraftOpen.value || hasBinding.value)
  const error = computed(() => query.error.value ?? bindingOptions.error.value ?? save.error.value)

  watch(
    () => [scriptId.value, userId.value] as const,
    () => {
      overrideDraftOpen.value = false
    }
  )

  watch(
    () => query.data.value,
    data => {
      binding.value = {
        game_id: data?.binding?.game_id ?? '-',
        device_id: data?.binding?.device_id ?? '-',
        unavailable_reason: data?.binding?.unavailable_reason,
      }
    },
    { immediate: true }
  )

  async function toggleOverride(checked: unknown) {
    overrideDraftOpen.value = Boolean(checked)
    if (!checked && (hasBinding.value || binding.value.device_id !== '-')) await resetBinding()
  }

  async function resetBinding() {
    await save.mutateAsync({ game_id: '-', device_id: '-' }).catch(() => {})
  }

  async function selectTarget(value: unknown) {
    if (typeof value !== 'string') return
    if (value === '-') {
      await resetBinding()
      return
    }
    const target = games.rows.value.find(game => game.uid === value)
    const device = target?.type.kind === 'client' ? (gameDevices(target)[0]?.uid ?? '-') : '-'
    binding.value = { game_id: value, device_id: device }
    overrideDraftOpen.value = false
    await save.mutateAsync({ ...binding.value }).catch(() => {})
  }

  async function selectDevice(value: unknown) {
    if (typeof value !== 'string') return
    binding.value = { ...binding.value, device_id: value }
    await save.mutateAsync({ ...binding.value }).catch(() => {})
  }

  function reload() {
    void query.refetch()
    void bindingOptions.refetch()
    void games.refresh()
  }

  return {
    games,
    binding,
    query,
    options: bindingOptions,
    bindingSupported,
    hasBinding,
    selectedOptionWarning,
    bindingProblem,
    bindingWarning,
    selected,
    devices,
    deviceOptions,
    deviceMissing,
    inheritedName,
    saving,
    controlsDisabled,
    overrideEnabled,
    error,
    toggleOverride,
    resetBinding,
    selectTarget,
    selectDevice,
    reload,
  }
}

export type GameBindingState = ReturnType<typeof useGameBinding>
