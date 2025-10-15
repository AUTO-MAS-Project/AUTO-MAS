<script setup lang="ts">
import { h, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import {
  CloseOutlined,
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
  SaveOutlined,
} from '@ant-design/icons-vue'
import type { EmulatorConfigIndexItem, EmulatorConfig } from '@/api'
import { Service } from '@/api'

const emulatorTypeOptions = [
  { value: 'general', label: '通用模拟器' },
  { value: 'mumu', label: 'MuMu模拟器' },
  { value: 'ldplayer', label: '雷电模拟器' },
  { value: 'nox', label: '夜神模拟器' },
  { value: 'memu', label: '逍遥模拟器' },
  { value: 'blueStacks', label: 'BlueStacks' },
]

const loading = ref(false)
const emulatorIndex = ref<EmulatorConfigIndexItem[]>([])
const emulatorData = ref<Record<string, EmulatorConfig>>({})
const editingId = ref<string | null>(null)
const editingData = ref<EmulatorConfig>({
  Info: { Name: '', Path: '' },
  Data: { Type: 'general', BossKey: '', MaxWaitTime: 60 },
})

const loadEmulators = async () => {
  loading.value = true
  console.log('[TabEmulator] 开始加载模拟器配置...')
  try {
    console.log('[TabEmulator] 调用 API: getEmulatorApiSettingEmulatorGetPost')
    const response = await Service.getEmulatorApiSettingEmulatorGetPost({ emulatorId: null })
    console.log('[TabEmulator] API 响应:', response)
    if (response.code === 200) {
      emulatorIndex.value = response.index
      emulatorData.value = response.data
      console.log('[TabEmulator] 加载成功, index:', response.index, 'data:', response.data)
    } else {
      console.error('[TabEmulator] API 返回错误:', response)
      message.error(response.message || '加载模拟器配置失败')
    }
  } catch (e) {
    console.error('[TabEmulator] 加载模拟器配置失败', e)
    message.error('加载模拟器配置失败')
  } finally {
    loading.value = false
  }
}

const handleAdd = async () => {
  if (editingId.value) await handleSave(editingId.value)
  try {
    const response = await Service.addEmulatorApiSettingEmulatorAddPost()
    if (response.code === 200) {
      message.success('添加成功')
      await loadEmulators()
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

const handleEdit = async (uuid: string) => {
  if (editingId.value && editingId.value !== uuid) await handleSave(editingId.value)
  editingId.value = uuid
  editingData.value = JSON.parse(JSON.stringify(emulatorData.value[uuid]))
}

const handleSave = async (uuid: string) => {
  try {
    const response = await Service.updateEmulatorApiSettingEmulatorUpdatePost({
      emulatorId: uuid,
      data: editingData.value,
    })
    if (response.code === 200) {
      if (response.correctedPath && editingData.value.Info) {
        editingData.value.Info.Path = response.correctedPath
        message.success(`路径已自动更正为: ${response.correctedPath}`)
      }
      if (response.detectedType && editingData.value.Data) {
        editingData.value.Data.Type = response.detectedType as any
        message.info(`检测到模拟器类型: ${response.detectedType}`)
      }
      if (!response.correctedPath && !response.detectedType) message.success('保存成功')
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

const handleCancel = () => {
  editingId.value = null
  editingData.value = {
    Info: { Name: '', Path: '' },
    Data: { Type: 'general', BossKey: '', MaxWaitTime: 60 },
  }
}

const handleDelete = async (uuid: string) => {
  try {
    const response = await Service.deleteEmulatorApiSettingEmulatorDeletePost({ emulatorId: uuid })
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

const selectEmulatorPath = async () => {
  try {
    if (!window.electronAPI) {
      message.error('文件选择功能不可用')
      return
    }
    const paths = await (window.electronAPI as any).selectFile([
      { name: '可执行文件', extensions: ['exe'] },
      { name: '快捷方式', extensions: ['lnk'] },
      { name: '所有文件', extensions: ['*'] },
    ])
    if (!paths || paths.length === 0) {
      const folders = await (window.electronAPI as any).selectFolder()
      if (folders && folders.length > 0 && editingData.value.Info) {
        editingData.value.Info.Path = folders[0]
        message.success('模拟器路径选择成功')
      }
    } else if (editingData.value.Info) {
      editingData.value.Info.Path = paths[0]
      message.success('模拟器路径选择成功')
    }
  } catch (error) {
    console.error('选择模拟器路径失败:', error)
    message.error('选择文件失败')
  }
}

onMounted(() => {
  loadEmulators()
})
</script>

<template>
  <div class="tab-content">
    <div class="form-section">
      <div class="section-header">
        <h3>模拟器配置</h3>
        <a-button type="primary" :icon="h(PlusOutlined)" @click="handleAdd">添加模拟器</a-button>
      </div>
      <a-spin :spinning="loading">
        <div v-if="emulatorIndex.length === 0" class="empty-state">
          <a-empty description="暂无模拟器配置">
            <a-button type="primary" @click="handleAdd">添加第一个模拟器</a-button>
          </a-empty>
        </div>
        <div v-else class="emulator-list">
          <div v-for="element in emulatorIndex" :key="element.uid" class="emulator-card">
            <div class="card-header">
              <div class="card-title">
                <span v-if="editingId !== element.uid">{{ emulatorData[element.uid]?.Info?.Name || '未命名' }}</span>
                <a-input v-else-if="editingData.Info" v-model:value="editingData.Info.Name" placeholder="模拟器名称"
                  style="max-width: 300px" />
              </div>
              <div class="card-actions">
                <template v-if="editingId === element.uid">
                  <a-button type="primary" size="small" :icon="h(SaveOutlined)"
                    @click="handleSave(element.uid)">保存</a-button>
                  <a-button size="small" :icon="h(CloseOutlined)" @click="handleCancel">取消</a-button>
                </template>
                <template v-else>
                  <a-button type="link" size="small" :icon="h(EditOutlined)"
                    @click="handleEdit(element.uid)">编辑</a-button>
                  <a-popconfirm title="确定要删除此模拟器配置吗？" ok-text="确定" cancel-text="取消"
                    @confirm="handleDelete(element.uid)">
                    <a-button type="link" danger size="small" :icon="h(DeleteOutlined)">删除</a-button>
                  </a-popconfirm>
                </template>
              </div>
            </div>
            <div v-if="editingId === element.uid && editingData.Data" class="card-content">
              <a-row :gutter="16">
                <a-col :span="12">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">模拟器类型</span>
                      <a-tooltip title="如: MuMu12, BlueStacks, LDPlayer等">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-select v-model:value="editingData.Data.Type" placeholder="选择模拟器类型" :options="emulatorTypeOptions"
                      style="width: 100%" />
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
                    <a-input-number v-model:value="editingData.Data.MaxWaitTime" placeholder="输入最大等待时间"
                      style="width: 100%" :min="10" :max="300" :step="5" />
                  </div>
                </a-col>
              </a-row>
              <div v-if="editingData.Info" class="form-item-vertical">
                <div class="form-label-wrapper">
                  <span class="form-label">模拟器路径</span>
                  <a-tooltip title="模拟器可执行文件的完整路径">
                    <QuestionCircleOutlined class="help-icon" />
                  </a-tooltip>
                </div>
                <div style="display: flex; gap: 8px">
                  <a-input v-model:value="editingData.Info.Path" placeholder="输入模拟器路径" :disabled="true" />
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
                <a-input v-model:value="editingData.Data.BossKey" placeholder="输入快捷键，如 Ctrl+Q" />
              </div>
            </div>
          </div>
        </div>
      </a-spin>
    </div>
  </div>
</template>

<style scoped>
.tab-content {
  padding: 24px;
  background: var(--bg-color-container);
  border-radius: 8px;
  min-height: 100vh
}

.form-section {
  background: var(--bg-color-elevated);
  padding: 24px;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1)
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px
}

.section-header h3 {
  color: var(--text-color-primary);
  margin: 0
}

.empty-state {
  text-align: center;
  padding: 48px 0
}

.emulator-card {
  background: var(--bg-color-container);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  margin-bottom: 16px;
  padding: 16px;
  transition: all 0.3s
}

.emulator-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  border-color: var(--border-color-hover)
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px
}

.card-title {
  display: flex;
  align-items: center;
  color: var(--text-color-primary)
}

.card-title span {
  font-size: 16px;
  font-weight: 600
}

.card-actions {
  display: flex;
  gap: 8px
}

.card-content {
  margin-top: 16px
}

.form-item-vertical {
  margin-bottom: 16px
}

.form-label-wrapper {
  display: flex;
  align-items: center;
  margin-bottom: 8px
}

.form-label {
  font-weight: 500;
  margin-right: 8px;
  color: var(--text-color-primary)
}

.help-icon {
  color: var(--text-color-tertiary)
}

:root {
  --bg-color-container: #f9f9f9;
  --bg-color-elevated: #ffffff;
  --border-color: #e8e8e8;
  --border-color-hover: #d9d9d9;
  --text-color-primary: rgba(0, 0, 0, 0.88);
  --text-color-secondary: rgba(0, 0, 0, 0.65);
  --text-color-tertiary: rgba(0, 0, 0, 0.45);
  --primary-color: #1890ff
}

html.dark {
  --bg-color-container: #1f1f1f;
  --bg-color-elevated: #141414;
  --border-color: #303030;
  --border-color-hover: #434343;
  --text-color-primary: rgba(255, 255, 255, 0.88);
  --text-color-secondary: rgba(255, 255, 255, 0.65);
  --text-color-tertiary: rgba(255, 255, 255, 0.45);
  --primary-color: #1890ff
}

html.dark .emulator-card {
  background: #1a1a1a
}

html.dark .form-section {
  background: #0a0a0a;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3)
}

html.dark .emulator-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4)
}
</style>
