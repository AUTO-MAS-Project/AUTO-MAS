<template>
  <div class="user-edit-header">
    <div class="header-nav">
      <div class="breadcrumb-row">
        <a-breadcrumb class="breadcrumb">
          <a-breadcrumb-item>
            <router-link to="/scripts" class="breadcrumb-link">{{
              t('core.comp.scripts')
            }}</router-link>
          </a-breadcrumb-item>
          <a-breadcrumb-item>
            <router-link :to="scriptTarget" class="breadcrumb-link">
              {{ scriptName }}
            </router-link>
          </a-breadcrumb-item>
          <a-breadcrumb-item>
            <span class="breadcrumb-current">
              {{ t(isEdit ? 'core.comp.editUser' : 'core.comp.addUser2') }}
            </span>
          </a-breadcrumb-item>
        </a-breadcrumb>
        <AccountIdentity
          v-if="isEdit"
          :name="userName"
          :logo-src="logoSrc || metadata.logo"
          @icon-error="onIconError?.($event)"
        />
      </div>
    </div>

    <a-space class="header-actions" :size="actionsSize" wrap>
      <slot name="extra-actions" />

      <a-button
        v-if="showConfigButton && !configActive"
        type="primary"
        ghost
        :size="buttonSize"
        :loading="configLoading"
        :disabled="configDisabled"
        @click="emit('config')"
      >
        <template #icon>
          <SettingOutlined />
        </template>
        {{ configLabel }}
      </a-button>
      <a-button
        v-if="showConfigButton && configActive"
        type="default"
        :size="buttonSize"
        disabled
        class="configuring-button"
      >
        <template #icon>
          <SettingOutlined />
        </template>
        {{ t('core.comp.configuring') }}
      </a-button>

      <a-button
        v-if="showFolderButton"
        :size="buttonSize"
        :loading="folderLoading"
        @click="handleOpenFolder"
      >
        <template #icon>
          <FolderOpenOutlined />
        </template>
        {{ t('core.comp.openConfigFolder') }}
      </a-button>

      <a-button
        :size="buttonSize"
        class="cancel-button"
        :loading="cancelLoading"
        @click="emit('cancel')"
      >
        <template #icon>
          <ArrowLeftOutlined />
        </template>
        {{ t('core.comp.back') }}
      </a-button>
    </a-space>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import type { RouteLocationRaw } from 'vue-router'
import { ArrowLeftOutlined, FolderOpenOutlined, SettingOutlined } from '@ant-design/icons-vue'
import { SCRIPT_METADATA } from '@/utils/scriptMetadata'
import AccountIdentity from '@/components/AccountIdentity.vue'
import type { UserEditHeaderProps } from '@/types/userEditor'
import { useUserApi } from '@/composables/useUserApi'

const { t } = useI18n()

const props = withDefaults(defineProps<UserEditHeaderProps>(), {
  scriptRoute: undefined,
  configLabel: undefined,
  configLoading: false,
  configActive: false,
  configDisabled: false,
  configVisible: true,
  userId: undefined,
  cancelLoading: false,
  buttonSize: 'middle',
  actionsSize: 'middle',
})

const emit = defineEmits<{
  cancel: []
  config: []
}>()

/** 只有声明了文字且未被显式隐藏时才渲染配置按钮 */
const showConfigButton = computed(() => Boolean(props.configLabel) && props.configVisible)

/** 已有用户才提供「配置文件夹」快捷入口，新增用户此时还没有配置目录 */
const showFolderButton = computed(() => Boolean(props.userId))

const metadata = computed(() => SCRIPT_METADATA[props.scriptType])
const scriptTarget = computed<RouteLocationRaw>(
  () => props.scriptRoute ?? `/scripts/${props.scriptId}/edit/${metadata.value.routeSuffix}`
)

const { loading: folderLoading, openUserConfigFolder } = useUserApi()

const handleOpenFolder = async () => {
  const userId = props.userId
  if (!userId) return
  await openUserConfigFolder(props.scriptId, userId)
}
</script>

<style scoped>
.user-edit-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  gap: 24px;
  flex-wrap: wrap;
}

.header-nav {
  flex: 1;
  min-width: 0;
}

.breadcrumb-row {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.breadcrumb {
  margin: 0;
  font-size: 12px;
}

.breadcrumb-current {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.header-actions {
  flex-shrink: 0;
}
.breadcrumb-link {
  overflow-wrap: anywhere;
}

.cancel-button {
  border: 1px solid var(--ant-color-border);
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text);
}

.cancel-button:hover,
:slotted(.cancel-button:hover) {
  border-color: var(--ant-color-primary);
  color: var(--ant-color-primary);
}

:slotted(.cancel-button) {
  border: 1px solid var(--ant-color-border);
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text);
}

.configuring-button {
  color: var(--ant-color-success);
  border-color: var(--ant-color-success);
}

@media (max-width: 768px) {
  .user-edit-header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }
}
</style>
