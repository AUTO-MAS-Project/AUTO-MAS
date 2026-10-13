<template>
  <a-modal
    v-model:open="openModel"
    :title="t('edit.queueTemplate')"
    :footer="null"
    width="720px"
    class="preset-template-modal"
  >
    <div class="queue-template-toolbar">
      <!-- 项目没有预设时只有「我的模板」，整个分段切换都不显示 -->
      <a-segmented
        v-if="presetTemplates.length > 0"
        v-model:value="activeTab"
        :options="tabOptions"
      />
      <a-button
        v-if="activeTab === 'mine'"
        type="dashed"
        class="queue-template-save-button"
        :disabled="draft.length === 0"
        @click="openSaveDialog"
      >
        <template #icon>
          <PlusOutlined />
        </template>
        {{ t('edit.queueTemplateSaveCurrent') }}
      </a-button>
    </div>

    <template v-if="activeTab === 'mine'">
      <div v-if="queueTemplates.length > 0" class="preset-section-modal">
        <MaaFWQueueCard
          v-for="template in queueTemplates"
          :key="template.name"
          kind="template"
          :title="template.name"
          :task-count="template.chips.length"
          :invalid-count="template.invalidCount"
          :chips="template.chips"
        >
          <template #actions>
            <a-button
              type="primary"
              :disabled="template.entries.length === 0"
              @click="emit('applyQueueTemplate', template.name)"
            >
              {{ t('edit.queueTemplateApply') }}
            </a-button>
            <a-dropdown :trigger="['click']">
              <a-button :aria-label="t('comp.more')">
                <template #icon>
                  <EllipsisOutlined />
                </template>
              </a-button>
              <template #overlay>
                <a-menu>
                  <a-menu-item key="rename" @click="openRenameDialog(template.name)">
                    {{ t('edit.queueTemplateRename') }}
                  </a-menu-item>
                  <a-menu-item key="delete" danger @click="confirmDelete(template.name)">
                    {{ t('edit.queueTemplateDelete') }}
                  </a-menu-item>
                </a-menu>
              </template>
            </a-dropdown>
          </template>
        </MaaFWQueueCard>
      </div>
      <a-empty v-else :description="t('edit.queueTemplateEmpty')" />
    </template>

    <div v-else class="preset-section-modal">
      <MaaFWQueueCard
        v-for="template in presetTemplates"
        :key="template.preset.name"
        kind="preset"
        :title="template.preset.label || template.preset.name"
        :description="template.preset.description"
        :base-path="basePath"
        :chips="presetChips(template)"
      >
        <template #actions>
          <a-button
            type="primary"
            :disabled="template.entries.length === 0"
            @click="emit('applyPresetTemplate', template.preset.name)"
          >
            {{ t('edit.applyPreset2') }}
          </a-button>
        </template>
      </MaaFWQueueCard>
    </div>
  </a-modal>

  <!-- 存为模板 / 重命名共用一个小弹窗：同一套名称校验，不覆盖同名 -->
  <a-modal
    v-model:open="nameDialogOpen"
    :title="
      nameDialogMode === 'save' ? t('edit.queueTemplateSaveTitle') : t('edit.queueTemplateRename')
    "
    width="480px"
    :ok-text="t('edit.queueTemplateSave')"
    :cancel-text="t('common.cancel')"
    :ok-button-props="{ disabled: !canSubmitName }"
    @ok="submitName"
  >
    <div class="queue-template-name-label">{{ t('edit.queueTemplateName') }}</div>
    <!-- antd 受控输入只绑 :value 会被重渲染清空，必须 v-model:value -->
    <a-input
      v-model:value="nameDraft"
      :status="nameProblem === 'duplicate' ? 'error' : undefined"
      @press-enter="submitName"
    />
    <div v-if="nameProblem === 'duplicate'" class="queue-template-name-error">
      {{ t('edit.queueTemplateNameExists') }}
    </div>
    <template v-if="nameDialogMode === 'save'">
      <div class="queue-template-draft-title">
        {{ t('edit.queueTemplateCurrentCount', { count: draft.length }) }}
      </div>
      <MaaFWQueueChips :chips="draft" />
    </template>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Modal } from 'ant-design-vue'
import { EllipsisOutlined, PlusOutlined } from '@ant-design/icons-vue'
import type { MaaFWQueueSourceChip } from '../maafwQueueSource'
import { checkMaaFWQueueTemplateName } from '../maafwQueueTemplates'
import type { MaaFWQueueTemplateView, PresetTemplate } from '../../MaaFWFlavor/sectionContracts'
import MaaFWQueueCard from './MaaFWQueueCard.vue'
import MaaFWQueueChips from './MaaFWQueueChips.vue'

/**
 * 「模板」弹窗：「我的模板」（本脚本的自定义模板，存 / 套用 / 重命名 / 删除）与「项目预设」
 * （interface 自带的 preset）。这里只管显示与交回动作，读写模板与替换队列都由页面做。
 */

const props = defineProps<{
  open: boolean
  queueTemplates: MaaFWQueueTemplateView[]
  presetTemplates: PresetTemplate[]
  /** 「存为模板」要存的任务（当前队列去掉虚影与受管任务） */
  draft: MaaFWQueueSourceChip[]
  /** 预设描述里的图片按项目目录解析 */
  basePath?: string
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  applyPresetTemplate: [presetName: string]
  saveQueueTemplate: [name: string]
  applyQueueTemplate: [name: string]
  renameQueueTemplate: [name: string, nextName: string]
  deleteQueueTemplate: [name: string]
}>()

type TemplateTab = 'mine' | 'presets'

const { t } = useI18n()

const openModel = computed({
  get: () => props.open,
  set: value => emit('update:open', value),
})

const activeTab = ref<TemplateTab>('mine')
const tabOptions = computed(() => [
  { value: 'mine', label: t('edit.queueTemplateMine') },
  { value: 'presets', label: t('edit.queueTemplatePresets') },
])

// 每次打开都回到「我的模板」；项目预设没了（换了 interface）也退回去
watch(
  () => [props.open, props.presetTemplates.length] as const,
  ([open, presetCount], previous) => {
    if ((open && !previous?.[0]) || presetCount === 0) activeTab.value = 'mine'
  }
)

const presetChips = (template: PresetTemplate) =>
  template.entries.map(entry => ({
    id: entry.id,
    label: entry.task.label || entry.task.name,
  }))

const nameDialogOpen = ref(false)
const nameDialogMode = ref<'save' | 'rename'>('save')
const nameDraft = ref('')
/** 重命名时的原名：改回原名不算重名 */
const renamingName = ref('')

const nameProblem = computed(() =>
  checkMaaFWQueueTemplateName(
    nameDraft.value,
    props.queueTemplates.map(item => item.name),
    nameDialogMode.value === 'rename' ? renamingName.value : undefined
  )
)

const canSubmitName = computed(() => {
  if (nameProblem.value) return false
  if (nameDialogMode.value === 'save') return props.draft.length > 0
  return nameDraft.value.trim() !== renamingName.value
})

const openSaveDialog = () => {
  nameDialogMode.value = 'save'
  nameDraft.value = ''
  renamingName.value = ''
  nameDialogOpen.value = true
}

const openRenameDialog = (name: string) => {
  nameDialogMode.value = 'rename'
  nameDraft.value = name
  renamingName.value = name
  nameDialogOpen.value = true
}

const submitName = () => {
  if (!canSubmitName.value) return
  const name = nameDraft.value.trim()
  if (nameDialogMode.value === 'save') {
    emit('saveQueueTemplate', name)
  } else {
    emit('renameQueueTemplate', renamingName.value, name)
  }
  nameDialogOpen.value = false
}

const confirmDelete = (name: string) => {
  Modal.confirm({
    title: t('edit.queueTemplateDeleteConfirm', { name }),
    okText: t('edit.queueTemplateDelete'),
    okType: 'danger',
    cancelText: t('common.cancel'),
    onOk: () => emit('deleteQueueTemplate', name),
  })
}
</script>

<style scoped>
.queue-template-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
}

.queue-template-save-button {
  margin-left: auto;
}

.preset-section-modal {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 60vh;
  overflow: auto;
}

.queue-template-name-label {
  margin-bottom: 8px;
  color: var(--ant-color-text);
}

.queue-template-name-error {
  margin-top: 4px;
  color: var(--ant-color-error);
  font-size: 13px;
}

.queue-template-draft-title {
  margin: 16px 0 8px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}
</style>
