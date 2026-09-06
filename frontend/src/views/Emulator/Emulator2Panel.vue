<script setup lang="ts">
/**
 * Emulator 2.0 面板。
 *
 * 与旧配置的区别：一条配置纳管多条模拟器路径，各家的实例合并成一张设备表。
 * 设备号由本配置统一编排，脚本绑定用的就是它；模拟器自己的实例号另外显示，
 * 因为两者不一定对得上（实例被删过就会错开）。
 */
import { computed, h, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import {
  DeleteOutlined,
  EyeInvisibleOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  PoweroffOutlined,
  ReloadOutlined,
  SearchOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'

import { Emulator20Service, EmulatorOperateIn, Service } from '@/api'
import type {
  Emulator2AffectedScript,
  Emulator2BatchResult,
  Emulator2DeviceItem,
  Emulator2PathItem,
  Emulator2SearchItem,
  Emulator2SettingField,
} from '@/api'

const props = defineProps<{ emulatorId: string }>()

const { t } = useI18n()
const logger = window.electronAPI.getLogger('Emulator2')

const loading = ref(false)
const paths = ref<Emulator2PathItem[]>([])
const devices = ref<Emulator2DeviceItem[]>([])

const searchOpen = ref(false)
const searching = ref(false)
const searchResults = ref<Emulator2SearchItem[]>([])
const selectedPaths = ref<string[]>([])
const adding = ref(false)

const removeOpen = ref(false)
const removing = ref(false)
const removeTarget = ref<Emulator2PathItem | null>(null)
const removeSlots = ref<string[]>([])
const removeAffected = ref<Emulator2AffectedScript[]>([])

const addableResults = computed(() => searchResults.value.filter(item => item.supported))

/** 模拟器类型 → 用户看得懂的名字。界面上不该出现 ldplayer / mumu 这种内部名。 */
const typeLabel = (type: string | undefined) => {
  if (!type) return ''
  const key = `emulator.type.${type}`
  const text = t(key)
  return text === key ? type : text
}

/** 判定原因枚举 → 用户文案。后端只给枚举，措辞在这里定。 */
const reasonLabel = (reason: string) => {
  const key = `emulator2.reason.${reason}`
  const text = t(key)
  return text === key ? reason : text
}

const reasonText = (item: Emulator2SearchItem) => reasonLabel(item.reason)

const reasonColor = (reason: string) => {
  if (reason === 'ok') return 'success'
  if (reason === 'planned') return 'processing'
  return 'default'
}

const loadDevices = async () => {
  if (!props.emulatorId) return
  loading.value = true
  try {
    const response = await Emulator20Service.listDevicesApiEmulator2DevicesPost({
      emulatorId: props.emulatorId,
    })
    if (response.code !== 200) {
      message.error(response.message)
      return
    }
    paths.value = response.paths || []
    devices.value = response.devices || []
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error(`加载设备列表失败: ${detail}`)
    message.error(t('emulator2.toast.loadFailed'))
  } finally {
    loading.value = false
  }
}

const openSearch = async () => {
  searchOpen.value = true
  selectedPaths.value = []
  searching.value = true
  try {
    const response = await Emulator20Service.searchEmulatorsApiEmulator2SearchPost({
      emulatorId: props.emulatorId,
    })
    if (response.code !== 200) {
      message.error(response.message)
      return
    }
    searchResults.value = response.emulators || []
    selectedPaths.value = addableResults.value.map(item => item.installPath)
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error(`搜索模拟器失败: ${detail}`)
    message.error(t('emulator2.toast.searchFailed'))
  } finally {
    searching.value = false
  }
}

const confirmAdd = async () => {
  if (!selectedPaths.value.length) return
  adding.value = true
  let added = 0
  try {
    for (const installPath of selectedPaths.value) {
      const item = searchResults.value.find(row => row.installPath === installPath)
      const response = await Emulator20Service.addPathApiEmulator2PathsAddPost({
        emulatorId: props.emulatorId,
        installPath,
        alias: item?.alias || null,
      })
      if (response.code === 200 && response.ok) {
        added += 1
      } else {
        message.warning(
          `${item?.alias || installPath}: ${
            response.reason ? reasonLabel(response.reason) : response.message
          }`
        )
      }
    }
  } finally {
    adding.value = false
  }
  if (added > 0) {
    message.success(t('emulator2.toast.addOk', { count: added }))
    searchOpen.value = false
    await loadDevices()
  }
}

const openRemove = async (path: Emulator2PathItem) => {
  removeTarget.value = path
  removeSlots.value = path.slots || []
  removeAffected.value = []
  removeOpen.value = true
  try {
    const response = await Emulator20Service.previewRemovePathApiEmulator2PathsRemovePreviewPost({
      emulatorId: props.emulatorId,
      pathId: path.pathId,
    })
    if (response.code === 200) {
      removeSlots.value = response.slots || []
      removeAffected.value = response.affectedScripts || []
    }
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error(`预览移除影响失败: ${detail}`)
  }
}

const confirmRemove = async () => {
  if (!removeTarget.value) return
  removing.value = true
  try {
    const response = await Emulator20Service.removePathApiEmulator2PathsRemovePost({
      emulatorId: props.emulatorId,
      pathId: removeTarget.value.pathId,
    })
    if (response.code !== 200 || !response.ok) {
      message.error(response.message)
      return
    }
    message.success(t('emulator2.toast.removeOk'))
    removeOpen.value = false
    await loadDevices()
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error(`移除模拟器路径失败: ${detail}`)
    message.error(t('emulator2.toast.removeFailed'))
  } finally {
    removing.value = false
  }
}

const runningAffected = computed(() => removeAffected.value.filter(item => item.running))

// ---- 新建 / 删除实例 ----

const createOpen = ref(false)
const creating = ref(false)
const createPathId = ref('')
const createName = ref('')

const pathSelectOptions = computed(() =>
  paths.value.map(item => ({
    value: item.pathId,
    label: item.alias + ' (' + typeLabel(item.type) + ')',
  }))
)

const openCreate = () => {
  createPathId.value = paths.value[0]?.pathId ?? ''
  createName.value = ''
  createOpen.value = true
}

const confirmCreate = async () => {
  if (!createPathId.value) return
  creating.value = true
  try {
    const response = await Emulator20Service.createInstanceApiEmulator2InstancesCreatePost({
      emulatorId: props.emulatorId,
      pathId: createPathId.value,
      name: createName.value || null,
    })
    if (response.code !== 200 || !response.ok) {
      message.error(response.message)
      return
    }
    message.success(t('emulator2.toast.createOk', { slot: response.slot }))
    createOpen.value = false
    await loadDevices()
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error('新建实例失败: ' + detail)
    message.error(t('emulator2.toast.createFailed'))
  } finally {
    creating.value = false
  }
}

const deleteOpen = ref(false)
const deleting = ref(false)
const deleteTarget = ref<Emulator2DeviceItem | null>(null)
const deleteAffected = ref<Emulator2AffectedScript[]>([])

const openDelete = async (device: Emulator2DeviceItem) => {
  deleteTarget.value = device
  deleteAffected.value = []
  deleteOpen.value = true
  try {
    const response =
      await Emulator20Service.previewDeleteInstanceApiEmulator2InstancesDeletePreviewPost({
        emulatorId: props.emulatorId,
        slot: device.slot,
      })
    if (response.code === 200) deleteAffected.value = response.affectedScripts || []
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error('预览删除影响失败: ' + detail)
  }
}

const confirmDelete = async () => {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    const response = await Emulator20Service.deleteInstanceApiEmulator2InstancesDeletePost({
      emulatorId: props.emulatorId,
      slot: deleteTarget.value.slot,
    })
    if (response.code !== 200 || !response.ok) {
      message.error(response.message)
      return
    }
    message.success(t('emulator2.toast.deleteOk'))
    deleteOpen.value = false
    await loadDevices()
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error('删除实例失败: ' + detail)
    message.error(t('emulator2.toast.deleteFailed'))
  } finally {
    deleting.value = false
  }
}

const FIELDS = ['width', 'height', 'dpi', 'cpu', 'memoryMb', 'fps'] as const
type FieldName = (typeof FIELDS)[number]
type FieldForm = Record<FieldName, number | null>

const emptyForm = (): FieldForm => ({
  width: null,
  height: null,
  dpi: null,
  cpu: null,
  memoryMb: null,
  fps: null,
})

const fieldOf = (device: Emulator2DeviceItem, name: FieldName): Emulator2SettingField | undefined =>
  device.settings?.[name]

const fieldValue = (device: Emulator2DeviceItem, name: FieldName) =>
  fieldOf(device, name)?.value ?? null

/** 表里显示的值。空着的显示破折号，而不是 0 或 null。 */
const fieldText = (device: Emulator2DeviceItem, name: FieldName) => {
  const value = fieldValue(device, name)
  return value === null ? '—' : String(value)
}

/**
 * 「默认」标注。
 *
 * 这不是可有可无的装饰：实例配置里没写 CPU 的雷电实例照样跑在雷电默认的 6 核上，
 * MuMu 没切 custom 模式时跑的也是预设档位而不是存着的自定义值。
 * 不标出来就是在声称用户保存过一个他从没设过的值。
 */
const fieldState = (device: Emulator2DeviceItem, name: FieldName) =>
  fieldOf(device, name)?.state ?? 'unset'

const resolutionText = (device: Emulator2DeviceItem) => {
  const w = fieldValue(device, 'width')
  const h = fieldValue(device, 'height')
  return w === null || h === null ? '—' : `${w} × ${h}`
}

// ---- 单台设置 ----

const settingsOpen = ref(false)
const savingSettings = ref(false)
const settingsTarget = ref<Emulator2DeviceItem | null>(null)
const settingsForm = ref<FieldForm>(emptyForm())
/** 表单打开时看到的值。保存时带回后端做冲突比对，避免盖掉别人的改动。 */
const settingsBaseline = ref<FieldForm>(emptyForm())

const openSettings = (device: Emulator2DeviceItem) => {
  settingsTarget.value = device
  const form = emptyForm()
  for (const name of FIELDS) form[name] = fieldValue(device, name)
  settingsForm.value = { ...form }
  settingsBaseline.value = { ...form }
  settingsOpen.value = true
}

/** 只提交用户真正改过的字段——其余键在文件里原样保留。 */
const changedFields = computed(() => {
  const changes: Record<string, number> = {}
  for (const name of FIELDS) {
    const value = settingsForm.value[name]
    if (value === null || value === undefined) continue
    if (value === settingsBaseline.value[name]) continue
    changes[name] = value
  }
  return changes
})

const confirmSettings = async () => {
  if (!settingsTarget.value) return
  const changes = changedFields.value
  if (!Object.keys(changes).length) {
    settingsOpen.value = false
    return
  }
  savingSettings.value = true
  try {
    const response = await Emulator20Service.applySettingsApiEmulator2SettingsApplyPost({
      emulatorId: props.emulatorId,
      slot: settingsTarget.value.slot,
      changes,
      expected: settingsBaseline.value,
    })
    if (response.code !== 200 || !response.ok) {
      message.error(response.message)
      return
    }
    message.success(t('emulator2.toast.settingsOk'))
    settingsOpen.value = false
    await loadDevices()
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error(`保存设置失败: ${detail}`)
    message.error(t('emulator2.toast.settingsFailed'))
  } finally {
    savingSettings.value = false
  }
}

// ---- 批量设置 ----

const batchOpen = ref(false)
const batchSaving = ref(false)
const batchForm = ref<FieldForm>(emptyForm())

/** 批量写入里失败的那几台，连原因一起显示在弹窗内。 */
const batchFailures = ref<Emulator2BatchResult[]>([])

const openBatch = () => {
  batchForm.value = emptyForm()
  batchFailures.value = []
  batchOpen.value = true
}

/** 留空的字段不下发——批量设置只改用户填了的那几项。 */
const batchChanges = computed(() => {
  const changes: Record<string, number> = {}
  for (const name of FIELDS) {
    const value = batchForm.value[name]
    if (value !== null && value !== undefined) changes[name] = value
  }
  return changes
})

const confirmBatch = async () => {
  const changes = batchChanges.value
  if (!Object.keys(changes).length) return
  batchSaving.value = true
  try {
    const response = await Emulator20Service.applySettingsToAllApiEmulator2SettingsApplyAllPost({
      emulatorId: props.emulatorId,
      changes,
    })
    if (response.code !== 200) {
      message.error(response.message)
      return
    }
    const failed = response.failCount ?? 0
    if (failed > 0) {
      // 只报「N 台失败」用户没法行动，把每台的原因一并列出来
      batchFailures.value = (response.results || []).filter(item => !item.ok)
      message.warning(
        t('emulator2.toast.batchPartial', {
          ok: response.okCount ?? 0,
          fail: failed,
        })
      )
    } else {
      batchFailures.value = []
      message.success(t('emulator2.toast.batchOk', { count: response.okCount ?? 0 }))
    }
    batchOpen.value = false
    await loadDevices()
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error(`批量设置失败: ${detail}`)
    message.error(t('emulator2.toast.batchFailed'))
  } finally {
    batchSaving.value = false
  }
}

// ---- 启动 / 关闭 / 隐藏 ----

const busySlots = ref<Set<string>>(new Set())

const operate = async (device: Emulator2DeviceItem, action: EmulatorOperateIn.operate) => {
  busySlots.value = new Set(busySlots.value).add(device.slot)
  try {
    const response = await Service.operationEmulatorApiEmulatorOperatePost({
      emulatorId: props.emulatorId,
      operate: action,
      index: device.slot,
    })
    if (response.code !== 200) {
      message.error(response.message)
      return
    }
    await loadDevices()
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error(`操作设备 #${device.slot} 失败: ${detail}`)
    message.error(t('emulator2.toast.operateFailed'))
  } finally {
    const next = new Set(busySlots.value)
    next.delete(device.slot)
    busySlots.value = next
  }
}

const isOnline = (device: Emulator2DeviceItem) =>
  device.availability === 'ok' && device.status === 0
const isReachable = (device: Emulator2DeviceItem) => device.availability === 'ok'

// ---- 稳定模式 ----

const stableOpen = ref(false)
const stableApplying = ref(false)
/** 只处理这台；为 null 表示全部。 */
const stableTarget = ref<Emulator2DeviceItem | null>(null)
const stableResults = ref<Emulator2BatchResult[]>([])

const openStable = (device: Emulator2DeviceItem | null) => {
  stableTarget.value = device
  stableResults.value = []
  stableOpen.value = true
}

/** 这次会动到哪几台。已经安全的不列出来。 */
const stablePending = computed(() =>
  (stableTarget.value ? [stableTarget.value] : devices.value).filter(
    item => item.availability === 'ok' && !item.stableMode
  )
)

/** 干扰项字段名 → 用户文案。后端只给字段名，措辞在这里定。 */
const stableItemLabel = (field: string) => {
  const key = `emulator2.stableItem.${field}`
  const text = t(key)
  return text === key ? field : text
}

const confirmStable = async () => {
  stableApplying.value = true
  try {
    const response = await Emulator20Service.applyStableModeApiEmulator2StableModeApplyPost({
      emulatorId: props.emulatorId,
      slots: stableTarget.value ? [stableTarget.value.slot] : [],
    })
    if (response.code !== 200) {
      message.error(response.message)
      return
    }
    const failed = response.failCount ?? 0
    if (failed > 0) {
      stableResults.value = (response.results || []).filter(item => !item.ok)
      message.warning(
        t('emulator2.toast.batchPartial', { ok: response.okCount ?? 0, fail: failed })
      )
    } else {
      message.success(t('emulator2.toast.stableOk', { count: response.okCount ?? 0 }))
      stableOpen.value = false
    }
    await loadDevices()
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error(`应用稳定模式失败: ${detail}`)
    message.error(t('emulator2.toast.stableFailed'))
  } finally {
    stableApplying.value = false
  }
}

// 实例必须先关闭才能删——避免删掉一台正在跑任务的设备
const canDelete = (device: Emulator2DeviceItem) =>
  device.availability === 'ok' && (device.status === 1 || device.status === 5)

/** 设备状态 → Tag。availability 优先：这次没枚举到就不该显示成离线。 */
const deviceStatus = (device: Emulator2DeviceItem) => {
  if (device.availability === 'unavailable') {
    return { color: 'default', text: t('emulator2.status.unavailable') }
  }
  if (device.availability === 'missing') {
    return { color: 'warning', text: t('emulator2.status.missing') }
  }
  const map: Record<number, { color: string; text: string }> = {
    0: { color: 'success', text: t('emulator.deviceStatus.online') },
    1: { color: 'default', text: t('emulator.deviceStatus.offline') },
    2: { color: 'processing', text: t('emulator.deviceStatus.starting') },
    3: { color: 'processing', text: t('emulator.deviceStatus.closing') },
    4: { color: 'error', text: t('emulator.deviceStatus.error') },
    5: { color: 'default', text: t('emulator.deviceStatus.notFound') },
  }
  return (
    map[device.status ?? 5] ?? {
      color: 'default',
      text: t('emulator.deviceStatus.unknown'),
    }
  )
}

const deviceColumns = computed(() => [
  { title: t('emulator2.colSource'), key: 'source', width: 150 },
  { title: t('emulator2.colSlot'), dataIndex: 'slot', key: 'slot', width: 90 },
  { title: t('emulator.colStatus'), key: 'status', width: 100 },
  {
    title: t('emulator.colName'),
    dataIndex: 'title',
    key: 'title',
    ellipsis: true,
  },
  {
    title: t('emulator.colAdb'),
    dataIndex: 'adbAddress',
    key: 'adb',
    ellipsis: true,
  },
  { title: t('emulator2.colResolution'), key: 'resolution', width: 130 },
  { title: t('emulator2.colCpu'), key: 'cpu', width: 80 },
  { title: t('emulator2.colMemory'), key: 'memory', width: 100 },
  { title: t('emulator2.colFps'), key: 'fps', width: 80 },
  { title: t('emulator2.colStable'), key: 'stable', width: 110 },
  { title: t('emulator.colAction'), key: 'action', width: 230 },
])

watch(() => props.emulatorId, loadDevices)
onMounted(loadDevices)

defineExpose({ reload: loadDevices })
</script>

<template>
  <div class="emulator2-panel">
    <div class="section-header">
      <h3>
        {{ t('emulator2.pathsTitle') }}
        <span class="section-hint">{{ t('emulator2.pathsHint') }}</span>
      </h3>
      <a-button size="small" type="primary" ghost :icon="h(SearchOutlined)" @click="openSearch">
        {{ t('emulator2.searchAndAdd') }}
      </a-button>
    </div>

    <a-empty v-if="!paths.length" :description="t('emulator2.noPath')">
      <a-button type="primary" :icon="h(PlusOutlined)" @click="openSearch">
        {{ t('emulator2.searchAndAdd') }}
      </a-button>
    </a-empty>

    <div v-else class="path-grid">
      <a-card v-for="path in paths" :key="path.pathId" size="small" class="path-card">
        <template #title>
          <a-space :size="6">
            <a-tag color="purple">{{ typeLabel(path.type) }}</a-tag>
            <span class="path-alias">{{ path.alias }}</span>
            <span class="path-version">{{ path.version }}</span>
          </a-space>
        </template>
        <template #extra>
          <a-button type="text" size="small" danger @click="openRemove(path)">
            {{ t('emulator2.removePath') }}
          </a-button>
        </template>
        <div class="path-line">{{ path.installPath }}</div>
        <div class="path-sub">
          {{
            t('emulator2.slotRange', {
              slots: (path.slots ?? []).map(s => `#${s}`).join(' ') || '—',
            })
          }}
        </div>
        <div class="path-sub">{{ t('emulator2.bossKeyHint') }}</div>
      </a-card>
    </div>

    <div class="section-header" style="margin-top: 20px">
      <h3>
        {{ t('emulator.deviceList') }}
        <span class="section-hint">{{ t('emulator2.deviceHint') }}</span>
      </h3>
      <a-space :size="8">
        <a-button
          size="small"
          type="primary"
          ghost
          :icon="h(PlusOutlined)"
          :disabled="!paths.length"
          @click="openCreate"
        >
          {{ t('emulator2.createInstance') }}
        </a-button>
        <a-button
          size="small"
          :icon="h(SafetyCertificateOutlined)"
          :disabled="!devices.length"
          @click="openStable(null)"
        >
          {{ t('emulator2.stableMode') }}
        </a-button>
        <a-button
          size="small"
          :icon="h(SettingOutlined)"
          :disabled="!devices.length"
          @click="openBatch"
        >
          {{ t('emulator2.batchSettings') }}
        </a-button>
        <a-button size="small" :icon="h(ReloadOutlined)" :loading="loading" @click="loadDevices">
          {{ t('emulator2.refresh') }}
        </a-button>
      </a-space>
    </div>

    <a-spin :spinning="loading">
      <a-empty v-if="!devices.length" :description="t('emulator.noDevice')" />
      <a-table
        v-else
        :data-source="devices"
        :columns="deviceColumns"
        :row-key="(record: Emulator2DeviceItem) => record.slot"
        :pagination="false"
        size="small"
        :scroll="{ x: 'max-content' }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'source'">
            <div class="source-cell">
              <a-tag color="purple">{{ typeLabel(record.realType) }}</a-tag>
              <span class="source-sub">
                {{ record.alias }} ·
                {{ t('emulator2.nativeIndex', { index: record.nativeIndex }) }}
              </span>
            </div>
          </template>
          <template v-else-if="column.key === 'slot'">
            <strong>#{{ record.slot }}</strong>
          </template>
          <template v-else-if="column.key === 'status'">
            <a-tag :color="deviceStatus(record).color">{{ deviceStatus(record).text }}</a-tag>
          </template>
          <template v-else-if="column.key === 'resolution'">
            <div class="setting-cell">
              <span>{{ resolutionText(record) }}</span>
              <span class="setting-sub">
                {{ fieldText(record, 'dpi') }} dpi
                <a-tag v-if="fieldState(record, 'dpi') === 'default'" size="small">
                  {{ t('emulator2.stateDefault') }}
                </a-tag>
              </span>
            </div>
          </template>
          <template v-else-if="column.key === 'cpu'">
            <span>{{ fieldText(record, 'cpu') }}</span>
            <a-tag v-if="fieldState(record, 'cpu') === 'default'" size="small">
              {{ t('emulator2.stateDefault') }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'memory'">
            <span>{{ fieldText(record, 'memoryMb') }}</span>
            <a-tag v-if="fieldState(record, 'memoryMb') === 'default'" size="small">
              {{ t('emulator2.stateDefault') }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'fps'">
            <span>{{ fieldText(record, 'fps') }}</span>
          </template>
          <template v-else-if="column.key === 'stable'">
            <a-tag v-if="record.stableMode" color="success">
              {{ t('emulator2.stableOn') }}
            </a-tag>
            <a-tooltip v-else :title="(record.stableUnsafe || []).map(stableItemLabel).join(' / ')">
              <a-tag color="warning">{{ t('emulator2.stableOff') }}</a-tag>
            </a-tooltip>
          </template>
          <template v-else-if="column.key === 'action'">
            <a-space :size="4">
              <a-tooltip :title="t('emulator2.start')">
                <a-button
                  size="small"
                  type="text"
                  :icon="h(PlayCircleOutlined)"
                  :loading="busySlots.has(record.slot)"
                  :disabled="!isReachable(record) || isOnline(record)"
                  @click="operate(record, EmulatorOperateIn.operate.OPEN)"
                />
              </a-tooltip>
              <a-tooltip :title="t('emulator2.stop')">
                <a-button
                  size="small"
                  type="text"
                  :icon="h(PoweroffOutlined)"
                  :loading="busySlots.has(record.slot)"
                  :disabled="!isOnline(record)"
                  @click="operate(record, EmulatorOperateIn.operate.CLOSE)"
                />
              </a-tooltip>
              <a-tooltip :title="t('emulator2.hide')">
                <a-button
                  size="small"
                  type="text"
                  :icon="h(EyeInvisibleOutlined)"
                  :loading="busySlots.has(record.slot)"
                  :disabled="!isOnline(record)"
                  @click="operate(record, EmulatorOperateIn.operate.SHOW)"
                />
              </a-tooltip>
              <a-tooltip
                :title="
                  record.stableMode ? t('emulator2.stableAlready') : t('emulator2.stableApply')
                "
              >
                <a-button
                  size="small"
                  type="text"
                  :icon="h(SafetyCertificateOutlined)"
                  :disabled="!isReachable(record) || record.stableMode"
                  @click="openStable(record)"
                />
              </a-tooltip>
              <a-tooltip :title="t('emulator2.settings')">
                <a-button
                  size="small"
                  type="text"
                  :icon="h(SettingOutlined)"
                  :disabled="!isReachable(record)"
                  @click="openSettings(record)"
                />
              </a-tooltip>
              <a-tooltip
                :title="
                  canDelete(record)
                    ? t('emulator2.deleteInstance')
                    : t('emulator2.deleteNeedsOffline')
                "
              >
                <a-button
                  size="small"
                  type="text"
                  danger
                  :icon="h(DeleteOutlined)"
                  :disabled="!canDelete(record)"
                  @click="openDelete(record)"
                />
              </a-tooltip>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-spin>

    <a-alert type="info" show-icon :message="t('emulator2.footerHint')" style="margin-top: 12px" />

    <!-- 单台设置 -->
    <a-modal
      v-model:open="settingsOpen"
      :title="t('emulator2.settingsTitle')"
      width="560px"
      :confirm-loading="savingSettings"
      :ok-text="t('emulator2.save')"
      @ok="confirmSettings"
    >
      <p v-if="settingsTarget">
        <strong>#{{ settingsTarget.slot }}</strong>
        — {{ settingsTarget.alias }} ·
        {{ t('emulator2.nativeIndex', { index: settingsTarget.nativeIndex }) }}
      </p>
      <a-form layout="vertical">
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item :label="t('emulator2.fieldWidth')">
              <a-input-number
                v-model:value="settingsForm.width"
                :min="160"
                :max="4096"
                style="width: 100%%"
                :placeholder="t('emulator2.keepCurrent')"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item :label="t('emulator2.fieldHeight')">
              <a-input-number
                v-model:value="settingsForm.height"
                :min="160"
                :max="4096"
                style="width: 100%%"
                :placeholder="t('emulator2.keepCurrent')"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item :label="t('emulator2.fieldDpi')">
              <a-input-number
                v-model:value="settingsForm.dpi"
                :min="80"
                :max="640"
                style="width: 100%%"
                :placeholder="t('emulator2.keepCurrent')"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item :label="t('emulator2.fieldFps')">
              <a-input-number
                v-model:value="settingsForm.fps"
                :min="1"
                :max="240"
                style="width: 100%%"
                :placeholder="t('emulator2.keepCurrent')"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item :label="t('emulator2.fieldCpu')">
              <a-input-number
                v-model:value="settingsForm.cpu"
                :min="1"
                :max="64"
                style="width: 100%%"
                :placeholder="t('emulator2.keepCurrent')"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item :label="t('emulator2.fieldMemory')">
              <a-input-number
                v-model:value="settingsForm.memoryMb"
                :min="512"
                :max="65536"
                :step="512"
                style="width: 100%%"
                :placeholder="t('emulator2.keepCurrent')"
              />
            </a-form-item>
          </a-col>
        </a-row>
      </a-form>
      <a-alert type="info" show-icon :message="t('emulator2.settingsHint')" />
    </a-modal>

    <!-- 批量设置 -->
    <a-modal
      v-model:open="batchOpen"
      :title="t('emulator2.batchTitle')"
      width="560px"
      :confirm-loading="batchSaving"
      :ok-text="t('emulator2.batchApply')"
      :ok-button-props="{ disabled: !Object.keys(batchChanges).length }"
      @ok="confirmBatch"
    >
      <a-alert
        type="warning"
        show-icon
        :message="t('emulator2.batchWarning', { count: devices.length })"
        style="margin-bottom: 12px"
      />
      <a-form layout="vertical">
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item :label="t('emulator2.fieldWidth')">
              <a-input-number
                v-model:value="batchForm.width"
                :min="160"
                :max="4096"
                style="width: 100%%"
                :placeholder="t('emulator2.keepCurrent')"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item :label="t('emulator2.fieldHeight')">
              <a-input-number
                v-model:value="batchForm.height"
                :min="160"
                :max="4096"
                style="width: 100%%"
                :placeholder="t('emulator2.keepCurrent')"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item :label="t('emulator2.fieldDpi')">
              <a-input-number
                v-model:value="batchForm.dpi"
                :min="80"
                :max="640"
                style="width: 100%%"
                :placeholder="t('emulator2.keepCurrent')"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item :label="t('emulator2.fieldFps')">
              <a-input-number
                v-model:value="batchForm.fps"
                :min="1"
                :max="240"
                style="width: 100%%"
                :placeholder="t('emulator2.keepCurrent')"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item :label="t('emulator2.fieldCpu')">
              <a-input-number
                v-model:value="batchForm.cpu"
                :min="1"
                :max="64"
                style="width: 100%%"
                :placeholder="t('emulator2.keepCurrent')"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item :label="t('emulator2.fieldMemory')">
              <a-input-number
                v-model:value="batchForm.memoryMb"
                :min="512"
                :max="65536"
                :step="512"
                style="width: 100%%"
                :placeholder="t('emulator2.keepCurrent')"
              />
            </a-form-item>
          </a-col>
        </a-row>
      </a-form>
      <a-alert type="info" show-icon :message="t('emulator2.batchHint')" />
      <a-list
        v-if="batchFailures.length"
        size="small"
        bordered
        :data-source="batchFailures"
        :header="t('emulator2.batchFailures')"
        style="margin-top: 12px"
      >
        <template #renderItem="{ item }">
          <a-list-item>
            <span>#{{ item.slot }}</span>
            <template #actions>
              <span class="batch-fail-reason">{{ item.message }}</span>
            </template>
          </a-list-item>
        </template>
      </a-list>
    </a-modal>

    <!-- 稳定模式 -->
    <a-modal
      v-model:open="stableOpen"
      :title="t('emulator2.stableTitle')"
      width="620px"
      :confirm-loading="stableApplying"
      :ok-text="t('emulator2.stableApply')"
      :ok-button-props="{ disabled: !stablePending.length }"
      @ok="confirmStable"
    >
      <a-alert
        type="info"
        show-icon
        :message="t('emulator2.stableIntro')"
        style="margin-bottom: 12px"
      />
      <a-empty v-if="!stablePending.length" :description="t('emulator2.stableNothing')" />
      <a-list
        v-else
        size="small"
        bordered
        :data-source="stablePending"
        :header="t('emulator2.stableWillChange', { count: stablePending.length })"
      >
        <template #renderItem="{ item }">
          <a-list-item>
            <span>
              <strong>#{{ item.slot }}</strong>
              {{ item.title || item.alias }}
            </span>
            <template #actions>
              <span class="stable-items">
                {{ (item.stableUnsafe || []).map(stableItemLabel).join(' / ') }}
              </span>
            </template>
          </a-list-item>
        </template>
      </a-list>
      <a-alert
        type="warning"
        show-icon
        :message="t('emulator2.stableOneWay')"
        style="margin-top: 12px"
      />
      <a-list
        v-if="stableResults.length"
        size="small"
        bordered
        :data-source="stableResults"
        :header="t('emulator2.batchFailures')"
        style="margin-top: 12px"
      >
        <template #renderItem="{ item }">
          <a-list-item>
            <span>#{{ item.slot }}</span>
            <template #actions>
              <span class="batch-fail-reason">{{ item.message }}</span>
            </template>
          </a-list-item>
        </template>
      </a-list>
    </a-modal>

    <!-- 新建实例 -->
    <a-modal
      v-model:open="createOpen"
      :title="t('emulator2.createTitle')"
      :confirm-loading="creating"
      :ok-text="t('emulator2.create')"
      :ok-button-props="{ disabled: !createPathId }"
      @ok="confirmCreate"
    >
      <a-form layout="vertical">
        <a-form-item :label="t('emulator2.createOnPath')">
          <a-select v-model:value="createPathId" :options="pathSelectOptions" />
        </a-form-item>
        <a-form-item :label="t('emulator2.createName')">
          <a-input v-model:value="createName" :placeholder="t('emulator2.createNamePlaceholder')" />
        </a-form-item>
      </a-form>
      <a-alert type="info" show-icon :message="t('emulator2.createHint')" />
    </a-modal>

    <!-- 删除实例 -->
    <a-modal
      v-model:open="deleteOpen"
      :title="t('emulator2.deleteTitle')"
      width="600px"
      :confirm-loading="deleting"
      :ok-text="t('emulator2.deleteInstance')"
      :ok-button-props="{ danger: true }"
      @ok="confirmDelete"
    >
      <p v-if="deleteTarget">
        <strong>#{{ deleteTarget.slot }}</strong>
        — {{ deleteTarget.alias }} ·
        {{ t('emulator2.nativeIndex', { index: deleteTarget.nativeIndex }) }}
      </p>
      <a-alert
        type="warning"
        show-icon
        :message="
          t('emulator2.deleteWarning', {
            slot: deleteTarget ? '#' + deleteTarget.slot : '',
            count: deleteAffected.length,
          })
        "
        style="margin-bottom: 12px"
      />
      <a-list
        v-if="deleteAffected.length"
        size="small"
        bordered
        :data-source="deleteAffected"
        :header="t('emulator2.affectedScripts')"
      >
        <template #renderItem="{ item }">
          <a-list-item>
            <span>{{ item.name }}</span>
            <template #actions>
              <a-tag v-if="item.running" color="processing">{{ t('emulator2.running') }}</a-tag>
            </template>
          </a-list-item>
        </template>
      </a-list>
    </a-modal>

    <!-- 添加模拟器 -->
    <a-modal
      v-model:open="searchOpen"
      :title="t('emulator2.addTitle')"
      width="760px"
      :confirm-loading="adding"
      :ok-text="t('emulator2.add')"
      :ok-button-props="{ disabled: !selectedPaths.length }"
      @ok="confirmAdd"
    >
      <a-alert
        type="info"
        show-icon
        :message="t('emulator2.addHint')"
        style="margin-bottom: 12px"
      />
      <a-spin :spinning="searching">
        <a-empty v-if="!searchResults.length" :description="t('emulator.searchEmpty')" />
        <a-checkbox-group v-else v-model:value="selectedPaths" style="width: 100%">
          <div v-for="item in searchResults" :key="item.installPath" class="search-row">
            <a-checkbox :value="item.installPath" :disabled="!item.supported" />
            <div class="search-main">
              <div>
                <a-tag :color="item.supported ? 'purple' : 'default'">{{
                  typeLabel(item.type)
                }}</a-tag>
                <span class="search-alias">{{ item.alias }}</span>
                <span class="search-version">{{ item.version }}</span>
              </div>
              <div class="search-path">{{ item.installPath }}</div>
            </div>
            <a-tag :color="reasonColor(item.reason)">{{ reasonText(item) }}</a-tag>
          </div>
        </a-checkbox-group>
      </a-spin>
    </a-modal>

    <!-- 移除路径 -->
    <a-modal
      v-model:open="removeOpen"
      :title="t('emulator2.removeTitle')"
      width="640px"
      :confirm-loading="removing"
      :ok-text="t('emulator2.removePath')"
      :ok-button-props="{ danger: true }"
      @ok="confirmRemove"
    >
      <p v-if="removeTarget">
        <a-tag color="purple">{{ typeLabel(removeTarget.type) }}</a-tag>
        {{ removeTarget.alias }} — {{ removeTarget.installPath }}
      </p>
      <a-alert
        type="warning"
        show-icon
        :message="
          t('emulator2.removeWarning', {
            slots: removeSlots.map(s => `#${s}`).join(' ') || '—',
            count: removeAffected.length,
          })
        "
        style="margin-bottom: 12px"
      />
      <a-list
        v-if="removeAffected.length"
        size="small"
        bordered
        :data-source="removeAffected"
        :header="t('emulator2.affectedScripts')"
      >
        <template #renderItem="{ item }">
          <a-list-item>
            <span>{{ item.name }}</span>
            <template #actions>
              <span>#{{ item.slot }}</span>
              <a-tag v-if="item.running" color="processing">{{ t('emulator2.running') }}</a-tag>
            </template>
          </a-list-item>
        </template>
      </a-list>
      <a-alert
        v-if="runningAffected.length"
        type="warning"
        show-icon
        :message="t('emulator2.removeRunningHint', { count: runningAffected.length })"
        style="margin-top: 12px"
      />
    </a-modal>
  </div>
</template>

<style scoped>
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.section-hint {
  margin-left: 8px;
  font-size: 13px;
  font-weight: 400;
  color: var(--ant-color-text-tertiary);
}

.path-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}

.path-alias {
  font-weight: 600;
}

.path-version,
.path-sub {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

.path-line {
  font-size: 13px;
  color: var(--ant-color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.source-sub {
  font-size: 11px;
  color: var(--ant-color-text-tertiary);
}

.search-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  margin-bottom: 8px;
}

.search-main {
  flex: 1;
  min-width: 0;
}

.search-alias {
  font-size: 14px;
}

.search-version,
.search-path {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

.search-path {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
