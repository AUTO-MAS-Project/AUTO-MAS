<template>
  <div class="user-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts" class="breadcrumb-link">脚本管理</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <router-link
            :to="`/scripts/${scriptId}/edit/${scriptEditSegment}`"
            class="breadcrumb-link"
          >
            {{ scriptName }}
          </router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <span class="breadcrumb-current">
            <img v-if="logoSrc" :src="logoSrc" :alt="scriptEditSegment" class="breadcrumb-logo" />
            {{ currentLabel ?? (isEdit ? '编辑用户' : '添加用户') }}
          </span>
        </a-breadcrumb-item>
      </a-breadcrumb>
    </div>

    <a-space size="middle">
      <slot name="extra-actions" />

      <a-button
        v-if="showConfigButton && !configActive"
        type="primary"
        ghost
        size="large"
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
        size="large"
        disabled
        class="configuring-button"
      >
        <template #icon>
          <SettingOutlined />
        </template>
        正在配置
      </a-button>

      <a-button size="large" class="cancel-button" @click="emit('cancel')">
        <template #icon>
          <ArrowLeftOutlined />
        </template>
        返回
      </a-button>
    </a-space>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ArrowLeftOutlined, SettingOutlined } from '@ant-design/icons-vue'

const props = withDefaults(
  defineProps<{
    /** 所属脚本 ID，用于第二级面包屑跳回脚本编辑页 */
    scriptId: string
    /** 脚本名称，显示在第二级面包屑 */
    scriptName: string
    /** true 为编辑已有用户，false 为新增用户 */
    isEdit: boolean
    /** 脚本编辑路由段，如 maa / hsr / oknte，拼成 /scripts/:id/edit/<segment> */
    scriptEditSegment: string
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
  }>(),
  {
    currentLabel: undefined,
    logoSrc: undefined,
    configLabel: undefined,
    configLoading: false,
    configActive: false,
    configDisabled: false,
    configVisible: true,
  }
)

const emit = defineEmits<{
  cancel: []
  config: []
}>()

/** 只有声明了文字且未被显式隐藏时才渲染配置按钮 */
const showConfigButton = computed(() => Boolean(props.configLabel) && props.configVisible)
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

.cancel-button:hover {
  border-color: var(--ant-color-primary);
  color: var(--ant-color-primary);
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
