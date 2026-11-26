<template>
  <div class="user-edit-container oknte-plan-detail">
    <div class="user-edit-content">
      <a-flex class="detail-header" justify="space-between" align="center" wrap="wrap" gap="middle">
        <h2>{{ t('core.plan.oknte.detail') }} — {{ dayLabel }}</h2>
        <a-button size="large" :aria-label="t('core.edit.back')" @click="back"
          ><template #icon><ArrowLeftOutlined /></template>{{ t('core.edit.back') }}</a-button
        >
      </a-flex>
      <SectionCard class="config-card">
        <OkNtePlanOverrideEditor ref="editor" :plan-id="planId" :day="day" />
      </SectionCard>
    </div>
  </div>
</template>
<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { SectionCard } from '@/components/ui'
import { navigateTo } from '@/router'
import { planDayLabel } from '@/utils/planDays'
import OkNtePlanOverrideEditor from './components/OkNtePlanOverrideEditor.vue'
import { ArrowLeftOutlined } from '@ant-design/icons-vue'
const { t } = useI18n()
const route = useRoute()
const planId = computed(() => String(route.params.planId))
const day = computed(() => String(route.params.day))
const dayLabel = computed(() => {
  const label = planDayLabel(day.value)
  return t(label.key, label.params)
})
const editor = ref<InstanceType<typeof OkNtePlanOverrideEditor>>()
async function back() {
  if (await editor.value?.saveAll()) navigateTo('/plans', { query: { planId: planId.value } })
}
</script>

<style scoped>
.user-edit-container {
  height: 100%;
  min-height: 0;
  background: var(--ant-color-bg-layout);
}
.user-edit-content {
  height: 100%;
  display: flex;
  flex-direction: column;
  max-width: 1200px;
  margin: 0 auto;
}
.detail-header {
  flex-shrink: 0;
  width: 100%;
  margin-bottom: 24px;
}
.detail-header h2 {
  margin: 0;
}
.user-edit-content > .config-card {
  flex: 1;
  min-height: 0;
  margin-bottom: 0;
  padding-block: var(--section-card-padding);
}
.config-card > :deep(.ui-section-card-body) {
  height: 100%;
}
@media (max-width: 768px) {
  .user-edit-content > .config-card {
    --section-card-padding: 20px;
  }
}
</style>
