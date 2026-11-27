<script setup lang="ts">
import { computed } from 'vue'
import { createReusableTemplate } from '@vueuse/core'
import { useI18n } from 'vue-i18n'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { ConfigEditShell, StateView } from '@/components/ui'
import { DeclarativeForm } from '@/components/declarative'
import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import GameBindingSection from '@/components/GameBindingSection.vue'
import ScriptEditHeader from '@/components/ScriptEditHeader.vue'
import { SCRIPT_METADATA } from '@/utils/scriptMetadata'
import { useDeclarativeConfigEditor, type ConfigEditorTarget } from './useDeclarativeConfigEditor'

const props = defineProps<
  { mode: 'script' | 'user'; planId?: never } | { mode: 'plan'; planId: string }
>()
const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const scriptId = computed(() => String(route.params.scriptId ?? ''))
const userId = computed(() => String(route.params.userId ?? ''))
const target = computed<ConfigEditorTarget>(() => {
  if (props.mode === 'plan') return { mode: 'plan', id: props.planId }
  if (props.mode === 'user') return { mode: 'user', scriptId: scriptId.value, id: userId.value }
  return { mode: 'script', id: scriptId.value }
})
const {
  draft,
  ui,
  configUid,
  groups,
  tables,
  saving,
  canSave,
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
const [DefineForm, EditorForm] = createReusableTemplate()

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
  <DefineForm>
    <StateView
      :loading="loading"
      :error="error"
      :empty="!groups.length"
      :empty-description="t('core.plugins.noConfigFields')"
      overlay-loading
      @retry="reload"
    >
      <DeclarativeForm
        :groups="groups"
        :tables="tables"
        :values="draft.values"
        :errors="draft.errors.value"
        :uid="configUid"
        :namespace="ui?.i18nNamespace ?? ''"
        :disabled="busy || loading"
        :active-fields="activeFields"
        :running-key="runningKey"
        @update:value="draft.update"
        @action="runAction"
      />
    </StateView>
    <a-flex v-if="groups.length" justify="end" align="center" gap="small">
      <span v-if="draft.dirtyCount.value">{{
        t('core.plugins.unsavedCount', { count: draft.dirtyCount.value })
      }}</span>
      <a-button :loading="loading" :disabled="busy" @click="reload">{{
        t('core.plugins.reload')
      }}</a-button>
      <a-button type="primary" :loading="saving" :disabled="!canSave" @click="save">{{
        t('core.plugins.save')
      }}</a-button>
    </a-flex>
  </DefineForm>
  <EditorForm v-if="mode === 'plan'" />
  <ConfigEditShell v-else :surface="mode === 'user'" :max-width="1040">
    <template #header>
      <ScriptEditHeader
        :script-type="String(route.params.scriptType)"
        :logo-src="SCRIPT_METADATA.General.logo"
        :logo-alt="String(route.params.scriptType)"
        :title="mode === 'user' ? t('core.comp.editUser') : t('core.comp.editScript')"
        @cancel="router.push({ name: 'Scripts' })"
      />
    </template>
    <ConfigLockPanel
      :script-id="scriptId"
      :user-id="mode === 'user' ? userId : undefined"
      content-class="config-editor-content"
    >
      <GameBindingSection v-if="mode === 'script'" :script-id="scriptId" />
      <EditorForm />
    </ConfigLockPanel>
  </ConfigEditShell>
</template>
