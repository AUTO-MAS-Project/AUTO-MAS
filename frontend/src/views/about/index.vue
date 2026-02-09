<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Service, type VersionOut } from '@/api'
import { getLogger } from '@/utils/logger'
import TabOthers from '@/views/setting/TabOthers.vue'

const logger = getLogger('关于')
const version = (import.meta as any).env?.VITE_APP_VERSION || '获取版本失败！'
const backendUpdateInfo = ref<VersionOut | null>(null)

// 后端版本
const getBackendVersion = async () => {
  try {
    backendUpdateInfo.value = await Service.getGitVersionApiInfoVersionPost()
  } catch (e) {
    logger.error('获取后端版本失败', e)
  }
}

onMounted(() => {
  getBackendVersion()
})
</script>

<template>
  <div class="about-container">
    <div class="about-header">
      <h1 class="page-title">关于</h1>
    </div>
    <div class="about-content">
      <TabOthers :version="version" :backend-update-info="backendUpdateInfo" />
    </div>
  </div>
</template>

<style scoped>
.about-container {
  width: 100%;
  margin: 0;
  padding: 0;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
}

.about-header {
  margin-bottom: 16px;
  padding: 0 4px;
}

.page-title {
  margin: 0;
  font-size: 32px;
  font-weight: 700;
  color: var(--ant-color-text);
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.about-content {
  background: var(--ant-color-bg-container);
  border-radius: 12px;
  width: 100%;
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
}

.about-content :deep(.tab-content) {
  padding: 24px;
  width: 100%;
}
</style>
