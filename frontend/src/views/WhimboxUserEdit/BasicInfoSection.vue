<template>
  <div class="form-section">
    <UserAccountHeading
      v-if="heading"
      :user-name="formData.userName"
      :options="{ ...heading, logoSrc: accountIcon }"
    />
    <div class="section-header">
      <h3>{{ t('core.edit.basicInfo') }}</h3>
    </div>
    <UserBasicInfoFields
      v-model:user-name="formData.userName"
      v-model:status="formData.Info.Status"
      v-model:remained-day="formData.Info.RemainedDay"
      v-model:notes="formData.Info.Notes"
      :disabled="loading"
      @save-name="emit('save', 'userName', formData.userName)"
      @save-status="emit('save', 'Info.Status', formData.Info.Status)"
      @save-days="emit('save', 'Info.RemainedDay', formData.Info.RemainedDay)"
      @save-notes="emit('save', 'Info.Notes', formData.Info.Notes)"
    />

    <a-row :gutter="24">
      <a-col :span="8">
        <a-form-item>
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.whimboxUserTag')"
              :hint="t('core.edit.whimboxUserTagHint')"
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
          :quick-config="formData.Info.Base === 'native' ? formData.Info.IfQuickConfig : undefined"
          :alert-message="t('core.edit.whimboxConfigSourceHint')"
          @change="(value: boolean | string) => emit('modeChange', value)"
          @quick-config-change="(value: boolean) => emit('quickConfigChange', value)"
        />
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import accountIcon from '@/assets/whimbox.png'
import UserAccountHeading from '@/components/UserAccountHeading.vue'
import type { UserAccountHeadingOptions } from '@/types/userEditor'
import UserBasicInfoFields from '@/components/UserBasicInfoFields.vue'
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
  heading?: Omit<UserAccountHeadingOptions, 'logoSrc'>
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
//（未启用覆写层时不写入；覆写层只对原生来源生效）。
// 值域来自共享表（同时被页面的切换校验消费），新增状态会在本表漏写时报类型错。
const modeMeta: Record<
  WhimboxConfigMode,
  { title: string; description: string; summary?: string; icon: 'database' | 'file' | 'setting' }
> = {
  shared: {
    title: t('core.edit.script'),
    description: t('core.edit.whimboxModeScriptDesc'),
    summary: t('core.edit.configModeSummaryIndependent'),
    icon: 'database',
  },
  independent: {
    title: t('core.edit.user'),
    description: t('core.edit.whimboxModeUserDesc'),
    icon: 'file',
  },
  native: {
    title: t('core.edit.directControl'),
    description: t('core.edit.whimboxModeDirectDesc'),
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

.user-tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  min-height: 40px;
}
</style>
