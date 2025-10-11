<template>
  <div class="install-mode-selection">
    <div class="header">
      <img src="/src/assets/AUTO-MAS.ico" alt="logo" class="logo" />
      <a-typography-title :level="1">AUTO-MAS</a-typography-title>
      <a-typography-title :level="3">选择安装方式</a-typography-title>
    </div>

    <div class="mode-cards">
      <!-- 快速安装模式 -->
      <div
        class="mode-card"
        :class="{ active: selectedMode === 'quick' }"
        @click="selectedMode = 'quick'"
      >
        <div class="card-header">
          <div class="card-title">
            <h3>快速安装</h3>
            <a-tag color="gold">推荐</a-tag>
          </div>
        </div>
        <div class="card-description">
          <p>从自建下载站获取预打包的环境和源码，安装速度更快，适合大多数用户。</p>
          <div class="features">
            <div class="feature">
              <span class="feature-icon">⚡</span>
              <span>安装速度快</span>
            </div>
            <div class="feature">
              <span class="feature-icon">📦</span>
              <span>预配置环境</span>
            </div>
            <div class="feature">
              <span class="feature-icon">🌐</span>
              <span>国内下载站</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 手动安装模式 -->
      <div
        class="mode-card"
        :class="{ active: selectedMode === 'manual' }"
        @click="selectedMode = 'manual'"
      >
        <div class="card-header">
          <div class="card-title">
            <h3>手动安装</h3>
            <a-tag color="blue">自定义</a-tag>
          </div>
        </div>
        <div class="card-description">
          <p>逐步下载并解压Python、Git等环境，从GitHub获取最新源码，适合开发者和高级用户。</p>
          <div class="features">
            <div class="feature">
              <span class="feature-icon">🔧</span>
              <span>完全控制</span>
            </div>
            <div class="feature">
              <span class="feature-icon">🔄</span>
              <span>最新代码</span>
            </div>
            <div class="feature">
              <span class="feature-icon">⚙️</span>
              <span>自定义配置</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="actions">
      <a-button type="primary" size="large" :disabled="!selectedMode" @click="handleConfirm">
        {{ selectedMode === 'quick' ? '开始快速安装' : '开始手动安装' }}
      </a-button>
    </div>

    <div class="additional-info">
      <a-alert
        v-if="selectedMode === 'quick'"
        message="快速安装说明"
        description="将从 AUTO-MAS 官方下载站下载预打包的环境和源码，包含Python、Git工具和后端源码。"
        type="info"
        show-icon
      />
      <a-alert
        v-if="selectedMode === 'manual'"
        message="手动安装说明"
        description="将逐步引导您安装Python环境、Git工具，并克隆最新源码。可以自定义镜像源和配置选项。"
        type="info"
        show-icon
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

// Props
interface Props {
  onModeSelected: (mode: 'quick' | 'manual') => void
}

const props = defineProps<Props>()

// 状态
const selectedMode = ref<'quick' | 'manual' | null>(null)

// 处理确认
function handleConfirm() {
  if (selectedMode.value) {
    props.onModeSelected(selectedMode.value)
  }
}
</script>

<style scoped>
.install-mode-selection {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: calc(100vh - 120px);
  padding: 20px;
  box-sizing: border-box;
}

.header {
  text-align: center;
  margin-bottom: 40px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.header h1 {
  font-size: 38px;
  font-weight: 600;
  color: var(--ant-color-text);
  margin: 0;
}

.header h3 {
  font-size: 20px;
  font-weight: 400;
  color: var(--ant-color-text-secondary);
  margin: 0;
}

.logo {
  width: 80px;
  height: 80px;
}

.mode-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
  gap: 24px;
  margin-bottom: 32px;
  max-width: 800px;
  width: 100%;
}

.mode-card {
  padding: 24px;
  border: 2px solid var(--ant-color-border);
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.3s ease;
  background: var(--ant-color-bg-container);
  position: relative;
}

.mode-card:hover {
  border-color: var(--ant-color-primary);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
  transform: translateY(-2px);
}

.mode-card.active {
  border-color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
  box-shadow: 0 4px 16px rgba(24, 144, 255, 0.2);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
}

.card-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.card-title h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.card-icon {
  color: var(--ant-color-primary);
  opacity: 0.8;
}

.card-description p {
  color: var(--ant-color-text-secondary);
  line-height: 1.6;
  margin-bottom: 16px;
}

.features {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.feature {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: var(--ant-color-text);
}

.feature-icon {
  font-size: 16px;
  width: 20px;
  text-align: center;
}

.actions {
  margin-bottom: 24px;
}

.additional-info {
  max-width: 600px;
  width: 100%;
}

/* 响应式优化 */
@media (max-width: 768px) {
  .mode-cards {
    grid-template-columns: 1fr;
    gap: 16px;
  }

  .mode-card {
    padding: 20px;
  }

  .header h1 {
    font-size: 32px;
  }

  .logo {
    width: 64px;
    height: 64px;
  }
}

@media (max-width: 480px) {
  .install-mode-selection {
    padding: 16px;
  }

  .mode-card {
    padding: 16px;
  }

  .card-header {
    flex-direction: column;
    gap: 12px;
    align-items: flex-start;
  }
}
</style>
