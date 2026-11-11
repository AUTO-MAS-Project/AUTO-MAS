<template>
  <div class="account-heading">
    <img
      v-if="options.logoSrc"
      :src="options.logoSrc"
      alt=""
      class="account-icon"
      @error="options.onIconError?.($event)"
    />
    <div class="account-title">
      <h1>
        {{ options.isEdit ? userName || t('core.comp.editUser') : t('core.comp.addUser2') }}
      </h1>
      <span
        class="save-status"
        :class="`save-status-${options.saveStatus ?? 'idle'}`"
        :title="options.saveErrorMessage"
      >
        <LoadingOutlined v-if="options.saveStatus === 'saving'" spin />
        {{
          t(
            options.saveStatus === 'saving'
              ? 'core.edit.savingNow'
              : options.saveStatus === 'saved'
                ? 'core.edit.autoSaved'
                : options.saveStatus === 'error'
                  ? 'core.edit.saveFailedShort'
                  : 'core.edit.maaEndAutoSaveHint'
          )
        }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { LoadingOutlined } from '@ant-design/icons-vue'
import type { UserAccountHeadingOptions } from '@/types/userEditor'

defineProps<{ userName: string; options: UserAccountHeadingOptions }>()
const { t } = useI18n()
</script>

<style scoped>
.account-heading {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
}
.account-icon {
  width: 44px;
  height: 44px;
  border-radius: 8px;
  object-fit: contain;
  flex-shrink: 0;
}
.account-title {
  min-width: 0;
}
.account-title h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  color: var(--ant-color-text-heading);
  overflow-wrap: anywhere;
}
.save-status {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}
.save-status-saved {
  color: var(--ant-color-success);
}
.save-status-error {
  color: var(--ant-color-error);
}
</style>
