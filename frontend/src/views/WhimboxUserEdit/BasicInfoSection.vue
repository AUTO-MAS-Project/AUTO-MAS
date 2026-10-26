<template>
  <div class="form-section">
    <div class="section-header">
      <h3>{{ t('edit.basicInfo') }}</h3>
    </div>
    <a-row :gutter="24">
      <a-col :span="12">
        <a-form-item name="userName" required>
          <template #label>
            <FieldLabelWithHint
              :text="t('edit.username')"
              :hint="t('edit.displayNameUsedIdentify')"
              variant="form"
            />
          </template>
          <a-input
            v-model:value="formData.userName"
            :placeholder="t('edit.enterUsername')"
            :disabled="loading"
            size="large"
            class="modern-input"
            @blur="emit('save', 'userName', formData.userName)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="6">
        <a-form-item name="status">
          <template #label>
            <FieldLabelWithHint
              :text="t('edit.enabled')"
              :hint="t('edit.whetherThisUserEnabled')"
              variant="form"
            />
          </template>
          <a-select
            v-model:value="formData.Info.Status"
            :disabled="loading"
            size="large"
            style="width: 100%"
            @change="emit('save', 'Info.Status', formData.Info.Status)"
          >
            <a-select-option :value="true">{{ t('edit.yes') }}</a-select-option>
            <a-select-option :value="false">{{ t('edit.no') }}</a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
      <a-col :span="6">
        <a-form-item name="remainedDay">
          <template #label>
            <FieldLabelWithHint
              :text="t('edit.daysLeft')"
              :hint="t('edit.daysLeftAccount1')"
              variant="form"
            />
          </template>
          <a-input-number
            v-model:value="formData.Info.RemainedDay"
            :min="-1"
            :max="9999"
            placeholder="-1"
            :disabled="loading"
            size="large"
            style="width: 100%"
            @blur="emit('save', 'Info.RemainedDay', formData.Info.RemainedDay)"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <a-row :gutter="24">
      <a-col :span="16">
        <a-form-item name="notes">
          <template #label>
            <FieldLabelWithHint
              :text="t('edit.note')"
              :hint="t('edit.addNoteAboutThis')"
              variant="form"
            />
          </template>
          <a-textarea
            v-model:value="formData.Info.Notes"
            :placeholder="t('edit.enterNote3')"
            :rows="3"
            :disabled="loading"
            class="modern-input"
            @blur="emit('save', 'Info.Notes', formData.Info.Notes)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="8">
        <a-form-item>
          <template #label>
            <FieldLabelWithHint
              :text="t('edit.whimboxUserTag')"
              :hint="t('edit.whimboxUserTagHint')"
              variant="form"
            />
          </template>
          <div class="user-tag-list">
            <a-tag
              v-for="(tag, index) in userTags"
              :key="index"
              :title="tag.text"
              :color="tag.color"
            >
              {{ tag.text }}
            </a-tag>
            <a-tag v-if="!userTags.length" color="default">-</a-tag>
          </div>
        </a-form-item>
      </a-col>
    </a-row>

    <a-row :gutter="24">
      <a-col :span="24">
        <!-- 三态 base 来源卡片 + 覆写层开关（基座渲染，绑定账号级 Info.IfQuickConfig：
             原生态开启时任务前物化面板覆盖集、结束还原；共享/独立态面板本就是 base） -->
        <GeneralConfigModeSelector
          :model-value="formData.Info.Base"
          :options="whimboxConfigModeOptions"
          :disabled="loading"
          :quick-config="formData.Info.IfQuickConfig"
          :alert-message="t('edit.whimboxConfigSourceHint')"
          @change="(value: boolean | string) => emit('modeChange', value)"
          @quick-config-change="(value: boolean) => emit('quickConfigChange', value)"
        />
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { parseStatusTagList } from '@/composables/useStatusTag.ts'
import GeneralConfigModeSelector from '@/views/EditView/User/GeneralConfigModeSelector.vue'
import { WHIMBOX_CONFIG_MODES, type WhimboxConfigMode } from './modes.ts'

const { t } = useI18n()

const props = defineProps<{
  formData: {
    userName: string
    Info: {
      Name: string
      Status: boolean
      Base: string
      IfQuickConfig: boolean
      RemainedDay: number
      Notes: string
      Tag: string
    }
  }
  loading: boolean
}>()

const emit = defineEmits<{
  save: [key: string, value: unknown]
  modeChange: [value: boolean | string]
  quickConfigChange: [value: boolean]
}>()

const formData = props.formData

// 只读标签：后端按运行情况生成的 JSON 字符串
const userTags = computed(() => parseStatusTagList(formData.Info.Tag))

// 配置来源三态卡片（#879 语义：base 来源=共享/独立/原生）：shared/independent base 是
// 本页面板值（当前运行行为一致、为后续特殊功能预留），native base 即奇想盒自带配置
//（MAS 零写入）。
// 值域来自共享表（同时被页面的切换校验消费），新增状态会在本表漏写时报类型错。
const modeMeta: Record<
  WhimboxConfigMode,
  { title: string; description: string; icon: 'database' | 'file' | 'setting' }
> = {
  shared: {
    title: t('edit.script'),
    description: t('edit.whimboxModeScriptDesc'),
    icon: 'database',
  },
  independent: {
    title: t('edit.user'),
    description: t('edit.whimboxModeUserDesc'),
    icon: 'file',
  },
  native: {
    title: t('edit.directControl'),
    description: t('edit.whimboxModeDirectDesc'),
    icon: 'setting',
  },
}

const whimboxConfigModeOptions = WHIMBOX_CONFIG_MODES.map(value => ({
  value,
  ...modeMeta[value],
}))
</script>

<style scoped>
.form-section {
  margin-bottom: 12px;
}

.section-header {
  margin-bottom: 6px;
}

.modern-input {
  border-radius: 8px;
  border: 2px solid var(--ant-color-border);
  background: var(--ant-color-bg-container);
  transition: all 0.3s ease;
}

.modern-input:hover {
  border-color: var(--ant-color-primary-hover);
}

.modern-input:focus,
.modern-input.ant-input-focused {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.1);
}

.user-tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  min-height: 40px;
}
</style>
