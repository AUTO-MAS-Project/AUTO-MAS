<template>
  <a-modal
    v-model:open="visible"
    :title="isEdit ? '编辑脚本' : '新建脚本'"
    width="800px"
    :confirm-loading="loading"
    @ok="handleSave"
    @cancel="handleCancel"
  >
    <a-form
      ref="formRef"
      :model="formData"
      :rules="rules"
      layout="vertical"
    >
      <a-row :gutter="16">
        <a-col :span="12">
          <a-form-item label="脚本名称" name="name">
            <a-input v-model:value="formData.name" placeholder="请输入脚本名称" />
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="脚本类型" name="type">
            <a-select v-model:value="formData.type" :disabled="isEdit">
              <a-select-option value="MAA">MAA</a-select-option>
              <a-select-option value="General">General</a-select-option>
            </a-select>
          </a-form-item>
        </a-col>
      </a-row>

      <!-- MAA脚本配置 -->
      <template v-if="formData.type === 'MAA'">
        <a-divider>基础配置</a-divider>
        <a-row :gutter="16">
          <a-col :span="24">
            <a-form-item label="脚本路径" name="path">
              <a-input v-model:value="maaConfig.Info.Path" placeholder="请输入MAA脚本路径" />
            </a-form-item>
          </a-col>
        </a-row>
        
        <a-divider>运行配置</a-divider>
        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="ADB搜索范围">
              <a-input-number 
                v-model:value="maaConfig.Run.ADBSearchRange" 
                :min="0" 
                style="width: 100%" 
              />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="剿灭时间限制(分钟)">
              <a-input-number 
                v-model:value="maaConfig.Run.AnnihilationTimeLimit" 
                :min="1" 
                style="width: 100%" 
              />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="代理次数限制">
              <a-input-number 
                v-model:value="maaConfig.Run.ProxyTimesLimit" 
                :min="0" 
                style="width: 100%" 
              />
            </a-form-item>
          </a-col>
        </a-row>
        
        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="日常时间限制(分钟)">
              <a-input-number 
                v-model:value="maaConfig.Run.RoutineTimeLimit" 
                :min="1" 
                style="width: 100%" 
              />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="运行次数限制">
              <a-input-number 
                v-model:value="maaConfig.Run.RunTimesLimit" 
                :min="1" 
                style="width: 100%" 
              />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="任务转换方式">
              <a-select v-model:value="maaConfig.Run.TaskTransitionMethod">
                <a-select-option value="NoAction">无操作</a-select-option>
                <a-select-option value="ExitEmulator">退出模拟器</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
        </a-row>
        
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="剿灭周限制">
              <a-switch v-model:checked="maaConfig.Run.AnnihilationWeeklyLimit" />
            </a-form-item>
          </a-col>
        </a-row>
      </template>

      <!-- General脚本配置 -->
      <template v-if="formData.type === 'General'">
        <a-divider>基础配置</a-divider>
        <a-row :gutter="16">
          <a-col :span="24">
            <a-form-item label="根路径" name="rootPath">
              <a-input v-model:value="generalConfig.Info.RootPath" placeholder="请输入根路径" />
            </a-form-item>
          </a-col>
        </a-row>
        
        <a-divider>游戏配置</a-divider>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="游戏路径">
              <a-input v-model:value="generalConfig.Game.Path" placeholder="请输入游戏路径" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="启动参数">
              <a-input v-model:value="generalConfig.Game.Arguments" placeholder="请输入启动参数" />
            </a-form-item>
          </a-col>
        </a-row>
        
        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="游戏样式">
              <a-select v-model:value="generalConfig.Game.Style">
                <a-select-option value="Emulator">模拟器</a-select-option>
                <a-select-option value="Game">游戏</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="等待时间(秒)">
              <a-input-number 
                v-model:value="generalConfig.Game.WaitTime" 
                :min="0" 
                style="width: 100%" 
              />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="启用游戏">
              <a-switch v-model:checked="generalConfig.Game.Enabled" />
            </a-form-item>
          </a-col>
        </a-row>
        
        <a-divider>脚本配置</a-divider>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="脚本路径">
              <a-input v-model:value="generalConfig.Script.ScriptPath" placeholder="请输入脚本路径" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="配置路径">
              <a-input v-model:value="generalConfig.Script.ConfigPath" placeholder="请输入配置路径" />
            </a-form-item>
          </a-col>
        </a-row>
      </template>
    </a-form>
  </a-modal>
</template>

<script setup lang="ts">
import { ref, reactive, watch, computed } from 'vue'
import { message } from 'ant-design-vue'
import type { FormInstance } from 'ant-design-vue'
import type { ScriptType, MAAScriptConfig, GeneralScriptConfig } from '@/types/script'
import { useScriptApi } from '@/composables/useScriptApi'

interface Props {
  open: boolean
  scriptData?: {
    id?: string
    type: ScriptType
    config: MAAScriptConfig | GeneralScriptConfig
  }
}

interface Emits {
  (e: 'update:open', value: boolean): void
  (e: 'success', data: any): void
}

const props = withDefaults(defineProps<Props>(), {
  open: false
})

const emit = defineEmits<Emits>()

const { addScript, updateScript, loading } = useScriptApi()

const formRef = ref<FormInstance>()
const visible = computed({
  get: () => props.open,
  set: (value) => emit('update:open', value)
})

const isEdit = computed(() => !!props.scriptData?.id)

const formData = reactive({
  name: '',
  type: 'MAA' as ScriptType
})

// MAA配置
const maaConfig = reactive<MAAScriptConfig>({
  Info: {
    Name: '',
    Path: '.'
  },
  Run: {
    ADBSearchRange: 0,
    AnnihilationTimeLimit: 40,
    AnnihilationWeeklyLimit: true,
    ProxyTimesLimit: 0,
    RoutineTimeLimit: 10,
    RunTimesLimit: 3,
    TaskTransitionMethod: 'ExitEmulator'
  },
  SubConfigsInfo: {
    UserData: {
      instances: []
    }
  }
})

// General配置
const generalConfig = reactive<GeneralScriptConfig>({
  Game: {
    Arguments: '',
    Enabled: false,
    IfForceClose: false,
    Path: '.',
    Style: 'Emulator',
    WaitTime: 0
  },
  Info: {
    Name: '',
    RootPath: '.'
  },
  Run: {
    ProxyTimesLimit: 0,
    RunTimeLimit: 10,
    RunTimesLimit: 3
  },
  Script: {
    Arguments: '',
    ConfigPath: '.',
    ConfigPathMode: '所有文件 (*)',
    ErrorLog: '',
    IfTrackProcess: false,
    LogPath: '.',
    LogPathFormat: '%Y-%m-%d',
    LogTimeEnd: 1,
    LogTimeStart: 1,
    LogTimeFormat: '%Y-%m-%d %H:%M:%S',
    ScriptPath: '.',
    SuccessLog: '',
    UpdateConfigMode: 'Never'
  },
  SubConfigsInfo: {
    UserData: {
      instances: []
    }
  }
})

const rules = {
  name: [{ required: true, message: '请输入脚本名称', trigger: 'blur' }],
  type: [{ required: true, message: '请选择脚本类型', trigger: 'change' }]
}

// 监听props变化，初始化表单数据
watch(() => props.scriptData, (data) => {
  if (data) {
    formData.name = data.type === 'MAA' ? (data.config as MAAScriptConfig).Info.Name : (data.config as GeneralScriptConfig).Info.Name
    formData.type = data.type
    
    if (data.type === 'MAA') {
      Object.assign(maaConfig, data.config)
    } else {
      Object.assign(generalConfig, data.config)
    }
  }
}, { immediate: true })

const handleSave = async () => {
  try {
    await formRef.value?.validate()
    
    if (isEdit.value) {
      // 编辑模式
      const config = formData.type === 'MAA' ? maaConfig : generalConfig
      if (formData.type === 'MAA') {
        maaConfig.Info.Name = formData.name
      } else {
        generalConfig.Info.Name = formData.name
      }
      
      const result = await updateScript(props.scriptData!.id!, config)
      if (result) {
        message.success('脚本更新成功')
        emit('success', { id: props.scriptData!.id, type: formData.type, config })
        visible.value = false
      }
    } else {
      // 新建模式
      const result = await addScript(formData.type)
      if (result) {
        message.success(result.message)
        emit('success', { id: result.scriptId, type: formData.type, config: result.data })
        visible.value = false
      }
    }
  } catch (error) {
    console.error('保存失败:', error)
  }
}

const handleCancel = () => {
  visible.value = false
}
</script>