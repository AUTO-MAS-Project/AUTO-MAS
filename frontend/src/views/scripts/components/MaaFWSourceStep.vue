<!-- 新建对话框 MFW 家族第二步「项目从哪来」的默认分节（契约 create.source，见
     views/EditView/MaaFWFlavor/sectionContracts.ts）。已导入过的项目直接列出来复用（从那个脚本的
     副本克隆，运行时与模型共用、不另占空间，来源目录删了也能建）；只列与入口同类型的项目。
     第一行永远是「新建一个别的项目」。选中状态归对话框所有，这里只显示并交回选择。 -->
<template>
  <SelectableOptionList
    :model-value="value"
    @update:model-value="(next: string | null) => emit('update:value', next ?? 'new')"
  >
    <SelectableOptionCard
      value="new"
      :title="t('scripts.create.mfwNewProject')"
      :description="t('scripts.create.mfwNewProjectDesc')"
      :selected="value === 'new'"
    >
      <template #icon>
        <span class="selectable-option-icon"><FolderOpenOutlined /></span>
      </template>
    </SelectableOptionCard>
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
      <SelectableOptionCard
        v-for="choice in choices"
        :key="choice.scriptId"
        :value="choice.scriptId"
        :title="reuseTitle(choice)"
        :description="reuseMeta(choice)"
        :selected="value === choice.scriptId"
        :disabled="choice.busy"
      >
        <template #icon>
          <span class="selectable-option-icon">
            <img
              v-if="showProjectIcon(choice)"
              :src="buildMaaFWScriptIconUrl(choice.scriptId)"
              alt=""
              class="choice-project-icon"
              @error="failedIcons.add(choice.scriptId)"
            />
            <CopyOutlined v-else />
          </span>
        </template>
      </SelectableOptionCard>
    </template>
    <div v-else-if="!error" class="choice-placeholder">
      {{ t('scripts.create.mfwReuseEmpty', { type: resolveMaaFWFlavor(type).typeTagLabel }) }}
    </div>
  </SelectableOptionList>
</template>

<script setup lang="ts">
import { reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { CopyOutlined, FolderOpenOutlined } from '@ant-design/icons-vue'
import { resolveMaaFWFlavor, usesMaaFWProjectIcon } from '@/composables/useMaaFWFlavor'
import { buildMaaFWScriptIconUrl } from '@/utils/maafwProjectIcon'
import SelectableOptionCard from '@/components/SelectableOptionCard.vue'
import SelectableOptionList from '@/components/SelectableOptionList.vue'
import type {
  MaaFWCreateSourceSectionEmits,
  MaaFWCreateSourceSectionProps,
} from '@/views/EditView/MaaFWFlavor/sectionContracts'
import type { MfwReuseChoice } from './scriptCreateFlow'

const { t } = useI18n()

// props / 事件的契约在 sectionContracts（特调替换这个分节时按同一份契约接收）
const props = defineProps<MaaFWCreateSourceSectionProps>()

// 通用 MaaFW 的每一行是不同的项目，用项目自己的图标认；没有图标（后端 404）就换回复制图标。
// 特调的行都是同一个项目类型，图标一样认不出来，保持复制图标
const failedIcons = reactive(new Set<string>())
const showProjectIcon = (choice: MfwReuseChoice) =>
  usesMaaFWProjectIcon(resolveMaaFWFlavor(props.type)) && !failedIcons.has(choice.scriptId)

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

<style scoped>
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

.template-alert {
  margin-bottom: 12px;
}

.choice-project-icon {
  width: 28px;
  height: 28px;
  object-fit: contain;
}
</style>
