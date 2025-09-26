<script setup lang="ts">
import { HomeOutlined, GithubOutlined, QqOutlined } from '@ant-design/icons-vue'
import type { VersionOut } from '@/api'

const { version, backendUpdateInfo } = defineProps<{
  version: string
  backendUpdateInfo: VersionOut | null
}>()
</script>
<template>
  <div class="tab-content">
    <div class="form-section">
      <div class="section-header">
        <h3>项目链接</h3>
      </div>
      <div class="link-grid">
        <div class="link-item">
          <div class="link-card">
            <div class="link-icon"><HomeOutlined /></div>
            <div class="link-content">
              <h4>软件官网</h4>
              <p>查看最新版本和功能介绍</p>
              <a href="https://auto-mas.top" target="_blank" class="link-button">访问官网</a>
            </div>
          </div>
        </div>
        <div class="link-item">
          <div class="link-card">
            <div class="link-icon"><GithubOutlined /></div>
            <div class="link-content">
              <h4>GitHub仓库</h4>
              <p>查看源代码、提交issue和捐赠</p>
              <a href="https://github.com/AUTO-MAS-Project/AUTO-MAS" target="_blank" class="link-button">访问仓库</a>
            </div>
          </div>
        </div>
        <div class="link-item">
          <div class="link-card">
            <div class="link-icon"><QqOutlined /></div>
            <div class="link-content">
              <h4>用户QQ群</h4>
              <p>加入社区，获取帮助和交流</p>
              <a href="https://qm.qq.com/q/bd9fISNoME" target="_blank" class="link-button">加入群聊</a>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>应用信息</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="info-item"><span class="info-label">软件名称：</span><span class="info-value">AUTO-MAS</span></div>
          <div class="info-item"><span class="info-label">许可证：</span><span class="info-value">GPL-3.0 license</span></div>
        </a-col>
        <a-col :span="12">
          <div class="info-item"><span class="info-label">开发者：</span><span class="info-value">AUTO-MAS Team</span></div>
        </a-col>
      </a-row>
      <a-divider />
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="info-item"><span class="info-label">当前前端版本：</span><span class="info-value">{{ version }}</span></div>
          <div class="info-item"><span class="info-label">当前后端哈希值：</span><span class="info-value">{{ backendUpdateInfo?.current_hash }}</span></div>
        </a-col>
        <a-col :span="12">
          <div class="info-item"><span class="info-label">当前后端版本：</span><span class="info-value">{{ backendUpdateInfo?.current_version }}</span></div>
          <div class="info-item"><span class="info-label">后端更新时间：</span><span class="info-value">{{ backendUpdateInfo?.current_time }}</span></div>
        </a-col>
      </a-row>
    </div>
  </div>
</template>

<style scoped>
/* Responsive grid for link cards: ensures cards expand to fill available width */
.link-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 24px;
  align-items: stretch;
  width: 100%;
}

.link-item {
  display: flex;
}

/* Make sure link-card fills its grid cell */
.link-card {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
}

.link-content {
  flex: 1 1 auto;
}

</style>
