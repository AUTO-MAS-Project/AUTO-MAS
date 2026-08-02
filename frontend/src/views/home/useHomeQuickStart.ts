import { ref } from 'vue'
import { message } from 'ant-design-vue'
import type { ComboBoxItem } from '@/api'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { Service } from '@/api/services/Service'
import { useAudioPlayer } from '@/composables/useAudioPlayer'
import { useSchedulerLogic } from '@/views/scheduler/useSchedulerLogic'

const mockSchedulerTasks: ComboBoxItem[] = [
  { label: '队列 - 每日自动化', value: 'mock-daily-queue' },
  { label: '脚本 - 通用巡检', value: 'mock-general-check' },
  { label: '队列 - 夜间批处理', value: 'mock-nightly-queue' },
]

const homeGreetingMessages = [
  '坐和放宽，脚本正在为你努力运行中。',
  '启动前请确认脚本路径已正确，否则它将无法找到自己。',
  '请勿™强制关闭AUTO-MAS，正在处理一些事情。',
  '好东西就要来了……别来无恙啊！',
  'AUTO-MAS正在为你的设备匹配专属脚本设置。',
  '启动AUTO-MAS脚本系统，不要说我们没有警告过你。',
  '需要重启脚本是正常现象，请不要惊慌。',
  '你的设备正在准备就绪，准备好迎接脚本运行了吗？',
  '运行完成后，你的游戏进度可能会发生位移。',
  '我们的脚本协议更新了，你只能同意不能不同意。',
  '请耐心等待，进度条只是看起来不动而已。',
  '感谢你使用AUTO-MAS，你永远可以相信脚本的力量。',
  '正在应用最适合当前宇宙版本的脚本设置。',
  '你的请求很重要，AUTO-MAS正在以看似安静的方式处理它。',
  'AUTO-MAS检测到一切正常，除非稍后它不正常。',
  '请稍候，系统正在把复杂问题包装成一个按钮。',
]

const pickHomeGreeting = () => {
  const index = Math.floor(Math.random() * homeGreetingMessages.length)
  return homeGreetingMessages[index] ?? homeGreetingMessages[0]
}

export const useHomeQuickStart = () => {
  const logger = window.electronAPI.getLogger('首页')
  const { playSound } = useAudioPlayer()
  const { trackStartedTask } = useSchedulerLogic()

  const commandTitle = ref(pickHomeGreeting())
  const schedulerTasksLoading = ref(false)
  const startingHomeTask = ref(false)
  const schedulerTaskOptions = ref<ComboBoxItem[]>(mockSchedulerTasks)
  const selectedHomeTaskId = ref<string | null>(mockSchedulerTasks[0]?.value ?? null)
  const selectedHomeMode = ref<TaskCreateIn.mode>(TaskCreateIn.mode.AUTO_PROXY)

  const fetchSchedulerTaskOptions = async (options?: { quiet?: boolean }) => {
    schedulerTasksLoading.value = true

    try {
      const response = await Service.getTaskComboxApiInfoComboxTaskPost()
      if (response.code === 200 && response.data?.length) {
        schedulerTaskOptions.value = response.data
        if (
          !selectedHomeTaskId.value ||
          !response.data.some(item => item.value === selectedHomeTaskId.value)
        ) {
          selectedHomeTaskId.value = response.data[0]?.value ?? null
        }
        return
      }

      schedulerTaskOptions.value = mockSchedulerTasks
      selectedHomeTaskId.value = mockSchedulerTasks[0]?.value ?? null
      if (!options?.quiet) {
        message.warning('任务列表暂不可用，已显示占位任务')
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.warn(`获取首页任务列表失败: ${errorMsg}`)
      schedulerTaskOptions.value = mockSchedulerTasks
      selectedHomeTaskId.value = mockSchedulerTasks[0]?.value ?? null
    } finally {
      schedulerTasksLoading.value = false
    }
  }

  const onSchedulerDropdownVisibleChange = (open: boolean) => {
    if (open) {
      fetchSchedulerTaskOptions({ quiet: true })
    }
  }

  const startHomeTask = async () => {
    if (!selectedHomeTaskId.value) {
      message.error('请选择任务项')
      return
    }

    if (selectedHomeTaskId.value.startsWith('mock-')) {
      message.info('当前为首页占位任务，接入真实任务列表后可直接启动')
      return
    }

    startingHomeTask.value = true
    try {
      const response = await Service.addTaskApiDispatchStartPost({
        taskId: selectedHomeTaskId.value,
        mode: selectedHomeMode.value,
      })

      if (response.code === 200) {
        const selectedTask = schedulerTaskOptions.value.find(
          option => option.value === selectedHomeTaskId.value
        )
        trackStartedTask({
          taskId: response.taskId,
          selectedTaskId: selectedHomeTaskId.value,
          selectedMode: selectedHomeMode.value,
          taskLabel: selectedTask?.label || '首页快速任务',
          modeLabel: '自动代理',
        })
        message.success('任务已开始')
        await playSound('task_started')
      } else {
        message.error(response.message || '开始任务失败')
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`首页开始任务失败: ${errorMsg}`)
      message.error('开始任务失败，请检查调度服务状态')
    } finally {
      startingHomeTask.value = false
    }
  }

  return {
    commandTitle,
    schedulerTasksLoading,
    startingHomeTask,
    schedulerTaskOptions,
    selectedHomeTaskId,
    fetchSchedulerTaskOptions,
    onSchedulerDropdownVisibleChange,
    startHomeTask,
  }
}
