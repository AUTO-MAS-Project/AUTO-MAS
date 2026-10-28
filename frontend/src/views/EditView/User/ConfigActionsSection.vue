<template>
  <a-form-item :label="t('core.edit.configSourceActions')">
    <div class="config-actions-control">
      <a-button
        v-if="showOpen"
        type="primary"
        ghost
        :loading="configLoading"
        :disabled="disabled"
        @click="$emit('configure')"
      >
        <template #icon>
          <SettingOutlined />
        </template>
        {{
          configuring
            ? t('core.edit.configuring')
            : t('core.edit.openConfigWindow', { script: scriptLabel })
        }}
      </a-button>
      <a-button
        v-if="showOpen && showImport"
        type="default"
        :loading="importLoading"
        :disabled="disabled"
        @click="$emit('importConfig')"
      >
        <template #icon>
          <ImportOutlined />
        </template>
        {{ t('core.edit.import2') }}
      </a-button>
      <a-button type="default" :disabled="disabled" @click="$emit('scriptConfig')">
        <template #icon>
          <EditOutlined />
        </template>
        {{ t('core.edit.editScriptSettings') }}
      </a-button>
    </div>

    <!--
      界面入口说明：一眼看清「这个按钮改的是哪一份配置」——动作与落点同排、落点加重，
      影响范围另起一行做次要说明。原生来源没有这个动作，整块不渲染。
    -->
    <div v-if="hint" class="config-actions-hint">
      <p class="config-actions-hint-target">
        <span class="config-actions-hint-action">
          {{ t('core.edit.openConfigWindow', { script: scriptLabel }) }}
        </span>
        <span class="config-actions-hint-arrow" aria-hidden="true">→</span>
        <strong>{{ hint.target }}</strong>
      </p>
      <p class="config-actions-hint-impact">{{ hint.impact }}</p>
    </div>
  </a-form-item>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { EditOutlined, ImportOutlined, SettingOutlined } from '@ant-design/icons-vue'

const { t } = useI18n()

const props = withDefaults(
  defineProps<{
    base: boolean | string
    scriptLabel: string
    disabled?: boolean
    configLoading?: boolean
    configuring?: boolean
    importLoading?: boolean
    showImport?: boolean
  }>(),
  {
    disabled: false,
    configLoading: false,
    configuring: false,
    importLoading: false,
    showImport: true,
  }
)

defineEmits<{
  configure: []
  importConfig: []
  scriptConfig: []
}>()

// 原生来源直接使用脚本自身配置，既不用打开配置界面，也没有可导入的 MAS 侧配置：
// 该来源下整个面板只剩「编辑托管设置」（与 MaaEnd 原实现一致）。
const showOpen = computed(() => props.base !== 'native')

/**
 * 界面入口说明的落点：打开配置界面改的是哪一份配置、影响到谁。
 * 只随 base 来源变化；原生来源没有「打开配置界面」这个动作，返回 undefined 让整块不渲染。
 */
const hint = computed(() => {
  if (!showOpen.value) return undefined
  return props.base === 'shared'
    ? {
        target: t('core.edit.configActionsTargetShared'),
        impact: t('core.edit.configActionsImpactShared'),
      }
    : {
        target: t('core.edit.configActionsTargetIndependent'),
        impact: t('core.edit.configActionsImpactIndependent'),
      }
})
</script>

<style scoped>
/* 下边距沿用 AntDV form-item 默认值（24px），与页面其它表单项同一节奏；
   清零会让该表单项贴住紧随其后的「任务配置」标题。 */
.config-actions-control {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

/* 界面入口说明：动作与落点同排，落点加重；影响范围另起一行，用次要色，便于一眼扫到重点 */
.config-actions-hint {
  margin-top: 8px;
}

.config-actions-hint-target {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 4px;
  margin: 0;
  color: var(--ant-color-text);
  font-size: 13px;
  font-weight: 600;
  line-height: 1.5;
}

.config-actions-hint-action {
  color: var(--ant-color-text-secondary);
  font-weight: 400;
}

.config-actions-hint-arrow {
  color: var(--ant-color-text-quaternary);
  font-weight: 400;
}

.config-actions-hint-impact {
  margin: 4px 0 0;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  line-height: 1.5;
}
</style>
