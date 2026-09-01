<template>
  <div class="script-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts" class="breadcrumb-link">{{ t('comp.scripts') }}</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <div class="breadcrumb-current">
            <img :src="logoSrc" :alt="logoAlt" class="breadcrumb-logo" />
            {{ headerTitle }}
          </div>
        </a-breadcrumb-item>
      </a-breadcrumb>
    </div>

    <a-space size="middle" wrap>
      <slot name="extra-actions" />
      <a
        v-if="docUrl"
        class="doc-link"
        :href="docUrl"
        target="_blank"
        rel="noreferrer"
        :aria-label="t('common.viewPageDocs')"
        @click="handleExternalLink"
      >
        <BookOutlined />
        {{ t('common.viewPageDocs') }}
        <ExportOutlined />
      </a>

      <a-button size="large" class="cancel-button" @click="emit('cancel')">
        <template #icon>
          <ArrowLeftOutlined />
        </template>
        {{ t('comp.back') }}
      </a-button>
    </a-space>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import { ArrowLeftOutlined, BookOutlined, ExportOutlined } from '@ant-design/icons-vue'
import type { ScriptType } from '@/types/script'
import { SCRIPT_LABELS, SCRIPT_LOGOS } from '@/utils/scriptLogos'
import { MAS_DOC_URLS, handleExternalLink } from '@/utils/openExternal'

const { t } = useI18n()

const props = defineProps<{
  /** 脚本类型，决定面包屑图标与 alt 文案 */
  scriptType: ScriptType
  /** 第二级面包屑文字，留空则用「编辑脚本」 */
  title?: string
}>()

// 默认值不能写在 withDefaults 里：defineProps 会被提升到 setup() 之外，
// 引用不到 useI18n() 返回的 t，编译期直接报错。改在这里兜底。
const headerTitle = computed(() => props.title ?? t('comp.editScript'))

const emit = defineEmits<{ cancel: [] }>()

const logoSrc = computed(() => SCRIPT_LOGOS[props.scriptType])
const logoAlt = computed(() => SCRIPT_LABELS[props.scriptType])
const docUrl = computed(() => MAS_DOC_URLS.scriptTypes[props.scriptType as keyof typeof MAS_DOC_URLS.scriptTypes])
</script>

<style scoped>
.script-edit-header {
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

.breadcrumb-link {
  align-items: center;
  gap: 8px;
  color: var(--ant-color-text-secondary);
  text-decoration: none;
  transition: color 0.3s ease;
}

.breadcrumb-current {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--ant-color-text);
  font-weight: 600;
}

.breadcrumb-logo {
  width: 20px;
  height: 20px;
  object-fit: contain;
}

.doc-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--ant-color-primary);
  white-space: nowrap;
}

@media (max-width: 768px) {
  .script-edit-header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }

  .cancel-button {
    height: 44px;
    font-size: 14px;
    padding: 0 20px;
  }
}
</style>
