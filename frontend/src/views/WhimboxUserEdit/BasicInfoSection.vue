<template>
  <div class="form-section">
    <div class="section-header">
      <h3>{{ t('edit.basicInfo') }}</h3>
    </div>
    <a-row :gutter="24">
      <a-col :span="12">
        <a-form-item name="userName" required>
          <template #label>
            <a-tooltip :title="t('edit.displayNameUsedIdentify')">
              <span class="form-label">
                {{ t('edit.username') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
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
            <a-tooltip :title="t('edit.whetherThisUserEnabled')">
              <span class="form-label">
                {{ t('edit.enabled') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
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
            <a-tooltip :title="t('edit.daysLeftAccount1')">
              <span class="form-label">
                {{ t('edit.daysLeft') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
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
            <a-tooltip :title="t('edit.addNoteAboutThis')">
              <span class="form-label">
                {{ t('edit.note') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
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
            <a-tooltip :title="t('edit.whimboxUserTagHint')">
              <span class="form-label">
                {{ t('edit.whimboxUserTag') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
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
        <!-- 奇想盒不接「快速配置」：显式传 quick-config=undefined 表明「未接入该字段」。
             基座已把该 prop 的默认值声明为 undefined（Boolean casting 的坑在基座内解决，
             见 GeneralConfigModeSelector 的 props 注释），这里显式传是为了不依赖基座
             默认值、意图一眼可见。 -->
        <GeneralConfigModeSelector
          :model-value="formData.Info.Mode"
          :options="whimboxConfigModeOptions"
          :disabled="loading"
          :quick-config="undefined"
          :alert-message="t('edit.whimboxConfigSourceHint')"
          @change="(value: boolean | string) => emit('modeChange', value)"
        />
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
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
      Mode: string
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
}>()

const formData = props.formData

// 只读标签：后端按运行情况生成的 JSON 字符串
const userTags = computed(() => parseStatusTagList(formData.Info.Tag))

// 配置来源两态卡片（脚本=用 MAS 面板配置 / 直控=用奇想盒原生配置）：
// 上游只有一份 config.json 且无脚本级一条龙配置，故不设「用户」态与快速配置开关。
// 值域来自共享表（同时被页面的切换校验消费），新增状态会在本表漏写时报类型错。
const modeMeta: Record<
  WhimboxConfigMode,
  { title: string; description: string; icon: 'database' | 'setting' }
> = {
  脚本: {
    title: t('edit.script'),
    description: t('edit.whimboxModeScriptDesc'),
    icon: 'database',
  },
  直控: {
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
  padding-bottom: 8px;
  border-bottom: 2px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 12px;
}

.section-header h3::before {
  content: '';
  width: 4px;
  height: 24px;
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  border-radius: 2px;
}

.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--ant-color-text);
  font-size: 14px;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
  cursor: help;
  transition: color 0.3s ease;
}

.help-icon:hover {
  color: var(--ant-color-primary);
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
