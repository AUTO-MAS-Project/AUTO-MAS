<script setup lang="ts">
const props = defineProps<{
  goToLogs: () => void
  openDevTools: () => void
  refreshingConfig: boolean
  refreshMirrorConfig: () => Promise<void>
  goToMirrorTest: () => void
}>()

const { goToLogs, openDevTools, refreshingConfig, refreshMirrorConfig, goToMirrorTest } = props
</script>
<template>
  <div class="tab-content">
    <div class="form-section">
      <div class="section-header">
        <h3>开发者选项</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="24">
          <a-space size="large">
            <a-button type="primary" size="large" @click="goToLogs"> 查看日志 </a-button>
            <a-button size="large" @click="openDevTools"> 打开开发者工具 </a-button>
          </a-space>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>镜像站配置</h3>
        <p class="section-description">
          管理下载站和加速站配置，支持从云端自动更新最新的镜像站列表
        </p>
      </div>

      <a-row :gutter="24">
        <a-col :span="24">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">配置管理</span>
            </div>
            <a-space size="large">
              <a-button
                type="primary"
                :loading="refreshingConfig"
                size="large"
                @click="refreshMirrorConfig"
                >更新云端最新配置</a-button
              >
              <a-button size="large" @click="goToMirrorTest">测试页面</a-button>
            </a-space>
          </div>
        </a-col>
      </a-row>

      <a-row :gutter="24" style="margin-top: 24px">
        <a-col :span="24">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">说明</span>
            </div>
            <a-alert message="镜像配置说明" type="info" show-icon>
              <template #description>
                <ul style="margin: 8px 0; padding-left: 20px">
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
