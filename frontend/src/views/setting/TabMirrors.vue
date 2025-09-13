<script setup lang="ts">
const { mirrorConfigStatus, refreshingConfig, refreshMirrorConfig, goToMirrorTest } = defineProps<{
  mirrorConfigStatus: { isUsingCloudConfig: boolean; version: string; lastUpdated: string; source: 'cloud' | 'fallback' }
  refreshingConfig: boolean
  refreshMirrorConfig: () => Promise<void>
  goToMirrorTest: () => void
}>()
</script>
<template>
  <div class="tab-content">
    <div class="form-section">
      <div class="section-header">
        <h3>镜像站配置</h3>
        <p class="section-description">管理下载站和加速站配置，支持从云端自动更新最新的镜像站列表</p>
      </div>
      <a-row :gutter="24">
        <a-col :span="24">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">配置状态</span>
            </div>
            <a-descriptions :column="1" bordered size="small">
              <a-descriptions-item label="配置来源">
                <a-tag :color="mirrorConfigStatus.source === 'cloud' ? 'green' : 'orange'">
                  {{ mirrorConfigStatus.source === 'cloud' ? '云端配置' : '本地兜底配置' }}
                </a-tag>
              </a-descriptions-item>
              <a-descriptions-item label="配置版本" v-if="mirrorConfigStatus.version">
                {{ mirrorConfigStatus.version }}
              </a-descriptions-item>
              <a-descriptions-item label="最后更新" v-if="mirrorConfigStatus.lastUpdated">
                {{ new Date(mirrorConfigStatus.lastUpdated).toLocaleString() }}
              </a-descriptions-item>
            </a-descriptions>
          </div>
        </a-col>
      </a-row>

      <a-row :gutter="24" style="margin-top:24px;">
        <a-col :span="24">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">配置管理</span>
            </div>
            <a-space size="large">
              <a-button type="primary" @click="refreshMirrorConfig" :loading="refreshingConfig" size="large">更新云端最新配置</a-button>
              <a-button @click="goToMirrorTest" size="large">测试页面</a-button>
            </a-space>
          </div>
        </a-col>
      </a-row>

      <a-row :gutter="24" style="margin-top: 24px;">
        <a-col :span="24">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">说明</span>
            </div>
            <a-alert message="镜像配置说明" type="info" show-icon>
              <template #description>
                <ul style="margin:8px 0; padding-left:20px;">
                  <li>应用启动时会自动尝试从云端拉取最新的镜像站配置</li>
                  <li>可以手动点击"刷新云端配置"按钮获取最新配置</li>
                </ul>
              </template>
            </a-alert>
          </div>
        </a-col>
      </a-row>
    </div>
  </div>
</template>
