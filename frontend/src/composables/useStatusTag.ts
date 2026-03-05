import { computed, type ComputedRef } from 'vue'

/**
 * 状态标签接口定义
 */
export interface StatusTag {
    text: string
    color: string
}

/**
 * 通用状态标签解析和管理 Composable
 * 
 * 该模块提供了一套完整的状态标签（Status Tag）管理方案，用于解析、序列化和显示状态标签。
 * 状态标签通常由后端以JSON字符串格式返回，格式为：{"text": "标签文本", "color": "颜色"}
 * 
 * 主要功能：
 * - 解析单个或多个状态标签
 * - 序列化标签为JSON字符串
 * - 提供Vue响应式的composable函数
 * - 自动适配深色模式（通过Ant Design Vue的Tag组件）
 * 
 * 使用示例：
 * 
 * 1. 基础解析：
 * ```typescript
 * import { parseStatusTag } from '@/composables/useStatusTag'
 * 
 * const status = '{"text": "运行中", "color": "green"}'
 * const tag = parseStatusTag(status, { text: '未启用', color: 'default' })
 * // 返回: { text: '运行中', color: 'green' }
 * ```
 * 
 * 2. 在组件中使用（推荐）：
 * ```vue
 * <script setup>
 * import { useStatusTag, createStatusTag } from '@/composables/useStatusTag'
 * 
 * const statusTag = useStatusTag(
 *   () => config.value.Status,
 *   createStatusTag('未启用', 'default')
 * )
 * </script>
 * 
 * <template>
 *   <a-tag v-if="statusTag" :color="statusTag.color">
 *     {{ statusTag.text }}
 *   </a-tag>
 * </template>
 * ```
 * 
 * 3. 解析标签列表：
 * ```typescript
 * import { parseStatusTagList } from '@/composables/useStatusTag'
 * 
 * const statusList = '[{"text": "状态1", "color": "blue"}, {"text": "状态2", "color": "green"}]'
 * const tags = parseStatusTagList(statusList)
 * // 返回: [{ text: '状态1', color: 'blue' }, { text: '状态2', color: 'green' }]
 * ```
 * 
 * 支持的颜色值：
 * - Ant Design预设颜色：success, processing, error, warning, default
 * - 标准颜色：blue, green, red, orange, cyan, purple, pink, magenta, volcano, geekblue, lime, gold
 * - 自定义十六进制颜色：#1890ff
 * 
 * 注意事项：
 * - Ant Design Vue的Tag组件会自动适配深色模式，无需手动处理
 * - 后端返回的Status字段应为JSON字符串或'-'（表示使用默认值）
 * - 解析失败时会自动降级到默认标签，不会抛出错误
 */

/**
 * 解析状态标签
 * @param status - JSON字符串或null/undefined，格式为 {"text": "xxx", "color": "xxx"}
 * @param defaultTag - 默认标签，当status为'-'或null时返回
 * @returns StatusTag对象或null
 */
export function parseStatusTag(
    status: string | null | undefined,
    defaultTag: StatusTag | null = null
): StatusTag | null {
    if (!status) return defaultTag

    if (status === '-') {
        return defaultTag
    }

    try {
        const tag = JSON.parse(status) as StatusTag
        // 确保必需字段存在
        if (!tag.text) {
            console.warn('解析状态标签时缺少text字段:', status)
            return defaultTag
        }
        return tag
    } catch (error) {
        console.error('解析状态标签失败:', error, 'status=', status)
        return defaultTag || { text: '未知', color: 'default' }
    }
}

/**
 * 解析状态标签数组
 * @param statusList - JSON字符串数组或JSON字符串（单个或数组格式）
 * @param defaultTags - 默认标签数组
 * @returns StatusTag对象数组
 */
export function parseStatusTagList(
    statusList: string | string[] | null | undefined,
    defaultTags: StatusTag[] = []
): StatusTag[] {
    if (!statusList) return defaultTags

    try {
        // 如果是字符串，尝试解析
        if (typeof statusList === 'string') {
            if (statusList === '-') {
                return defaultTags
            }

            const parsed = JSON.parse(statusList)

            // 如果解析结果是数组
            if (Array.isArray(parsed)) {
                return parsed.filter((tag): tag is StatusTag => {
                    return tag && typeof tag.text === 'string'
                })
            }

            // 如果解析结果是单个对象
            if (parsed && typeof parsed.text === 'string') {
                return [parsed as StatusTag]
            }

            return defaultTags
        }

        // 如果已经是数组，处理每个元素
        if (Array.isArray(statusList)) {
            return statusList
                .map(item => parseStatusTag(item, null))
                .filter((tag): tag is StatusTag => tag !== null)
        }

        return defaultTags
    } catch (error) {
        console.error('解析状态标签列表失败:', error, 'statusList=', statusList)
        return defaultTags
    }
}

/**
 * 序列化状态标签为JSON字符串
 * @param tag - StatusTag对象
 * @returns JSON字符串
 */
export function serializeStatusTag(tag: StatusTag): string {
    return JSON.stringify(tag)
}

/**
 * 序列化状态标签数组为JSON字符串
 * @param tags - StatusTag对象数组
 * @returns JSON字符串
 */
export function serializeStatusTagList(tags: StatusTag[]): string {
    return JSON.stringify(tags)
}

/**
 * 使用状态标签的Composable
 * @param statusGetter - 获取状态字符串的函数
 * @param defaultTag - 默认标签
 * @returns 计算属性，返回解析后的StatusTag或null
 */
export function useStatusTag(
    statusGetter: () => string | null | undefined,
    defaultTag: StatusTag | null = null
): ComputedRef<StatusTag | null> {
    return computed(() => parseStatusTag(statusGetter(), defaultTag))
}

/**
 * 使用状态标签列表的Composable
 * @param statusListGetter - 获取状态字符串数组的函数
 * @param defaultTags - 默认标签数组
 * @returns 计算属性，返回解析后的StatusTag数组
 */
export function useStatusTagList(
    statusListGetter: () => string | string[] | null | undefined,
    defaultTags: StatusTag[] = []
): ComputedRef<StatusTag[]> {
    return computed(() => parseStatusTagList(statusListGetter(), defaultTags))
}

/**
 * 创建状态标签对象
 * @param text - 标签文本
 * @param color - 标签颜色（支持Ant Design预设颜色或自定义颜色）
 * @returns StatusTag对象
 * @example
 * createStatusTag('运行中', 'green')
 * createStatusTag('已停止', '#ff0000')
 */
export function createStatusTag(text: string, color: string): StatusTag {
    return { text, color }
}
