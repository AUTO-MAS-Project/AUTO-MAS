<!-- 新建对话框 MFW 家族第二步「项目从哪来」的默认分节（契约 create.source，见
     views/EditView/MaaFWFlavor/sectionContracts.ts）。已导入过的项目直接列出来复用（从那个脚本的
     副本克隆，运行时与模型共用、不另占空间，来源目录删了也能建）；只列与入口同类型的项目。
     第一行永远是「新建一个别的项目」。选中状态归对话框所有，这里只显示并交回选择。 -->
<template>
  <a-radio-group
    :value="value"
    class="choice-list"
    @update:value="(next: string) => emit('update:value', next)"
  >
    <label :class="['choice-row', { selected: value === 'new' }]">
      <a-radio value="new" />
      <span class="choice-icon"><FolderOpenOutlined /></span>
      <span class="choice-copy">
        <span class="choice-title">{{ t('scripts.create.mfwNewProject') }}</span>
        <span class="choice-description">{{ t('scripts.create.mfwNewProjectDesc') }}</span>
      </span>
    </label>
    <div class="choice-group-heading">
      <span class="choice-group-title">{{ t('scripts.create.mfwReuse') }}</span>
      <span class="choice-group-description">{{ t('scripts.create.mfwReuseDesc') }}</span>
    </div>
    <a-alert v-if="error" type="error" show-icon :message="error" class="template-alert">
      <template #action>
        <a-button size="small" @click="emit('retry')">{{ t('scripts.create.retry') }}</a-button>
      </template>
    </a-alert>
    <div v-if="loading" class="choice-placeholder">
      <a-spin size="small" />
      <span>{{ t('scripts.create.mfwReuseLoading') }}</span>
    </div>
    <template v-else-if="choices.length">
      <label
        v-for="choice in choices"
        :key="choice.scriptId"
        :class="['choice-row', { selected: value === choice.scriptId, disabled: choice.busy }]"
      >
        <a-radio :value="choice.scriptId" :disabled="choice.busy" />
        <span class="choice-icon"><CopyOutlined /></span>
        <span class="choice-copy">
          <span class="choice-title">{{ reuseTitle(choice) }}</span>
          <span class="choice-description">{{ reuseMeta(choice) }}</span>
        </span>
      </label>
    </template>
    <div v-else-if="!error" class="choice-placeholder">
      {{ t('scripts.create.mfwReuseEmpty', { type }) }}
    </div>
  </a-radio-group>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { CopyOutlined, FolderOpenOutlined } from '@ant-design/icons-vue'
import type {
  MaaFWCreateSourceSectionEmits,
  MaaFWCreateSourceSectionProps,
} from '@/views/EditView/MaaFWFlavor/sectionContracts'
import type { MfwReuseChoice } from './scriptCreateFlow'

const { t } = useI18n()

// props / 事件的契约在 sectionContracts（特调替换这个分节时按同一份契约接收）
defineProps<MaaFWCreateSourceSectionProps>()

const emit = defineEmits<MaaFWCreateSourceSectionEmits>()

// 标题是项目名（interface 读不出就用脚本名）；副标题「来自脚本「x」 · 版本」，
// 持有该项目的脚本都在跑时标一句「运行中」，那一行本身已禁用
const reuseTitle = (choice: MfwReuseChoice) =>
  choice.projectName || choice.scriptName || choice.scriptId.slice(0, 8)
const reuseMeta = (choice: MfwReuseChoice) => {
  const name = choice.scriptName || choice.scriptId.slice(0, 8)
  const from =
    choice.scriptCount > 1
      ? t('scripts.create.mfwReuseFromMany', { name, count: choice.scriptCount })
      : t('scripts.create.mfwReuseFrom', { name })
  const parts = [from, choice.version]
  if (choice.busy) parts.push(t('scripts.create.mfwReuseBusy'))
  return parts.filter(Boolean).join(' · ')
}
</script>

<!-- 与新建对话框里同名的样式一字不差（对话框的 scoped 样式管不到子组件里面） -->
<style scoped>
.choice-copy {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
}

.choice-list {
  display: flex;
  width: 100%;
  flex-direction: column;
  gap: 10px;
}

.choice-row {
  display: flex;
  min-width: 0;
  gap: 12px;
  align-items: center;
  padding: 14px;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  color: var(--ant-color-text);
  background: var(--ant-color-bg-container);
  cursor: pointer;
}

.choice-row:hover,
.choice-row.selected {
  border-color: var(--ant-color-primary);
}

.choice-row.selected {
  background: var(--ant-color-primary-bg);
}

.choice-row.disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.choice-group-heading {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 10px;
  padding: 0 2px;
}

.choice-group-title {
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 600;
}

.choice-group-description {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.choice-placeholder {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 14px;
  border: 1px dashed var(--ant-color-border);
  border-radius: 8px;
  color: var(--ant-color-text-tertiary);
  font-size: 13px;
}

.choice-icon {
  display: inline-flex;
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
  font-size: 19px;
}

.choice-title {
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 600;
}

.choice-description {
  margin-top: 3px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.template-alert {
  margin-bottom: 12px;
}
</style>
