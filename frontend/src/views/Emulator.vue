<!-- eslint-disable vue/multi-word-component-names -->
<script setup lang="ts">
// 挂载和卸载键盘监听
import { h, onMounted, onUnmounted, ref } from 'vue'
import { useDebounceFn, useEventListener } from '@vueuse/core'
import { message } from 'ant-design-vue'
import {
  DeleteOutlined,
  FolderOpenOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
  ReloadOutlined,
  SearchOutlined,
  StopOutlined,
} from '@ant-design/icons-vue'
import type { EmulatorConfigIndexItem, EmulatorSearchResult } from '@/api'
import { Service } from '@/api'

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
    console.error('JSON 解析失败:', e)
    return fallback
  }
}

// 模拟器类型映射
const emulatorTypeOptions = [
  { value: 'general', label: '通用模拟器' },
  { value: 'mumu', label: 'MuMu模拟器' },
  { value: 'ldplayer', label: '雷电模拟器' },
  { value: 'nox', label: '夜神模拟器' },
  { value: 'memu', label: '逍遥模拟器' },
  { value: 'blueStacks', label: 'BlueStacks' },
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

// 每个模拟器的编辑数据（使用 Map 存储）
const editingDataMap = ref<Map<string, EmulatorInfo>>(new Map())

// 自动保存状态
const savingMap = ref<Map<string, boolean>>(new Map())

// 老板键录制状态（为每个模拟器单独管理）
const recordingBossKeyMap = ref<Map<string, boolean>>(new Map())
const recordedKeysMap = ref<Map<string, Set<string>>>(new Map())
const bossKeyInputMap = ref<Record<string, string>>({})

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

// 自动保存（使用 VueUse 的 useDebounceFn 实现防抖）
// 注意：useDebounceFn 返回的是防抖函数本身，不是带控制方法的对象
const autoSaveFn = useDebounceFn((uuid: string) => {
  handleSave(uuid, true) // true 表示静默保存
}, 1000)

// 封装防抖保存调用
const autoSave = (uuid: string) => {
  autoSaveFn(uuid)
}

// 立即保存（不防抖）- 直接调用 handleSave，绕过防抖
const saveImmediately = async (uuid: string, skipReload = false) => {
  // 直接执行保存，不经过防抖
  // skipReload: 在Tab切换等场景下，跳过重新加载以避免干扰切换流程
  await handleSave(uuid, true, skipReload)
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
    console.error('加载模拟器配置失败', e)
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
      message.success('添加成功')
      await loadEmulators()
      // 自动切换到新模拟器
      activeKey.value = response.emulatorId
      saveActiveKey(activeKey.value)
      await loadDevices(response.emulatorId)
    } else {
      message.error(response.message || '添加失败')
    }
  } catch (e) {
    console.error('添加模拟器失败', e)
    message.error('添加模拟器失败')
  }
}

// 保存编辑
const handleSave = async (uuid: string, silent = false, skipReload = false) => {
  const editData = editingDataMap.value.get(uuid)
  if (!editData) {
    if (!silent) message.error('未找到编辑数据')
    return
  }

  savingMap.value.set(uuid, true)

  try {
    // 将前端的扁平结构转换为后端需要的分组结构
    const configData = {
      Info: {
        Name: editData.name,
        Path: editData.path,
      },
      Data: {
        Type: editData.type as 'general' | 'mumu' | 'ldplayer' | 'nox' | 'memu' | 'blueStacks',
        MaxWaitTime: editData.max_wait_time,
        BossKey: JSON.stringify(editData.boss_keys),
      },
    }

    const response = await Service.updateEmulatorApiEmulatorUpdatePost({
      emulatorId: uuid,
      data: configData,
    })
    if (response.code === 200) {
      if (!silent) message.success('保存成功')

      // 保存成功后重新从后端获取最新配置（除非明确跳过）
      if (!skipReload) {
        await loadEmulators()
      }
    } else {
      if (!silent) message.error(response.message || '保存失败')
    }
  } catch (e) {
    console.error('保存模拟器配置失败', e)
    if (!silent) message.error('保存模拟器配置失败')
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
      message.success('删除成功')

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
    console.error('删除模拟器失败', e)
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
    console.error('搜索模拟器失败', e)
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
    console.error('导入模拟器失败', e)
    message.error('导入模拟器失败')
  }
}

// 展开/折叠设备信息（已废弃，Tab模式下不需要）
// const toggleDevices = async (uuid: string) => {
//   await loadDevices(uuid)
// }

// 加载设备信息 - 使用新的status API
const loadDevices = async (uuid: string) => {
  loadingDevices.value.add(uuid)
  loadingDevices.value = new Set(loadingDevices.value)

  try {
    const response = await Service.getStatusApiEmulatorStatusPost({
      emulatorId: uuid,
    })

    if (response.code === 200) {
      devicesData.value[uuid] = response.data || {}
    } else {
      message.error(response.message || '获取设备信息失败')
    }
  } catch (e) {
    console.error('获取设备信息失败', e)
    message.error('获取设备信息失败')
  } finally {
    loadingDevices.value.delete(uuid)
    loadingDevices.value = new Set(loadingDevices.value)
  }
}

// 刷新设备信息
const refreshDevices = async (uuid: string) => {
  await loadDevices(uuid)
  message.success('刷新成功')
}

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
    console.error('启动模拟器失败', e)
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
    console.error('关闭模拟器失败', e)
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
      editData.path = paths[0]
      message.success('模拟器路径选择成功')
      // 触发自动保存
      autoSave(uuid)
    }
  } catch (error) {
    console.error('选择模拟器路径失败:', error)
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

const handleKeyUp = (event: KeyboardEvent) => {
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
      autoSave(recordingUuid)
    }
    recordingBossKeyMap.value.delete(recordingUuid)
    recordedKeysMap.value.delete(recordingUuid)
  }
}

// 使用 VueUse 的 useEventListener 替代手动管理事件监听器
useEventListener(document, 'keydown', handleKeyDown)
useEventListener(document, 'keyup', handleKeyUp)

onMounted(() => {
  loadEmulators()
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
  // 切换前先立即保存当前 Tab 的数据（跳过重新加载以避免干扰切换）
  if (activeKey.value && editingDataMap.value.has(activeKey.value)) {
    await saveImmediately(activeKey.value, true) // true = skipReload
  }

  activeKey.value = key
  saveActiveKey(key)
  // 如果切换到已有的模拟器 Tab,加载其设备信息
  if (emulatorIndex.value.some(e => e.uid === key)) {
    await loadDevices(key)
  }
}

// 组件卸载时保存所有数据
onUnmounted(async () => {
  // 立即保存所有有数据的模拟器（防抖会自动失效）
  const savePromises = Array.from(editingDataMap.value.keys()).map(uuid => handleSave(uuid, true))
  await Promise.all(savePromises)
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

// 重写 loadEmulators,加载后自动选择第一个（挂载时使用）
onMounted(async () => {
  await loadEmulators()
  await onEmulatorsLoaded()
})

const handleSetBossKey = (uuid: string) => {
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
      autoSave(uuid)
      // 不清空输入框，保持显示
      // bossKeyInputMap.value[uuid] = ''
    }
  }
}

// 处理输入框变化，同步到 boss_keys
const handleBossKeyInputChange = (uuid: string) => {
  const bossKeyInput = bossKeyInputMap.value[uuid] || ''
  const editData = editingDataMap.value.get(uuid)
  if (editData) {
    if (bossKeyInput.trim()) {
      editData.boss_keys = [bossKeyInput.trim()]
    } else {
      editData.boss_keys = []
    }
    autoSave(uuid)
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
            <a-button
              type="primary"
              size="large"
              :icon="h(SearchOutlined)"
              :loading="searching"
              @click="handleSearch"
            >
              自动搜索多开器
            </a-button>
            <a-button size="large" :icon="h(PlusOutlined)" @click="handleAddWithSwitch">
              手动添加多开器
            </a-button>
          </a-space>
        </div>

        <!-- Tab 模式：有模拟器时显示 Tabs -->
        <a-tabs
          v-else
          v-model:active-key="activeKey"
          type="editable-card"
          hide-add
          class="emulator-tabs"
          @change="onTabChange"
        >
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
                  <h3>多开器配置</h3>
                  <div class="section-actions">
                    <a-spin v-if="savingMap.get(element.uid)" size="small" />
                    <a-popconfirm
                      title="确定要删除此模拟器配置吗？"
                      ok-text="确定"
                      cancel-text="取消"
                      @confirm="handleDelete(element.uid)"
                    >
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
                      <a-input
                        v-model:value="getEditingData(element.uid).name"
                        placeholder="输入模拟器名称"
                        size="small"
                        :bordered="false"
                        @input="syncNameToDisplay(element.uid, getEditingData(element.uid).name)"
                        @change="autoSave(element.uid)"
                      />
                    </a-descriptions-item>
                    <a-descriptions-item>
                      <template #label>
                        <span>模拟器类型</span>
                        <a-tooltip title="如: MuMu12, BlueStacks, LDPlayer等">
                          <QuestionCircleOutlined style="margin-left: 4px" />
                        </a-tooltip>
                      </template>
                      <a-select
                        v-model:value="getEditingData(element.uid).type"
                        placeholder="选择模拟器类型"
                        :options="emulatorTypeOptions"
                        size="small"
                        :bordered="false"
                        style="width: 100%"
                        @change="autoSave(element.uid)"
                      />
                    </a-descriptions-item>
                    <a-descriptions-item label="模拟器路径" :span="2">
                      <a-input
                        v-model:value="getEditingData(element.uid).path"
                        placeholder="输入或选择模拟器路径"
                        size="small"
                        :bordered="false"
                        @change="autoSave(element.uid)"
                      >
                        <template #suffix>
                          <FolderOpenOutlined
                            style="cursor: pointer; color: #1890ff"
                            @click="selectEmulatorPath(element.uid)"
                          />
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
                      <a-input-number
                        v-model:value="getEditingData(element.uid).max_wait_time"
                        placeholder="输入最大等待时间"
                        size="small"
                        :bordered="false"
                        style="width: 100%"
                        :min="10"
                        :max="300"
                        :step="5"
                        suffix="秒"
                        @change="autoSave(element.uid)"
                      />
                    </a-descriptions-item>
                    <a-descriptions-item>
                      <template #label>
                        <span>老板键</span>
                        <a-tooltip title="快速隐藏模拟器的快捷键组合">
                          <QuestionCircleOutlined style="margin-left: 4px" />
                        </a-tooltip>
                      </template>
                      <a-input
                        v-model:value="bossKeyInputMap[element.uid]"
                        :placeholder="
                          recordingBossKeyMap.get(element.uid)
                            ? '请按下快捷键组合...'
                            : '输入格式如 Ctrl+Q，按回车添加'
                        "
                        size="small"
                        :bordered="false"
                        :disabled="recordingBossKeyMap.get(element.uid)"
                        @press-enter="handleSetBossKey(element.uid)"
                        @change="handleBossKeyInputChange(element.uid)"
                      >
                        <template #suffix>
                          <a-button
                            v-if="!recordingBossKeyMap.get(element.uid)"
                            type="default"
                            size="small"
                            @click="startRecordBossKey(element.uid)"
                          >
                            录制
                          </a-button>
                          <a-button
                            v-else
                            type="primary"
                            danger
                            size="small"
                            @click="stopRecordBossKey(element.uid)"
                          >
                            取消录制
                          </a-button>
                        </template>
                      </a-input>
                    </a-descriptions-item>
                  </a-descriptions>
                </div>
              </div>

              <!-- 设备列表区域 -->
              <div class="devices-section">
                <div class="section-header">
                  <h3>设备列表</h3>
                  <a-button
                    size="small"
                    :icon="h(ReloadOutlined)"
                    :loading="loadingDevices.has(element.uid)"
                    @click="refreshDevices(element.uid)"
                  >
                    刷新
                  </a-button>
                </div>

                <a-spin :spinning="loadingDevices.has(element.uid)">
                  <div
                    v-if="
                      !devicesData[element.uid] ||
                      Object.keys(devicesData[element.uid]).length === 0
                    "
                    class="empty-devices"
                  >
                    <a-empty description="暂无设备信息">
                      <template #extra>
                        <a-space>
                          <a-button
                            type="primary"
                            size="small"
                            :icon="h(ReloadOutlined)"
                            :loading="loadingDevices.has(element.uid)"
                            @click="refreshDevices(element.uid)"
                          >
                            刷新设备列表
                          </a-button>
                          <a-button
                            size="small"
                            :icon="h(PlayCircleOutlined)"
                            @click="startEmulator(element.uid, '0')"
                          >
                            启动多开器
                          </a-button>
                        </a-space>
                      </template>
                    </a-empty>
                  </div>

                  <div v-else class="devices-grid">
                    <div
                      v-for="(device, index) in devicesData[element.uid]"
                      :key="index"
                      class="device-card-item"
                    >
                      <div class="device-header">
                        <span class="device-index">设备 #{{ index }}</span>
                        <a-tag :color="device.status === '0' ? 'success' : 'default'">
                          {{ device.status === '0' ? '在线' : '离线' }}
                        </a-tag>
                      </div>
                      <div class="device-info">
                        <div class="info-item">
                          <span class="info-label">名称:</span>
                          <span class="info-value">{{ device.title }}</span>
                        </div>
                        <div class="info-item">
                          <span class="info-label">状态码:</span>
                          <span class="info-value">{{ device.status }}</span>
                        </div>
                      </div>
                      <div class="device-actions">
                        <a-button
                          type="primary"
                          size="small"
                          :icon="h(PlayCircleOutlined)"
                          :loading="startingDevices.has(`${element.uid}-${index}`)"
                          :disabled="device.status === '0'"
                          @click="startEmulator(element.uid, String(index))"
                        >
                          启动
                        </a-button>
                        <a-button
                          danger
                          size="small"
                          :icon="h(StopOutlined)"
                          :loading="stoppingDevices.has(`${element.uid}-${index}`)"
                          :disabled="device.status !== '0'"
                          @click="stopEmulator(element.uid, String(index))"
                        >
                          关闭
                        </a-button>
                      </div>
                    </div>
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
  padding: 16px;
  background: var(--bg-color-container);
  min-height: 100vh;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.page-header h1 {
  color: var(--text-color-primary);
  margin: 0;
  font-size: 22px;
  font-weight: 600;
}

.page-content {
  background: var(--bg-color-elevated);
  padding: 16px;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  min-height: 500px;
}

/* 空状态样式 */
.empty-state-large {
  text-align: center;
  padding: 120px 0;
  min-height: 400px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
}

.empty-state {
  text-align: center;
  padding: 48px 0;
}

/* Tab 样式 */
.emulator-tabs {
  min-height: 500px;
}

.emulator-tabs :deep(.ant-tabs-nav) {
  margin-bottom: 16px;
}

/* 禁止 Tab 内容滚动 */
.emulator-tabs :deep(.ant-tabs-content) {
  overflow: visible !important;
}

.emulator-tabs :deep(.ant-tabs-tabpane) {
  overflow: visible !important;
}

.tab-title {
  font-weight: 500;
}

.tab-extra-actions {
  display: flex;
  gap: 4px;
  align-items: center;
  padding-right: 8px;
}

.tab-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 配置区域 */
.config-section {
  background: var(--bg-color-container);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 12px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.section-header h3 {
  margin: 0;
  color: var(--text-color-primary);
  font-size: 15px;
  font-weight: 500;
}

.section-actions {
  display: flex;
  gap: 8px;
}

.config-display {
  margin-top: 12px;
}

.config-form {
  margin-top: 12px;
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

/* 设备列表区域 */
.devices-section {
  background: var(--bg-color-container);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 12px;
}

.empty-devices {
  padding: 48px 0;
  text-align: center;
}

.devices-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
  margin-top: 12px;
}

.device-card-item {
  background: var(--bg-color-elevated);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 10px;
  transition: all 0.3s;
}

.device-card-item:hover {
  border-color: var(--primary-color);
  box-shadow: 0 2px 8px rgba(24, 144, 255, 0.1);
}

.device-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.device-index {
  font-weight: 500;
  color: var(--text-color-primary);
}

.device-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 10px;
}

.info-item {
  display: flex;
  align-items: center;
}

.info-label {
  color: var(--text-color-secondary);
  margin-right: 8px;
  min-width: 60px;
  font-size: 12px;
}

.info-value {
  color: var(--text-color-primary);
  font-size: 12px;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.device-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
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

html.dark .device-card-item:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
}
</style>
