import { Emulator20Service as Api20, Service as Api, EmulatorOperateIn } from '@/api'
import type { AnalyticsEventProps } from '@/types/analytics'
import { analyticsCountBucket, beginAnalyticsOperation } from '@/utils/analytics'
import { apiOutcome, observeFeature } from '@/utils/featureAnalytics'
import { subscribe, unsubscribe } from '@/services/websocket/subscriptions'
import {
  WS_EMULATOR_OPERATION_FINISHED,
  WS_ID_EMULATOR_MANAGER,
  type WSEmulatorOperationData,
} from '@/services/websocket/types'

export { EmulatorOperateIn }
type Family = AnalyticsEventProps['emulator_discovery_finished']['emulator_family']
const families = new Map<string, Family>()
const deviceFamilies = new Map<string, Family>()
const remember = <T>(cache: Map<string, T>, key: string, value: T) => {
  if (!cache.has(key) && cache.size >= 128) cache.delete(cache.keys().next().value!)
  cache.set(key, value)
}
const family = (value: unknown): Family => {
  const known: Record<string, Family> = {
    mumu: 'mumu',
    ldplayer: 'leidian',
    leidian: 'leidian',
    bluestacks: 'bluestacks',
    avd: 'avd',
    emulator2: 'multi',
  }
  return typeof value === 'string' ? (known[value.toLowerCase()] ?? 'unknown') : 'unknown'
}
const combinedFamily = (types: unknown[]): Family => {
  const values = new Set(types.map(family))
  return values.size > 1 ? 'multi' : (values.values().next().value ?? 'unknown')
}
const configFamily = (id: string) => families.get(id) ?? 'unknown'
const deviceFamily = (id: string, slot: string) =>
  deviceFamilies.get(id + ':' + slot) ?? configFamily(id)
const commandResult = (result: { code?: number; ok?: boolean }) =>
  result.code !== 200
    ? ('failure' as const)
    : result.ok === true
      ? ('success' as const)
      : ('failure' as const)
const batchResult = (result: { code?: number; okCount?: number; failCount?: number }) =>
  result.code !== 200
    ? ('failure' as const)
    : (result.failCount ?? 0) > 0
      ? (result.okCount ?? 0) > 0
        ? ('partial' as const)
        : ('failure' as const)
      : ('success' as const)

type Observation = {
  telemetry: ReturnType<typeof beginAnalyticsOperation<'emulator_operation_observed_finished'>>
  emulator_family: Family
  operation: WSEmulatorOperationData['operate']
  accepted: boolean
  result?: boolean
  startedAt: number
}
const operations = new Map<string, Observation>()
const ambiguousOperations = new Map<string, number>()
let subscription: string | null = null
const operationKey = (id: string, index: string, action: string) => id + ':' + index + ':' + action
function settle(key: string, entry: Observation) {
  if (!entry.accepted || entry.result === undefined || operations.get(key) !== entry) return
  operations.delete(key)
  entry.telemetry.finish({
    emulator_family: entry.emulator_family,
    operation: entry.operation,
    outcome: entry.result ? 'success' : 'failure',
  })
}

export function bootstrapEmulatorAnalytics(): void {
  if (subscription) return
  subscription = subscribe(
    { id: WS_ID_EMULATOR_MANAGER, type: WS_EMULATOR_OPERATION_FINISHED },
    ({ data }) => {
      const key = operationKey(data.emulatorId, data.index, data.operate)
      const entry = operations.get(key)
      if (!entry) return
      if (performance.now() - entry.startedAt > 120_000) {
        operations.delete(key)
        return
      }
      entry.result = data.ok
      settle(key, entry)
    }
  )
}
export function disposeEmulatorAnalytics(): void {
  if (subscription) unsubscribe(subscription)
  subscription = null
  operations.clear()
  ambiguousOperations.clear()
}

function operate(input: Parameters<typeof Api.operationEmulatorApiEmulatorOperatePost>[0]) {
  const key = operationKey(input.emulatorId, input.index, input.operate)
  const entry: Observation = {
    telemetry: beginAnalyticsOperation('emulator_operation_observed_finished'),
    emulator_family: deviceFamily(input.emulatorId, input.index),
    operation: input.operate,
    accepted: false,
    startedAt: performance.now(),
  }
  // 无操作 ID 的同设备并发不能可靠关联，不把任意一条结束帧配给新请求。
  const previous = operations.get(key)
  if (previous && performance.now() - previous.startedAt < 120_000) {
    operations.delete(key)
    remember(ambiguousOperations, key, performance.now() + 120_000)
  } else if ((ambiguousOperations.get(key) ?? 0) <= performance.now()) {
    ambiguousOperations.delete(key)
    remember(operations, key, entry)
  }
  const request = observeFeature(
    'emulator_operation_result',
    { emulator_family: entry.emulator_family, operation: input.operate },
    () => Api.operationEmulatorApiEmulatorOperatePost(input),
    result => (result.code === 200 ? 'accepted' : 'rejected')
  )
  void request.then(
    result => {
      if (result.code !== 200) {
        if (operations.get(key) === entry) operations.delete(key)
        return
      }
      entry.accepted = true
      settle(key, entry)
    },
    () => {
      if (operations.get(key) === entry) operations.delete(key)
    }
  )
  return request
}

/** 仅这些显式模拟器操作参与统计；读取只利用已有响应缓存类别，不增加请求。 */
export const Service = {
  getStatusApiEmulatorStatusPost: Api.getStatusApiEmulatorStatusPost,
  getEmulatorApiEmulatorGetPost(input: Parameters<typeof Api.getEmulatorApiEmulatorGetPost>[0]) {
    const request = Api.getEmulatorApiEmulatorGetPost(input)
    void request.then(
      result => {
        if (result.code === 200)
          for (const item of result.index)
            remember(families, item.uid, family(result.data[item.uid]?.Info?.Type))
      },
      () => {}
    )
    return request
  },
  addEmulatorApiEmulatorAddPost: Api.addEmulatorApiEmulatorAddPost,
  deleteEmulatorApiEmulatorDeletePost(
    input: Parameters<typeof Api.deleteEmulatorApiEmulatorDeletePost>[0]
  ) {
    return observeFeature(
      'emulator_discovery_finished',
      { action: 'delete', emulator_family: configFamily(input.emulatorId), count_bucket: '1' },
      () => Api.deleteEmulatorApiEmulatorDeletePost(input),
      apiOutcome
    )
  },
  updateEmulatorApiEmulatorUpdatePost(
    input: Parameters<typeof Api.updateEmulatorApiEmulatorUpdatePost>[0]
  ) {
    const info = input.data.Info
    if (info && (typeof info.StableMode === 'boolean' || typeof info.ConfigGuard === 'boolean')) {
      const stable = typeof info.StableMode === 'boolean'
      return observeFeature(
        'emulator_guard_changed',
        {
          guard_kind: stable ? 'stable' : 'config',
          action: (stable ? info.StableMode : info.ConfigGuard) ? 'enable' : 'disable',
        },
        () => Api.updateEmulatorApiEmulatorUpdatePost(input),
        apiOutcome
      )
    }
    return observeFeature(
      'emulator_discovery_finished',
      {
        action: 'update',
        emulator_family:
          family(info?.Type) === 'unknown' ? configFamily(input.emulatorId) : family(info?.Type),
        count_bucket: '1',
      },
      () => Api.updateEmulatorApiEmulatorUpdatePost(input),
      apiOutcome
    )
  },
  searchEmulatorsApiEmulatorEmulatorSearchPost() {
    return observeFeature(
      'emulator_discovery_finished',
      { action: 'search', emulator_family: 'unknown', count_bucket: '0' },
      () => Api.searchEmulatorsApiEmulatorEmulatorSearchPost(),
      result => ({
        outcome: apiOutcome(result),
        count_bucket: analyticsCountBucket(result.emulators?.length ?? 0),
        emulator_family: combinedFamily((result.emulators ?? []).map(item => item.type)),
      })
    )
  },
  operationEmulatorApiEmulatorOperatePost: operate,
}

export const Emulator20Service = {
  previewDeleteInstanceApiEmulator2InstancesDeletePreviewPost:
    Api20.previewDeleteInstanceApiEmulator2InstancesDeletePreviewPost,
  previewRemovePathApiEmulator2PathsRemovePreviewPost:
    Api20.previewRemovePathApiEmulator2PathsRemovePreviewPost,
  listDevicesApiEmulator2DevicesPost(
    input: Parameters<typeof Api20.listDevicesApiEmulator2DevicesPost>[0]
  ) {
    const request = Api20.listDevicesApiEmulator2DevicesPost(input)
    void request.then(
      result => {
        if (result.code !== 200) return
        remember(
          families,
          input.emulatorId,
          combinedFamily((result.paths ?? []).map(item => item.type))
        )
        for (const device of result.devices ?? [])
          remember(deviceFamilies, input.emulatorId + ':' + device.slot, family(device.realType))
      },
      () => {}
    )
    return request
  },
  searchEmulatorsApiEmulator2SearchPost(
    input: Parameters<typeof Api20.searchEmulatorsApiEmulator2SearchPost>[0]
  ) {
    return observeFeature(
      'emulator_discovery_finished',
      { action: 'search', emulator_family: 'unknown', count_bucket: '0' },
      () => Api20.searchEmulatorsApiEmulator2SearchPost(input),
      result => ({
        outcome: apiOutcome(result),
        count_bucket: analyticsCountBucket(result.emulators?.length ?? 0),
        emulator_family: combinedFamily((result.emulators ?? []).map(item => item.type)),
      })
    )
  },
  addPathApiEmulator2PathsAddPost(
    input: Parameters<typeof Api20.addPathApiEmulator2PathsAddPost>[0]
  ) {
    return observeFeature(
      'emulator_discovery_finished',
      { action: 'import', emulator_family: configFamily(input.emulatorId), count_bucket: '1' },
      () => Api20.addPathApiEmulator2PathsAddPost(input),
      commandResult
    )
  },
  removePathApiEmulator2PathsRemovePost(
    input: Parameters<typeof Api20.removePathApiEmulator2PathsRemovePost>[0]
  ) {
    return observeFeature(
      'emulator_discovery_finished',
      { action: 'delete', emulator_family: configFamily(input.emulatorId), count_bucket: '1' },
      () => Api20.removePathApiEmulator2PathsRemovePost(input),
      commandResult
    )
  },
  createInstanceApiEmulator2InstancesCreatePost(
    input: Parameters<typeof Api20.createInstanceApiEmulator2InstancesCreatePost>[0]
  ) {
    return observeFeature(
      'emulator_instance_manage_finished',
      {
        action: 'create',
        scope: 'single',
        emulator_family: configFamily(input.emulatorId),
        count_bucket: '1',
      },
      () => Api20.createInstanceApiEmulator2InstancesCreatePost(input),
      commandResult
    )
  },
  deleteInstanceApiEmulator2InstancesDeletePost(
    input: Parameters<typeof Api20.deleteInstanceApiEmulator2InstancesDeletePost>[0]
  ) {
    return observeFeature(
      'emulator_instance_manage_finished',
      {
        action: 'delete',
        scope: 'single',
        emulator_family: deviceFamily(input.emulatorId, input.slot),
        count_bucket: '1',
      },
      () => Api20.deleteInstanceApiEmulator2InstancesDeletePost(input),
      commandResult
    )
  },
  applySettingsApiEmulator2SettingsApplyPost(
    input: Parameters<typeof Api20.applySettingsApiEmulator2SettingsApplyPost>[0]
  ) {
    return observeFeature(
      'emulator_instance_manage_finished',
      {
        action: 'settings',
        scope: 'single',
        emulator_family: deviceFamily(input.emulatorId, input.slot),
        count_bucket: '1',
      },
      () => Api20.applySettingsApiEmulator2SettingsApplyPost(input),
      commandResult
    )
  },
  applySettingsToAllApiEmulator2SettingsApplyAllPost(
    input: Parameters<typeof Api20.applySettingsToAllApiEmulator2SettingsApplyAllPost>[0]
  ) {
    return observeFeature(
      'emulator_instance_manage_finished',
      {
        action: 'batch_settings',
        scope: 'batch',
        emulator_family: configFamily(input.emulatorId),
        count_bucket: '0',
      },
      () => Api20.applySettingsToAllApiEmulator2SettingsApplyAllPost(input),
      result => ({
        outcome: batchResult(result),
        count_bucket: analyticsCountBucket((result.okCount ?? 0) + (result.failCount ?? 0)),
      })
    )
  },
  openStoreApiEmulator2InstancesStoreOpenPost(
    input: Parameters<typeof Api20.openStoreApiEmulator2InstancesStoreOpenPost>[0]
  ) {
    return observeFeature(
      'emulator_operation_result',
      { operation: 'store', emulator_family: deviceFamily(input.emulatorId, input.slot) },
      () => Api20.openStoreApiEmulator2InstancesStoreOpenPost(input),
      commandResult
    )
  },
  captureBaselinesApiEmulator2GuardCapturePost(
    input: Parameters<typeof Api20.captureBaselinesApiEmulator2GuardCapturePost>[0]
  ) {
    return observeFeature(
      'emulator_guard_changed',
      { guard_kind: 'config', action: 'capture' },
      () => Api20.captureBaselinesApiEmulator2GuardCapturePost(input),
      apiOutcome
    )
  },
  applyStableModeApiEmulator2StableModeApplyPost(
    input: Parameters<typeof Api20.applyStableModeApiEmulator2StableModeApplyPost>[0]
  ) {
    return observeFeature(
      'emulator_guard_changed',
      { guard_kind: 'stable', action: 'apply' },
      () => Api20.applyStableModeApiEmulator2StableModeApplyPost(input),
      batchResult
    )
  },
}
