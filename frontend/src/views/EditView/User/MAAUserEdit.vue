<template>
  <div class="user-edit-container">
    <!-- MAA配置遮罩层 -->
    <teleport to="body">
      <div v-if="showMAAConfigMask" class="maa-config-mask">
        <div class="mask-content">
          <div class="mask-icon">
            <SettingOutlined :style="{ fontSize: '48px', color: '#1890ff' }" />
          </div>
          <h2 class="mask-title">正在进行MAA配置</h2>
          <p class="mask-description">
            当前正在配置该用户的 MAA，请在 MAA 配置界面完成相关设置。
            <br />
            配置完成后，请点击"保存配置"按钮来结束配置会话。
          </p>
          <div class="mask-actions">
            <a-button
              v-if="maaWebsocketId"
              type="primary"
              size="large"
              @click="handleSaveMAAConfig"
            >
              保存配置
            </a-button>
          </div>
        </div>
      </div>
    </teleport>
    <!-- 头部组件 -->
    <MAAUserEditHeader
      :script-id="scriptId"
      :script-name="scriptName"
      :is-edit="isEdit"
      :user-mode="formData.Info.Mode"
      :maa-config-loading="maaConfigLoading"
      :loading="loading"
      @handle-m-a-a-config="handleMAAConfig"
      @handle-cancel="handleCancel"
      @handle-submit="handleSubmit"
    />

    <div class="user-edit-content">
      <a-card class="config-card">
        <a-form
          ref="formRef"
          :model="formData"
          :rules="rules"
          layout="vertical"
          class="config-form"
        >
          <!-- 基本信息组件 -->
          <BasicInfoSection
            :form-data="formData"
            :loading="loading"
            :server-options="serverOptions"
            :infrastructure-config-path="infrastructureConfigPath"
            :infrastructure-importing="infrastructureImporting"
            :is-edit="isEdit"
            @select-infrastructure-config="selectInfrastructureConfig"
            @import-infrastructure-config="importInfrastructureConfig"
          />

          <!-- 关卡配置组件 -->
          <StageConfigSection
            :form-data="formData"
            :loading="loading"
            :stage-mode-options="stageModeOptions"
            :stage-options="stageOptions"
            :stage-remain-options="stageRemainOptions"
            :is-plan-mode="isPlanMode"
            :display-medicine-numb="displayMedicineNumb"
            :display-series-numb="displaySeriesNumb"
            :display-stage="displayStage"
            :display-stage1="displayStage1"
            :display-stage2="displayStage2"
            :display-stage3="displayStage3"
            :display-stage-remain="displayStageRemain"
            :medicine-numb-tooltip="medicineNumbTooltip"
            :series-numb-tooltip="seriesNumbTooltip"
            :stage-tooltip="stageTooltip"
            :stage1-tooltip="stage1Tooltip"
            :stage2-tooltip="stage2Tooltip"
            :stage3-tooltip="stage3Tooltip"
            :stage-remain-tooltip="stageRemainTooltip"
            @update-medicine-numb="updateMedicineNumb"
            @update-series-numb="updateSeriesNumb"
            @update-stage="updateStage"
            @update-stage1="updateStage1"
            @update-stage2="updateStage2"
            @update-stage3="updateStage3"
            @update-stage-remain="updateStageRemain"
            @handle-add-custom-stage="addCustomStage"
            @handle-add-custom-stage1="addCustomStage1"
            @handle-add-custom-stage2="addCustomStage2"
            @handle-add-custom-stage3="addCustomStage3"
            @handle-add-custom-stage-remain="addCustomStageRemain"
          />

          <!-- 任务配置组件 -->
          <TaskConfigSection :form-data="formData" :loading="loading" />

          <!-- 森空岛配置组件 -->
          <SkylandConfigSection :form-data="formData" :loading="loading" />

          <!-- 通知配置组件 -->
          <NotifyConfigSection
            :form-data="formData"
            :loading="loading"
            :script-id="scriptId"
            :user-id="userId"
          />
        </a-form>
      </a-card>
    </div>

    <a-float-button
      type="primary"
      class="float-button"
      :style="{
        right: '24px',
      }"
      @click="handleSubmit"
    >
      <template #icon>
        <SaveOutlined />
      </template>
    </a-float-button>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { SaveOutlined, SettingOutlined } from '@ant-design/icons-vue'
import type { FormInstance, Rule } from 'ant-design-vue/es/form'
import { useUserApi } from '@/composables/useUserApi.ts'
import { useScriptApi } from '@/composables/useScriptApi.ts'
import { usePlanApi } from '@/composables/usePlanApi.ts'
import { useWebSocket } from '@/composables/useWebSocket.ts'
import { Service } from '@/api'
import { TaskCreateIn } from '@/api/models/TaskCreateIn.ts'
import { GetStageIn } from '@/api/models/GetStageIn.ts'
import { getWeekdayInTimezone } from '@/utils/dateUtils.ts'

// 导入拆分的组件
import MAAUserEditHeader from '../../MAAUserEdit/MAAUserEditHeader.vue'
import BasicInfoSection from '../../MAAUserEdit/BasicInfoSection.vue'
import StageConfigSection from '../../MAAUserEdit/StageConfigSection.vue'
import TaskConfigSection from '../../MAAUserEdit/TaskConfigSection.vue'
import SkylandConfigSection from '../../MAAUserEdit/SkylandConfigSection.vue'
import NotifyConfigSection from '../../MAAUserEdit/NotifyConfigSection.vue'

const router = useRouter()
const route = useRoute()
const { addUser, updateUser, getUsers, loading: userLoading } = useUserApi()
const { getScript } = useScriptApi()
const { getPlans } = usePlanApi()
const { subscribe, unsubscribe } = useWebSocket()

const formRef = ref<FormInstance>()
const loading = computed(() => userLoading.value)

// 路由参数
const scriptId = route.params.scriptId as string
const userId = route.params.userId as string
const isEdit = computed(() => !!userId)

// 脚本信息
const scriptName = ref('')

// MAA配置相关
const maaConfigLoading = ref(false)
const maaSubscriptionId = ref<string | null>(null)
const maaWebsocketId = ref<string | null>(null)
const showMAAConfigMask = ref(false)
let maaConfigTimeout: number | null = null

// 基建配置文件相关
const infrastructureConfigPath = ref('')
const infrastructureImporting = ref(false)

// 服务器选项
const serverOptions = [
  { label: '官服', value: 'Official' },
  { label: 'B服', value: 'Bilibili' },
  { label: '国际服（YoStarEN）', value: 'YoStarEN' },
  { label: '日服（YoStarJP）', value: 'YoStarJP' },
  { label: '韩服（YoStarKR）', value: 'YoStarKR' },
  { label: '繁中服（txwy）', value: 'txwy' },
]

// 关卡选项
const stageOptions = ref<any[]>([{ label: '不选择', value: '' }])

// 剩余理智关卡专用选项（将"当前/上次"改为"不选择"）
const stageRemainOptions = computed(() => {
  return stageOptions.value.map(option => {
    if (option.value === '-') {
      return { ...option, label: option.label.replace('当前/上次', '不选择') }
    }
    return option
  })
})

// 判断值是否为自定义关卡
const isCustomStage = (value: string) => {
  if (!value || value === '' || value === '-') return false

  // 检查是否在从API加载的关卡列表中
  const predefinedStage = stageOptions.value.find(
    option => option.value === value && !option.isCustom
  )

  return !predefinedStage
}

// 关卡配置模式选项
const stageModeOptions = ref<any[]>([{ label: '固定', value: 'Fixed' }])

// 计划模式状态
const isPlanMode = computed(() => {
  return formData.Info.StageMode !== 'Fixed'
})
const planModeConfig = ref<any>(null)
// 新增：存储完整的计划数据用于悬浮提示
const fullPlanData = ref<any>(null)

// 新增：生成计划表悬浮提示内容的函数
const getPlanTooltip = (fieldName: string) => {
  if (!fullPlanData.value || !isPlanMode.value) return ''

  const planData = fullPlanData.value
  const mode = planData.Info?.Mode || 'ALL'

  if (mode === 'ALL') {
    return '此项由全局计划表控制'
  } else if (mode === 'Weekly') {
    const weekdays = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    const weekdaysZh = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

    let tooltip = '此项由周计划表控制:\n'

    weekdays.forEach((day, index) => {
      const dayConfig = planData[day]
      let value = ''

      if (dayConfig && dayConfig[fieldName] !== undefined) {
        value = dayConfig[fieldName]
      } else if (planData.ALL && planData.ALL[fieldName] !== undefined) {
        value = planData.ALL[fieldName] + ' (全局)'
      } else {
        value = '未设置'
      }

      // 格式化特殊字段的显示
      if (fieldName === 'SeriesNumb') {
        if (value === '0') value = 'AUTO'
        else if (value === '-1') value = '不切换'
      } else if (
        fieldName === 'Stage' ||
        fieldName === 'Stage_1' ||
        fieldName === 'Stage_2' ||
        fieldName === 'Stage_3'
      ) {
        if (value === '-') value = '当前/上次'
        else if (value === '') value = '不选择'
      } else if (fieldName === 'Stage_Remain') {
        if (value === '-') value = '不选择'
        else if (value === '') value = '不选择'
      }

      tooltip += `${weekdaysZh[index]}: ${value}\n`
    })

    return tooltip.trim()
  }

  return ''
}

// 新增：各字段的悬浮提示计算属性
const medicineNumbTooltip = computed(() => getPlanTooltip('MedicineNumb'))
const seriesNumbTooltip = computed(() => getPlanTooltip('SeriesNumb'))
const stageTooltip = computed(() => getPlanTooltip('Stage'))
const stage1Tooltip = computed(() => getPlanTooltip('Stage_1'))
const stage2Tooltip = computed(() => getPlanTooltip('Stage_2'))
const stage3Tooltip = computed(() => getPlanTooltip('Stage_3'))
const stageRemainTooltip = computed(() => getPlanTooltip('Stage_Remain'))

// 计算属性用于显示正确的值（来自计划表或用户配置）
const displayMedicineNumb = computed({
  get: () => {
    if (isPlanMode.value && planModeConfig.value?.MedicineNumb !== undefined) {
      return planModeConfig.value.MedicineNumb
    }
    return formData.Info.MedicineNumb
  },
  set: value => {
    if (!isPlanMode.value) {
      formData.Info.MedicineNumb = value
    }
  },
})

const displaySeriesNumb = computed({
  get: () => {
    if (isPlanMode.value && planModeConfig.value?.SeriesNumb !== undefined) {
      return planModeConfig.value.SeriesNumb
    }
    return formData.Info.SeriesNumb
  },
  set: value => {
    if (!isPlanMode.value) {
      formData.Info.SeriesNumb = value
    }
  },
})

const displayStage = computed({
  get: () => {
    if (isPlanMode.value && planModeConfig.value?.Stage !== undefined) {
      return planModeConfig.value.Stage
    }
    return formData.Info.Stage
  },
  set: value => {
    if (!isPlanMode.value) {
      formData.Info.Stage = value
    }
  },
})

const displayStage1 = computed({
  get: () => {
    if (isPlanMode.value && planModeConfig.value?.Stage_1 !== undefined) {
      return planModeConfig.value.Stage_1
    }
    return formData.Info.Stage_1
  },
  set: value => {
    if (!isPlanMode.value) {
      formData.Info.Stage_1 = value
    }
  },
})

const displayStage2 = computed({
  get: () => {
    if (isPlanMode.value && planModeConfig.value?.Stage_2 !== undefined) {
      return planModeConfig.value.Stage_2
    }
    return formData.Info.Stage_2
  },
  set: value => {
    if (!isPlanMode.value) {
      formData.Info.Stage_2 = value
    }
  },
})

const displayStage3 = computed({
  get: () => {
    if (isPlanMode.value && planModeConfig.value?.Stage_3 !== undefined) {
      return planModeConfig.value.Stage_3
    }
    return formData.Info.Stage_3
  },
  set: value => {
    if (!isPlanMode.value) {
      formData.Info.Stage_3 = value
    }
  },
})

const displayStageRemain = computed({
  get: () => {
    if (isPlanMode.value && planModeConfig.value?.Stage_Remain !== undefined) {
      return planModeConfig.value.Stage_Remain
    }
    return formData.Info.Stage_Remain
  },
  set: value => {
    if (!isPlanMode.value) {
      formData.Info.Stage_Remain = value
    }
  },
})

// 获取计划当前配置
const getPlanCurrentConfig = (planData: any) => {
  if (!planData) return null

  const mode = planData.Info?.Mode || 'ALL'

  if (mode === 'ALL') {
    return planData.ALL || null
  } else if (mode === 'Weekly') {
    // 使用东4区时区的今天是星期几（已经是数字0-6）
    const todayWeekday = getWeekdayInTimezone(4)

    const weekdays = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    const today = weekdays[todayWeekday]

    console.log('计划表周模式调试:', {
      东4区星期几: todayWeekday,
      星期: today,
      计划数据: planData,
    })

    // 优先使用今天的配置，如果没有或为空则使用ALL配置
    const todayConfig = planData[today]
    if (todayConfig && Object.keys(todayConfig).length > 0) {
      return todayConfig
    }
    return planData.ALL || null
  }

  return null
}

// MAA脚本默认用户数据
const getDefaultMAAUserData = () => ({
  Info: {
    Name: '',
    Id: '',
    Password: '',
    Server: 'Official',
    MedicineNumb: 0,
    RemainedDay: -1,
    SeriesNumb: '0',
    Notes: '',
    Status: true,
    Mode: '简洁',
    InfrastMode: 'Normal',
    InfrastPath: '',
    Annihilation: 'Annihilation',
    Stage: '1-7',
    StageMode: 'Fixed',
    Stage_1: '',
    Stage_2: '',
    Stage_3: '',
    Stage_Remain: '',
    IfSkland: false,
    SklandToken: '',
  },
  Task: {
    IfWakeUp: true,
    IfBase: true,
    IfCombat: true,
    IfMall: true,
    IfMission: true,
    IfRecruiting: true,
    IfReclamation: false,
    IfAutoRoguelike: false,
  },
  Notify: {
    Enabled: false,
    ToAddress: '',
    IfSendMail: false,
    IfSendSixStar: false,
    IfSendStatistic: false,
    IfServerChan: false,
    ServerChanKey: '',
    ServerChanChannel: '',
    ServerChanTag: '',
    CustomWebhooks: [],
  },
  Data: {
    CustomInfrastPlanIndex: '',
    IfPassCheck: false,
    LastAnnihilationDate: '',
    LastProxyDate: '',
    LastSklandDate: '',
    ProxyTimes: 0,
  },
})

// 创建扁平化的表单数据，用于表单验证
const formData = reactive({
  // 扁平化的验证字段
  userName: '',
  userId: '',
  // 嵌套的实际数据
  ...getDefaultMAAUserData(),
})

// 表单验证规则
const rules = computed(() => {
  const baseRules: Record<string, Rule[]> = {
    userName: [
      { required: true, message: '请输入用户名', trigger: 'blur' },
      { min: 1, max: 50, message: '用户名长度应在1-50个字符之间', trigger: 'blur' },
    ],
  }
  return baseRules
})

// 同步扁平化字段与嵌套数据
watch(
  () => formData.Info.Name,
  newVal => {
    if (formData.userName !== newVal) {
      formData.userName = newVal || ''
    }
  },
  { immediate: true }
)

watch(
  () => formData.Info.Id,
  newVal => {
    if (formData.userId !== newVal) {
      formData.userId = newVal || ''
    }
  },
  { immediate: true }
)

watch(
  () => formData.userName,
  newVal => {
    if (formData.Info.Name !== newVal) {
      formData.Info.Name = newVal || ''
    }
  }
)

watch(
  () => formData.userId,
  newVal => {
    if (formData.Info.Id !== newVal) {
      formData.Info.Id = newVal || ''
    }
  }
)

// 加载脚本信息
const loadScriptInfo = async () => {
  try {
    const script = await getScript(scriptId)
    if (script) {
      scriptName.value = script.name

      // 如果是编辑模式，加载用户数据
      if (isEdit.value) {
        await loadUserData()
      }
    } else {
      message.error('脚本不存在')
      handleCancel()
    }
  } catch (error) {
    console.error('加载脚本信息失败:', error)
    message.error('加载脚本信息失败')
  }
}

// 加载用户数据
const loadUserData = async () => {
  try {
    const userResponse = await getUsers(scriptId, userId)

    if (userResponse && userResponse.code === 200) {
      // 查找指定的用户数据
      const userIndex = userResponse.index.find(index => index.uid === userId)
      if (userIndex && userResponse.data[userId]) {
        const userData = userResponse.data[userId] as any

        // 填充MAA用户数据
        if (userIndex.type === 'MaaUserConfig') {
          Object.assign(formData, {
            Info: { ...getDefaultMAAUserData().Info, ...userData.Info },
            Task: { ...getDefaultMAAUserData().Task, ...userData.Task },
            Notify: { ...getDefaultMAAUserData().Notify, ...userData.Notify },
            Data: { ...getDefaultMAAUserData().Data, ...userData.Data },
          })
        }

        // 同步扁平字段 - 使用nextTick确保数据更新完成后再同步
        await nextTick()
        formData.userName = formData.Info.Name || ''
        formData.userId = formData.Info.Id || ''

        // 检查并添加自定义关卡到选项列表
        const stageFields = ['Stage', 'Stage_1', 'Stage_2', 'Stage_3', 'Stage_Remain']
        stageFields.forEach(field => {
          const stageValue = (formData.Info as any)[field]
          if (stageValue && isCustomStage(stageValue)) {
            // 检查是否已存在
            const exists = stageOptions.value.find((option: any) => option.value === stageValue)
            if (!exists) {
              stageOptions.value.push({
                label: stageValue,
                value: stageValue,
                isCustom: true,
              })
            }
          }
        })

        console.log('用户数据加载成功:', {
          userName: formData.userName,
          userId: formData.userId,
          InfoName: formData.Info.Name,
          InfoId: formData.Info.Id,
          fullData: formData,
        })
      } else {
        message.error('用户不存在')
        handleCancel()
      }
    } else {
      message.error('获取用户数据失败')
      handleCancel()
    }
  } catch (error) {
    console.error('加载用户数据失败:', error)
    message.error('加载用户数据失败')
  }
}

const loadStageOptions = async () => {
  try {
    const response = await Service.getStageComboxApiInfoComboxStagePost({
      type: GetStageIn.type.TODAY,
    })
    if (response && response.code === 200 && response.data) {
      stageOptions.value = [...response.data].map(option => ({
        ...option,
        isCustom: false, // 明确标记从API加载的关卡为非自定义
      }))
    }
  } catch (error) {
    console.error('加载关卡选项失败:', error)
  }
}

const loadStageModeOptions = async () => {
  try {
    const response = await Service.getPlanComboxApiInfoComboxPlanPost()
    if (response && response.code === 200 && response.data) {
      stageModeOptions.value = response.data
    }
  } catch (error) {
    console.error('加载关卡配置模式选项失败:', error)
    // 保持默认的固定选项
  }
}

// 选择基建配置文件
const selectInfrastructureConfig = async () => {
  try {
    const path = await (window as any).electronAPI?.selectFile([
      { name: 'JSON 文件', extensions: ['json'] },
      { name: '所有文件', extensions: ['*'] },
    ])
    if (path && path.length > 0) {
      infrastructureConfigPath.value = path
      formData.Info.InfrastPath = path[0]
      message.success('文件选择成功')
    }
  } catch (error) {
    console.error('文件选择失败:', error)
    message.error('文件选择失败')
  }
}

// 导入基建配置
const importInfrastructureConfig = async () => {
  if (!infrastructureConfigPath.value) {
    message.warning('请先选择配置文件')
    return
  }
  if (!isEdit.value) {
    message.warning('请先保存用户后再导入配置')
    return
  }
  try {
    infrastructureImporting.value = true
    const result = await Service.importInfrastructureApiScriptsUserInfrastructurePost({
      scriptId: scriptId,
      userId: userId,
      jsonFile: infrastructureConfigPath.value[0],
    })
    if (result && result.code === 200) {
      message.success('基建配置导入成功')
      infrastructureConfigPath.value = ''
    } else {
      message.error('基建配置导入失败')
    }
  } catch (error) {
    console.error('基建配置导入失败:', error)
    message.error('基建配置导入失败')
  } finally {
    infrastructureImporting.value = false
  }
}

const handleSubmit = async () => {
  try {
    await formRef.value?.validate()

    // 确保扁平化字段同步到嵌套数据
    formData.Info.Name = formData.userName
    formData.Info.Id = formData.userId

    console.log('提交前的表单数据:', {
      userName: formData.userName,
      userId: formData.userId,
      InfoName: formData.Info.Name,
      InfoId: formData.Info.Id,
      isEdit: isEdit.value,
    })

    // 排除 InfrastPath 字段
    const { InfrastPath, ...infoWithoutInfrastPath } = formData.Info

    // 构建提交数据
    const userData = {
      Info: { ...infoWithoutInfrastPath },
      Task: { ...formData.Task },
      Notify: { ...formData.Notify },
      Data: { ...formData.Data },
    }

    if (isEdit.value) {
      // 编辑模式
      const result = await updateUser(scriptId, userId, userData)
      if (result) {
        message.success('用户更新成功')
        handleCancel()
      }
    } else {
      // 添加模式
      const result = await addUser(scriptId)
      if (result) {
        // 创建成功后立即更新用户数据
        try {
          const updateResult = await updateUser(scriptId, result.userId, userData)
          console.log('用户数据更新结果:', updateResult)

          if (updateResult) {
            message.success('用户创建成功')
            handleCancel()
          } else {
            message.error('用户创建成功，但数据更新失败，请手动编辑用户信息')
            // 不跳转，让用户可以重新保存
          }
        } catch (updateError) {
          console.error('更新用户数据时发生错误:', updateError)
          message.error('用户创建成功，但数据更新失败，请手动编辑用户信息')
        }
      }
    }
  } catch (error) {
    console.error('表单验证失败:', error)
  }
}

const handleMAAConfig = async () => {
  if (!isEdit.value) {
    message.warning('请先保存用户后再进行MAA配置')
    return
  }

  try {
    maaConfigLoading.value = true

    // 如果已有连接，先断开
    if (maaSubscriptionId.value) {
      unsubscribe(maaSubscriptionId.value)
      maaSubscriptionId.value = null
      maaWebsocketId.value = null
      showMAAConfigMask.value = false
      if (maaConfigTimeout) {
        window.clearTimeout(maaConfigTimeout)
        maaConfigTimeout = null
      }
    }

    // 调用后端启动任务接口，传入 userId 作为 taskId 与设置模式
    const response = await Service.addTaskApiDispatchStartPost({
      taskId: userId,
      mode: TaskCreateIn.mode.SettingScriptMode,
    })

    if (response && response.websocketId) {
      const wsId = response.websocketId

      // 订阅 websocket
      const subscriptionId = subscribe({ id: wsId }, (wsMessage: any) => {
        if (wsMessage.type === 'error') {
          console.error(
            `用户 ${formData.Info?.Name || formData.userName} MAA配置错误:`,
            wsMessage.data
          )
          message.error(`MAA配置连接失败: ${wsMessage.data}`)
          unsubscribe(subscriptionId)
          maaSubscriptionId.value = null
          maaWebsocketId.value = null
          showMAAConfigMask.value = false
          return
        }

        if (wsMessage.data && wsMessage.data.Accomplish) {
          message.success(`用户 ${formData.Info?.Name || formData.userName} 的配置已完成`)
          unsubscribe(subscriptionId)
          maaSubscriptionId.value = null
          maaWebsocketId.value = null
          showMAAConfigMask.value = false
        }
      })

      maaSubscriptionId.value = subscriptionId
      maaWebsocketId.value = wsId
      showMAAConfigMask.value = true
      message.success(`已开始配置用户 ${formData.Info?.Name || formData.userName} 的MAA设置`)

      // 设置 30 分钟超时自动断开
      maaConfigTimeout = window.setTimeout(
        () => {
          if (maaSubscriptionId.value) {
            unsubscribe(maaSubscriptionId.value)
            maaSubscriptionId.value = null
            maaWebsocketId.value = null
            showMAAConfigMask.value = false
            message.info(`用户 ${formData.Info?.Name || formData.userName} 的配置会话已超时断开`)
          }
          maaConfigTimeout = null
        },
        30 * 60 * 1000
      )
    } else {
      message.error(response?.message || '启动MAA配置失败')
    }
  } catch (error) {
    console.error('启动MAA配置失败:', error)
    message.error('启动MAA配置失败')
  } finally {
    maaConfigLoading.value = false
  }
}

const handleSaveMAAConfig = async () => {
  try {
    const websocketId = maaWebsocketId.value
    if (!websocketId) {
      message.error('未找到活动的配置会话')
      return
    }

    const response = await Service.stopTaskApiDispatchStopPost({ taskId: websocketId })
    if (response && response.code === 200) {
      if (maaSubscriptionId.value) {
        unsubscribe(maaSubscriptionId.value)
        maaSubscriptionId.value = null
      }
      maaWebsocketId.value = null
      showMAAConfigMask.value = false
      if (maaConfigTimeout) {
        window.clearTimeout(maaConfigTimeout)
        maaConfigTimeout = null
      }
      message.success('用户的配置已保存')
    } else {
      message.error(response.message || '保存配置失败')
    }
  } catch (error) {
    console.error('保存MAA配置失败:', error)
    message.error('保存MAA配置失败')
  }
}

// 验证关卡名称格式
const validateStageName = (stageName: string): boolean => {
  if (!stageName || !stageName.trim()) {
    return false
  }

  // 简单的关卡名称验证，可以根据实际需要调整
  const stagePattern = /^[a-zA-Z0-9\-_\u4e00-\u9fa5]+$/
  return stagePattern.test(stageName.trim())
}

// 添加自定义关卡到选项列表
const addStageToOptions = (stageName: string) => {
  if (!stageName || !stageName.trim()) {
    return false
  }

  const trimmedName = stageName.trim()

  // 检查是否已存在
  const exists = stageOptions.value.find((option: any) => option.value === trimmedName)
  if (exists) {
    message.warning(`关卡 "${trimmedName}" 已存在`)
    return false
  }

  // 添加到选项列表
  stageOptions.value.push({
    label: trimmedName,
    value: trimmedName,
    isCustom: true,
  })

  message.success(`自定义关卡 "${trimmedName}" 添加成功`)
  return true
}

// 添加主关卡
const addCustomStage = (stageName: string) => {
  if (!validateStageName(stageName)) {
    message.error('请输入有效的关卡名称')
    return
  }

  if (addStageToOptions(stageName)) {
    if (!isPlanMode.value) {
      formData.Info.Stage = stageName.trim()
    }
  }
}

// 添加备选关卡-1
const addCustomStage1 = (stageName: string) => {
  if (!validateStageName(stageName)) {
    message.error('请输入有效的关卡名称')
    return
  }

  if (addStageToOptions(stageName)) {
    if (!isPlanMode.value) {
      formData.Info.Stage_1 = stageName.trim()
    }
  }
}

// 添加备选关卡-2
const addCustomStage2 = (stageName: string) => {
  if (!validateStageName(stageName)) {
    message.error('请输入有效的关卡名称')
    return
  }

  if (addStageToOptions(stageName)) {
    if (!isPlanMode.value) {
      formData.Info.Stage_2 = stageName.trim()
    }
  }
}

// 添加备选关卡-3
const addCustomStage3 = (stageName: string) => {
  if (!validateStageName(stageName)) {
    message.error('请输入有效的关卡名称')
    return
  }

  if (addStageToOptions(stageName)) {
    if (!isPlanMode.value) {
      formData.Info.Stage_3 = stageName.trim()
    }
  }
}

// 添加剩余理智关卡
const addCustomStageRemain = (stageName: string) => {
  if (!validateStageName(stageName)) {
    message.error('请输入有效的关卡名称')
    return
  }

  if (addStageToOptions(stageName)) {
    if (!isPlanMode.value) {
      formData.Info.Stage_Remain = stageName.trim()
    }
  }
}

const handleCancel = () => {
  if (maaSubscriptionId.value) {
    unsubscribe(maaSubscriptionId.value)
    maaSubscriptionId.value = null
    maaWebsocketId.value = null
  }
  router.push('/scripts')
}
// 新增：处理来自StageConfigSection的值更新事件
const updateMedicineNumb = (value: number) => {
  if (!isPlanMode.value) {
    formData.Info.MedicineNumb = value
  }
}

const updateSeriesNumb = (value: string) => {
  if (!isPlanMode.value) {
    formData.Info.SeriesNumb = value
  }
}

const updateStage = (value: string) => {
  if (!isPlanMode.value) {
    formData.Info.Stage = value
  }
}

const updateStage1 = (value: string) => {
  if (!isPlanMode.value) {
    formData.Info.Stage_1 = value
  }
}

const updateStage2 = (value: string) => {
  if (!isPlanMode.value) {
    formData.Info.Stage_2 = value
  }
}

const updateStage3 = (value: string) => {
  if (!isPlanMode.value) {
    formData.Info.Stage_3 = value
  }
}

const updateStageRemain = (value: string) => {
  if (!isPlanMode.value) {
    formData.Info.Stage_Remain = value
  }
}

// 初始化加载
onMounted(() => {
  if (!scriptId) {
    message.error('缺少脚本ID参数')
    handleCancel()
    return
  }

  loadScriptInfo()
  loadStageModeOptions()
  loadStageOptions()

  // 设置StageMode变化监听器
  watch(
    () => formData.Info.StageMode,
    async newStageMode => {
      if (newStageMode === 'Fixed') {
        // 切换到固定模式，清除计划配置
        planModeConfig.value = null
      } else if (newStageMode && newStageMode !== '') {
        // 切换到计划模式，加载计划配置
        try {
          const response = await getPlans(newStageMode)

          if (response && response.code === 200 && response.data[newStageMode]) {
            const planData = response.data[newStageMode]
            const currentConfig = getPlanCurrentConfig(planData)
            planModeConfig.value = currentConfig

            // 新增：保存完整的计划数据用于悬浮提示
            fullPlanData.value = planData

            console.log('计划配置加载成功:', {
              planId: newStageMode,
              currentConfig,
              planModeConfigValue: planModeConfig.value,
            })

            // 从stageModeOptions中查找对应的计划名称
            const planOption = stageModeOptions.value.find(option => option.value === newStageMode)
            const planName = planOption ? planOption.label : newStageMode

            message.success(`已切换到计划模式：${planName}`)
          } else {
            message.warning('计划配置加载失败，请检查计划是否存在')
            planModeConfig.value = null
          }
        } catch (error) {
          console.error('加载计划配置失败:', error)
          message.error('加载计划配置时发生错误')
          planModeConfig.value = null
        }
      }
    },
    { immediate: false }
  )
})
</script>

<style scoped>
.user-edit-container {
  padding: 32px;
  min-height: 100vh;
  background: var(--ant-color-bg-layout);
}

.user-edit-content {
  max-width: 1200px;
  margin: 0 auto;
}

.config-card {
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.config-card :deep(.ant-card-body) {
  padding: 32px;
}

.config-form {
  max-width: none;
}

.float-button {
  width: 60px;
  height: 60px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .user-edit-container {
    padding: 16px;
  }

  .user-edit-content {
    max-width: 100%;
  }
}

/* MAA 配置遮罩样式（与 Scripts.vue 一致，用于全局覆盖） */
.maa-config-mask {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.mask-content {
  background: var(--ant-color-bg-elevated);
  border-radius: 8px;
  padding: 24px;
  max-width: 480px;
  width: 100%;
  text-align: center;
  box-shadow:
    0 6px 16px 0 rgba(0, 0, 0, 0.08),
    0 3px 6px -4px rgba(0, 0, 0, 0.12),
    0 9px 28px 8px rgba(0, 0, 0, 0.05);
  border: 1px solid var(--ant-color-border);
}

.mask-icon {
  margin-bottom: 16px;
}

.mask-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 8px;
  color: var(--ant-color-text);
}

.mask-description {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
  margin: 0 0 24px;
  line-height: 1.5;
}

.mask-actions {
  display: flex;
  justify-content: center;
}
</style>
