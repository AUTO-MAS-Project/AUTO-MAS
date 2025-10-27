<template>
  <div class="ocr-debug-page">
    <!-- 标题 -->
    <div class="page-header">
      <h1>OCR 功能测试页面</h1>
      <p class="description">在此测试窗口截图功能</p>
    </div>

    <!-- 参数配置卡片 -->
    <a-card title="截图参数配置" class="config-card">
      <a-form :model="formData" layout="vertical">
        <a-row :gutter="16">
          <a-col :span="24">
            <a-form-item label="窗口标题" required>
              <a-input
                v-model:value="formData.window_title"
                placeholder="请输入窗口标题关键字（如：记事本、Chrome）"
              />
            </a-form-item>
          </a-col>
        </a-row>

        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="宽高比 - 宽度">
              <a-input-number
                v-model:value="formData.aspect_ratio_width"
                :min="1"
                :max="32"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="宽高比 - 高度">
              <a-input-number
                v-model:value="formData.aspect_ratio_height"
                :min="1"
                :max="32"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
        </a-row>

        <a-row :gutter="16">
          <a-col :span="24">
            <a-form-item label="预处理模式">
              <a-switch
                v-model:checked="formData.should_preprocess"
                checked-children="启用"
                un-checked-children="禁用"
              />
              <span style="margin-left: 12px; color: var(--ant-color-text-secondary)">
                启用时将排除窗口边框和标题栏
              </span>
            </a-form-item>
          </a-col>
        </a-row>

        <a-form-item>
          <a-space>
            <a-button type="primary" :loading="loading" @click="handleScreenshot">
              <template #icon>
                <CameraOutlined />
              </template>
              获取截图
            </a-button>
            <a-button @click="handleReset">
              <template #icon>
                <ClearOutlined />
              </template>
              重置参数
            </a-button>
          </a-space>
        </a-form-item>
      </a-form>
    </a-card>

    <!-- 截图结果展示 -->
    <a-card v-if="screenshotResult" title="截图结果" class="result-card">
      <a-descriptions bordered :column="2">
        <a-descriptions-item label="状态">
          <a-tag :color="screenshotResult.code === 200 ? 'success' : 'error'">
            {{ screenshotResult.status }}
          </a-tag>
        </a-descriptions-item>
        <a-descriptions-item label="消息">
          {{ screenshotResult.message }}
        </a-descriptions-item>
        <a-descriptions-item label="截图区域">
          {{ screenshotResult.region ? `(${screenshotResult.region.join(', ')})` : 'N/A' }}
        </a-descriptions-item>
        <a-descriptions-item label="图片尺寸">
          {{ screenshotResult.image_width }} × {{ screenshotResult.image_height }}
        </a-descriptions-item>
      </a-descriptions>

      <!-- 图片展示 -->
      <div v-if="screenshotResult.image_base64" class="image-container">
        <h3>截图预览：</h3>
        <img
          :src="`data:image/png;base64,${screenshotResult.image_base64}`"
          alt="截图"
          class="screenshot-image"
        />
      </div>
      <a-empty v-else description="未获取到截图数据" />
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { message } from 'ant-design-vue'
import { CameraOutlined, ClearOutlined } from '@ant-design/icons-vue'
import { OcrService } from '@/api/services/OcrService'
import type { OCRScreenshotIn } from '@/api/models/OCRScreenshotIn'
import type { OCRScreenshotOut } from '@/api/models/OCRScreenshotOut'

// 表单数据
const formData = reactive<OCRScreenshotIn>({
  window_title: '',
  should_preprocess: true,
  aspect_ratio_width: 16,
  aspect_ratio_height: 9,
})

// 加载状态
const loading = ref(false)

// 截图结果
const screenshotResult = ref<OCRScreenshotOut | null>(null)

// 获取截图
const handleScreenshot = async () => {
  if (!formData.window_title.trim()) {
    message.error('请输入窗口标题')
    return
  }

  try {
    loading.value = true
    screenshotResult.value = null

    const response = await OcrService.getScreenshotApiOcrScreenshotPost({
      window_title: formData.window_title,
      should_preprocess: formData.should_preprocess,
      aspect_ratio_width: formData.aspect_ratio_width,
      aspect_ratio_height: formData.aspect_ratio_height,
    })

    screenshotResult.value = response

    if (response.code === 200) {
      message.success('截图获取成功！')
    } else {
      message.error(response.message || '截图失败')
    }
  } catch (error) {
    console.error('获取截图失败:', error)
    message.error(`获取截图失败: ${error}`)
  } finally {
    loading.value = false
  }
}

// 重置参数
const handleReset = () => {
  formData.window_title = ''
  formData.should_preprocess = true
  formData.aspect_ratio_width = 16
  formData.aspect_ratio_height = 9
  screenshotResult.value = null
}
</script>

<style scoped>
.ocr-debug-page {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 24px;
}

.page-header h1 {
  margin: 0 0 8px 0;
  font-size: 28px;
  font-weight: 700;
  color: var(--ant-color-text);
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.description {
  margin: 0;
  color: var(--ant-color-text-secondary);
  font-size: 14px;
}

.config-card {
  margin-bottom: 24px;
}

.result-card {
  margin-top: 24px;
}

.image-container {
  margin-top: 24px;
  padding: 16px;
  background: var(--ant-color-bg-layout);
  border-radius: 8px;
}

.image-container h3 {
  margin: 0 0 16px 0;
  font-size: 16px;
  font-weight: 600;
}

.screenshot-image {
  max-width: 100%;
  height: auto;
  border: 1px solid var(--ant-color-border);
  border-radius: 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}
</style>
