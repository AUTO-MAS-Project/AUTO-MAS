<!--
  游戏社区：抽卡记录页（占位）。
  本轮只迁移明日方舟的抽卡记录，页面骨架先落位，等森空岛明日方舟数据接入后再补内容。
-->
<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const emit = defineEmits<{ back: [] }>()

const { t } = useI18n()
</script>

<template>
  <div class="gacha-page">
    <h3 class="gacha-title">{{ t('core.gamesign.gacha.title') }}</h3>
    <a-result
      status="info"
      :title="t('core.gamesign.gacha.pending')"
      :sub-title="t('core.gamesign.gacha.pendingDesc')"
    >
      <template #extra>
        <a-button type="primary" @click="emit('back')">
          {{ t('core.gamesign.nav.sign') }}
        </a-button>
      </template>
    </a-result>
  </div>
</template>

<style scoped>
.gacha-page {
  padding: 20px 24px 24px;
}

.gacha-title {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 600;
  line-height: 24px;
  color: var(--ant-color-text);
}
</style>
