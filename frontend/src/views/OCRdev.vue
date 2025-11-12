<template>
  <div class="ocr-debug-page">
    <!-- 标题 -->
    <div class="page-header">
      <h1>OCR 功能测试页面</h1>
      <p class="description">测试窗口截图、ADB 截图、图像检查和点击操作功能</p>
      <p class="description">别忘了它只是个孩子，可能出现各种奇怪的问题</p>
    </div>

    <!-- 功能选项卡 -->
    <a-tabs v-model:activeKey="activeTab" type="card">
      <!-- 截图测试 -->
      <a-tab-pane key="screenshot" tab="窗口截图">
        <a-card title="截图参数配置" class="config-card">
          <a-form :model="screenshotForm" layout="vertical">
            <a-row :gutter="16">
              <a-col :span="24">
                <a-form-item label="窗口标题" required>
                  <a-input
                    v-model:value="screenshotForm.window_title"
                    placeholder="请输入窗口标题关键字（如：记事本、Chrome）"
                  />
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="16">
              <a-col :span="12">
                <a-form-item label="宽高比 - 宽度">
                  <a-input-number
                    v-model:value="screenshotForm.aspect_ratio_width"
                    :min="1"
                    :max="32"
                    style="width: 100%"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item label="宽高比 - 高度">
                  <a-input-number
                    v-model:value="screenshotForm.aspect_ratio_height"
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
                    v-model:checked="screenshotForm.should_preprocess"
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
                <a-button type="primary" :loading="screenshotLoading" @click="handleScreenshot">
                  <template #icon>
                    <CameraOutlined />
                  </template>
                  获取截图
                </a-button>
                <a-button @click="resetScreenshotForm">
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
      </a-tab-pane>

      <!-- ADB 截图测试 -->
      <a-tab-pane key="adb-screenshot" tab="ADB 截图">
        <a-card title="ADB 截图参数配置" class="config-card">
          <a-form :model="adbScreenshotForm" layout="vertical">
            <a-row :gutter="16">
              <a-col :span="24">
                <a-form-item label="ADB 可执行文件路径" required>
                  <a-input
                    v-model:value="adbScreenshotForm.adb_path"
                    placeholder="请输入 ADB 可执行文件的完整路径（如：D:\Android\platform-tools\adb.exe）"
                  />
                  <span style="color: var(--ant-color-text-secondary); font-size: 12px">
                    Windows 示例: D:\Android\platform-tools\adb.exe
                  </span>
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="16">
              <a-col :span="24">
                <a-form-item label="设备序列号" required>
                  <a-input
                    v-model:value="adbScreenshotForm.serial"
                    placeholder="请输入设备序列号（如：127.0.0.1:5555 或 emulator-5554）"
                  />
                  <span style="color: var(--ant-color-text-secondary); font-size: 12px">
                    网络设备示例: 127.0.0.1:5555 | USB设备示例: emulator-5554 | 可通过 adb devices 命令查看
                  </span>
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="16">
              <a-col :span="24">
                <a-form-item label="截图方法">
                  <a-switch
                    v-model:checked="adbScreenshotForm.use_screencap"
                    checked-children="PNG"
                    un-checked-children="RAW"
                  />
                  <span style="margin-left: 12px; color: var(--ant-color-text-secondary)">
                    PNG 方法速度更快（推荐），RAW 方法兼容性更好
                  </span>
                </a-form-item>
              </a-col>
            </a-row>

            <a-form-item>
              <a-space>
                <a-button type="primary" :loading="adbScreenshotLoading" @click="handleADBScreenshot">
                  <template #icon>
                    <CameraOutlined />
                  </template>
                  获取 ADB 截图
                </a-button>
                <a-button @click="resetADBScreenshotForm">
                  <template #icon>
                    <ClearOutlined />
                  </template>
                  重置参数
                </a-button>
              </a-space>
            </a-form-item>
          </a-form>
        </a-card>

        <!-- ADB 截图结果展示 -->
        <a-card v-if="adbScreenshotResult" title="ADB 截图结果" class="result-card">
          <a-descriptions bordered :column="2">
            <a-descriptions-item label="状态">
              <a-tag :color="adbScreenshotResult.code === 200 ? 'success' : 'error'">
                {{ adbScreenshotResult.status }}
              </a-tag>
            </a-descriptions-item>
            <a-descriptions-item label="消息">
              {{ adbScreenshotResult.message }}
            </a-descriptions-item>
            <a-descriptions-item label="设备序列号">
              {{ adbScreenshotResult.serial }}
            </a-descriptions-item>
            <a-descriptions-item label="图片尺寸">
              {{ adbScreenshotResult.image_width }} × {{ adbScreenshotResult.image_height }}
            </a-descriptions-item>
          </a-descriptions>

          <!-- 图片展示 -->
          <div v-if="adbScreenshotResult.image_base64" class="image-container">
            <h3>截图预览：</h3>
            <img
              :src="`data:image/png;base64,${adbScreenshotResult.image_base64}`"
              alt="ADB 截图"
              class="screenshot-image"
            />
          </div>
          <a-empty v-else description="未获取到截图数据" />
        </a-card>
      </a-tab-pane>

      <!-- 图像检查测试 -->
      <a-tab-pane key="check" tab="图像检查">
        <a-card title="图像检查配置" class="config-card">
          <a-form :model="checkForm" layout="vertical">
            <a-row :gutter="16">
              <a-col :span="24">
                <a-form-item label="检查模式" required>
                  <a-radio-group v-model:value="checkForm.mode" button-style="solid">
                    <a-radio-button value="single">单个图像</a-radio-button>
                    <a-radio-button value="any">任意一个</a-radio-button>
                    <a-radio-button value="all">全部图像</a-radio-button>
                  </a-radio-group>
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="16">
              <a-col :span="24">
                <a-form-item label="窗口标题" required>
                  <a-input
                    v-model:value="checkForm.window_title"
                    placeholder="请输入窗口标题关键字"
                  />
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="16">
              <a-col :span="24">
                <a-form-item :label="checkForm.mode === 'single' ? '图片路径' : '图片路径列表'" required>
                  <a-textarea
                    v-model:value="checkForm.image_paths_text"
                    :placeholder="checkForm.mode === 'single' ? '请输入图片完整路径' : '请输入图片路径，每行一个'"
                    :rows="4"
                  />
                  <span style="color: var(--ant-color-text-secondary); font-size: 12px">
                    {{ checkForm.mode === 'single' ? '例如: D:\\images\\button.png' : '多个路径时每行一个路径' }}
                  </span>
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="16">
              <a-col :span="8">
                <a-form-item label="重试次数">
                  <a-input-number
                    v-model:value="checkForm.retry_times"
                    :min="1"
                    :max="20"
                    style="width: 100%"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="8">
                <a-form-item label="间隔时间(秒)">
                  <a-input-number
                    v-model:value="checkForm.interval"
                    :min="0"
                    :max="10"
                    :step="0.5"
                    style="width: 100%"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="8">
                <a-form-item label="匹配阈值">
                  <a-input-number
                    v-model:value="checkForm.threshold"
                    :min="0"
                    :max="1"
                    :step="0.05"
                    style="width: 100%"
                  />
                </a-form-item>
              </a-col>
            </a-row>

            <a-form-item>
              <a-space>
                <a-button type="primary" :loading="checkLoading" @click="handleCheck">
                  <template #icon>
                    <SearchOutlined />
                  </template>
                  开始检查
                </a-button>
                <a-button @click="resetCheckForm">
                  <template #icon>
                    <ClearOutlined />
                  </template>
                  重置参数
                </a-button>
              </a-space>
            </a-form-item>
          </a-form>
        </a-card>

        <!-- 检查结果展示 -->
        <a-card v-if="checkResult" title="检查结果" class="result-card">
          <a-descriptions bordered :column="2">
            <a-descriptions-item label="状态">
              <a-tag :color="checkResult.code === 200 ? 'success' : 'error'">
                {{ checkResult.status }}
              </a-tag>
            </a-descriptions-item>
            <a-descriptions-item label="消息">
              {{ checkResult.message }}
            </a-descriptions-item>
            <a-descriptions-item label="查找结果">
              <a-tag :color="checkResult.found ? 'success' : 'warning'">
                {{ checkResult.found ? '✓ 找到' : '✗ 未找到' }}
              </a-tag>
            </a-descriptions-item>
            <a-descriptions-item label="尝试次数">
              {{ checkResult.attempts }}
            </a-descriptions-item>
          </a-descriptions>
        </a-card>
      </a-tab-pane>

      <!-- 点击操作测试 -->
      <a-tab-pane key="click" tab="点击操作">
        <a-card title="点击操作配置" class="config-card">
          <a-form :model="clickForm" layout="vertical">
            <a-row :gutter="16">
              <a-col :span="24">
                <a-form-item label="点击模式" required>
                  <a-radio-group v-model:value="clickForm.mode" button-style="solid">
                    <a-radio-button value="image">点击图像</a-radio-button>
                    <a-radio-button value="text">点击文字</a-radio-button>
                  </a-radio-group>
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="16">
              <a-col :span="24">
                <a-form-item label="窗口标题" required>
                  <a-input
                    v-model:value="clickForm.window_title"
                    placeholder="请输入窗口标题关键字"
                  />
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="16">
              <a-col :span="24">
                <a-form-item v-if="clickForm.mode === 'image'" label="图片路径" required>
                  <a-input
                    v-model:value="clickForm.image_path"
                    placeholder="请输入要点击的图片完整路径"
                  />
                  <span style="color: var(--ant-color-text-secondary); font-size: 12px">
                    例如: D:\images\button.png
                  </span>
                </a-form-item>
                <a-form-item v-else label="文字内容" required>
                  <a-input
                    v-model:value="clickForm.text"
                    placeholder="请输入要点击的文字内容"
                  />
                  <span style="color: var(--ant-color-text-secondary); font-size: 12px">
                    将通过OCR识别并点击该文字
                  </span>
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="16">
              <a-col :span="8">
                <a-form-item label="重试次数">
                  <a-input-number
                    v-model:value="clickForm.retry_times"
                    :min="1"
                    :max="20"
                    style="width: 100%"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="8">
                <a-form-item label="间隔时间(秒)">
                  <a-input-number
                    v-model:value="clickForm.interval"
                    :min="0"
                    :max="10"
                    :step="0.5"
                    style="width: 100%"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="8" v-if="clickForm.mode === 'image'">
                <a-form-item label="匹配阈值">
                  <a-input-number
                    v-model:value="clickForm.threshold"
                    :min="0"
                    :max="1"
                    :step="0.05"
                    style="width: 100%"
                  />
                </a-form-item>
              </a-col>
            </a-row>

            <a-form-item>
              <a-space>
                <a-button type="primary" danger :loading="clickLoading" @click="handleClick">
                  <template #icon>
                    <ThunderboltOutlined />
                  </template>
                  执行点击
                </a-button>
                <a-button @click="resetClickForm">
                  <template #icon>
                    <ClearOutlined />
                  </template>
                  重置参数
                </a-button>
              </a-space>
            </a-form-item>
          </a-form>
        </a-card>

        <!-- 点击结果展示 -->
        <a-card v-if="clickResult" title="点击结果" class="result-card">
          <a-descriptions bordered :column="2">
            <a-descriptions-item label="状态">
              <a-tag :color="clickResult.code === 200 ? 'success' : 'error'">
                {{ clickResult.status }}
              </a-tag>
            </a-descriptions-item>
            <a-descriptions-item label="消息">
              {{ clickResult.message }}
            </a-descriptions-item>
            <a-descriptions-item label="点击结果">
              <a-tag :color="clickResult.success ? 'success' : 'error'">
                {{ clickResult.success ? '✓ 成功' : '✗ 失败' }}
              </a-tag>
            </a-descriptions-item>
            <a-descriptions-item label="尝试次数">
              {{ clickResult.attempts }}
            </a-descriptions-item>
          </a-descriptions>
        </a-card>
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { message } from 'ant-design-vue'
import {
  CameraOutlined,
  ClearOutlined,
  SearchOutlined,
  ThunderboltOutlined
} from '@ant-design/icons-vue'
import { OcrService } from '@/api/services/OcrService'
import type { OCRScreenshotIn } from '@/api/models/OCRScreenshotIn'
import type { OCRScreenshotOut } from '@/api/models/OCRScreenshotOut'
import type { ADBScreenshotIn } from '@/api/models/ADBScreenshotIn'
import type { ADBScreenshotOut } from '@/api/models/ADBScreenshotOut'

// 当前激活的标签页
const activeTab = ref('screenshot')

// ========== 截图测试 ==========
const screenshotForm = reactive<OCRScreenshotIn>({
  window_title: '',
  should_preprocess: true,
  aspect_ratio_width: 16,
  aspect_ratio_height: 9,
})
const screenshotLoading = ref(false)
const screenshotResult = ref<OCRScreenshotOut | null>(null)

const handleScreenshot = async () => {
  if (!screenshotForm.window_title.trim()) {
    message.error('请输入窗口标题')
    return
  }

  try {
    screenshotLoading.value = true
    screenshotResult.value = null

    const response = await OcrService.getScreenshotApiOcrScreenshotPost({
      window_title: screenshotForm.window_title,
      should_preprocess: screenshotForm.should_preprocess,
      aspect_ratio_width: screenshotForm.aspect_ratio_width,
      aspect_ratio_height: screenshotForm.aspect_ratio_height,
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
    screenshotLoading.value = false
  }
}

const resetScreenshotForm = () => {
  screenshotForm.window_title = ''
  screenshotForm.should_preprocess = true
  screenshotForm.aspect_ratio_width = 16
  screenshotForm.aspect_ratio_height = 9
  screenshotResult.value = null
}

// ========== ADB 截图测试 ==========
const adbScreenshotForm = reactive<ADBScreenshotIn>({
  adb_path: '',
  serial: '',
  use_screencap: true,
})
const adbScreenshotLoading = ref(false)
const adbScreenshotResult = ref<ADBScreenshotOut | null>(null)

const handleADBScreenshot = async () => {
  if (!adbScreenshotForm.adb_path.trim()) {
    message.error('请输入 ADB 可执行文件路径')
    return
  }

  if (!adbScreenshotForm.serial.trim()) {
    message.error('请输入设备序列号')
    return
  }

  try {
    adbScreenshotLoading.value = true
    adbScreenshotResult.value = null

    const response = await OcrService.getScreenshotAdbApiOcrScreenshotAdbPost({
      adb_path: adbScreenshotForm.adb_path,
      serial: adbScreenshotForm.serial,
      use_screencap: adbScreenshotForm.use_screencap,
    })

    adbScreenshotResult.value = response

    if (response.code === 200) {
      message.success('ADB 截图获取成功！')
    } else {
      message.error(response.message || 'ADB 截图失败')
    }
  } catch (error) {
    console.error('获取 ADB 截图失败:', error)
    message.error(`获取 ADB 截图失败: ${error}`)
  } finally {
    adbScreenshotLoading.value = false
  }
}

const resetADBScreenshotForm = () => {
  adbScreenshotForm.adb_path = ''
  adbScreenshotForm.serial = ''
  adbScreenshotForm.use_screencap = true
  adbScreenshotResult.value = null
}

// ========== 图像检查测试 ==========
const checkForm = reactive({
  mode: 'single' as 'single' | 'any' | 'all',
  window_title: '',
  image_paths_text: '',
  retry_times: 1,
  interval: 0,
  threshold: 0.8,
})
const checkLoading = ref(false)
const checkResult = ref<any>(null)

const handleCheck = async () => {
  if (!checkForm.window_title.trim()) {
    message.error('请输入窗口标题')
    return
  }

  if (!checkForm.image_paths_text.trim()) {
    message.error('请输入图片路径')
    return
  }

  try {
    checkLoading.value = true
    checkResult.value = null

    let response: any

    if (checkForm.mode === 'single') {
      // 单个图像检查
      response = await OcrService.checkImageApiOcrCheckImagePost({
        window_title: checkForm.window_title,
        image_path: checkForm.image_paths_text.trim(),
        retry_times: checkForm.retry_times,
        interval: checkForm.interval,
        threshold: checkForm.threshold,
      })
    } else {
      // 多个图像检查
      const imagePaths = checkForm.image_paths_text
        .split('\n')
        .map(path => path.trim())
        .filter(path => path.length > 0)

      if (imagePaths.length === 0) {
        message.error('请至少输入一个图片路径')
        return
      }

      if (checkForm.mode === 'any') {
        response = await OcrService.checkImageAnyApiOcrCheckImageAnyPost({
          window_title: checkForm.window_title,
          image_paths: imagePaths,
          retry_times: checkForm.retry_times,
          interval: checkForm.interval,
          threshold: checkForm.threshold,
        })
      } else {
        response = await OcrService.checkImageAllApiOcrCheckImageAllPost({
          window_title: checkForm.window_title,
          image_paths: imagePaths,
          retry_times: checkForm.retry_times,
          interval: checkForm.interval,
          threshold: checkForm.threshold,
        })
      }
    }

    checkResult.value = response

    if (response.code === 200) {
      if (response.found) {
        message.success('图像检查完成：找到目标图像！')
      } else {
        message.warning('图像检查完成：未找到目标图像')
      }
    } else {
      message.error(response.message || '图像检查失败')
    }
  } catch (error) {
    console.error('图像检查失败:', error)
    message.error(`图像检查失败: ${error}`)
  } finally {
    checkLoading.value = false
  }
}

const resetCheckForm = () => {
  checkForm.mode = 'single'
  checkForm.window_title = ''
  checkForm.image_paths_text = ''
  checkForm.retry_times = 1
  checkForm.interval = 0
  checkForm.threshold = 0.8
  checkResult.value = null
}

// ========== 点击操作测试 ==========
const clickForm = reactive({
  mode: 'image' as 'image' | 'text',
  window_title: '',
  image_path: '',
  text: '',
  retry_times: 1,
  interval: 0,
  threshold: 0.8,
})
const clickLoading = ref(false)
const clickResult = ref<any>(null)

const handleClick = async () => {
  if (!clickForm.window_title.trim()) {
    message.error('请输入窗口标题')
    return
  }

  if (clickForm.mode === 'image' && !clickForm.image_path.trim()) {
    message.error('请输入图片路径')
    return
  }

  if (clickForm.mode === 'text' && !clickForm.text.trim()) {
    message.error('请输入文字内容')
    return
  }

  try {
    clickLoading.value = true
    clickResult.value = null

    let response: any

    if (clickForm.mode === 'image') {
      response = await OcrService.clickImageApiOcrClickImagePost({
        window_title: clickForm.window_title,
        image_path: clickForm.image_path.trim(),
        retry_times: clickForm.retry_times,
        interval: clickForm.interval,
        threshold: clickForm.threshold,
      })
    } else {
      response = await OcrService.clickTextApiOcrClickTextPost({
        window_title: clickForm.window_title,
        text: clickForm.text.trim(),
        retry_times: clickForm.retry_times,
        interval: clickForm.interval,
      })
    }

    clickResult.value = response

    if (response.code === 200) {
      if (response.success) {
        message.success('点击操作成功！')
      } else {
        message.warning('点击操作失败：未找到目标')
      }
    } else {
      message.error(response.message || '点击操作失败')
    }
  } catch (error) {
    console.error('点击操作失败:', error)
    message.error(`点击操作失败: ${error}`)
  } finally {
    clickLoading.value = false
  }
}

const resetClickForm = () => {
  clickForm.mode = 'image'
  clickForm.window_title = ''
  clickForm.image_path = ''
  clickForm.text = ''
  clickForm.retry_times = 1
  clickForm.interval = 0
  clickForm.threshold = 0.8
  clickResult.value = null
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

