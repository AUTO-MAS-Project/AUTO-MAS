<template>
  <div class="script-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts" class="breadcrumb-link"> 脚本管理</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <div class="breadcrumb-current">
            <img
              src="../../../assets/MAA.png"
              alt="MAA"
              class="breadcrumb-logo"
            />
            编辑脚本
          </div>
        </a-breadcrumb-item>
      </a-breadcrumb>
    </div>

    <a-space size="middle">
      <a-button size="large" @click="handleCancel" class="cancel-button">
        <template #icon>
          <ArrowLeftOutlined />
        </template>
        返回
      </a-button>
    </a-space>
  </div>

  <div class="script-edit-content">
    <a-card title="MAA脚本配置" :loading="pageLoading" class="config-card">
      <template #extra>
        <a-tag color="blue" class="type-tag">
          MAA
        </a-tag>
      </template>

      <a-form ref="formRef" :model="formData" :rules="rules" layout="vertical" class="config-form">
        <!-- 基本信息 -->
        <div class="form-section">
          <div class="section-header">
            <h3>基本信息</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item name="name">
                <template #label>
                  <a-tooltip title="为脚本设置一个易于识别的名称">
                    <span class="form-label">
                      脚本名称
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input
                  v-model:value="formData.name"
                  placeholder="请输入脚本名称"
                  size="large"
                  class="modern-input"
                />
              </a-form-item>
            </a-col>
            <a-col :span="16">
              <a-form-item name="path">
                <template #label>
                  <a-tooltip title="选择MAA.exe所在的文件夹路径">
                    <span class="form-label">
                      MAA路径
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="maaConfig.Info.Path"
                    placeholder="请选择MAA.exe所在的文件夹"
                    size="large"
                    class="path-input"
                    readonly
                  />
                  <a-button size="large" @click="selectMAAPath" class="path-button">
                    <template #icon>
                      <FolderOpenOutlined />
                    </template>
                    选择文件夹
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <!-- 运行配置 -->
        <div class="form-section">
          <div class="section-header">
            <h3>运行配置</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <a-tooltip title="切换账号时需要执行的操作">
                    <span class="form-label">
                      账号切换方法
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select v-model:value="maaConfig.Run.TaskTransitionMethod" size="large">
                  <a-select-option value="ExitEmulator">重启模拟器</a-select-option>
                  <a-select-option value="ExitGame">重启明日方舟</a-select-option>
                  <a-select-option value="NoAction">直接切换账号</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <a-tooltip title="使用mumu模拟器时设为3，其他模拟器设为0">
                    <span class="form-label">
                      ADB端口号搜索范围
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-number
                  v-model:value="maaConfig.Run.ADBSearchRange"
                  :min="0"
                  :max="3"
                  size="large"
                  class="modern-number-input"
                  style="width: 100%"
                />
              </a-form-item>
            </a-col>

            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <a-tooltip title="当用户本日代理成功次数达到该阀值时跳过代理，阈值为「0」时视为无代理次数上限">
                    <span class="form-label">
                      用户单日代理次数上限
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-number
                  v-model:value="maaConfig.Run.ProxyTimesLimit"
                  :min="0"
                  :max="999"
                  size="large"
                  class="modern-number-input"
                  style="width: 100%"
                />
              </a-form-item>
            </a-col>
          </a-row>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <a-tooltip title="执行剿灭代理任务时，MAA日志无变化时间超过该阀值视为超时">
                    <span class="form-label">
                      剿灭代理超时限制（分钟）
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-number
                  v-model:value="maaConfig.Run.AnnihilationTimeLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  class="modern-number-input"
                  style="width: 100%"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <a-tooltip title="每周剿灭达到上限后，本周剩余时间不在执行剿灭任务，本功能存在误判可能，请谨慎使用">
                    <span class="form-label">
                      每周剿灭仅执行到上限
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select v-model:value="maaConfig.Run.AnnihilationWeeklyLimit" size="large">
                  <a-select-option :value="true">是</a-select-option>
                  <a-select-option :value="false">否</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
          </a-row>

          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <a-tooltip title="执行日常代理任务时，MAA日志无变化时间超过该阀值视为超时">
                    <span class="form-label">
                      日常代理超时限制（分钟）
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-number
                  v-model:value="maaConfig.Run.RoutineTimeLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  class="modern-number-input"
                  style="width: 100%"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <a-tooltip title="若重试超过该次数限制仍未完成代理，视为代理失败">
                    <span class="form-label">
                      代理重试次数限制
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-number
                  v-model:value="maaConfig.Run.RunTimesLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  class="modern-number-input"
                  style="width: 100%"
                />
              </a-form-item>
            </a-col>
          </a-row>
        </div>
      </a-form>
    </a-card>
  </div>
  <a-float-button
    type="primary"
    @click="handleSave"
    class="float-button"
    :style="{
      right: '24px',
    }"
  >
    <template #icon>
      <SaveOutlined />
    </template>
  </a-float-button>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { FormInstance } from 'ant-design-vue'
import { message } from 'ant-design-vue'
import type { MAAScriptConfig, ScriptType } from '../../../types/script.ts'
import { useScriptApi } from '../../../composables/useScriptApi.ts'
import {
  ArrowLeftOutlined,
  FolderOpenOutlined,
  QuestionCircleOutlined,
  SaveOutlined,
} from '@ant-design/icons-vue'

const route = useRoute()
const router = useRouter()
const { getScript, updateScript, loading } = useScriptApi()

const formRef = ref<FormInstance>()
const pageLoading = ref(false)
const scriptId = route.params.id as string

const formData = reactive({
  name: '',
  type: 'MAA' as ScriptType,
})

// MAA配置
const maaConfig = reactive<MAAScriptConfig>({
  Info: {
    Name: '',
    Path: '.',
  },
  Run: {
    ADBSearchRange: 0,
    AnnihilationTimeLimit: 40,
    AnnihilationWeeklyLimit: true,
    ProxyTimesLimit: 0,
    RoutineTimeLimit: 10,
    RunTimesLimit: 3,
    TaskTransitionMethod: 'ExitEmulator',
  },
  SubConfigsInfo: {
    UserData: {
      instances: [],
    },
  },
})

const rules = {
  name: [{ required: true, message: '请输入脚本名称', trigger: 'blur' }],
  type: [{ required: true, message: '请选择脚本类型', trigger: 'change' }],
}

onMounted(async () => {
  await loadScript()
})

const loadScript = async () => {
  pageLoading.value = true
  try {
    // 检查是否有通过路由状态传递的数据（新建脚本时）
    const routeState = history.state as any
    if (routeState?.scriptData) {
      // 使用API返回的新建脚本数据
      const scriptData = routeState.scriptData
      const config = scriptData.config as MAAScriptConfig
      formData.name = config.Info.Name || '新建MAA脚本'
      Object.assign(maaConfig, config)
      // 如果名称为空，设置默认名称
      if (!maaConfig.Info.Name) {
        maaConfig.Info.Name = '新建MAA脚本'
        formData.name = '新建MAA脚本'
      }
    } else {
      // 编辑现有脚本时，从API获取数据
      const scriptDetail = await getScript(scriptId)

      if (!scriptDetail) {
        message.error('脚本不存在或加载失败')
        router.push('/scripts')
        return
      }

      formData.type = scriptDetail.type
      formData.name = scriptDetail.name

      Object.assign(maaConfig, scriptDetail.config as MAAScriptConfig)
    }
  } catch (error) {
    console.error('加载脚本失败:', error)
    message.error('加载脚本失败')
    router.push('/scripts')
  } finally {
    pageLoading.value = false
  }
}

const handleSave = async () => {
  try {
    await formRef.value?.validate()

    maaConfig.Info.Name = formData.name

    const result = await updateScript(scriptId, maaConfig)
    if (result) {
      message.success('脚本更新成功')
      router.push('/scripts')
    }
  } catch (error) {
    console.error('保存失败:', error)
  }
}

const handleCancel = () => {
  router.push('/scripts')
}

// 文件选择方法
const selectMAAPath = async () => {
  try {
    if (!window.electronAPI) {
      message.error('文件选择功能不可用，请在 Electron 环境中运行')
      return
    }

    const path = await (window.electronAPI as any).selectFolder()
    if (path) {
      maaConfig.Info.Path = path
      message.success('MAA路径选择成功')
    }
  } catch (error) {
    console.error('选择MAA路径失败:', error)
    message.error('选择文件夹失败')
  }
}
</script>

<style scoped>
/* 头部区域 */
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
  transition: all 0.3s ease;
}

/* 内容区域 */
.script-edit-content {
  flex: 1;
}

.config-card {
  border-radius: 16px;
  box-shadow:
    0 4px 20px rgba(0, 0, 0, 0.08),
    0 1px 3px rgba(0, 0, 0, 0.1);
  border: 1px solid var(--ant-color-border-secondary);
  overflow: hidden;
}

.config-card :deep(.ant-card-head) {
  background: var(--ant-color-bg-container);
  border-bottom: 2px solid var(--ant-color-border-secondary);
  padding: 24px 32px;
}

.config-card :deep(.ant-card-head-title) {
  font-size: 24px;
  font-weight: 700;
  color: var(--ant-color-text);
}

.config-card :deep(.ant-card-body) {
  padding: 32px;
  background: var(--ant-color-bg-container);
}

.type-tag {
  font-size: 14px;
  font-weight: 600;
  padding: 8px 16px;
  border-radius: 8px;
  border: none;
}

/* 表单样式 */
.config-form {
  max-width: none;
}

.form-section {
  margin-bottom: 12px;
}

.form-section:last-child {
  margin-bottom: 0;
}

.section-header {
  margin-bottom: 6px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 12px;
}

.section-header h3::before {
  content: '';
  width: 4px;
  height: 24px;
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  border-radius: 2px;
}

/* 表单标签 */
.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--ant-color-text);
  font-size: 14px;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
  cursor: help;
  transition: color 0.3s ease;
}

.help-icon:hover {
  color: var(--ant-color-primary);
}

.modern-input {
  border-radius: 8px;
  border: 2px solid var(--ant-color-border);
  background: var(--ant-color-bg-container);
  transition: all 0.3s ease;
}

.modern-input:hover {
  border-color: var(--ant-color-primary-hover);
}

.modern-input:focus,
.modern-input.ant-input-focused {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.1);
}

.modern-select :deep(.ant-select-selector) {
  border: 2px solid var(--ant-color-border) !important;
  border-radius: 8px !important;
  background: var(--ant-color-bg-container) !important;
  transition: all 0.3s ease;
}

.modern-select:hover :deep(.ant-select-selector) {
  border-color: var(--ant-color-primary-hover) !important;
}

.modern-select.ant-select-focused :deep(.ant-select-selector) {
  border-color: var(--ant-color-primary) !important;
  box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.1) !important;
}

.modern-number-input {
  border-radius: 8px;
}

.modern-number-input :deep(.ant-input-number) {
  border: 2px solid var(--ant-color-border);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
  transition: all 0.3s ease;
}

.modern-number-input :deep(.ant-input-number:hover) {
  border-color: var(--ant-color-primary-hover);
}

.modern-number-input :deep(.ant-input-number-focused) {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.1);
}

/* 路径输入组 */
.path-input-group {
  display: flex;
  border-radius: 8px;
  overflow: hidden;
  border: 2px solid var(--ant-color-border);
  transition: all 0.3s ease;
}

.path-input-group:hover {
  border-color: var(--ant-color-primary-hover);
}

.path-input-group:focus-within {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.1);
}

.path-input {
  flex: 1;
  border: none !important;
  border-radius: 0 !important;
  background: var(--ant-color-bg-container) !important;
}

.path-input:focus {
  box-shadow: none !important;
}

.path-button {
  border: none;
  border-radius: 0;
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  font-weight: 600;
  padding: 0 20px;
  transition: all 0.3s ease;
  border-left: 1px solid var(--ant-color-border-secondary);
}

.path-button:hover {
  background: var(--ant-color-primary);
  color: white;
  transform: none;
}

/* 表单项间距 */
.config-form :deep(.ant-form-item) {
  margin-bottom: 24px;
}

.config-form :deep(.ant-form-item-label) {
  padding-bottom: 8px;
}

.config-form :deep(.ant-form-item-label > label) {
  font-weight: 600;
  color: var(--ant-color-text);
}

/* 深色模式适配 */
@media (prefers-color-scheme: dark) {
  .config-card {
    box-shadow:
      0 4px 20px rgba(0, 0, 0, 0.3),
      0 1px 3px rgba(0, 0, 0, 0.4);
  }

  .path-input-group:focus-within {
    box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.2);
  }

  .modern-input:focus,
  .modern-input.ant-input-focused {
    box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.2);
  }

  .modern-select.ant-select-focused :deep(.ant-select-selector) {
    box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.2) !important;
  }

  .modern-number-input :deep(.ant-input-number-focused) {
    box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.2);
  }
}

/* 响应式设计 */
@media (max-width: 1200px) {
  .config-card :deep(.ant-card-body) {
    padding: 24px;
  }

  .form-section {
    margin-bottom: 12px;
  }
}

@media (max-width: 768px) {
  .script-edit-header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }

  .config-card :deep(.ant-card-head) {
    padding: 16px 20px;
  }

  .config-card :deep(.ant-card-head-title) {
    font-size: 20px;
  }

  .config-card :deep(.ant-card-body) {
    padding: 20px;
  }

  .section-header h3 {
    font-size: 18px;
  }

  .form-section {
    margin-bottom: 12px;
  }

  .path-button {
    padding: 0 16px;
    font-size: 14px;
  }

  .cancel-button,
  .save-button {
    height: 44px;
    font-size: 14px;
    padding: 0 20px;
  }
}

/* 动画效果 */
@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.form-section {
  animation: fadeInUp 0.6s ease-out;
}

.form-section:nth-child(2) {
  animation-delay: 0.1s;
}

.form-section:nth-child(3) {
  animation-delay: 0.2s;
}

.form-section:nth-child(4) {
  animation-delay: 0.3s;
}

/* Tooltip样式优化 */
:deep(.ant-tooltip-inner) {
  background: var(--ant-color-bg-elevated);
  color: var(--ant-color-text);
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  padding: 12px 16px;
  font-size: 13px;
  line-height: 1.5;
  max-width: 300px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

:deep(.ant-tooltip-arrow::before) {
  background: var(--ant-color-bg-elevated);
  border: 1px solid var(--ant-color-border);
}

.float-button {
  width: 60px;
  height: 60px;
}
</style>
