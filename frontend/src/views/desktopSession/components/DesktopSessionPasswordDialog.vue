<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { LockOutlined } from '@ant-design/icons-vue'
import { AppModal } from '@/components/ui'

const props = defineProps<{ firstLogin?: boolean; submitting?: boolean }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ submit: [password: string]; cancel: [] }>()
const { t } = useI18n()
const password = ref('')
const passwordless = ref(false)
watch(open, visible => {
  if (!visible) {
    password.value = ''
    passwordless.value = false
  }
})
function submit() {
  if (props.submitting || (!passwordless.value && !password.value)) return
  const input = passwordless.value ? '' : password.value
  password.value = ''
  emit('submit', input)
}
</script>

<template>
  <AppModal
    v-model:open="open"
    size="sm"
    :icon="LockOutlined"
    :title="t('bootstrap.desktopSession.passwordTitle')"
    :ok-text="t('bootstrap.desktopSession.connect')"
    :cancel-text="t('bootstrap.desktopSession.cancel')"
    :ok-disabled="!passwordless && !password"
    :submitting="submitting"
    @ok="submit"
    @cancel="emit('cancel')"
  >
    <a-flex vertical gap="small">
      <slot />
      <a-input-password
        v-if="!passwordless"
        v-model:value="password"
        :placeholder="t('bootstrap.desktopSession.password')"
        :maxlength="512"
        autocomplete="off"
        @press-enter="submit"
      />
      <a-checkbox
        v-if="firstLogin"
        v-model:checked="passwordless"
        :disabled="submitting"
        @change="password = ''"
        >{{ t('bootstrap.desktopSession.passwordless') }}</a-checkbox
      >
    </a-flex>
  </AppModal>
</template>
