<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RightOutlined } from '@ant-design/icons-vue'
import PluginDetailFields from '../components/PluginDetailFields.vue'
import type { InstalledPluginView } from '../pluginCenterModel'

/** 已安装行展开后的信息区；诊断信息默认收起，展开后可整段复制。 */
const props = defineProps<{ view: InstalledPluginView }>()
const { t } = useI18n()

/** 宽窗三列、最小窗口两列。 */
const DETAIL_MIN_COLUMN_WIDTH = 240

const diagnosticsOpen = ref(false)
const diagnosticsText = computed(() =>
  props.view.diagnostics.map(item => `${t(item.labelKey)}  ${item.value}`).join('\n')
)
</script>

<template>
  <div class="installed-detail">
    <PluginDetailFields :view="view" :min-column-width="DETAIL_MIN_COLUMN_WIDTH">
      <div v-if="view.diagnostics.length" class="installed-diagnostics">
        <a-button
          type="text"
          size="small"
          class="installed-diagnostics-toggle"
          :aria-expanded="diagnosticsOpen"
          @click="diagnosticsOpen = !diagnosticsOpen"
          ><template #icon
            ><RightOutlined
              class="installed-diagnostics-chevron"
              :class="{ 'is-open': diagnosticsOpen }" /></template
          >{{ t('core.plugins.diagnostics') }}</a-button
        >
        <a-typography-paragraph
          v-if="diagnosticsOpen"
          class="installed-diagnostics-text"
          :copyable="{ text: diagnosticsText }"
          >{{ diagnosticsText }}</a-typography-paragraph
        >
      </div>
    </PluginDetailFields>
  </div>
</template>

<style scoped>
.installed-detail {
  padding: 4px 16px 16px 68px;
  background: var(--ant-color-fill-quaternary);
}

.installed-diagnostics {
  display: flex;
  padding-top: 12px;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  border-top: 1px solid var(--ant-color-border-secondary);
}

.installed-diagnostics-toggle {
  padding-inline: 0;
  color: var(--ant-color-text-secondary);
}

.installed-diagnostics-chevron {
  transition: transform 0.15s;
}

.installed-diagnostics-chevron.is-open {
  transform: rotate(90deg);
}

.installed-diagnostics-text {
  width: 100%;
  margin: 0;
  padding: 12px;
  box-sizing: border-box;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 6px;
  /* 半透明填充：自定义背景下不能出现不透明的实心块。 */
  background: var(--ant-color-fill-tertiary);
  font-family: var(--font-monospace);
  font-size: 12px;
  line-height: 20px;
  white-space: pre-wrap;
}
</style>
