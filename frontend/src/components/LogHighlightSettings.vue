<script setup lang="ts">
import { ref, computed } from 'vue'
import { QuestionCircleOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { useLogHighlight, type LogHighlightColors } from '@/composables/useLogHighlight'
import { useTheme } from '@/composables/useTheme'
import { message } from 'ant-design-vue'

const { isDark } = useTheme()
const {
    lightColors,
    darkColors,
    styles,
    editorConfig,
    defaultLightColors,
    defaultDarkColors,
    defaultStyles,
    defaultEditorConfig,
    setLightColors,
    setDarkColors,
    setStyles,
    setEditorConfig,
    resetToDefaults,
} = useLogHighlight()

// 当前编辑的主题
const editingTheme = ref<'light' | 'dark'>(isDark.value ? 'dark' : 'light')

// 当前编辑的颜色
const currentColors = computed(() =>
    editingTheme.value === 'light' ? lightColors.value : darkColors.value
)

// 颜色配置项分组
const colorGroups: {
    title: string
    items: { key: keyof LogHighlightColors; label: string; description: string }[]
}[] = [
        {
            title: '时间相关',
            items: [
                { key: 'timestamp', label: '时间戳', description: '完整的日期时间格式' },
                { key: 'date', label: '日期', description: '单独的日期格式' },
            ]
        },
        {
            title: '日志级别',
            items: [
                { key: 'error', label: '错误', description: 'ERROR/FATAL/CRITICAL 级别' },
                { key: 'warning', label: '警告', description: 'WARN/WARNING 级别' },
                { key: 'info', label: '信息', description: 'INFO/NOTICE 级别' },
                { key: 'debug', label: '调试', description: 'DEBUG 级别' },
                { key: 'trace', label: '追踪', description: 'TRACE/VERBOSE 级别' },
            ]
        },
        {
            title: '结构元素',
            items: [
                { key: 'module', label: '模块名', description: '方括号内的模块/线程名' },
                { key: 'bracket', label: '括号内容', description: '圆括号内的内容' },
            ]
        },
        {
            title: '网络相关',
            items: [
                { key: 'ip', label: 'IP 地址', description: 'IPv4 地址' },
                { key: 'url', label: 'URL', description: 'HTTP/HTTPS 链接' },
                { key: 'port', label: '端口', description: '端口号' },
            ]
        },
        {
            title: '文件系统',
            items: [
                { key: 'path', label: '文件路径', description: '完整的文件路径' },
                { key: 'filename', label: '文件名', description: '带扩展名的文件名' },
            ]
        },
        {
            title: '数据类型',
            items: [
                { key: 'number', label: '数字', description: '整数、小数、科学计数法' },
                { key: 'string', label: '字符串', description: '引号包裹的字符串' },
                { key: 'boolean', label: '布尔值', description: 'true/false/null' },
                { key: 'uuid', label: 'UUID', description: 'UUID 格式的标识符' },
            ]
        },
        {
            title: '关键词',
            items: [
                { key: 'errorKeyword', label: '错误关键词', description: 'Exception/Error/Failed 等' },
                { key: 'success', label: '成功关键词', description: 'Success/Complete/Done 等' },
            ]
        },
        {
            title: '特殊内容',
            items: [
                { key: 'stackTrace', label: '堆栈跟踪', description: 'Java/Python 堆栈信息' },
                { key: 'json', label: 'JSON', description: 'JSON 对象/数组' },
                { key: 'variable', label: '变量', description: 'key=value 格式的变量名' },
                { key: 'operator', label: '操作符', description: '= < > ! 等操作符' },
            ]
        },
    ]

// 更新颜色
const updateColor = (key: keyof LogHighlightColors, value: string) => {
    const colorValue = value.replace('#', '')
    if (editingTheme.value === 'light') {
        setLightColors({ [key]: colorValue })
    } else {
        setDarkColors({ [key]: colorValue })
    }
}

// 重置为默认
const handleReset = () => {
    resetToDefaults()
    message.success('已重置为默认配置')
}

// 重置单个颜色
const resetSingleColor = (key: keyof LogHighlightColors) => {
    const defaultColors = editingTheme.value === 'light' ? defaultLightColors : defaultDarkColors
    if (editingTheme.value === 'light') {
        setLightColors({ [key]: defaultColors[key] })
    } else {
        setDarkColors({ [key]: defaultColors[key] })
    }
}

// 字体大小选项
const fontSizeOptions = [11, 12, 13, 14, 15, 16, 18, 20]

// 行高选项
const lineHeightOptions = [1.2, 1.4, 1.5, 1.6, 1.8, 2.0]
</script>

<template>
    <div class="log-highlight-settings">
        <!-- 文本配置 -->
        <div class="config-section no-border">
            <div class="section-title">文本配置</div>
            <div class="text-config-grid">
                <div class="text-config-item">
                    <div class="text-config-label">字体大小</div>
                    <div class="text-config-control">
                        <a-select :value="editorConfig.fontSize" size="small" style="width: 100%"
                            @change="(v: number) => setEditorConfig({ fontSize: v })">
                            <a-select-option v-for="size in fontSizeOptions" :key="size" :value="size">
                                {{ size }}px
                            </a-select-option>
                        </a-select>
                    </div>
                </div>
                <div class="text-config-item">
                    <div class="text-config-label">行高</div>
                    <div class="text-config-control">
                        <a-select :value="editorConfig.lineHeight" size="small" style="width: 100%"
                            @change="(v: number) => setEditorConfig({ lineHeight: v })">
                            <a-select-option v-for="h in lineHeightOptions" :key="h" :value="h">
                                {{ h }}
                            </a-select-option>
                        </a-select>
                    </div>
                </div>
            </div>
            <div class="text-style-checkboxes">
                <div class="checkbox-row">
                    <a-checkbox :checked="styles.timestampBold"
                        @change="(e: any) => setStyles({ timestampBold: e.target.checked })">
                        时间戳加粗
                    </a-checkbox>
                    <a-checkbox :checked="styles.levelBold"
                        @change="(e: any) => setStyles({ levelBold: e.target.checked })">
                        日志级别加粗
                    </a-checkbox>
                    <a-checkbox :checked="styles.keywordBold"
                        @change="(e: any) => setStyles({ keywordBold: e.target.checked })">
                        关键词加粗
                    </a-checkbox>
                    <a-checkbox :checked="styles.urlUnderline"
                        @change="(e: any) => setStyles({ urlUnderline: e.target.checked })">
                        URL 下划线
                    </a-checkbox>
                </div>
            </div>
        </div>

        <!-- 颜色配置 -->
        <div class="config-section">
            <div class="section-header">
                <div class="section-title">颜色配置</div>
                <div class="section-actions">
                    <a-radio-group v-model:value="editingTheme" button-style="solid" size="small">
                        <a-radio-button value="light">浅色主题</a-radio-button>
                        <a-radio-button value="dark">深色主题</a-radio-button>
                    </a-radio-group>
                    <a-button size="small" @click="handleReset">
                        <template #icon>
                            <ReloadOutlined />
                        </template>
                        重置全部
                    </a-button>
                </div>
            </div>

            <div v-for="group in colorGroups" :key="group.title" class="color-group">
                <div class="group-title">{{ group.title }}</div>
                <div class="color-grid">
                    <div v-for="item in group.items" :key="item.key" class="color-item">
                        <div class="color-info">
                            <span class="color-label">{{ item.label }}</span>
                            <a-tooltip :title="item.description">
                                <QuestionCircleOutlined class="help-icon" />
                            </a-tooltip>
                        </div>
                        <div class="color-controls">
                            <input type="color" :value="'#' + currentColors[item.key]" class="color-picker"
                                @input="(e: Event) => updateColor(item.key, (e.target as HTMLInputElement).value)" />
                            <span class="color-value">#{{ currentColors[item.key] }}</span>
                            <a-button size="small" type="text" @click="resetSingleColor(item.key)" title="重置此颜色">
                                <template #icon>
                                    <ReloadOutlined />
                                </template>
                            </a-button>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- 预览 -->
        <div class="config-section">
            <div class="section-title">预览效果</div>
            <div class="preview-content" :class="editingTheme === 'dark' ? 'preview-dark' : 'preview-light'" :style="{
                fontSize: editorConfig.fontSize + 'px',
                lineHeight: editorConfig.lineHeight
            }">
                <div class="preview-line">
                    <span
                        :style="{ color: '#' + currentColors.timestamp, fontWeight: styles.timestampBold ? 'bold' : 'normal' }">2024-12-09
                        10:30:45.123</span>
                    <span
                        :style="{ color: '#' + currentColors.info, fontWeight: styles.levelBold ? 'bold' : 'normal' }">
                        INFO
                    </span>
                    <span :style="{ color: '#' + currentColors.module }">[MainModule]</span>
                    <span> 应用启动成功，端口</span>
                    <span :style="{ color: '#' + currentColors.port }">:8080</span>
                </div>
                <div class="preview-line">
                    <span
                        :style="{ color: '#' + currentColors.timestamp, fontWeight: styles.timestampBold ? 'bold' : 'normal' }">2024-12-09
                        10:30:46.456</span>
                    <span
                        :style="{ color: '#' + currentColors.warning, fontWeight: styles.levelBold ? 'bold' : 'normal' }">
                        WARN </span>
                    <span :style="{ color: '#' + currentColors.module }">[Network]</span>
                    <span> 连接超时，IP: </span>
                    <span :style="{ color: '#' + currentColors.ip }">192.168.1.100</span>
                    <span :style="{ color: '#' + currentColors.variable }"> retries</span>
                    <span :style="{ color: '#' + currentColors.operator }">=</span>
                    <span :style="{ color: '#' + currentColors.number }">3</span>
                </div>
                <div class="preview-line">
                    <span
                        :style="{ color: '#' + currentColors.timestamp, fontWeight: styles.timestampBold ? 'bold' : 'normal' }">2024-12-09
                        10:30:47.789</span>
                    <span
                        :style="{ color: '#' + currentColors.error, fontWeight: styles.levelBold ? 'bold' : 'normal' }">
                        ERROR
                    </span>
                    <span :style="{ color: '#' + currentColors.module }">[Database]</span>
                    <span
                        :style="{ color: '#' + currentColors.errorKeyword, fontWeight: styles.keywordBold ? 'bold' : 'normal' }">
                        Exception</span>
                    <span>: 连接失败 </span>
                    <span :style="{ color: '#' + currentColors.string }">"Connection refused"</span>
                </div>
                <div class="preview-line">
                    <span :style="{ color: '#' + currentColors.stackTrace }"> at
                        com.example.Database.connect(Database.java:42)</span>
                </div>
                <div class="preview-line">
                    <span
                        :style="{ color: '#' + currentColors.timestamp, fontWeight: styles.timestampBold ? 'bold' : 'normal' }">2024-12-09
                        10:30:48.000</span>
                    <span :style="{ color: '#' + currentColors.debug }"> DEBUG </span>
                    <span :style="{ color: '#' + currentColors.module }">[Task]</span>
                    <span> UUID: </span>
                    <span :style="{ color: '#' + currentColors.uuid }">550e8400-e29b-41d4-a716-446655440000</span>
                </div>
                <div class="preview-line">
                    <span
                        :style="{ color: '#' + currentColors.timestamp, fontWeight: styles.timestampBold ? 'bold' : 'normal' }">2024-12-09
                        10:30:49.123</span>
                    <span :style="{ color: '#' + currentColors.trace }"> TRACE </span>
                    <span :style="{ color: '#' + currentColors.module }">[HTTP]</span>
                    <span> 请求 </span>
                    <span
                        :style="{ color: '#' + currentColors.url, textDecoration: styles.urlUnderline ? 'underline' : 'none' }">https://api.example.com/data</span>
                    <span
                        :style="{ color: '#' + currentColors.success, fontWeight: styles.keywordBold ? 'bold' : 'normal' }">
                        Success</span>
                </div>
                <div class="preview-line">
                    <span :style="{ color: '#' + currentColors.trace }"> TRACE </span>
                    <span> 响应: </span>
                    <span :style="{ color: '#' + currentColors.json }">{"status": "ok", "count": 42}</span>
                    <span> enabled</span>
                    <span :style="{ color: '#' + currentColors.operator }">=</span>
                    <span :style="{ color: '#' + currentColors.boolean }">true</span>
                </div>
            </div>
        </div>
    </div>
</template>

<style scoped>
.log-highlight-settings {
    padding: 8px 0;
}

.config-section {
    margin-bottom: 20px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--ant-color-border-secondary);
}

.config-section.no-border {
    border-bottom: none;
}

.config-section:last-child {
    border-bottom: none;
    margin-bottom: 0;
}

.section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
}

.section-title {
    font-size: 14px;
    font-weight: 600;
    color: var(--ant-color-text);
    margin-bottom: 12px;
}

.section-header .section-title {
    margin-bottom: 0;
}

.section-actions {
    display: flex;
    align-items: center;
    gap: 12px;
}

/* 文本配置样式 */
.text-config-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 8px;
    margin-bottom: 12px;
}

.text-config-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 6px 10px;
    background: var(--ant-color-bg-container);
    border: 1px solid var(--ant-color-border);
    border-radius: 4px;
}

.text-config-label {
    font-size: 12px;
    font-weight: 500;
    color: var(--ant-color-text);
    flex-shrink: 0;
}

.text-config-control {
    flex: 1;
    max-width: 120px;
    margin-left: 12px;
}

.text-style-checkboxes {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding-left: 4px;
}

.checkbox-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
}

.checkbox-row :deep(.ant-checkbox-wrapper) {
    font-size: 14px;
}

/* 原有颜色配置样式 */
.config-item {
    display: flex;
    flex-direction: column;
    gap: 4px;
}

.config-label {
    font-size: 12px;
    color: var(--ant-color-text-secondary);
}

.color-group {
    margin-bottom: 16px;
}

.color-group:last-child {
    margin-bottom: 0;
}

.group-title {
    font-size: 13px;
    font-weight: 500;
    color: var(--ant-color-text-secondary);
    margin-bottom: 8px;
    padding-left: 4px;
}

.color-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 8px;
}

.color-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 6px 10px;
    background: var(--ant-color-bg-container);
    border: 1px solid var(--ant-color-border);
    border-radius: 4px;
}

.color-info {
    display: flex;
    align-items: center;
    gap: 4px;
}

.color-label {
    font-size: 12px;
    font-weight: 500;
    color: var(--ant-color-text);
}

.help-icon {
    color: var(--ant-color-text-secondary);
    font-size: 11px;
}

.color-controls {
    display: flex;
    align-items: center;
    gap: 6px;
}

.color-picker {
    width: 28px;
    height: 20px;
    padding: 0;
    border: 1px solid var(--ant-color-border);
    border-radius: 3px;
    cursor: pointer;
    background: transparent;
}

.color-picker::-webkit-color-swatch-wrapper {
    padding: 1px;
}

.color-picker::-webkit-color-swatch {
    border: none;
    border-radius: 2px;
}

.color-value {
    font-family: monospace;
    font-size: 11px;
    color: var(--ant-color-text-secondary);
    min-width: 55px;
}

.preview-content {
    padding: 12px;
    border-radius: 6px;
    overflow-x: auto;
    font-family: SFMono-Regular, Consolas, 'Liberation Mono', Menlo, Courier, monospace;
}

.preview-light {
    background: #ffffff;
    color: #333333;
    border: 1px solid #d9d9d9;
}

.preview-dark {
    background: #1e1e1e;
    color: #d4d4d4;
    border: 1px solid #424242;
}

.preview-line {
    white-space: nowrap;
}
</style>
