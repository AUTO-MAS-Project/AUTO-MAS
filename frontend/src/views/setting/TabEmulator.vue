<script setup lang="ts">
import { h, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import {
  CloseOutlined,
  DeleteOutlined,
  EditOutlined,
  HolderOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
  SaveOutlined,
  SearchOutlined,
} from '@ant-design/icons-vue'
import draggable from 'vuedraggable'
import type { EmulatorIndexItem, EmulatorInfo, EmulatorSearchResult } from '@/api'
import { Service } from '@/api'

// 数据状态
const loading = ref(false)
const searching = ref(false)
const emulatorIndex = ref<EmulatorIndexItem[]>([])
const emulatorData = ref<Record<string, EmulatorInfo>>({})
const searchResults = ref<EmulatorSearchResult[]>([])
const showSearchModal = ref(false)

// 编辑状态
const editingId = ref<string | null>(null)
const editingData = ref<EmulatorInfo>({
  name: '',
  type: '',
  path: '',
  max_wait_time: 60,
  boss_keys: [],
})

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
  try {
    const response = await Service.addEmulatorApiSettingEmulatorAddPost()
    if (response.code === 200) {
      message.success('添加成功')
      await loadEmulators()
      // 自动进入编辑模式
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
const handleEdit = (uuid: string) => {
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

// 拖拽排序
const handleDragEnd = async (newIndex: EmulatorIndexItem[]) => {
  try {
    const indexList = newIndex.map(item => item.uuid)
    const response = await Service.reorderEmulatorApiSettingEmulatorOrderPost({
      indexList,
    })
    if (response.code === 200) {
      message.success('排序已保存')
      emulatorIndex.value = newIndex
    } else {
      message.error(response.message || '排序保存失败')
      await loadEmulators() // 恢复原顺序
    }
  } catch (e) {
    console.error('保存排序失败', e)
    message.error('保存排序失败')
    await loadEmulators() // 恢复原顺序
  }
}

// Boss键输入处理
const bossKeyInput = ref('')
const handleAddBossKey = () => {
  if (bossKeyInput.value.trim() && editingData.value.boss_keys) {
    if (!editingData.value.boss_keys.includes(bossKeyInput.value.trim())) {
      editingData.value.boss_keys.push(bossKeyInput.value.trim())
      bossKeyInput.value = ''
    }
  }
}

const handleRemoveBossKey = (key: string) => {
  if (editingData.value.boss_keys) {
    editingData.value.boss_keys = editingData.value.boss_keys.filter(k => k !== key)
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
        <div style="display: flex; gap: 8px">
          <a-button
            type="primary"
            :icon="h(SearchOutlined)"
            @click="handleSearch"
            :loading="searching"
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

        <draggable
          v-else
          v-model="emulatorIndex"
          item-key="uuid"
          @end="handleDragEnd"
          handle=".drag-handle"
          animation="200"
        >
          <template #item="{ element }">
            <div class="emulator-card">
              <div class="card-header">
                <div class="card-title">
                  <HolderOutlined class="drag-handle" />
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
                      <a-input v-model:value="editingData.type" placeholder="模拟器类型" />
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
                        :min="10"
                        :max="300"
                        style="width: 100%"
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
                  <a-input v-model:value="editingData.path" placeholder="C:\Program Files\..." />
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
                      placeholder="输入快捷键，如 Ctrl+Q"
                      @press-enter="handleAddBossKey"
                    />
                    <a-button @click="handleAddBossKey">添加</a-button>
                  </div>
                  <div
                    v-if="editingData.boss_keys && editingData.boss_keys.length > 0"
                    class="boss-key-list"
                  >
                    <a-tag
                      v-for="key in editingData.boss_keys"
                      :key="key"
                      closable
                      @close="handleRemoveBossKey(key)"
                    >
                      {{ key }}
                    </a-tag>
                  </div>
                </div>
              </div>

              <div v-else class="card-content card-content-view">
                <div class="info-row">
                  <span class="info-label">类型：</span>
                  <span class="info-value">{{ emulatorData[element.uuid]?.type || '未设置' }}</span>
                </div>
                <div class="info-row">
                  <span class="info-label">路径：</span>
                  <span class="info-value">{{ emulatorData[element.uuid]?.path || '未设置' }}</span>
                </div>
                <div class="info-row">
                  <span class="info-label">等待时间：</span>
                  <span class="info-value"
                    >{{ emulatorData[element.uuid]?.max_wait_time || 60 }} 秒</span
                  >
                </div>
                <div v-if="emulatorData[element.uuid]?.boss_keys?.length" class="info-row">
                  <span class="info-label">老板键：</span>
                  <span class="info-value">
                    <a-tag v-for="key in emulatorData[element.uuid].boss_keys" :key="key">{{
                      key
                    }}</a-tag>
                  </span>
                </div>
              </div>
            </div>
          </template>
        </draggable>
      </a-spin>
    </div>

    <!-- 搜索结果弹窗 -->
    <a-modal v-model:open="showSearchModal" title="搜索到的模拟器" :footer="null" width="600px">
      <div class="search-results">
        <a-list :data-source="searchResults" :loading="searching">
          <template #renderItem="{ item }">
            <a-list-item>
              <a-list-item-meta>
                <template #title>{{ item.name }}</template>
                <template #description>
                  <div>类型: {{ item.type }}</div>
                  <div>路径: {{ item.path }}</div>
                </template>
              </a-list-item-meta>
              <template #actions>
                <a-button type="primary" size="small" @click="handleImportFromSearch(item)">
                  导入
                </a-button>
              </template>
            </a-list-item>
          </template>
        </a-list>
      </div>
    </a-modal>
  </div>
</template>

<style scoped>
.emulator-card {
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  margin-bottom: 16px;
  overflow: hidden;
  transition: all 0.3s ease;
}

.emulator-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: var(--ant-color-bg-layout);
  border-bottom: 1px solid var(--ant-color-border);
}

.card-title {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.drag-handle {
  cursor: move;
  font-size: 16px;
  color: var(--ant-color-text-secondary);
}

.drag-handle:hover {
  color: var(--ant-color-primary);
}

.card-actions {
  display: flex;
  gap: 8px;
}

.card-content {
  padding: 20px;
}

.card-content-view {
  background: var(--ant-color-bg-layout);
}

.info-row {
  display: flex;
  align-items: flex-start;
  margin-bottom: 8px;
  line-height: 1.8;
}

.info-label {
  font-weight: 600;
  color: var(--ant-color-text);
  min-width: 80px;
  flex-shrink: 0;
}

.info-value {
  color: var(--ant-color-text-secondary);
  word-break: break-all;
}

.boss-key-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.empty-state {
  padding: 60px 20px;
  text-align: center;
}

.search-results {
  max-height: 500px;
  overflow-y: auto;
}
</style>
