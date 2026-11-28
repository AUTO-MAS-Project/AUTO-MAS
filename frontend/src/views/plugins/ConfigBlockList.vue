<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { createReusableTemplate } from '@vueuse/core'
import { useI18n } from 'vue-i18n'
import { DeclarativeForm } from '@/components/declarative'
import GameBindingSection from '@/components/GameBindingSection.vue'
import PluginUiMount from '@/components/PluginUiMount.vue'
import WebhookManager from '@/components/WebhookManager.vue'
import ConfigRestoreSection from '@/components/shared/ConfigRestoreSection.vue'
import { compatibleWheel } from '@/utils/pluginScriptTypes'
import type { useDeclarativeConfigEditor } from './useDeclarativeConfigEditor'

const props = defineProps<{
  editor: ReturnType<typeof useDeclarativeConfigEditor>
  mode: 'script' | 'user' | 'plan'
  scriptType: string
  scriptId: string
  userId: string
  locked: boolean
  setupMode: boolean
}>()
const emit = defineEmits<{ finish: [] }>()
const { t } = useI18n()
const {
  activeFields,
  backupTargets,
  blockOptions,
  busy,
  canSave,
  canSubmit,
  configUid,
  creatingUser,
  draft,
  groups,
  hasWebhooks,
  loading,
  native,
  onRestored,
  refreshWheel,
  reload,
  restoreApi,
  runAction,
  runningKey,
  save,
  saving,
  startNative,
  tables,
  ui,
  wheelEditor,
  wheelTarget,
} = props.editor

const restoreOpen = ref(false)
watch(configUid, () => {
  restoreOpen.value = false
})
const groupsFor = (names: string[]) =>
  names.map(name => groups.value.find(group => group.name === name)).filter(g => g !== undefined)
const blocks = computed(() =>
  (ui.value?.blocks ?? [])
    .map(block => {
      if (block.kind === 'plugin')
        return {
          kind: block.kind,
          pageId: block.pageId,
          wheel: compatibleWheel(block.mount),
          visibleGroups: groupsFor(block.fallbackGroups),
        }
      if (block.kind === 'declarative')
        return { kind: block.kind, visibleGroups: groupsFor(block.groups) }
      if (block.kind === 'host') return { kind: block.kind, name: block.name }
    })
    .filter(block => block !== undefined)
)
const wheelFor = (pageId: string) =>
  blocks.value.find(block => block.kind === 'plugin' && block.pageId === pageId)?.wheel

const [DefineForm, BlockForm] = createReusableTemplate<{
  formGroups: typeof groups.value
  notice?: boolean
}>({ inheritAttrs: false })
</script>

<template>
  <DefineForm v-slot="{ formGroups, notice }">
    <a-alert
      v-if="notice"
      type="info"
      show-icon
      :message="
        t('bootstrap.apiErrors.pluginPanelFallback', '插件界面不可用，已切换到内置编辑器。')
      "
    />
    <DeclarativeForm
      v-if="formGroups.length"
      block-mode
      :groups="formGroups"
      :options="blockOptions"
      :tables="tables"
      :sections="ui?.sections"
      :values="draft.values"
      :errors="draft.errors.value"
      :uid="configUid"
      :namespace="ui?.i18nNamespace ?? ''"
      :scope="mode"
      :disabled="locked || busy || loading"
      :active-fields="activeFields"
      :running-key="runningKey"
      @update:value="draft.update"
      @action="runAction"
    />
  </DefineForm>
  <a-flex vertical gap="small">
    <template
      v-for="(block, index) in blocks"
      :key="block.kind === 'plugin' ? block.pageId : index"
    >
      <template v-if="block.kind === 'host'">
        <GameBindingSection
          v-if="block.name === 'game_binding' && scriptId"
          :script-id="scriptId"
        />
        <template v-else-if="block.name === 'config_restore' && backupTargets.length">
          <div>
            <a-button :disabled="busy || loading" @click="restoreOpen = true">
              {{ t('core.edit.configRestoreTitle') }}
            </a-button>
          </div>
          <ConfigRestoreSection
            v-model:open="restoreOpen"
            :targets="backupTargets"
            :api="restoreApi"
            :on-restored="onRestored"
            :dirty="draft.dirtyCount.value > 0"
            :disabled="locked || busy || loading"
            :script-name="scriptType"
            :script-id="scriptId"
            :user-id="mode === 'user' ? userId : null"
          />
        </template>
        <div
          v-else-if="block.name === 'native_session' && ui?.nativeSession && !native.taskId.value"
        >
          <a-button
            :disabled="busy || loading || !!activeFields.length"
            :loading="native.configLoading.value"
            @click="startNative"
          >
            {{
              ui.nativeSession === 'view'
                ? t('core.scheduler.mode.scriptView')
                : t('core.edit.openConfigWindow', { script: scriptType })
            }}
          </a-button>
        </div>
        <WebhookManager
          v-else-if="block.name === 'webhooks' && mode === 'user' && hasWebhooks"
          :key="userId"
          mode="user"
          :script-id="scriptId"
          :user-id="userId"
        />
      </template>
      <BlockForm v-else-if="block.kind === 'declarative'" :form-groups="block.visibleGroups" />
      <template v-else-if="block.kind === 'plugin'">
        <PluginUiMount
          v-if="block.wheel"
          :mount="block.wheel"
          :target="wheelTarget"
          :editor="wheelEditor(locked, () => wheelFor(block.pageId), block.visibleGroups)"
          :refresh="() => refreshWheel(() => wheelFor(block.pageId))"
        >
          <template #fallback>
            <BlockForm :form-groups="block.visibleGroups" :notice="true" />
          </template>
        </PluginUiMount>
        <BlockForm v-else :form-groups="block.visibleGroups" :notice="true" />
      </template>
    </template>
    <a-flex justify="end" align="center" gap="small">
      <span v-if="draft.dirtyCount.value">{{
        t('core.plugins.unsavedCount', { count: draft.dirtyCount.value })
      }}</span>
      <a-button :loading="loading" :disabled="locked || busy || loading" @click="reload">
        {{ t('core.plugins.reload') }}
      </a-button>
      <a-button
        type="primary"
        :loading="saving || creatingUser"
        :disabled="locked || (setupMode ? !canSubmit : !canSave)"
        @click="setupMode ? emit('finish') : save()"
      >
        {{ setupMode ? t('core.taskboard.complete') : t('core.plugins.save') }}
      </a-button>
    </a-flex>
  </a-flex>
</template>
