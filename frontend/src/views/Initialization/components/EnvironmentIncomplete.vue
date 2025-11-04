<template>
  <div class="environment-incomplete">
    <div class="header">
      <img src="/src/assets/AUTO-MAS.ico" alt="logo" class="logo" />
      <a-typography-title :level="1">AUTO-MAS</a-typography-title>
    </div>

    <div class="content">
      <a-result
        status="warning"
        title="环境不完整"
        sub-title="检测到运行环境中缺少必要的组件，需要重新配置环境"
      >
        <template #extra>
          <div class="missing-components">
            <a-typography-title :level="4">缺失的组件：</a-typography-title>
            <a-list :data-source="missingComponents" size="small">
              <template #renderItem="{ item }">
                <a-list-item>
                  <a-typography-text type="danger">
                    <ExclamationCircleOutlined /> {{ item }}
                  </a-typography-text>
                </a-list-item>
              </template>
            </a-list>
          </div>

          <div class="description">
            <a-typography-paragraph> 这种情况通常由以下原因导致： </a-typography-paragraph>
            <ul>
              <li>杀毒软件误删了相关文件</li>
              <li>手动删除了环境文件</li>
              <li>系统更新或清理工具清理了相关文件</li>
            </ul>
            <a-typography-paragraph> 建议重新配置环境以确保程序正常运行。 </a-typography-paragraph>
          </div>

          <div class="actions">
            <a-button type="primary" size="large" @click="handleReconfigure">
              重新配置环境
            </a-button>
            <a-button size="large" style="margin-left: 16px" @click="handleForceEnter">
              跳过初始化
            </a-button>
          </div>
        </template>
      </a-result>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ExclamationCircleOutlined } from '@ant-design/icons-vue'
import { forceEnterApp } from '@/utils/appEntry.ts'

// Props
interface Props {
  missingComponents: string[]
  onSwitchToManual: () => void
}

const props = defineProps<Props>()

// 重新配置环境
function handleReconfigure() {
  props.onSwitchToManual()
}

// 跳过初始化
async function handleForceEnter() {
  await forceEnterApp('环境不完整-强行进入')
}
</script>

<style scoped>
.environment-incomplete {
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
  align-items: center;
  justify-content: center;
  gap: 16px;
}

.header h1 {
  font-size: 38px;
  font-weight: 600;
  color: var(--ant-color-text);
  margin-bottom: 8px;
}

.logo {
  width: 100px;
  height: 100px;
}

.content {
  width: 100%;
  max-width: 600px;
}

.missing-components {
  margin-bottom: 24px;
  text-align: left;
}

.missing-components h4 {
  margin-bottom: 12px;
}

.description {
  text-align: left;
  margin-bottom: 24px;
}

.description ul {
  margin: 12px 0;
  padding-left: 20px;
}

.description li {
  margin: 4px 0;
  color: var(--ant-color-text-secondary);
}

.actions {
  text-align: center;
}

/* 响应式优化 */
@media (max-height: 700px) {
  .environment-incomplete {
    min-height: auto;
    padding: 10px;
  }

  .header {
    margin-bottom: 20px;
  }

  .header h1 {
    font-size: 32px;
  }

  .logo {
    width: 80px;
    height: 80px;
  }
}

@media (max-width: 600px) {
  .actions {
    display: flex;
    flex-direction: column;
    gap: 12px;
    align-items: center;
  }

  .actions .ant-btn {
    width: 200px;
  }
}
</style>
