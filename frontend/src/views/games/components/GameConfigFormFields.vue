<template>
  <a-form layout="vertical" class="config-grid-form">
    <a-row :gutter="[16, 0]">
      <a-col v-if="showAdapterSelect" :span="24">
        <a-form-item :label="t('core.games.adapter')" required>
          <a-select
            :value="selectedType"
            :options="types.map(item => ({ value: item.type, label: item.name }))"
            :aria-label="t('core.games.adapter')"
            @update:value="handleAdapterChange"
          />
        </a-form-item>
      </a-col>

      <a-col :xs="24" :md="twoColumn ? 12 : 24">
        <a-form-item :label="t('core.games.name')" required>
          <a-input v-model:value="draft.name" :aria-label="t('core.games.name')" />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :md="twoColumn ? 12 : 24">
        <a-form-item :label="t('core.games.waitTime')">
          <a-input-number v-model:value="draft.waitTime" :min="1" :max="9999" class="w-full" />
        </a-form-item>
      </a-col>

      <a-col :span="24">
        <a-form-item
          :label="t(selectedType === 'avd' ? 'core.games.installRoot' : 'core.games.executable')"
          :required="selectedType !== 'general_emulator'"
        >
          <a-input v-model:value="draft.path" readonly :placeholder="t('core.games.selectPath')">
            <template #suffix>
              <a-button
                type="text"
                size="small"
                :aria-label="t('core.games.browse')"
                @click="emit('pickPath', 'path')"
              >
                <template #icon><FolderOpenOutlined /></template>
              </a-button>
            </template>
          </a-input>
        </a-form-item>
      </a-col>

      <template v-if="clientType">
        <a-col :xs="24" :md="twoColumn ? 12 : 24">
          <a-form-item :label="t('core.games.launcher')">
            <a-input
              v-model:value="draft.launcher"
              readonly
              :placeholder="t('core.games.optional')"
            >
              <template #suffix>
                <a-button
                  type="text"
                  size="small"
                  :aria-label="t('core.games.browse')"
                  @click="emit('pickPath', 'launcher')"
                >
                  <template #icon><FolderOpenOutlined /></template>
                </a-button>
              </template>
            </a-input>
          </a-form-item>
        </a-col>
        <a-col :xs="24" :md="twoColumn ? 12 : 24">
          <a-form-item :label="t('core.games.workingDirectory')">
            <a-input v-model:value="draft.cwd" readonly :placeholder="t('core.games.optional')">
              <template #suffix>
                <a-button
                  type="text"
                  size="small"
                  :aria-label="t('core.games.browse')"
                  @click="emit('pickPath', 'cwd')"
                >
                  <template #icon><FolderOpenOutlined /></template>
                </a-button>
              </template>
            </a-input>
          </a-form-item>
        </a-col>
        <a-col :span="24">
          <a-form-item :label="t('core.games.arguments')">
            <a-textarea
              v-model:value="draft.arguments"
              :placeholder="t('core.games.oneArgumentPerLine')"
              :auto-size="{ minRows: 2, maxRows: 4 }"
            />
          </a-form-item>
        </a-col>
      </template>

      <a-col v-else-if="selectedType === 'general_emulator'" :span="24">
        <a-form-item :label="t('core.games.adbPath')">
          <a-input v-model:value="draft.adb" readonly :placeholder="t('core.games.optional')">
            <template #suffix>
              <a-button
                type="text"
                size="small"
                :aria-label="t('core.games.browse')"
                @click="emit('pickPath', 'adb')"
              >
                <template #icon><FolderOpenOutlined /></template>
              </a-button>
            </template>
          </a-input>
        </a-form-item>
      </a-col>
    </a-row>

    <div class="config-switches">
      <label class="switch-item">
        <span>{{ t('core.games.concurrent') }}</span>
        <a-switch v-model:checked="draft.concurrent" />
      </label>
      <template v-if="clientType">
        <label class="switch-item">
          <span>{{ t('core.games.launchWithLauncher') }}</span>
          <a-switch v-model:checked="draft.launchWithLauncher" />
        </label>
        <label class="switch-item">
          <span>{{ t('core.games.forceClose') }}</span>
          <a-switch v-model:checked="draft.forceClose" />
        </label>
      </template>
      <template v-else-if="!creating && selectedType && selectedType !== 'general_emulator'">
        <label v-if="selectedType !== 'avd'" class="switch-item">
          <span>{{ t('core.games.stableMode') }}</span>
          <a-switch v-model:checked="draft.stable" />
        </label>
        <label v-if="selectedType !== 'avd'" class="switch-item">
          <span>{{ t('core.games.configGuard') }}</span>
          <a-switch v-model:checked="draft.guard" />
        </label>
        <label v-if="selectedType === 'mumu'" class="switch-item">
          <span>{{ t('core.games.forceBeforeLaunch') }}</span>
          <a-switch v-model:checked="draft.forceBefore" />
        </label>
        <span class="switch-group">
          <label class="switch-item">
            <span>{{ t('core.games.forceClose') }}</span>
            <a-switch v-model:checked="draft.forceClose" />
          </label>
          <span v-if="selectedType === 'avd'" class="switch-warning">
            {{ t('core.games.forceCloseDataLossWarning') }}
          </span>
        </span>
      </template>
    </div>
  </a-form>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { FolderOpenOutlined } from '@ant-design/icons-vue'
import type { SelectValue } from 'ant-design-vue/es/select'
import type { GameTypeItem } from '@/api'

export interface GameConfigDraft {
  name: string
  path: string
  launcher: string
  cwd: string
  adb: string
  arguments: string
  waitTime: number
  concurrent: boolean
  stable: boolean
  guard: boolean
  forceBefore: boolean
  forceClose: boolean
  launchWithLauncher: boolean
}

defineProps<{
  draft: GameConfigDraft
  selectedType: string
  clientType: boolean
  types: GameTypeItem[]
  showAdapterSelect?: boolean
  twoColumn?: boolean
  creating?: boolean
}>()

const emit = defineEmits<{
  'update:selectedType': [value: string]
  pickPath: [field: 'path' | 'launcher' | 'cwd' | 'adb']
}>()

const { t } = useI18n()

function handleAdapterChange(value: SelectValue): void {
  if (typeof value === 'string') emit('update:selectedType', value)
}
</script>

<style scoped>
/* 栅格行的负外边距会比表单宽出半个间距，放进对话框时底部多出一条横向滚动条；
   超出的部分只有列的内边距，裁掉即可 */
.config-grid-form {
  overflow-x: clip;
}

.config-grid-form :deep(.ant-form-item) {
  margin-bottom: 12px;
}

.w-full {
  width: 100%;
}

.config-switches {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 24px;
  padding: 10px 12px;
  border-radius: var(--ant-border-radius);
  background: var(--ant-color-fill-quaternary);
}

.switch-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--ant-color-text);
}

.switch-group {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px 8px;
  min-width: 0;
}

.switch-warning {
  font-size: 12px;
  color: var(--ant-color-error);
}
</style>
