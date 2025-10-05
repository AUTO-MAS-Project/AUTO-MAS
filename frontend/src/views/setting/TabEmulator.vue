<script setup lang="ts">
// 挂载和卸载键盘监听
import { h, onMounted, onUnmounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import {
  CloseOutlined,
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
  SaveOutlined,
  SearchOutlined,
} from '@ant-design/icons-vue'
import type { EmulatorIndexItem, EmulatorInfo, EmulatorSearchResult } from '@/api'
import { Service } from '@/api'

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
const emulatorIndex = ref<EmulatorIndexItem[]>([])
const emulatorData = ref<Record<string, EmulatorInfo>>({})
const searchResults = ref<EmulatorSearchResult[]>([])
const showSearchModal = ref(false)

// 设备信息相关状态
const expandedEmulators = ref<Set<string>>(new Set())
const devicesData = ref<Record<string, Record<string, { title: string; status: string }>>>({})
const loadingDevices = ref<Set<string>>(new Set())

// 编辑状态
const editingId = ref<string | null>(null)
const editingData = ref<EmulatorInfo>({
  name: '',
  type: '',
  path: '',
  max_wait_time: 60,
  boss_keys: [],
})

// 老板键录制状态
const recordingBossKey = ref(false)
const recordedKeys = ref<Set<string>>(new Set())
const bossKeyInput = ref('')

// 加载模拟器列表
const loadEmulators = async () => {
  loading.value = true
  try {
    const response = await Service.getEmulatorsApiSettingEmulatorGetPost({
      emulatorId: null,
    })
    if (response.code === 200) {
      emulatorIndex.value = response.index
      emulatorData.value = response.data
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
  // 如果有正在编辑的模拟器，先保存
  if (editingId.value) {
    await handleSave(editingId.value)
  }

  try {
    const response = await Service.addEmulatorApiSettingEmulatorAddPost()
    if (response.code === 200) {
      message.success('添加成功')
      await loadEmulators()
      // 自动进入编辑模式，焦点切换到新模拟器
      editingId.value = response.emulatorId
      editingData.value = { ...response.data }
    } else {
      message.error(response.message || '添加失败')
    }
  } catch (e) {
    console.error('添加模拟器失败', e)
    message.error('添加模拟器失败')
  }
}

// 开始编辑
const handleEdit = async (uuid: string) => {
  // 如果有正在编辑的其他模拟器，先保存
  if (editingId.value && editingId.value !== uuid) {
    await handleSave(editingId.value)
  }

  editingId.value = uuid
  editingData.value = { ...emulatorData.value[uuid] }
}

// 保存编辑
const handleSave = async (uuid: string) => {
  try {
    const response = await Service.updateEmulatorApiSettingEmulatorUpdatePost({
      emulatorId: uuid,
      data: editingData.value,
    })
    if (response.code === 200) {
      message.success('保存成功')
      await loadEmulators()
      editingId.value = null
    } else {
      message.error(response.message || '保存失败')
    }
  } catch (e) {
    console.error('保存模拟器配置失败', e)
    message.error('保存模拟器配置失败')
  }
}

// 取消编辑
const handleCancel = () => {
  editingId.value = null
  editingData.value = {
    name: '',
    type: '',
    path: '',
    max_wait_time: 60,
    boss_keys: [],
  }
  recordingBossKey.value = false
  recordedKeys.value.clear()
}

// 删除模拟器
const handleDelete = async (uuid: string) => {
  try {
    const response = await Service.deleteEmulatorApiSettingEmulatorDeletePost({
      emulatorId: uuid,
    })
    if (response.code === 200) {
      message.success('删除成功')
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
    const response = await Service.searchEmulatorsApiSettingEmulatorSearchPost()
    if (response.code === 200) {
      searchResults.value = response.emulators
      if (searchResults.value.length > 0) {
        showSearchModal.value = true
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
    const response = await Service.addEmulatorApiSettingEmulatorAddPost()
    if (response.code === 200) {
      // 更新新添加的模拟器配置
      const updateResponse = await Service.updateEmulatorApiSettingEmulatorUpdatePost({
        emulatorId: response.emulatorId,
        data: {
          name: result.name,
          type: result.type,
          path: result.path,
          max_wait_time: 60,
          boss_keys: [],
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

// 展开/折叠设备信息
const toggleDevices = async (uuid: string) => {
  if (expandedEmulators.value.has(uuid)) {
    // 如果已展开，则折叠
    expandedEmulators.value.delete(uuid)
    expandedEmulators.value = new Set(expandedEmulators.value)
  } else {
    // 如果未展开，则加载并展开
    expandedEmulators.value.add(uuid)
    expandedEmulators.value = new Set(expandedEmulators.value)

    // 如果还没有加载设备信息，则加载
    if (!devicesData.value[uuid]) {
      await loadDevices(uuid)
    }
  }
}

// 加载设备信息
const loadDevices = async (uuid: string) => {
  loadingDevices.value.add(uuid)
  loadingDevices.value = new Set(loadingDevices.value)

  try {
    // const response = await Service.getEmulatorDevicesApiSettingEmulatorDevicesPost({
    //   emulatorId: uuid,
    // })
    // if (response.code === 200) {
    //   devicesData.value[uuid] = response.devices
    // } else {
    //   message.error(response.message || '获取设备信息失败')
    //   expandedEmulators.value.delete(uuid)
    //   expandedEmulators.value = new Set(expandedEmulators.value)
    // }

    // 临时数据用于测试UI
    await new Promise(resolve => setTimeout(resolve, 500))
    devicesData.value[uuid] = {
      '0': { title: '模拟器-1', status: '0' },
      '1': { title: '模拟器-2', status: '1' },
    }
  } catch (e) {
    console.error('获取设备信息失败', e)
    message.error('获取设备信息失败')
    // 加载失败时取消展开
    expandedEmulators.value.delete(uuid)
    expandedEmulators.value = new Set(expandedEmulators.value)
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

// 路径选择
const selectEmulatorPath = async () => {
  try {
    if (!window.electronAPI) {
      message.error('文件选择功能不可用，请在 Electron 环境中运行')
      return
    }

    const paths = await (window.electronAPI as any).selectFile([
      { name: '可执行文件', extensions: ['exe'] },
      { name: '所有文件', extensions: ['*'] },
    ])
    if (paths && paths.length > 0) {
      editingData.value.path = paths[0]
      message.success('模拟器路径选择成功')
    }
  } catch (error) {
    console.error('选择模拟器路径失败:', error)
    message.error('选择文件失败')
  }
}

// 开始录制老板键
const startRecordBossKey = () => {
  recordingBossKey.value = true
  recordedKeys.value.clear()
  bossKeyInput.value = ''
  message.info('请按下快捷键组合...')
}

// 停止录制老板键
const stopRecordBossKey = () => {
  recordingBossKey.value = false
  recordedKeys.value.clear()
  bossKeyInput.value = ''
}

// 键盘事件处理
const handleKeyDown = (event: KeyboardEvent) => {
  if (!recordingBossKey.value) return

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
    recordedKeys.value = new Set(keys)
  }
}

const handleKeyUp = (event: KeyboardEvent) => {
  if (!recordingBossKey.value) return

  event.preventDefault()
  event.stopPropagation()

  // 如果已经记录了按键，停止录制并设置为老板键
  if (recordedKeys.value.size > 0) {
    const keyCombo = Array.from(recordedKeys.value).join('+')
    editingData.value.boss_keys = [keyCombo]
    message.success(`已设置老板键: ${keyCombo}`)
    recordingBossKey.value = false
    recordedKeys.value.clear()
  }
}

onMounted(() => {
  loadEmulators()
  document.addEventListener('keydown', handleKeyDown)
  document.addEventListener('keyup', handleKeyUp)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeyDown)
  document.removeEventListener('keyup', handleKeyUp)
})

const handleSetBossKey = () => {
  if (bossKeyInput.value.trim()) {
    editingData.value.boss_keys = [bossKeyInput.value.trim()]
    bossKeyInput.value = ''
    message.success('老板键已设置')
  }
}

const handleRemoveBossKey = () => {
  editingData.value.boss_keys = []
  message.success('老板键已清除')
}
</script>

<template>
  <div class="tab-content">
    <div class="form-section">
      <div class="section-header">
        <h3>模拟器配置</h3>
        <div style="display: flex; gap: 8px">
          <a-button
            type="primary"
            :icon="h(SearchOutlined)"
            :loading="searching"
            @click="handleSearch"
          >
            自动搜索
          </a-button>
          <a-button type="primary" :icon="h(PlusOutlined)" @click="handleAdd">
            添加模拟器
          </a-button>
        </div>
      </div>

      <a-spin :spinning="loading">
        <div v-if="emulatorIndex.length === 0" class="empty-state">
          <a-empty description="暂无模拟器配置">
            <a-button type="primary" @click="handleAdd">添加第一个模拟器</a-button>
          </a-empty>
        </div>

        <div v-else class="emulator-list">
          <div v-for="element in emulatorIndex" :key="element.uuid" class="emulator-card">
            <div class="card-header">
              <div class="card-title">
                <span v-if="editingId !== element.uuid">{{
                  emulatorData[element.uuid]?.name || '未命名'
                }}</span>
                <a-input
                  v-else
                  v-model:value="editingData.name"
                  placeholder="模拟器名称"
                  style="max-width: 300px"
                />
              </div>
              <div class="card-actions">
                <template v-if="editingId === element.uuid">
                  <a-button
                    type="primary"
                    size="small"
                    :icon="h(SaveOutlined)"
                    @click="handleSave(element.uuid)"
                  >
                    保存
                  </a-button>
                  <a-button size="small" :icon="h(CloseOutlined)" @click="handleCancel">
                    取消
                  </a-button>
                </template>
                <template v-else>
                  <a-button type="link" size="small" @click="toggleDevices(element.uuid)">
                    {{ expandedEmulators.has(element.uuid) ? '折叠设备' : '查看设备' }}
                  </a-button>
                  <a-button
                    type="link"
                    size="small"
                    :icon="h(EditOutlined)"
                    @click="handleEdit(element.uuid)"
                  >
                    编辑
                  </a-button>
                  <a-popconfirm
                    title="确定要删除此模拟器配置吗？"
                    ok-text="确定"
                    cancel-text="取消"
                    @confirm="handleDelete(element.uuid)"
                  >
                    <a-button type="link" danger size="small" :icon="h(DeleteOutlined)">
                      删除
                    </a-button>
                  </a-popconfirm>
                </template>
              </div>
            </div>

            <div v-if="editingId === element.uuid" class="card-content">
              <a-row :gutter="16">
                <a-col :span="12">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">模拟器类型</span>
                      <a-tooltip title="如: MuMu12, BlueStacks, LDPlayer等">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-select
                      v-model:value="editingData.type"
                      placeholder="选择模拟器类型"
                      :options="emulatorTypeOptions"
                      style="width: 100%"
                    />
                  </div>
                </a-col>
                <a-col :span="12">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">最大等待时间（秒）</span>
                      <a-tooltip title="启动模拟器后的最大等待时间">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-input-number
                      v-model:value="editingData.max_wait_time"
                      placeholder="输入最大等待时间"
                      style="width: 100%"
                      min="10"
                      max="300"
                      step="5"
                    />
                  </div>
                </a-col>
              </a-row>

              <div class="form-item-vertical">
                <div class="form-label-wrapper">
                  <span class="form-label">模拟器路径</span>
                  <a-tooltip title="模拟器可执行文件的完整路径">
                    <QuestionCircleOutlined class="help-icon" />
                  </a-tooltip>
                </div>
                <div style="display: flex; gap: 8px">
                  <a-input
                    v-model:value="editingData.path"
                    placeholder="输入模拟器路径"
                    :disabled="true"
                  />
                  <a-button @click="selectEmulatorPath">选择路径</a-button>
                </div>
              </div>

              <div class="form-item-vertical">
                <div class="form-label-wrapper">
                  <span class="form-label">老板键</span>
                  <a-tooltip title="快速隐藏模拟器的快捷键组合">
                    <QuestionCircleOutlined class="help-icon" />
                  </a-tooltip>
                </div>
                <div style="display: flex; gap: 8px; margin-bottom: 8px">
                  <a-input
                    v-model:value="bossKeyInput"
                    :placeholder="
                      recordingBossKey ? '请按下快捷键组合...' : '输入快捷键，如 Ctrl+Q'
                    "
                    :disabled="recordingBossKey"
                    @press-enter="handleSetBossKey"
                  />
                  <a-button v-if="!recordingBossKey" type="default" @click="startRecordBossKey">
                    录制
                  </a-button>
                  <a-button v-else type="primary" danger @click="stopRecordBossKey">
                    取消录制
                  </a-button>
                  <a-button :disabled="recordingBossKey" @click="handleSetBossKey"> 设置 </a-button>
                </div>
                <div
                  v-if="editingData.boss_keys && editingData.boss_keys.length > 0"
                  class="boss-key-list"
                >
                  <a-tag
                    v-for="key in editingData.boss_keys"
                    :key="key"
                    closable
                    @close="handleRemoveBossKey()"
                  >
                    {{ key }}
                  </a-tag>
                </div>
              </div>
            </div>

            <!-- 设备信息展示区域 -->
            <div v-if="expandedEmulators.has(element.uuid)" class="devices-section">
              <div class="devices-header">
                <h4>设备列表</h4>
                <a-button
                  size="small"
                  :loading="loadingDevices.has(element.uuid)"
                  @click="refreshDevices(element.uuid)"
                >
                  刷新
                </a-button>
              </div>

              <a-spin :spinning="loadingDevices.has(element.uuid)">
                <div
                  v-if="
                    !devicesData[element.uuid] ||
                    Object.keys(devicesData[element.uuid]).length === 0
                  "
                  class="empty-devices"
                >
                  <a-empty description="暂无设备信息" />
                </div>

                <div v-else class="devices-grid">
                  <div
                    v-for="(device, index) in devicesData[element.uuid]"
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
                  </div>
                </div>
              </a-spin>
            </div>
          </div>
        </div>
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
                <a-button type="primary" size="small" @click="handleImportFromSearch(item)">
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
.tab-content {
  padding: 24px;
  background: var(--bg-color-container);
  border-radius: 8px;
  min-height: 100vh;
}

.form-section {
  background: var(--bg-color-elevated);
  padding: 24px;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.section-header h3 {
  color: var(--text-color-primary);
  margin: 0;
}

.empty-state {
  text-align: center;
  padding: 48px 0;
}

.emulator-card {
  background: var(--bg-color-container);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  margin-bottom: 16px;
  padding: 16px;
  transition: all 0.3s;
}

.emulator-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  border-color: var(--border-color-hover);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.card-title {
  display: flex;
  align-items: center;
  color: var(--text-color-primary);
}

.card-title span {
  font-size: 16px;
  font-weight: 600;
}

.drag-handle {
  cursor: move;
  margin-right: 8px;
  color: var(--text-color-secondary);
  transition: color 0.3s;
}

.drag-handle:hover {
  color: var(--primary-color);
}

.card-actions {
  display: flex;
  gap: 8px;
}

.card-content {
  margin-top: 16px;
}

.form-item-vertical {
  margin-bottom: 16px;
}

.form-label-wrapper {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
}

.form-label {
  font-weight: 500;
  margin-right: 8px;
  color: var(--text-color-primary);
}

.help-icon {
  color: var(--text-color-tertiary);
}

.boss-key-list {
  margin-top: 8px;
}

/* 设备信息展示样式 */
.devices-section {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border-color);
}

.devices-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.devices-header h4 {
  margin: 0;
  color: var(--text-color-primary);
}

.empty-devices {
  padding: 24px 0;
  text-align: center;
}

.devices-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}

.device-card-item {
  background: var(--bg-color-elevated);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 12px;
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
  gap: 6px;
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

.ant-list-item-meta {
  flex: 1;
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

/* 暗色模式下的额外调整 */
html.dark .emulator-card {
  background: #1a1a1a;
}

html.dark .form-section {
  background: #0a0a0a;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

html.dark .emulator-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
}
</style>
