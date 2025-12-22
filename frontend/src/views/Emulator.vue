<!-- eslint-disable vue/multi-word-component-names -->
<script setup lang="ts">
// 挂载和卸载键盘监听
import { h, onMounted, onUnmounted, ref, watch } from 'vue'
import { useEventListener } from '@vueuse/core'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  DeleteOutlined,
  FolderOpenOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
  SearchOutlined,
  StopOutlined,
} from '@ant-design/icons-vue'
import type { EmulatorConfigIndexItem, EmulatorSearchResult } from '@/api'
import { Service } from '@/api'
import { getLogger } from '@/utils/logger'

const logger = getLogger('模拟器管理')

// 编辑数据接口
interface EmulatorInfo {
  name: string
  type: string
  path: string
  max_wait_time: number
  boss_keys: string[]
}

// 安全的 JSON 解析函数
const safeJsonParse = (jsonString: string | null | undefined, fallback: any = []) => {
  if (!jsonString) return fallback
  try {
    return JSON.parse(jsonString)
  } catch (e) {
    logger.error('JSON 解析失败:', e)
    return fallback
  }
}

// 模拟器类型映射
const emulatorTypeOptions = [
  { value: 'general', label: '通用模拟器' },
  { value: 'mumu', label: 'MuMu模拟器' },
  { value: 'ldplayer', label: '雷电模拟器' },
  // { value: 'nox', label: '夜神模拟器' },
  // { value: 'memu', label: '逍遥模拟器' },
  // { value: 'blueStacks', label: 'BlueStacks' },
]

// 数据状态
const loading = ref(false)
const searching = ref(false)
const emulatorIndex = ref<EmulatorConfigIndexItem[]>([])
const emulatorData = ref<Record<string, any>>({})
const searchResults = ref<EmulatorSearchResult[]>([])
const showSearchModal = ref(false)

// Tab 相关状态（使用 localStorage 持久化）
const STORAGE_KEY = 'emulator_active_key'
const activeKey = ref<string>(localStorage.getItem(STORAGE_KEY) || '')

// 监听 activeKey 变化，保存到 localStorage
const saveActiveKey = (key: string) => {
  if (key) {
    localStorage.setItem(STORAGE_KEY, key)
  }
}

// 设备信息相关状态
const devicesData = ref<Record<string, Record<string, Record<string, any>>>>({})
const loadingDevices = ref<Set<string>>(new Set())
const startingDevices = ref<Set<string>>(new Set())
const stoppingDevices = ref<Set<string>>(new Set())

// 轮询相关状态
const pollingTimer = ref<ReturnType<typeof setTimeout> | null>(null)
const POLLING_INTERVAL = 5000 // 5秒轮询一次

// 路由监听
const route = useRoute()

// 轮询获取所有模拟器的设备状态
const pollDevicesStatus = async () => {
  // 只在有模拟器时轮询
  if (emulatorIndex.value.length === 0) {
    return
  }

  // 静默获取设备状态，不显示loading
  try {
    for (const emulator of emulatorIndex.value) {
      const response = await Service.getStatusApiEmulatorStatusPost({
        emulatorId: emulator.uid,
      })

      if (response.code === 200) {
        const allDevicesData = response.data || {}
        const currentDevices = allDevicesData[emulator.uid] || {}
        devicesData.value[emulator.uid] = currentDevices
      }
    }
  } catch (e) {
    // 轮询时的错误静默处理，避免频繁弹错误提示
    logger.warn('轮询设备状态时出错:', e)
  }
}

// 启动轮询
const startPolling = () => {
  if (pollingTimer.value) {
    clearInterval(pollingTimer.value)
  }
  pollingTimer.value = setInterval(pollDevicesStatus, POLLING_INTERVAL)
  logger.info('模拟器页面轮询已启动')
}

// 停止轮询
const stopPolling = () => {
  if (pollingTimer.value) {
    clearInterval(pollingTimer.value)
    pollingTimer.value = null
    logger.info('模拟器页面轮询已停止')
  }
}

// 每个模拟器的编辑数据（使用 Map 存储）
const editingDataMap = ref<Map<string, EmulatorInfo>>(new Map())

// 自动保存状态
const savingMap = ref<Map<string, boolean>>(new Map())

// 老板键录制状态（为每个模拟器单独管理）
const recordingBossKeyMap = ref<Map<string, boolean>>(new Map())
const recordedKeysMap = ref<Map<string, Set<string>>>(new Map())
const bossKeyInputMap = ref<Record<string, string>>({})

// 设备状态枚举定义（与后端保持一致）
const DeviceStatus = {
  ONLINE: 0, // 设备在线
  OFFLINE: 1, // 设备离线
  STARTING: 2, // 设备开启中
  CLOSING: 3, // 设备关闭中
  ERROR: 4, // 错误
  NOT_FOUND: 5, // 未找到设备
  UNKNOWN: 10, // 未知状态
} as const

// 获取设备状态显示信息
const getDeviceStatusInfo = (status: number) => {
  switch (status) {
    case DeviceStatus.ONLINE:
      return { text: '在线', color: 'success' }
    case DeviceStatus.OFFLINE:
      return { text: '离线', color: 'default' }
    case DeviceStatus.STARTING:
      return { text: '启动中', color: 'processing' }
    case DeviceStatus.CLOSING:
      return { text: '关闭中', color: 'warning' }
    case DeviceStatus.ERROR:
      return { text: '错误', color: 'error' }
    case DeviceStatus.NOT_FOUND:
      return { text: '未找到', color: 'error' }
    case DeviceStatus.UNKNOWN:
      return { text: '未知', color: 'default' }
    default:
      return { text: '未知', color: 'default' }
  }
}

// 判断设备是否可以启动
const canStartDevice = (status: number) => {
  return (
    status === DeviceStatus.OFFLINE ||
    status === DeviceStatus.ERROR ||
    status === DeviceStatus.NOT_FOUND ||
    status === DeviceStatus.UNKNOWN
  )
}

// 判断设备是否可以关闭
const canStopDevice = (status: number) => {
  return status === DeviceStatus.ONLINE || status === DeviceStatus.STARTING
}

// 获取当前模拟器的编辑数据
const getEditingData = (uuid: string): EmulatorInfo => {
  if (!editingDataMap.value.has(uuid)) {
    const configData = emulatorData.value[uuid]
    editingDataMap.value.set(uuid, {
      name: configData?.Info?.Name || '',
      type: configData?.Data?.Type || '',
      path: configData?.Info?.Path || '',
      max_wait_time: configData?.Data?.MaxWaitTime || 60,
      boss_keys: safeJsonParse(configData?.Data?.BossKey, []),
    })
  }
  return editingDataMap.value.get(uuid)!
}

// 同步名称到显示数据（立即更新 Tab 标题）
const syncNameToDisplay = (uuid: string, name: string) => {
  // 更新 emulatorData 中的名称（Tab 标题使用）
  if (emulatorData.value[uuid]?.Info) {
    emulatorData.value[uuid].Info.Name = name
  }
  // 注意: emulatorIndex 只包含 uid 和 type，不包含 name
  // name 的显示由 emulatorData[uuid]?.Info?.Name 提供
}

// 加载模拟器列表
const loadEmulators = async () => {
  loading.value = true
  try {
    const response = await Service.getEmulatorApiEmulatorGetPost({ emulatorId: null })
    if (response.code === 200 && 'index' in response && 'data' in response) {
      emulatorIndex.value = (response.index as EmulatorConfigIndexItem[]) || []
      emulatorData.value = (response.data as Record<string, any>) || {}

      // 初始化所有模拟器的编辑数据
      emulatorIndex.value.forEach(item => {
        const configData = emulatorData.value[item.uid]
        const bossKeys = safeJsonParse(configData?.Data?.BossKey, [])
        editingDataMap.value.set(item.uid, {
          name: configData?.Info?.Name || '',
          type: configData?.Data?.Type || '',
          path: configData?.Info?.Path || '',
          max_wait_time: configData?.Data?.MaxWaitTime || 60,
          boss_keys: bossKeys,
        })
        // 同步 boss_keys 到输入框显示
        if (bossKeys.length > 0) {
          bossKeyInputMap.value[item.uid] = bossKeys[0]
        }
      })
    } else {
      message.error(response.message || '加载模拟器配置失败')
    }
  } catch (e) {
    logger.error('加载模拟器配置失败', e)
    message.error('加载模拟器配置失败')
  } finally {
    loading.value = false
  }
}

// 添加模拟器
const handleAdd = async () => {
  try {
    const response = await Service.addEmulatorApiEmulatorAddPost()
    if (response.code === 200) {
      await loadEmulators()
      // 自动切换到新模拟器
      activeKey.value = response.emulatorId
      saveActiveKey(activeKey.value)
      await loadDevices(response.emulatorId)
    } else {
      message.error(response.message || '添加失败')
    }
  } catch (e) {
    logger.error('添加模拟器失败', e)
    message.error('添加模拟器失败')
  }
}

// 刷新模拟器配置 - 保存成功后调用
const refreshEmulatorConfig = async (uuid?: string) => {
  try {
    const response = await Service.getEmulatorApiEmulatorGetPost({ emulatorId: uuid || null })
    if (response.code === 200 && 'index' in response && 'data' in response) {
      emulatorIndex.value = (response.index as EmulatorConfigIndexItem[]) || []
      emulatorData.value = (response.data as Record<string, any>) || {}

      // 更新编辑数据
      emulatorIndex.value.forEach(item => {
        const configData = emulatorData.value[item.uid]
        const bossKeys = safeJsonParse(configData?.Data?.BossKey, [])
        editingDataMap.value.set(item.uid, {
          name: configData?.Info?.Name || '',
          type: configData?.Data?.Type || '',
          path: configData?.Info?.Path || '',
          max_wait_time: configData?.Data?.MaxWaitTime || 60,
          boss_keys: bossKeys,
        })
        // 同步 boss_keys 到输入框显示
        if (bossKeys.length > 0) {
          bossKeyInputMap.value[item.uid] = bossKeys[0]
        }
      })
    }
  } catch (e) {
    logger.error('刷新模拟器配置失败', e)
  }
}

// 即时保存函数 - 只发送修改的字段（遵循最小原则）
const handleSaveChange = async (uuid: string, key: string, value: any) => {
  savingMap.value.set(uuid, true)

  try {
    // 构建更新数据 - 只包含修改的字段
    let configData: any = {}

    if (key === 'name') {
      configData = { Info: { Name: value } }
    } else if (key === 'path') {
      configData = { Info: { Path: value } }
    } else if (key === 'type') {
      configData = {
        Data: { Type: value as 'general' | 'mumu' | 'ldplayer' | 'nox' | 'memu' | 'blueStacks' },
      }
    } else if (key === 'max_wait_time') {
      configData = { Data: { MaxWaitTime: value } }
    } else if (key === 'boss_keys') {
      configData = { Data: { BossKey: JSON.stringify(value) } }
    }

    const response = await Service.updateEmulatorApiEmulatorUpdatePost({
      emulatorId: uuid,
      data: configData,
    })

    if (response.code === 200) {
      logger.info(`配置已保存: ${key}`)
      // 保存成功后重新获取最新配置
      await refreshEmulatorConfig(uuid)
    } else {
      message.error(response.message || '保存失败')
    }
  } catch (e) {
    logger.error('保存模拟器配置失败', e)
    message.error('保存模拟器配置失败')
  } finally {
    savingMap.value.set(uuid, false)
  }
}

// 删除模拟器
const handleDelete = async (uuid: string) => {
  try {
    const response = await Service.deleteEmulatorApiEmulatorDeletePost({
      emulatorId: uuid,
    })
    if (response.code === 200) {

      // 如果删除的是当前激活的 Tab，需要跳转到其他 Tab
      if (activeKey.value === uuid) {
        const currentIndex = emulatorIndex.value.findIndex(e => e.uid === uuid)
        // 优先跳转到下一个，如果没有则跳转到上一个
        if (currentIndex < emulatorIndex.value.length - 1) {
          activeKey.value = emulatorIndex.value[currentIndex + 1].uid
        } else if (currentIndex > 0) {
          activeKey.value = emulatorIndex.value[currentIndex - 1].uid
        } else {
          activeKey.value = ''
          localStorage.removeItem(STORAGE_KEY)
        }
        saveActiveKey(activeKey.value)
      }

      await loadEmulators()
    } else {
      message.error(response.message || '删除失败')
    }
  } catch (e) {
    logger.error('删除模拟器失败', e)
    message.error('删除模拟器失败')
  }
}

// 自动搜索模拟器
const handleSearch = async () => {
  searching.value = true
  try {
    const response = await Service.searchEmulatorsApiEmulatorEmulatorSearchPost()
    if (response.code === 200) {
      searchResults.value = response.emulators || []
      if (searchResults.value.length > 0) {
        showSearchModal.value = true
        message.success(`找到 ${searchResults.value.length} 个模拟器`)
      } else {
        message.info('未找到已安装的模拟器')
      }
    } else {
      message.error(response.message || '搜索失败')
    }
  } catch (e) {
    logger.error('搜索模拟器失败', e)
    message.error('搜索模拟器失败')
  } finally {
    searching.value = false
  }
}

// 从搜索结果导入
const handleImportFromSearch = async (result: EmulatorSearchResult) => {
  try {
    const response = await Service.addEmulatorApiEmulatorAddPost()
    if (response.code === 200) {
      // 更新新添加的模拟器配置，使用分组结构
      const updateResponse = await Service.updateEmulatorApiEmulatorUpdatePost({
        emulatorId: response.emulatorId,
        data: {
          Info: {
            Name: result.name,
            Path: result.path,
          },
          Data: {
            Type: result.type as 'general' | 'mumu' | 'ldplayer' | 'nox' | 'memu' | 'blueStacks',
            MaxWaitTime: 60,
            BossKey: JSON.stringify([]),
          },
        },
      })
      if (updateResponse.code === 200) {
        message.success('导入成功')
        await loadEmulators()
        showSearchModal.value = false
      } else {
        message.error(updateResponse.message || '导入失败')
      }
    } else {
      message.error(response.message || '导入失败')
    }
  } catch (e) {
    logger.error('导入模拟器失败', e)
    message.error('导入模拟器失败')
  }
}

// 展开/折叠设备信息（已废弃，Tab模式下不需要）
// const toggleDevices = async (uuid: string) => {
//   await loadDevices(uuid)
// }

// 加载设备信息 - 简化版，不使用缓存
const loadDevices = async (uuid: string) => {
  loadingDevices.value.add(uuid)
  loadingDevices.value = new Set(loadingDevices.value)

  try {
    const response = await Service.getStatusApiEmulatorStatusPost({
      emulatorId: uuid,
    })

    if (response.code === 200) {
      // 后端返回的data是 { "模拟器UUID": { "设备索引": {...} } }
      // 需要提取当前模拟器的设备列表
      const allDevicesData = response.data || {}
      const currentDevices = allDevicesData[uuid] || {}
      devicesData.value[uuid] = currentDevices
    } else {
      message.error(response.message || '获取设备信息失败')
    }
  } catch (e) {
    logger.error('获取设备信息失败', e)
    message.error('获取设备信息失败')
  } finally {
    loadingDevices.value.delete(uuid)
    loadingDevices.value = new Set(loadingDevices.value)
  }
}

// refreshDevices 函数已删除，改为轮询机制

// 启动模拟器
const startEmulator = async (uuid: string, index: string) => {
  const deviceKey = `${uuid}-${index}`
  startingDevices.value.add(deviceKey)
  startingDevices.value = new Set(startingDevices.value)

  try {
    const response = await Service.operationEmulatorApiEmulatorOperatePost({
      emulatorId: uuid,
      operate: 'open' as any,
      index: index,
    })

    if (response.code === 200) {
      message.success(response.message || `模拟器 ${index} 启动成功`)
      // 刷新设备状态
      await loadDevices(uuid)
    } else {
      message.error(response.message || '启动失败')
    }
  } catch (e) {
    logger.error('启动模拟器失败', e)
    message.error('启动模拟器失败')
  } finally {
    startingDevices.value.delete(deviceKey)
    startingDevices.value = new Set(startingDevices.value)
  }
}

// 关闭模拟器
const stopEmulator = async (uuid: string, index: string) => {
  const deviceKey = `${uuid}-${index}`
  stoppingDevices.value.add(deviceKey)
  stoppingDevices.value = new Set(stoppingDevices.value)

  try {
    const response = await Service.operationEmulatorApiEmulatorOperatePost({
      emulatorId: uuid,
      operate: 'close' as any,
      index: index,
    })

    if (response.code === 200) {
      message.success(response.message || `模拟器 ${index} 已关闭`)
      // 刷新设备状态
      await loadDevices(uuid)
    } else {
      message.error(response.message || '关闭失败')
    }
  } catch (e) {
    logger.error('关闭模拟器失败', e)
    message.error('关闭模拟器失败')
  } finally {
    stoppingDevices.value.delete(deviceKey)
    stoppingDevices.value = new Set(stoppingDevices.value)
  }
}

// 路径选择
const selectEmulatorPath = async (uuid: string) => {
  try {
    if (!window.electronAPI) {
      message.error('文件选择功能不可用,请在 Electron 环境中运行')
      return
    }

    const editData = editingDataMap.value.get(uuid)
    if (!editData) return

    // 选择任意文件
    const paths = await (window.electronAPI as any).selectFile([
      { name: '所有文件', extensions: ['*'] },
    ])

    if (paths && paths.length > 0) {
      const originalPath = editData.path
      editData.path = paths[0]
      message.success('模拟器路径选择成功')
      // 立刻保存并从后端获取被纠正后的路径
      await handleSaveChange(uuid, 'path', paths[0])

      // 检查路径是否被后端纠正
      const newPath = editingDataMap.value.get(uuid)?.path || ''
      if (paths[0] !== newPath && newPath) {
        message.info(`路径已自动调整: ${paths[0]} -> ${newPath}`)
      }
    }
  } catch (error) {
    logger.error('选择模拟器路径失败:', error)
    message.error('选择文件失败')
  }
}

// 开始录制老板键
const startRecordBossKey = (uuid: string) => {
  recordingBossKeyMap.value.set(uuid, true)
  recordedKeysMap.value.set(uuid, new Set())
  bossKeyInputMap.value[uuid] = ''
  message.info('请按下快捷键组合...')
}

// 停止录制老板键
const stopRecordBossKey = (uuid: string) => {
  recordingBossKeyMap.value.delete(uuid)
  recordedKeysMap.value.delete(uuid)
  delete bossKeyInputMap.value[uuid]
}

// 键盘事件处理
const handleKeyDown = (event: KeyboardEvent) => {
  // 检查是否有正在录制的模拟器
  const recordingUuid = Array.from(recordingBossKeyMap.value.entries()).find(
    ([, recording]) => recording
  )?.[0]

  if (!recordingUuid) return

  event.preventDefault()
  event.stopPropagation()

  const keys: string[] = []

  if (event.ctrlKey) keys.push('Ctrl')
  if (event.shiftKey) keys.push('Shift')
  if (event.altKey) keys.push('Alt')
  if (event.metaKey) keys.push('Meta')

  // 获取主键
  const mainKey = event.key
  if (mainKey !== 'Control' && mainKey !== 'Shift' && mainKey !== 'Alt' && mainKey !== 'Meta') {
    // 将字母转为大写
    const displayKey = mainKey.length === 1 ? mainKey.toUpperCase() : mainKey
    keys.push(displayKey)
  }

  if (keys.length > 0) {
    recordedKeysMap.value.set(recordingUuid, new Set(keys))
  }
}

const handleKeyUp = async (event: KeyboardEvent) => {
  // 检查是否有正在录制的模拟器
  const recordingUuid = Array.from(recordingBossKeyMap.value.entries()).find(
    ([, recording]) => recording
  )?.[0]

  if (!recordingUuid) return

  event.preventDefault()
  event.stopPropagation()

  // 如果已经记录了按键，停止录制并设置为老板键
  const recordedKeys = recordedKeysMap.value.get(recordingUuid)
  if (recordedKeys && recordedKeys.size > 0) {
    const keyCombo = Array.from(recordedKeys).join('+')
    const editData = editingDataMap.value.get(recordingUuid)
    if (editData) {
      // 设置为唯一的老板键（替换而不是追加）
      editData.boss_keys = [keyCombo]
      // 同时更新输入框显示
      bossKeyInputMap.value[recordingUuid] = keyCombo
      message.success(`老板键已设置为: ${keyCombo}`)
      // 即时保存老板键
      await handleSaveChange(recordingUuid, 'boss_keys', [keyCombo])
    }
    recordingBossKeyMap.value.delete(recordingUuid)
    recordedKeysMap.value.delete(recordingUuid)
  }
}

// 使用 VueUse 的 useEventListener 替代手动管理事件监听器
useEventListener(document, 'keydown', handleKeyDown)
useEventListener(document, 'keyup', handleKeyUp)

// 监听路由变化，控制轮询启停
watch(
  () => route.path,
  newPath => {
    if (newPath === '/emulators') {
      // 进入模拟器页面，启动轮询
      logger.info('进入模拟器页面，启动轮询')
      startPolling()
    } else {
      // 离开模拟器页面，停止轮询
      logger.info('离开模拟器页面，停止轮询')
      stopPolling()
    }
  },
  { immediate: true }
)

onMounted(async () => {
  await loadEmulators()
  await onEmulatorsLoaded()
  // 轮询的启动由路由监听器控制，这里不需要手动启动
})

// 监听加载完成后自动选中第一个 Tab 或加载设备信息
const onEmulatorsLoaded = async () => {
  if (emulatorIndex.value.length > 0) {
    // 尝试恢复上次的 activeKey，如果不存在或已被删除，则选择第一个
    const savedKey = activeKey.value
    const isValidKey = emulatorIndex.value.some(e => e.uid === savedKey)

    if (!savedKey || !isValidKey) {
      activeKey.value = emulatorIndex.value[0].uid
      saveActiveKey(activeKey.value)
    }

    // 自动加载当前激活 Tab 的设备信息
    await loadDevices(activeKey.value)
  }
}

// Tab 切换时自动加载设备信息并保存状态
const onTabChange = async (key: string) => {
  // 即时保存模式下，切换前无需额外保存，数据已在编辑完成时保存
  activeKey.value = key
  saveActiveKey(key)
  // 如果切换到已有的模拟器 Tab,加载其设备信息
  if (emulatorIndex.value.some(e => e.uid === key)) {
    await loadDevices(key)
  }
}

// 组件卸载时停止轮询
onUnmounted(() => {
  // 停止轮询
  stopPolling()
  // 即时保存模式下，无需额外保存，数据已在编辑完成时保存
})

// 重写 handleAdd:添加后自动切换到新Tab并加载
const handleAddWithSwitch = async () => {
  await handleAdd()
  if (emulatorIndex.value.length > 0) {
    const newEmulator = emulatorIndex.value[emulatorIndex.value.length - 1]
    activeKey.value = newEmulator.uid
    saveActiveKey(activeKey.value)
    await loadDevices(newEmulator.uid)
  }
}

// 重写 handleSearch:搜索并在模态框导入后自动切换
const handleSearchAndImport = async (result: EmulatorSearchResult) => {
  await handleImportFromSearch(result)
  if (emulatorIndex.value.length > 0) {
    const newEmulator = emulatorIndex.value[emulatorIndex.value.length - 1]
    activeKey.value = newEmulator.uid
    saveActiveKey(activeKey.value)
    await loadDevices(newEmulator.uid)
  }
}

const handleSetBossKey = async (uuid: string) => {
  // 如果正在录制，不处理手动输入
  if (recordingBossKeyMap.value.get(uuid)) {
    return
  }

  const bossKeyInput = bossKeyInputMap.value[uuid] || ''
  if (bossKeyInput.trim()) {
    const editData = editingDataMap.value.get(uuid)
    if (editData) {
      // 设置为唯一的老板键（替换而不是追加）
      editData.boss_keys = [bossKeyInput.trim()]
      message.success(`老板键已设置为: ${bossKeyInput.trim()}`)
      // 即时保存老板键
      await handleSaveChange(uuid, 'boss_keys', [bossKeyInput.trim()])
      // 不清空输入框，保持显示
      // bossKeyInputMap.value[uuid] = ''
    }
  }
}

// 处理输入框变化，同步到 boss_keys（仅更新本地数据，不保存）
const handleBossKeyInputChange = (uuid: string) => {
  const bossKeyInput = bossKeyInputMap.value[uuid] || ''
  const editData = editingDataMap.value.get(uuid)
  if (editData) {
    if (bossKeyInput.trim()) {
      editData.boss_keys = [bossKeyInput.trim()]
    } else {
      editData.boss_keys = []
    }
  }
}
</script>

<template>
  <div class="emulator-page">
    <div class="page-header">
      <h1>模拟器管理</h1>
    </div>

    <div class="page-content">
      <a-spin :spinning="loading">
        <!-- 空状态：无模拟器时居中显示大按钮 -->
        <div v-if="emulatorIndex.length === 0" class="empty-state-large">
          <a-empty />
          <a-space direction="horizontal" :size="16">
            <a-button type="primary" size="large" :icon="h(SearchOutlined)" :loading="searching" @click="handleSearch">
              自动搜索模拟器
            </a-button>
            <a-button size="large" :icon="h(PlusOutlined)" @click="handleAddWithSwitch">
              手动添加模拟器
            </a-button>
          </a-space>
        </div>

        <!-- Tab 模式：有模拟器时显示 Tabs -->
        <a-tabs v-else v-model:active-key="activeKey" type="editable-card" hide-add class="emulator-tabs"
          @change="onTabChange">
          <!-- 每个模拟器一个 Tab -->
          <a-tab-pane v-for="element in emulatorIndex" :key="element.uid" :closable="false">
            <template #tab>
              <span class="tab-title">
                {{ emulatorData[element.uid]?.Info?.Name || '未命名' }}
              </span>
            </template>

            <!-- Tab 内容：配置 + 设备列表 -->
            <div class="tab-content">
              <!-- 配置区域 -->
              <div class="config-section">
                <div class="section-header">
                  <h3>模拟器配置</h3>
                  <div class="section-actions">
                    <a-spin v-if="savingMap.get(element.uid)" size="small" />
                    <a-popconfirm title="确定要删除此模拟器配置吗？" ok-text="确定" cancel-text="取消"
                      @confirm="handleDelete(element.uid)">
                      <a-button type="link" danger size="small" :icon="h(DeleteOutlined)">
                        删除
                      </a-button>
                    </a-popconfirm>
                  </div>
                </div>

                <!-- 直接可编辑的配置表单（无边框） -->
                <div class="config-form">
                  <a-descriptions :column="2" bordered size="small">
                    <a-descriptions-item label="模拟器名称">
                      <a-input v-model:value="getEditingData(element.uid).name" placeholder="输入模拟器名称" size="small"
                        :bordered="false" @input="syncNameToDisplay(element.uid, getEditingData(element.uid).name)"
                        @blur="
                          handleSaveChange(element.uid, 'name', getEditingData(element.uid).name)
                          " />
                    </a-descriptions-item>
                    <a-descriptions-item>
                      <template #label>
                        <span>模拟器类型</span>
                        <a-tooltip title="如: MuMu12, BlueStacks, LDPlayer等">
                          <QuestionCircleOutlined style="margin-left: 4px" />
                        </a-tooltip>
                      </template>
                      <a-select v-model:value="getEditingData(element.uid).type" placeholder="选择模拟器类型"
                        :options="emulatorTypeOptions" size="small" :bordered="false" style="width: 100%"
                        @change="handleSaveChange(element.uid, 'type', $event)" />
                    </a-descriptions-item>
                    <a-descriptions-item label="模拟器路径" :span="2">
                      <a-input v-model:value="getEditingData(element.uid).path" placeholder="输入或选择模拟器路径" size="small"
                        :bordered="false" @blur="
                          handleSaveChange(element.uid, 'path', getEditingData(element.uid).path)
                          " @press-enter="
                          handleSaveChange(element.uid, 'path', getEditingData(element.uid).path)
                          ">
                        <template #suffix>
                          <FolderOpenOutlined style="cursor: pointer; color: #1890ff"
                            @click="selectEmulatorPath(element.uid)" />
                        </template>
                      </a-input>
                    </a-descriptions-item>
                    <a-descriptions-item>
                      <template #label>
                        <span>最大等待时间</span>
                        <a-tooltip title="启动模拟器后的最大等待时间">
                          <QuestionCircleOutlined style="margin-left: 4px" />
                        </a-tooltip>
                      </template>
                      <a-input-number v-model:value="getEditingData(element.uid).max_wait_time" placeholder="输入最大等待时间"
                        size="small" :bordered="false" style="width: 100%" :min="10" :max="300" :step="5" suffix="秒"
                        @change="handleSaveChange(element.uid, 'max_wait_time', $event)" />
                    </a-descriptions-item>
                    <a-descriptions-item>
                      <template #label>
                        <span>老板键</span>
                        <a-tooltip title="快速隐藏模拟器的快捷键组合（MuMu模拟器不支持）">
                          <QuestionCircleOutlined style="margin-left: 4px" />
                        </a-tooltip>
                      </template>
                      <a-input v-if="getEditingData(element.uid).type !== 'mumu'"
                        v-model:value="bossKeyInputMap[element.uid]" :placeholder="recordingBossKeyMap.get(element.uid)
                            ? '请按下快捷键组合...'
                            : '输入格式如 Ctrl+Q，按回车添加'
                          " size="small" :bordered="false" :disabled="recordingBossKeyMap.get(element.uid)"
                        @press-enter="handleSetBossKey(element.uid)" @blur="handleSetBossKey(element.uid)"
                        @input="handleBossKeyInputChange(element.uid)">
                        <template #suffix>
                          <a-button v-if="!recordingBossKeyMap.get(element.uid)" type="default" size="small"
                            @click="startRecordBossKey(element.uid)">
                            录制
                          </a-button>
                          <a-button v-else type="primary" danger size="small" @click="stopRecordBossKey(element.uid)">
                            取消录制
                          </a-button>
                        </template>
                      </a-input>
                      <span v-else style="color: var(--text-color-tertiary); font-size: 12px">
                        MuMu模拟器无需配置老板键
                      </span>
                    </a-descriptions-item>
                  </a-descriptions>
                </div>
              </div>

              <!-- 设备列表区域 -->
              <div class="devices-panel">
                <div class="panel-header">
                  <h4 class="panel-title">设备列表</h4>
                </div>

                <a-spin :spinning="loadingDevices.has(element.uid)">
                  <div v-if="
                    !devicesData[element.uid] ||
                    Object.keys(devicesData[element.uid]).length === 0
                  " class="empty-devices">
                    <a-empty description="暂无设备信息">
                      <template #extra>
                        <a-button type="primary" size="small" :icon="h(PlayCircleOutlined)"
                          @click="startEmulator(element.uid, '0')">
                          启动模拟器
                        </a-button>
                      </template>
                    </a-empty>
                  </div>

                  <div v-else class="devices-grid">
                    <a-table :data-source="Object.entries(devicesData[element.uid]).map(([index, device]) => ({
                      key: index,
                      index,
                      ...device,
                    }))
                      " :columns="[
                        {
                          title: '设备',
                          dataIndex: 'index',
                          key: 'index',
                          width: 60,
                          customRender: ({ text }: any) => `#${text}`,
                        },
                        {
                          title: '状态',
                          dataIndex: 'status',
                          key: 'status',
                          width: 60,
                        },
                        { title: '名称', dataIndex: 'title', key: 'title', ellipsis: true },
                        {
                          title: 'ADB地址',
                          dataIndex: 'adb_address',
                          key: 'adb_address',
                          ellipsis: true,
                        },
                        { title: '操作', key: 'action', width: 100 },
                      ]" :pagination="false" size="small" :scroll="{ x: 'max-content', y: 'calc(100vh - 560px)' }">
                      <template #bodyCell="{ column, record }">
                        <template v-if="column.key === 'status'">
                          <a-tag :color="getDeviceStatusInfo(record.status).color" size="small">
                            {{ getDeviceStatusInfo(record.status).text }}
                          </a-tag>
                        </template>
                        <template v-else-if="column.key === 'action'">
                          <a-button v-if="canStartDevice(record.status)" type="primary" :icon="h(PlayCircleOutlined)"
                            :loading="startingDevices.has(`${element.uid}-${record.index}`)"
                            @click="startEmulator(element.uid, String(record.index))">
                            启动
                          </a-button>
                          <a-button v-else-if="canStopDevice(record.status)" danger :icon="h(StopOutlined)"
                            :loading="stoppingDevices.has(`${element.uid}-${record.index}`)"
                            @click="stopEmulator(element.uid, String(record.index))">
                            关闭
                          </a-button>
                          <a-button v-else disabled>
                            {{ getDeviceStatusInfo(record.status).text }}
                          </a-button>
                        </template>
                      </template>
                    </a-table>
                  </div>
                </a-spin>
              </div>
            </div>
          </a-tab-pane>

          <!-- 添加模拟器的特殊 Tab -->
          <template #rightExtra>
            <div class="tab-extra-actions">
              <a-dropdown :trigger="['hover']" placement="bottomRight">
                <a-button type="text" size="small" :icon="h(PlusOutlined)" />
                <template #overlay>
                  <a-menu>
                    <a-menu-item key="search" @click="handleSearch">
                      <template #icon>
                        <SearchOutlined />
                      </template>
                      自动搜索模拟器
                    </a-menu-item>
                    <a-menu-item key="add" @click="handleAddWithSwitch">
                      <template #icon>
                        <PlusOutlined />
                      </template>
                      手动添加多开器
                    </a-menu-item>
                  </a-menu>
                </template>
              </a-dropdown>
            </div>
          </template>
        </a-tabs>
      </a-spin>
    </div>

    <!-- 搜索结果导入模态框 -->
    <a-modal v-model:visible="showSearchModal" title="搜索到的模拟器" width="600" :footer="null">
      <a-spin :spinning="searching">
        <div v-if="searchResults.length === 0" class="empty-state">
          <a-empty description="未找到任何模拟器" />
        </div>

        <a-list v-else item-layout="horizontal" :data-source="searchResults">
          <template #renderItem="{ item }">
            <a-list-item>
              <template #actions>
                <a-button type="primary" size="small" @click="handleSearchAndImport(item)">
                  导入
                </a-button>
              </template>
              <a-list-item-meta :title="item.name" :description="`${item.type} - ${item.path}`" />
            </a-list-item>
          </template>
        </a-list>
      </a-spin>
    </a-modal>
  </div>
</template>

<style scoped>
.emulator-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--ant-color-bg-layout);
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding: 0;
}

.page-header h1 {
  margin: 0 0 8px 0;
  font-size: 32px;
  font-weight: 700;
  color: var(--ant-color-text);
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.page-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: transparent;
  padding: 0;
  border-radius: 0;
  box-shadow: none;
}

/* 空状态样式 */
.empty-state-large {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  text-align: center;
  padding: 60px 20px;
}

.empty-state {
  text-align: center;
  padding: 48px 0;
}

/* Tab 样式 */
.emulator-tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background-color: var(--ant-color-bg-container);
  border-radius: 12px;
  padding: 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  border: 1px solid var(--ant-color-border-secondary);
}

.emulator-tabs :deep(.ant-tabs) {
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: var(--ant-color-bg-container);
}

.emulator-tabs :deep(.ant-tabs-nav) {
  margin-bottom: 16px;
}

/* 禁止 Tab 内容滚动 */
.emulator-tabs :deep(.ant-tabs-content) {
  flex: 1;
  overflow: hidden;
}

.emulator-tabs :deep(.ant-tabs-tabpane) {
  height: 100%;
  overflow: hidden;
}

.tab-title {
  font-weight: 500;
}

.tab-extra-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  padding-right: 0;
}

.tab-content {
  height: calc(100vh - 248px);
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow: hidden;
}

/* 配置区域 */
.config-section {
  background-color: var(--ant-color-bg-container);
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  border: 1px solid var(--ant-color-border-secondary);
  padding: 16px;
  overflow: hidden;
  flex-shrink: 0;
}

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
  color: var(--ant-color-text);
  font-size: 16px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-actions {
  display: flex;
  gap: 8px;
}

.config-display {
  margin-top: 0;
}

.config-form {
  margin-top: 0;
}

/* 无边框输入优化 */
.config-form :deep(.ant-input-borderless),
.config-form :deep(.ant-input-number-borderless),
.config-form :deep(.ant-select-borderless .ant-select-selector) {
  background: transparent;
  padding: 0;
}

.config-form :deep(.ant-input-borderless:hover),
.config-form :deep(.ant-input-number-borderless:hover) {
  background: var(--bg-color-elevated);
}

.config-form :deep(.ant-input-borderless:focus),
.config-form :deep(.ant-input-number-borderless:focus) {
  background: var(--bg-color-elevated);
  box-shadow: none;
}

.config-form :deep(.ant-select-borderless:hover .ant-select-selector) {
  background: var(--bg-color-elevated) !important;
}

.config-form :deep(.ant-select-focused.ant-select-borderless .ant-select-selector) {
  background: var(--bg-color-elevated) !important;
  box-shadow: none !important;
}

/* 文件夹图标样式 */
.config-form :deep(.anticon-folder-open) {
  transition: all 0.3s;
}

.config-form :deep(.anticon-folder-open:hover) {
  color: #40a9ff !important;
  transform: scale(1.1);
}

/* 设备面板 */
.devices-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}

.panel-header {
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--ant-color-border);
}

.panel-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.empty-devices {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px 0;
  text-align: center;
}

.devices-grid {
  flex: 1;
  overflow: hidden;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.devices-grid :deep(.ant-table) {
  font-size: 14px;
  margin-bottom: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
}

.devices-grid :deep(.ant-table-container) {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.devices-grid :deep(.ant-table-content) {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.devices-grid :deep(.ant-table-body) {
  flex: 1;
  overflow-y: auto !important;
  scrollbar-width: thin;
  scrollbar-color: var(--ant-color-border) transparent;
  min-height: 0;
}

.devices-grid :deep(.ant-table-body)::-webkit-scrollbar {
  width: 6px;
}

.devices-grid :deep(.ant-table-body)::-webkit-scrollbar-track {
  background: transparent;
}

.devices-grid :deep(.ant-table-body)::-webkit-scrollbar-thumb {
  background-color: var(--ant-color-border);
  border-radius: 3px;
}

.devices-grid :deep(.ant-table-body)::-webkit-scrollbar-thumb:hover {
  background-color: var(--ant-color-border-secondary);
}

.devices-grid :deep(.ant-table-thead > tr > th) {
  padding: 8px 12px;
  background: var(--bg-color-container);
  font-weight: 500;
  position: sticky;
  top: 0;
  z-index: 10;
}

.devices-grid :deep(.ant-table-tbody > tr > td) {
  padding: 6px 12px;
}

.devices-grid :deep(.ant-table-tbody > tr:hover > td) {
  background: var(--bg-color-elevated);
}

/* 老板键列表 */
.boss-key-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

/* 暗色模式支持 */
:root {
  --bg-color-container: #f9f9f9;
  --bg-color-elevated: #ffffff;
  --border-color: #e8e8e8;
  --border-color-hover: #d9d9d9;
  --text-color-primary: rgba(0, 0, 0, 0.88);
  --text-color-secondary: rgba(0, 0, 0, 0.65);
  --text-color-tertiary: rgba(0, 0, 0, 0.45);
  --primary-color: #1890ff;
}

html.dark {
  --bg-color-container: #1f1f1f;
  --bg-color-elevated: #141414;
  --border-color: #303030;
  --border-color-hover: #434343;
  --text-color-primary: rgba(255, 255, 255, 0.88);
  --text-color-secondary: rgba(255, 255, 255, 0.65);
  --text-color-tertiary: rgba(255, 255, 255, 0.45);
  --primary-color: #1890ff;
}

html.dark .config-section,
html.dark .devices-section {
  background: #1a1a1a;
}

html.dark .page-content {
  background: #0a0a0a;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

/* 响应式 - 移动端适配 */
@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }

  .emulator-tabs {
    padding: 12px;
  }

  .tab-content {
    height: calc(100vh - 188px);
    gap: 12px;
  }

  .config-section {
    padding: 12px;
  }

  .devices-section {
    padding: 12px 12px 8px 12px;
  }

  .devices-grid :deep(.ant-table) {
    font-size: 12px;
  }
}
</style>
