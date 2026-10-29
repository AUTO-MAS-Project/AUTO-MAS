<script setup lang="ts">
import { computed, ref } from 'vue'
import { message } from 'ant-design-vue'
import { QqService } from '@/api'
import type { ClawBindingState } from './ClawBinding.vue'

const props = defineProps<{ binding: ClawBindingState }>()
const expanded = ref<string[]>([])
const loading = ref(false)
const error = ref('')
const bindingId = ref('')
const appId = ref('')
const userOpenId = ref('')
const clientSecret = ref('')
const secretSet = ref(false)
const originalAppId = ref('')
const busy = computed(() => loading.value || props.binding.manualSaving)
const disabled = computed(
  () => busy.value || props.binding.open || props.binding.unbinding || props.binding.targetSaving
)
const canSave = computed(
  () =>
    !!bindingId.value &&
    !!appId.value.trim() &&
    !!userOpenId.value.trim() &&
    (!!clientSecret.value.trim() || (secretSet.value && appId.value.trim() === originalAppId.value))
)

async function load() {
  loading.value = true
  error.value = ''
  bindingId.value = ''
  clientSecret.value = ''
  try {
    const result = await QqService.getCredentialsApiSettingOpenclawQqCredentialsGetPost()
    if (result.code !== 200) throw new Error(result.message)
    bindingId.value = result.bindingId || ''
    appId.value = originalAppId.value = result.appId || ''
    userOpenId.value = result.userOpenId || ''
    secretSet.value = !!result.secretSet
  } catch {
    error.value = props.binding.label('ManualLoadError')
  } finally {
    loading.value = false
  }
}
function change(keys: string | string[]) {
  expanded.value = Array.isArray(keys) ? keys : [keys]
  if (expanded.value.length) void load()
  else clientSecret.value = ''
}
async function save() {
  error.value = ''
  try {
    const saved = await props.binding.saveCredentials({
      bindingId: bindingId.value,
      appId: appId.value.trim(),
      userOpenId: userOpenId.value.trim(),
      ...(clientSecret.value.trim() ? { clientSecret: clientSecret.value.trim() } : {}),
    })
    if (!saved) return
    clientSecret.value = ''
    message.success(props.binding.label('ManualSaved'))
    await load()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : props.binding.label('ManualSaveError')
  }
}
</script>

<template>
  <a-collapse :active-key="expanded" ghost @change="change">
    <a-collapse-panel
      key="manual"
      :header="binding.label('ManualTitle')"
      :collapsible="busy ? 'disabled' : undefined"
    >
      <a-typography-paragraph type="secondary">{{
        binding.label('ManualHint')
      }}</a-typography-paragraph>
      <a-spin :spinning="loading">
        <a-form layout="vertical" :disabled="disabled" @finish="save">
          <a-form-item label="AppID" required html-for="qq-manual-app-id">
            <a-input id="qq-manual-app-id" v-model:value="appId" autocomplete="off" />
          </a-form-item>
          <a-form-item
            label="AppSecret"
            :required="!secretSet || appId.trim() !== originalAppId"
            html-for="qq-manual-secret"
          >
            <a-input-password
              id="qq-manual-secret"
              v-model:value="clientSecret"
              autocomplete="new-password"
              :placeholder="
                secretSet && appId.trim() === originalAppId ? binding.label('ManualKeepSecret') : ''
              "
            />
          </a-form-item>
          <a-form-item :label="binding.label('ManualOpenId')" required html-for="qq-manual-openid">
            <a-input id="qq-manual-openid" v-model:value="userOpenId" autocomplete="off" />
          </a-form-item>
          <a-form-item v-if="error">
            <a-alert type="error" show-icon :message="error" />
          </a-form-item>
          <a-space wrap>
            <a-button
              type="primary"
              html-type="submit"
              :loading="binding.manualSaving"
              :disabled="disabled || !canSave"
            >
              {{ binding.label('ManualSave') }}
            </a-button>
            <a-button :disabled="disabled" @click="load">{{
              binding.label('StatusRetry')
            }}</a-button>
          </a-space>
        </a-form>
      </a-spin>
    </a-collapse-panel>
  </a-collapse>
</template>
