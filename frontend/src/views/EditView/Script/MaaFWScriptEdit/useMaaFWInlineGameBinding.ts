import { computed, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { useGameBinding } from '@/composables/useGameBinding'
import { bindingTargetOptions } from '@/types/games'

/** 控制方式类型对应的游戏目标类型；「自动」时不限定 */
export const gameKindOfController = (controllerType: string): string | undefined =>
  controllerType === 'Adb' ? 'emulator' : controllerType === 'Win32' ? 'client' : undefined

/**
 * 控制配置里内嵌的游戏目标 / 设备选择：数据与保存都走托管的游戏绑定（与绑定卡片同一份），
 * 这里只按控制方式过滤目标、拼出提示。页面加载时解析出的控制方式不落盘，后端常常不知道
 * 控制方式、也就不给类型不一致的提示，所以类型是否相符在这里按当前控制方式自己判断。
 */
export function useMaaFWInlineGameBinding(scriptId: () => string, controllerType: () => string) {
  const { t } = useI18n()
  const state = useGameBinding({ scriptId })
  const kind = computed(() => gameKindOfController(controllerType()))
  const loading = computed(
    () => state.query.isPending.value || state.options.isPending.value || state.games.loading.value
  )
  const targetOptions = computed(() =>
    bindingTargetOptions(
      state.options.data.value?.data,
      state.games.rows.value,
      kind.value,
      state.binding.value.game_id,
      loading.value ? '' : t('core.games.deleted')
    )
  )
  const kindMismatch = computed(
    () => !!kind.value && !!state.selected.value && state.selected.value.type.kind !== kind.value
  )
  const warning = computed(
    () =>
      state.bindingProblem.value ||
      state.selectedOptionWarning.value ||
      (kindMismatch.value ? t('core.games.kindMismatch') : '')
  )
  return reactive({
    /** 专项支持绑定，或已有绑定需要能看见、清掉 */
    available: computed(() => state.bindingSupported.value || state.hasBinding.value),
    loading,
    disabled: state.controlsDisabled,
    targetValue: computed(() =>
      state.binding.value.game_id === '-' ? undefined : state.binding.value.game_id
    ),
    targetOptions,
    hasCandidates: computed(() => targetOptions.value.some(option => !option.stale)),
    targetSelected: computed(() => state.binding.value.game_id !== '-'),
    deviceValue: computed(() =>
      state.binding.value.device_id === '-' ? undefined : state.binding.value.device_id
    ),
    deviceOptions: state.deviceOptions,
    deviceDisabled: computed(
      () =>
        state.controlsDisabled.value ||
        !state.bindingSupported.value ||
        state.binding.value.game_id === '-'
    ),
    /** 桌面端只在要选设备时出「设备」格：目标有两台及以上设备，或所绑设备已删除（条目还在，
     * 或已移除、后端清空了设备并写明原因） */
    desktopDeviceVisible: computed(
      () =>
        !!state.selected.value &&
        (state.devices.value.length >= 2 ||
          state.deviceMissing.value ||
          (state.binding.value.device_id === '-' && !!state.binding.value.unavailable_reason))
    ),
    error: computed(() => state.error.value?.message ?? ''),
    warning,
    canClear: computed(() => state.hasBinding.value || state.binding.value.device_id !== '-'),
    selectTarget: state.selectTarget,
    selectDevice: state.selectDevice,
    resetBinding: state.resetBinding,
    reload: state.reload,
  })
}

export type MaaFWInlineGameBinding = ReturnType<typeof useMaaFWInlineGameBinding>
