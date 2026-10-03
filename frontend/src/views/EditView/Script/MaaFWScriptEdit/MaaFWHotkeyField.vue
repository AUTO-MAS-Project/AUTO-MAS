<template>
  <!-- interface 里没有对当前控制器 / 资源生效的 hotkey option 时整格不渲染 -->
  <a-col v-if="options.length > 0" :span="6">
    <a-form-item>
      <template #label>
        <span class="form-label">{{ t('edit.mfwHotkey') }}</span>
      </template>
      <a-input-group compact class="path-input-group">
        <a-input :value="summary" size="large" class="path-input" readonly />
        <a-button size="large" class="path-button" @click="modalOpen = true">
          <template #icon>
            <SettingOutlined />
          </template>
          {{ t('edit.mfwHotkeySet') }}
        </a-button>
      </a-input-group>
    </a-form-item>
    <MaaFWHotkeyModal
      v-model:open="modalOpen"
      :options="options"
      :values="effectiveValues"
      :description="description"
      :gates="gates"
      :import-candidates="importCandidates"
      :import-dir="importDir"
      :script-id="scriptId"
      @save="handleSave"
    />
  </a-col>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { SettingOutlined } from '@ant-design/icons-vue'
import { useMaaFWShellInstanceApi } from '@/composables/useMaaFWShellInstanceApi'
import type { MaaFWInterfacePreviewData } from '@/types/script'
import MaaFWHotkeyModal from './MaaFWHotkeyModal.vue'
import { collectHotkeyImportCandidates, type MaaFWShellHotkeySource } from './hotkeyImport'
import {
  collectHotkeyGates,
  collectHotkeyOptions,
  countChangedHotkeys,
  effectiveHotkeyValues,
  hotkeySettingDescription,
  mergeHotkeyMap,
  parseHotkeyMap,
  type MaaFWHotkeyMap,
} from './hotkeyOptions'

const props = defineProps<{
  /** 脚本 ID：「从项目导入」按它读外壳配置实例 */
  scriptId: string
  previewData: MaaFWInterfacePreviewData | null
  controllerName: string
  resourceName: string
  /** 脚本配置 Game.Hotkeys（JSON 字符串） */
  value: string | undefined
}>()

const emit = defineEmits<{
  /** 保存后的 Game.Hotkeys（JSON 字符串） */
  save: [value: string]
}>()

const { t } = useI18n()

const modalOpen = ref(false)

const options = computed(() =>
  collectHotkeyOptions(props.previewData, props.controllerName, props.resourceName)
)
const storedMap = computed(() => parseHotkeyMap(props.value))
const effectiveValues = computed(() => effectiveHotkeyValues(options.value, storedMap.value))
const description = computed(() => hotkeySettingDescription(props.previewData, options.value))
const gates = computed(() =>
  collectHotkeyGates(props.previewData, props.controllerName, props.resourceName)
)

const summary = computed(() => {
  const changed = countChangedHotkeys(options.value, storedMap.value)
  return changed > 0 ? t('edit.mfwHotkeyChanged', { n: changed }) : t('edit.mfwHotkeyDefault')
})

// 「从项目导入」：第一次打开弹窗时读一次外壳配置实例，读不到（没有外壳配置、接口失败）就当没有
const { listShellInstances } = useMaaFWShellInstanceApi()
const shellInstances = ref<MaaFWShellHotkeySource[]>([])
let shellInstancesRequested = false
watch(modalOpen, async open => {
  if (!open || shellInstancesRequested || !props.scriptId) return
  shellInstancesRequested = true
  try {
    shellInstances.value = await listShellInstances(props.scriptId)
  } catch {
    shellInstances.value = []
  }
})
const importCandidates = computed(() =>
  collectHotkeyImportCandidates(shellInstances.value, options.value)
)
// 扫到这些配置的目录（导入项目时记下的来源目录，或兜底的内嵌副本）
const importDir = computed(() => shellInstances.value[0]?.sourceDir ?? '')

const handleSave = (values: MaaFWHotkeyMap) => {
  emit('save', JSON.stringify(mergeHotkeyMap(storedMap.value, options.value, values)))
}
</script>

<style scoped>
/* 与控制分节「选择 exe」那组同一套样式（scoped 样式不跨组件，照抄一份） */
.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.path-input-group {
  display: flex;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--ant-color-border);
}

.path-input {
  flex: 1;
  border: none !important;
  border-radius: 0 !important;
}

.path-input:focus {
  box-shadow: none !important;
}

.path-button {
  border: none;
  border-left: 1px solid var(--ant-color-border-secondary);
  border-radius: 0;
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  font-weight: 600;
}
</style>
