<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { createReusableTemplate } from '@vueuse/core'
import { useI18n } from 'vue-i18n'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { ConfigEditShell, StateView } from '@/components/ui'
import { DeclarativeForm } from '@/components/declarative'
import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import PluginUiMount from '@/components/PluginUiMount.vue'
import ConfigRestoreSection from '@/components/shared/ConfigRestoreSection.vue'
import GameBindingSection from '@/components/GameBindingSection.vue'
import ScriptEditHeader from '@/components/ScriptEditHeader.vue'
import { SCRIPT_METADATA } from '@/utils/scriptMetadata'
import { useScriptEditorNavigation } from '@/router/scriptEditorRoutes'
import type { PluginUiActivation } from '@/utils/pluginUiRequests'
import { useDeclarativeConfigEditor, type ConfigEditorTarget } from './useDeclarativeConfigEditor'

const props = defineProps<
  ({ mode: 'script' | 'user'; planId?: never } | { mode: 'plan'; planId: string }) & {
    setup?: boolean
  }
>()
const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const openEditor = useScriptEditorNavigation()
const scriptType = computed(() => String(route.params.scriptType))
const scriptId = computed(() => String(route.params.scriptId ?? ''))
const userId = computed(() => String(route.params.userId ?? ''))
const setupMode = computed(() => props.mode === 'script' && props.setup === true)
const target = computed<ConfigEditorTarget>(() => {
  if (props.mode === 'plan') return { mode: 'plan', id: props.planId }
  if (props.mode === 'user') return { mode: 'user', scriptId: scriptId.value, id: userId.value }
  return { mode: setupMode.value ? 'setup' : 'script', id: scriptId.value }
})
const {
  draft,
  ui,
  configUid,
  groups,
  surface,
  wheel,
  wheelTarget,
  refreshWheel,
  wheelEditor,
  tables,
  saving,
  canSave,
  canSubmit,
  optionsInvalid,
  creatingUser,
  finishSetup,
  backupTargets,
  restoreApi,
  onRestored,
  native,
  startNative,
  stopNative,
  busy,
  loading,
  error,
  activeFields,
  runningKey,
  runAction,
  beforeLeave,
  reload,
  save,
} = useDeclarativeConfigEditor(target)
const [DefineForm, EditorForm] = createReusableTemplate<{ locked: boolean }>()
const [DefineFallback, EditorFallback] = createReusableTemplate<{ locked: boolean }>()
const { restore } = restoreApi
const restoreOpen = ref(false)
watch(configUid, () => {
  restoreOpen.value = false
})
function finish(activation?: PluginUiActivation) {
  if (!setupMode.value) return save()
  return finishSetup(
    id => openEditor(scriptType.value, 'user', { scriptId: scriptId.value, userId: id }),
    activation
  )
}

if (props.mode !== 'plan') {
  onBeforeRouteLeave(beforeLeave)
  onBeforeRouteUpdate(
    (to, from) =>
      (to.params.scriptId === from.params.scriptId && to.params.userId === from.params.userId) ||
      beforeLeave()
  )
}
defineExpose({ beforeLeave })
</script>

<template>
  <DefineFallback v-slot="{ locked }">
    <a-alert
      v-if="surface"
      class="panel-fallback-notice"
      type="info"
      show-icon
      :message="
        t('bootstrap.apiErrors.pluginPanelFallback', '插件界面不可用，已切换到内置编辑器。')
      "
    />
    <slot name="fallback">
      <DeclarativeForm
        v-if="groups.length || setupMode"
        :groups="groups"
        :tables="tables"
        :steps="ui?.steps"
        :sections="ui?.sections"
        :plugin-name="ui?.pluginName"
        :setup-mode="setupMode"
        :submit-disabled="setupMode ? !canSubmit : !canSave"
        :submitting="saving || creatingUser"
        :values="draft.values"
        :errors="draft.errors.value"
        :uid="configUid"
        :namespace="ui?.i18nNamespace ?? ''"
        :disabled="locked || busy || loading"
        :active-fields="activeFields"
        :running-key="runningKey"
        @update:value="draft.update"
        @update:options-invalid="optionsInvalid = $event"
        @action="runAction"
        @finish="finish()"
      >
        <template #actions="{ wizard }">
          <span v-if="draft.dirtyCount.value">{{
            t('core.plugins.unsavedCount', { count: draft.dirtyCount.value })
          }}</span>
          <a-button :loading="loading" :disabled="busy" @click="reload">{{
            t('core.plugins.reload')
          }}</a-button>
          <a-button
            v-if="!wizard"
            type="primary"
            :loading="saving"
            :disabled="!canSave"
            @click="save()"
            >{{ t('core.plugins.save') }}</a-button
          >
        </template>
      </DeclarativeForm>
    </slot>
  </DefineFallback>
  <DefineForm v-slot="{ locked }">
    <StateView
      :loading="loading"
      :error="error"
      :empty="
        !configUid ||
        (!surface &&
          !$slots.fallback &&
          !groups.length &&
          !setupMode &&
          !backupTargets.length &&
          !ui?.nativeSession)
      "
      :empty-description="t('core.plugins.noConfigFields')"
      overlay-loading
      @retry="reload"
    >
      <PluginUiMount
        v-if="wheel"
        :mount="wheel"
        :target="wheelTarget"
        :editor="wheelEditor(locked)"
        :refresh="refreshWheel"
      >
        <template #fallback><EditorFallback :locked="locked" /></template>
        <a-button
          v-if="setupMode"
          type="primary"
          :disabled="locked || !canSubmit"
          :loading="saving || creatingUser"
          @click="finish(wheel)"
        >
          {{ t('core.taskboard.complete') }}
        </a-button>
      </PluginUiMount>
      <EditorFallback v-else :locked="locked" />
    </StateView>
  </DefineForm>
  <EditorForm v-if="mode === 'plan'" :locked="ui?.locked ?? false" />
  <ConfigEditShell v-else :surface="mode === 'user'" :max-width="1040">
    <template #header>
      <ScriptEditHeader
        :script-type="scriptType"
        :logo-src="SCRIPT_METADATA.General.logo"
        :logo-alt="scriptType"
        :title="mode === 'user' ? t('core.comp.editUser') : t('core.comp.editScript')"
        @cancel="router.push({ name: 'Scripts' })"
      >
        <template #extra-actions>
          <a-button v-if="native.taskId.value" :loading="native.stopping.value" @click="stopNative">
            {{
              native.currentSessionViewOnly.value
                ? t('core.edit.generalViewClose')
                : t('core.scripts.mask.saveConfig')
            }}
          </a-button>
        </template>
      </ScriptEditHeader>
    </template>
    <ConfigLockPanel
      v-slot="{ locked }"
      :script-id="scriptId"
      :user-id="mode === 'user' ? userId : undefined"
      content-class="config-editor-content"
    >
      <GameBindingSection v-if="mode === 'script'" :script-id="scriptId" />
      <a-space v-if="backupTargets.length || ui?.nativeSession">
        <a-button
          v-if="backupTargets.length"
          :disabled="busy || loading"
          @click="restoreOpen = true"
        >
          {{ t('core.edit.configRestoreTitle') }}
        </a-button>
        <a-button
          v-if="ui?.nativeSession && !native.taskId.value"
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
      </a-space>
      <ConfigRestoreSection
        v-if="backupTargets.length"
        v-model:open="restoreOpen"
        :targets="backupTargets"
        :api="{ ...restoreApi, restore }"
        :on-restored="onRestored"
        :dirty="draft.dirtyCount.value > 0"
        :disabled="locked || busy || loading"
        :script-name="scriptType"
        :script-id="scriptId"
        :user-id="mode === 'user' ? userId : null"
      />
      <EditorForm :locked="locked || !!ui?.locked" />
    </ConfigLockPanel>
  </ConfigEditShell>
</template>

<style scoped>
.panel-fallback-notice {
  margin-bottom: 8px;
}
</style>
