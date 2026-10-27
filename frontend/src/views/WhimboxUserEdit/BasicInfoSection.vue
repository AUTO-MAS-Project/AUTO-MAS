<template>
  <div class="form-section">
    <div class="section-header">
      <h3>{{ t('edit.basicInfo') }}</h3>
    </div>
    <a-row :gutter="24">
      <a-col :span="12">
        <UserNameField
          name="userName"
          required
          v-model="formData.userName"
          :hint="t('edit.displayNameUsedIdentify')"
          :placeholder="t('edit.enterUsername')"
          :disabled="loading"
          enhanced
          @save="emit('save', 'userName', formData.userName)"
        />
      </a-col>
      <a-col :span="6">
        <UserStatusField
          name="status"
          v-model="formData.Info.Status"
          :hint="t('edit.whetherThisUserEnabled')"
          :disabled="loading"
          @save="emit('save', 'Info.Status', formData.Info.Status)"
        />
      </a-col>
      <a-col :span="6">
        <UserRemainedDayField
          name="remainedDay"
          v-model="formData.Info.RemainedDay"
          :hint="t('edit.daysLeftAccount1')"
          placeholder="-1"
          :disabled="loading"
          @save="emit('save', 'Info.RemainedDay', formData.Info.RemainedDay)"
        />
      </a-col>
    </a-row>

    <a-row :gutter="24">
      <a-col :span="16">
        <UserNotesField
          name="notes"
          v-model="formData.Info.Notes"
          :hint="t('edit.addNoteAboutThis')"
          :placeholder="t('edit.enterNote3')"
          :disabled="loading"
          :rows="3"
          enhanced
          @save="emit('save', 'Info.Notes', formData.Info.Notes)"
        />
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
import UserNameField from '@/views/EditView/User/components/UserNameField.vue'
import UserNotesField from '@/views/EditView/User/components/UserNotesField.vue'
import UserRemainedDayField from '@/views/EditView/User/components/UserRemainedDayField.vue'
import UserStatusField from '@/views/EditView/User/components/UserStatusField.vue'
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

.user-tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  min-height: 40px;
}
</style>
