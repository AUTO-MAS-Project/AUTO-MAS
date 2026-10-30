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
              <img v-if="logoSrc" :src="logoSrc" :alt="scriptEditSegment" class="breadcrumb-logo" />
              {{ currentLabel ?? (isEdit ? t('core.comp.editUser') : t('core.comp.addUser2')) }}
            </span>
          </a-breadcrumb-item>
        </a-breadcrumb>
        <slot name="breadcrumb-extra" />
      </div>
      <slot name="below-breadcrumb" />
    </div>

    <a-space :size="actionsSize">
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
import { useUserApi } from '@/composables/useUserApi'

const { t } = useI18n()

const props = withDefaults(
  defineProps<{
    /** 所属脚本 ID，用于第二级面包屑跳回脚本编辑页 */
    scriptId: string
    /** 脚本名称，显示在第二级面包屑 */
    scriptName: string
    /** true 为编辑已有用户，false 为新增用户 */
    isEdit: boolean
    /** 脚本编辑路由段，如 maa / hsr / oknte，拼成 /scripts/:id/edit/<segment> */
    scriptEditSegment?: string
    /** 脚本页命名路由；提供时优先于 scriptEditSegment */
    scriptRoute?: RouteLocationRaw
    /** 覆盖第三级面包屑文字，默认按 isEdit 显示「编辑用户」「添加用户」 */
    currentLabel?: string
    /** 第三级面包屑前的脚本图标，省略则不显示 */
    logoSrc?: string
    /** 配置按钮文字，省略则不渲染配置按钮 */
    configLabel?: string
    /** 配置按钮 loading 态 */
    configLoading?: boolean
    /** 配置进行中，改为显示不可点击的「正在配置」 */
    configActive?: boolean
    /** 配置按钮禁用态 */
    configDisabled?: boolean
    /** 是否展示配置按钮，用于「简洁」模式下整体隐藏 */
    configVisible?: boolean
    /** 当前用户 ID，编辑已有用户时提供，用于渲染「配置文件夹」按钮 */
    userId?: string
    /** 返回按钮 loading 态，用于离开前等待保存或确认 */
    cancelLoading?: boolean
    /** 操作按钮尺寸，默认大号 */
    buttonSize?: 'small' | 'middle' | 'large'
    /** 操作按钮间距，默认中等 */
    actionsSize?: 'small' | 'middle' | 'large'
  }>(),
  {
    scriptEditSegment: undefined,
    scriptRoute: undefined,
    currentLabel: undefined,
    logoSrc: undefined,
    configLabel: undefined,
    configLoading: false,
    configActive: false,
    configDisabled: false,
    configVisible: true,
    userId: undefined,
    cancelLoading: false,
    buttonSize: 'large',
    actionsSize: 'middle',
  }
)

const emit = defineEmits<{
  cancel: []
  config: []
}>()

/** 只有声明了文字且未被显式隐藏时才渲染配置按钮 */
const showConfigButton = computed(() => Boolean(props.configLabel) && props.configVisible)

/** 已有用户才提供「配置文件夹」快捷入口，新增用户此时还没有配置目录 */
const showFolderButton = computed(() => Boolean(props.userId))

const scriptTarget = computed<RouteLocationRaw>(
  () => props.scriptRoute ?? `/scripts/${props.scriptId}/edit/${props.scriptEditSegment}`
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
  margin-bottom: 32px;
  padding: 0 8px;
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
}

.breadcrumb-current {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.breadcrumb-logo {
  width: 20px;
  height: 20px;
  object-fit: contain;
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
