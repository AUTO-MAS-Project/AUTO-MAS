<template>
  <div class="user-edit-header">
    <div class="header-title">
      <h1>{{ isEdit ? '编辑用户' : '添加用户' }}</h1>
      <p class="subtitle">{{ scriptName }}</p>
    </div>
    <a-space size="middle">
      <a-button size="large" @click="handleCancel" class="cancel-button">
        <template #icon>
          <ArrowLeftOutlined />
        </template>
        返回
      </a-button>
      <a-button
        type="primary"
        size="large"
        @click="handleSubmit"
        :loading="loading"
        class="save-button"
      >
        <template #icon>
          <SaveOutlined />
        </template>
        {{ isEdit ? '保存修改' : '创建用户' }}
      </a-button>
    </a-space>
  </div>

  <div class="user-edit-content">
    <a-form ref="formRef" :model="formData" :rules="rules" layout="vertical" class="user-form">
      <a-card title="基本信息" class="form-card">
        <a-row :gutter="24">
          <a-col :span="12">
            <a-form-item name="userName" required>
              <template #label>
                <a-tooltip title="用于识别用户的显示名称">
                  <span class="form-label">
                    用户名
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-input
                v-model:value="formData.userName"
                placeholder="请输入用户名"
                :disabled="loading"
                size="large"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item name="userId" required>
              <template #label>
                <a-tooltip title="官服输入手机号，B服输入B站ID">
                  <span class="form-label">
                    账号ID
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-input
                v-model:value="formData.userId"
                placeholder="官服输入手机号，B服输入B站ID"
                :disabled="loading"
                size="large"
              />
            </a-form-item>
          </a-col>
        </a-row>

        <a-row :gutter="24">
          <a-col :span="12">
            <a-form-item name="status">
              <template #label>
                <a-tooltip title="是否启用该用户">
                  <span class="form-label">
                    启用状态
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-select v-model:value="formData.Info.Status" size="large">
                <a-select-option :value="true">是</a-select-option>
                <a-select-option :value="false">否</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item :name="['Info', 'Password']">
              <template #label>
                <a-tooltip title="用户登录游戏的密码">
                  <span class="form-label">
                    密码(密码仅用于储存,防止遗忘!此外无任何作用)
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-input-password
                v-model:value="formData.Info.Password"
                placeholder="请输入密码"
                :disabled="loading"
                size="large"
              />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="24">
          <a-col :span="12">
            <a-form-item name="server">
              <template #label>
                <a-tooltip title="选择用户所在的游戏服务器">
                  <span class="form-label">
                    服务器
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-select
                v-model:value="formData.Info.Server"
                placeholder="请选择服务器"
                :disabled="loading"
                :options="serverOptions"
                size="large"
              />
            </a-form-item>
          </a-col>

          <a-col :span="12">
            <a-form-item name="remainedDay">
              <template #label>
                <a-tooltip title="账号剩余的有效天数(-1表示无限)">
                  <span class="form-label">
                    剩余天数(-1表示无限)
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-input-number
                v-model:value="formData.Info.RemainedDay"
                :min="0"
                :max="9999"
                placeholder="0"
                :disabled="loading"
                size="large"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
        </a-row>

        <a-row :gutter="24">
          <a-col :span="12">
            <a-form-item name="mode">
              <template #label>
                <a-tooltip title="选择用户操作模式">
                  <span class="form-label">
                    用户配置模式
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-select
                v-model:value="formData.Info.Mode"
                :options="[
                  { label: '简洁', value: '简洁' },
                  { label: '详细', value: '详细' },
                ]"
                :disabled="loading"
                size="large"
              />
            </a-form-item>
          </a-col>

          <a-col :span="12">
            <a-form-item name="mode">
              <template #label>
                <a-tooltip title="剿灭代理">
                  <span class="form-label">
                    基建模式
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-select
                v-model:value="formData.Info.InfrastMode"
                :options="[
                  { label: '常规模式', value: 'Normal' },
                  { label: '一键轮休', value: 'Rotation' },
                  { label: '自定义基建', value: 'Custom' },
                ]"
                :disabled="loading"
                size="large"
              />
            </a-form-item>
          </a-col>
          <!--          <a-col :span="8">-->
          <!--            <a-form-item name="medicineNumb">-->
          <!--              <template #label>-->
          <!--                <a-tooltip title="用户拥有的理智药数量，用于恢复理智">-->
          <!--                  <span class="form-label">-->
          <!--                    理智药数量-->
          <!--                    <QuestionCircleOutlined class="help-icon" />-->
          <!--                  </span>-->
          <!--                </a-tooltip>-->
          <!--              </template>-->
          <!--              <a-input-number-->
          <!--                v-model:value="formData.Info.MedicineNumb"-->
          <!--                :min="0"-->
          <!--                :max="999"-->
          <!--                placeholder="0"-->
          <!--                :disabled="loading"-->
          <!--                size="large"-->
          <!--                style="width: 100%"-->
          <!--              />-->
          <!--            </a-form-item>-->
          <!--          </a-col>-->
        </a-row>

        <a-form-item name="notes">
          <template #label>
            <a-tooltip title="为用户添加备注信息，便于管理和识别">
              <span class="form-label">
                备注
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-textarea
            v-model:value="formData.Info.Notes"
            placeholder="请输入备注信息"
            :rows="4"
            :disabled="loading"
          />
        </a-form-item>
      </a-card>

      <a-card title="关卡配置" class="form-card">
        <!--        <a-row :gutter="24">-->
        <!--          <a-col :span="12">-->
        <!--            <a-form-item name="proxyTimes">-->
        <!--              <template #label>-->
        <!--                <a-tooltip title="刷关代理次数，-1表示无限代理">-->
        <!--                  <span class="form-label">-->
        <!--                    刷关代理次数-->
        <!--                    <QuestionCircleOutlined class="help-icon" />-->
        <!--                  </span>-->
        <!--                </a-tooltip>-->
        <!--              </template>-->
        <!--              <div class="desc-text" style="color: #888; font-size: 14px; margin-top: 4px">-->
        <!--                今日已代理{{ formData.Data.ProxyTimes }}次 | 本周代理已完成-->
        <!--              </div>-->
        <!--            </a-form-item>-->
        <!--          </a-col>-->
        <!--        </a-row>-->

        <a-row :gutter="24">
          <a-col :span="12">
            <a-form-item name="mode">
              <template #label>
                <a-tooltip title="剿灭代理">
                  <span class="form-label">
                    剿灭代理
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-select
                v-model:value="formData.Info.Annihilation"
                :options="[
                  { label: '关闭', value: 'Close' },
                  { label: '当期剿灭', value: 'Annihilation' },
                  { label: '切尔诺伯格', value: 'Chernobog@Annihilation' },
                  { label: '龙门外环', value: 'LungmenOutskirts@Annihilation' },
                  { label: '龙门市区', value: 'LungmenDowntown@Annihilation' },
                ]"
                :disabled="loading"
                size="large"
              />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="24"></a-row>
        <a-row :gutter="24">
          <a-col :span="6">
            <a-form-item name="remainedDay">
              <template #label>
                <a-tooltip title="吃理智药数量">
                  <span class="form-label">
                    吃理智药数量
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-input-number
                v-model:value="formData.Info.MedicineNumb"
                :min="0"
                :max="9999"
                placeholder="0"
                :disabled="loading"
                size="large"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
          <a-col :span="6">
            <a-form-item name="mode">
              <template #label>
                <a-tooltip title="连战次数">
                  <span class="form-label">
                    连战次数
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-select
                v-model:value="formData.Info.SeriesNumb"
                :options="[
                  { label: 'AUTO', value: 'AUTO' },
                  { label: '0', value: '0' },
                  { label: '1', value: '1' },
                  { label: '2', value: '2' },
                  { label: '3', value: '3' },
                  { label: '4', value: '4' },
                  { label: '5', value: '5' },
                  { label: '6', value: '6' },
                ]"
                :disabled="loading"
                size="large"
              />
            </a-form-item>
          </a-col>
          <a-col :span="6">
            <a-form-item name="mode">
              <template #label>
                <a-tooltip title="关卡选择">
                  <span class="form-label">
                    关卡配置模式
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-select
                v-model:value="formData.Info.StageMode"
                :options="[
                  { label: '固定', value: '固定' },
                  { label: '刷完即停', value: '刷完即停' },
                ]"
                :disabled="loading"
                size="large"
              />
            </a-form-item>
          </a-col>
          <a-col :span="6">
            <a-form-item name="mode">
              <template #label>
                <a-tooltip title="关卡选择">
                  <span class="form-label">
                    关卡选择
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-select
                v-model:value="formData.Info.Stage"
                :options="[
                  { label: '不选择', value: '' },
                  { label: '后期接口获取,先占位符', value: 'Other' },
                ]"
                :disabled="loading"
                size="large"
              />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="24">
          <a-col :span="6">
            <a-form-item name="mode">
              <template #label>
                <a-tooltip title="备选关卡-1">
                  <span class="form-label">
                    备选关卡-1
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-select
                v-model:value="formData.Info.Stage_1"
                :options="[
                  { label: '不选择', value: '' },
                  { label: '后期接口获取,先占位符', value: 'Other' },
                ]"
                :disabled="loading"
                size="large"
              />
            </a-form-item>
          </a-col>
          <a-col :span="6">
            <a-form-item name="mode">
              <template #label>
                <a-tooltip title="备选关卡-2">
                  <span class="form-label">
                    备选关卡-2
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-select
                v-model:value="formData.Info.Stage_2"
                :options="[
                  { label: '不选择', value: '' },
                  { label: '后期接口获取,先占位符', value: 'Other' },
                ]"
                :disabled="loading"
                size="large"
              />
            </a-form-item>
          </a-col>
          <a-col :span="6">
            <a-form-item name="mode">
              <template #label>
                <a-tooltip title="备选关卡-3">
                  <span class="form-label">
                    备选关卡-3
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-select
                v-model:value="formData.Info.Stage_3"
                :options="[
                  { label: '不选择', value: '' },
                  { label: '后期接口获取,先占位符', value: 'Other' },
                ]"
                :disabled="loading"
                size="large"
              />
            </a-form-item>
          </a-col>
          <a-col :span="6">
            <a-form-item name="mode">
              <template #label>
                <a-tooltip title="剩余理智">
                  <span class="form-label">
                    剩余理智
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-select
                v-model:value="formData.Info.Stage_Remain"
                :options="[
                  { label: '不选择', value: '' },
                  { label: '后期接口获取,先占位符', value: 'Other' },
                ]"
                :disabled="loading"
                size="large"
              />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="24"></a-row>
      </a-card>

      <a-card title="任务配置" class="form-card">
        <a-row :gutter="24">
          <a-col :span="6">
            <a-form-item name="ifWakeUp" label="开始唤醒">
              <a-switch v-model:checked="formData.Task.IfWakeUp" :disabled="loading" />
            </a-form-item>
          </a-col>
          <a-col :span="6">
            <a-form-item name="ifRecruiting" label="自动公招">
              <a-switch v-model:checked="formData.Task.IfRecruiting" :disabled="loading" />
            </a-form-item>
          </a-col>
          <a-col :span="6">
            <a-form-item name="ifBase" label="基建换班">
              <a-switch v-model:checked="formData.Task.IfBase" :disabled="loading" />
            </a-form-item>
          </a-col>
          <a-col :span="6">
            <a-form-item name="ifCombat" label="刷理智">
              <a-switch v-model:checked="formData.Task.IfCombat" :disabled="loading" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="24">
          <a-col :span="6">
            <a-form-item name="ifMall" label="获取信用及购物">
              <a-switch v-model:checked="formData.Task.IfMall" :disabled="loading" />
            </a-form-item>
          </a-col>
          <a-col :span="6">
            <a-form-item name="ifMission" label="领取奖励">
              <a-switch v-model:checked="formData.Task.IfMission" :disabled="loading" />
            </a-form-item>
          </a-col>
          <a-col :span="6">
            <a-form-item name="ifAutoRoguelike">
              <template #label>
                <a-tooltip title="暂不支持">
                  <span>自动肉鸽 </span>
                  <QuestionCircleOutlined class="help-icon" />
                </a-tooltip>
              </template>
              <a-switch v-model:checked="formData.Task.IfAutoRoguelike" :disabled="loading" />
            </a-form-item>
          </a-col>
          <a-col :span="6">
            <a-form-item name="ifReclamation">
              <template #label>
                <a-tooltip title="暂不支持">
                  <span>生息演算 </span>
                  <QuestionCircleOutlined class="help-icon" />
                </a-tooltip>
              </template>
              <a-switch v-model:checked="formData.Task.IfReclamation" :disabled="loading" />
            </a-form-item>
          </a-col>
        </a-row>
      </a-card>

      <a-card title="森空岛配置" class="form-card">
        <a-row :gutter="24" align="middle">
          <a-col :span="6">
            <span style="font-weight: 500">启用森空岛</span>
          </a-col>
          <a-col :span="18">
            <a-switch v-model:checked="formData.Info.IfSkland" :disabled="loading" />
            <span class="switch-description">开启后将启用森空岛相关功能</span>
          </a-col>
        </a-row>
        <a-row :gutter="24" style="margin-top: 16px">
          <a-col :span="24">
            <span style="font-weight: 500">森空岛Token</span>
            <a-input-password
              v-model:value="formData.Info.SklandToken"
              :disabled="loading || !formData.Info.IfSkland"
              placeholder="请输入森空岛Token"
              size="large"
              style="margin-top: 8px; width: 100%"
              allow-clear
            />
            <div style="color: #999; font-size: 12px; margin-top: 4px">
              请在森空岛官网获取您的专属Token并粘贴到此处,详细教程建官网文档
            </div>
          </a-col>
        </a-row>
      </a-card>

      <a-card title="通知配置" class="form-card">
        <a-row :gutter="24" align="middle">
          <a-col :span="6">
            <span style="font-weight: 500">启用通知</span>
          </a-col>
          <a-col :span="18">
            <a-switch v-model:checked="formData.Notify.Enabled" :disabled="loading" />
            <span class="switch-description">启用后将发送任务通知</span>
          </a-col>
        </a-row>

        <!-- 邮件通知 -->
        <a-row :gutter="24" style="margin-top: 16px">
          <a-col :span="6">
            <a-checkbox
              v-model:checked="formData.Notify.IfSendMail"
              :disabled="loading || !formData.Notify.Enabled"
              >邮件通知
            </a-checkbox>
          </a-col>
          <a-col :span="18">
            <a-input
              v-model:value="formData.Notify.ToAddress"
              placeholder="请输入收件人邮箱地址"
              :disabled="loading || !formData.Notify.Enabled || !formData.Notify.IfSendMail"
              size="large"
              style="width: 100%"
            />
          </a-col>
        </a-row>

        <!-- Server酱通知 -->
        <a-row :gutter="24" style="margin-top: 16px">
          <a-col :span="6">
            <a-checkbox
              v-model:checked="formData.Notify.IfServerChan"
              :disabled="loading || !formData.Notify.Enabled"
              >Server酱
            </a-checkbox>
          </a-col>
          <a-col :span="18" style="display: flex; gap: 8px">
            <a-input
              v-model:value="formData.Notify.ServerChanKey"
              placeholder="SENDKEY"
              :disabled="loading || !formData.Notify.Enabled || !formData.Notify.IfServerChan"
              size="large"
              style="flex: 2"
            />
          </a-col>
        </a-row>

        <!-- 企业微信群机器人通知 -->
        <a-row :gutter="24" style="margin-top: 16px">
          <a-col :span="6">
            <a-checkbox
              v-model:checked="formData.Notify.IfCompanyWebHookBot"
              :disabled="loading || !formData.Notify.Enabled"
              >企业微信群机器人
            </a-checkbox>
          </a-col>
          <a-col :span="18">
            <a-input
              v-model:value="formData.Notify.CompanyWebHookBotUrl"
              placeholder="请输入机器人Webhook地址"
              :disabled="
                loading || !formData.Notify.Enabled || !formData.Notify.IfCompanyWebHookBot
              "
              size="large"
              style="width: 100%"
            />
          </a-col>
        </a-row>

        <!-- 发送统计/六星等可选通知 -->
        <a-row :gutter="24" style="margin-top: 16px">
          <a-col :span="6">
            <span style="font-weight: 500">通知内容</span>
          </a-col>
          <a-col :span="18" style="display: flex; gap: 32px">
            <a-checkbox
              v-model:checked="formData.Notify.IfSendStatistic"
              :disabled="loading || !formData.Notify.Enabled"
              >发送统计
            </a-checkbox>
            <a-checkbox
              v-model:checked="formData.Notify.IfSendSixStar"
              :disabled="loading || !formData.Notify.Enabled"
              >六星掉落推送
            </a-checkbox>
          </a-col>
        </a-row>
      </a-card>
    </a-form>
  </div>

  <a-float-button
    type="primary"
    @click="handleSubmit"
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
import { ref, reactive, onMounted, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined, SaveOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { FormInstance, Rule } from 'ant-design-vue/es/form'
import type { User } from '@/types/script'
import { useUserApi } from '@/composables/useUserApi'
import { useScriptApi } from '@/composables/useScriptApi'

const router = useRouter()
const route = useRoute()
const { addUser, updateUser, loading: userLoading } = useUserApi()
const { getScript } = useScriptApi()

const formRef = ref<FormInstance>()
const loading = computed(() => userLoading.value)

// 路由参数
const scriptId = route.params.scriptId as string
const userId = route.params.userId as string
const isEdit = computed(() => !!userId)

// 脚本信息
const scriptName = ref('')

// 服务器选项
const serverOptions = [
  { label: '官服', value: 'Official' },
  { label: 'B服', value: 'Bilibili' },
]

// 默认用户数据
const getDefaultUserData = () => ({
  Info: {
    Name: '',
    Id: '',
    Password: '',
    Server: '官服',
    MedicineNumb: 0,
    RemainedDay: 0,
    SeriesNumb: '',
    Notes: '',
    Status: true,
    Mode: 'MAA',
    InfrastMode: '默认',
    Routine: true,
    Annihilation: '当期',
    Stage: '1-7',
    StageMode: '刷完即停',
    Stage_1: '',
    Stage_2: '',
    Stage_3: '',
    Stage_Remain: '',
    IfSkland: false,
    SklandToken: '',
  },
  Task: {
    IfBase: true,
    IfCombat: true,
    IfMall: true,
    IfMission: true,
    IfRecruiting: true,
    IfReclamation: false,
    IfAutoRoguelike: false,
    IfWakeUp: false,
  },
  Notify: {
    Enabled: false,
    ToAddress: '',
    IfSendMail: false,
    IfSendSixStar: false,
    IfSendStatistic: false,
    IfServerChan: false,
    IfCompanyWebHookBot: false,
    ServerChanKey: '',
    ServerChanChannel: '',
    ServerChanTag: '',
    CompanyWebHookBotUrl: '',
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
  ...getDefaultUserData(),
})

// 表单验证规则
const rules: Record<string, Rule[]> = {
  userName: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 1, max: 50, message: '用户名长度应在1-50个字符之间', trigger: 'blur' },
  ],
  userId: [
    { required: true, message: '请输入用户ID', trigger: 'blur' },
    { min: 1, max: 50, message: '用户ID长度应在1-50个字符之间', trigger: 'blur' },
  ],
}

// 同步扁平化字段与嵌套数据
watch(
  () => formData.Info.Name,
  newVal => {
    formData.userName = newVal
  },
  { immediate: true }
)

watch(
  () => formData.Info.Id,
  newVal => {
    formData.userId = newVal
  },
  { immediate: true }
)

watch(
  () => formData.userName,
  newVal => {
    formData.Info.Name = newVal
  }
)

watch(
  () => formData.userId,
  newVal => {
    formData.Info.Id = newVal
  }
)

// 加载脚本信息
const loadScriptInfo = async () => {
  try {
    const script = await getScript(scriptId)
    if (script) {
      scriptName.value = script.name

      // 如果是编辑模式，加载用户数据
      if (isEdit.value && script.config) {
        const config = script.config as any
        if (config.SubConfigsInfo?.UserData?.instances) {
          const userInstance = config.SubConfigsInfo.UserData.instances.find(
            (instance: any) => instance.uid === userId
          )

          if (userInstance) {
            // 从用户数据中获取实际的用户信息
            const userData = config.SubConfigsInfo.UserData[userInstance.uid]
            if (userData) {
              // 填充用户数据
              Object.assign(formData, {
                Info: { ...getDefaultUserData().Info, ...userData.Info },
                Task: { ...getDefaultUserData().Task, ...userData.Task },
                Notify: { ...getDefaultUserData().Notify, ...userData.Notify },
                Data: { ...getDefaultUserData().Data, ...userData.Data },
                QFluentWidgets: {
                  ...getDefaultUserData().QFluentWidgets,
                  ...userData.QFluentWidgets,
                },
              })
              // 同步扁平化字段
              formData.userName = formData.Info.Name
              formData.userId = formData.Info.Id
            }
          }
        }
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

const handleSubmit = async () => {
  try {
    await formRef.value?.validate()

    // 构建提交数据
    const userData = {
      Info: { ...formData.Info },
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
        // 创建成功后更新用户数据
        await updateUser(scriptId, result.userId, userData)
        message.success('用户创建成功')
        handleCancel()
      }
    }
  } catch (error) {
    console.error('表单验证失败:', error)
  }
}

const handleCancel = () => {
  router.push('/scripts')
}

onMounted(() => {
  if (!scriptId) {
    message.error('缺少脚本ID参数')
    handleCancel()
    return
  }

  loadScriptInfo()
})
</script>

<style scoped>
.user-edit-container {
  padding: 32px;
  min-height: 100vh;
  background: var(--ant-color-bg-layout);
}

.user-edit-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
  padding: 0 8px;
}

.header-title h1 {
  margin: 0;
  font-size: 32px;
  font-weight: 700;
  color: var(--ant-color-text);
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.subtitle {
  margin: 4px 0 0 0;
  font-size: 16px;
  color: var(--ant-color-text-secondary);
}

.user-edit-content {
  max-width: 1200px;
  margin: 0 auto;
}

.form-card {
  margin-bottom: 24px;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.form-card :deep(.ant-card-head) {
  border-bottom: 2px solid var(--ant-color-border-secondary);
}

.form-card :deep(.ant-card-head-title) {
  font-size: 18px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.user-form :deep(.ant-form-item-label > label) {
  font-weight: 500;
  color: var(--ant-color-text);
}

.switch-description,
.task-description {
  margin-left: 12px;
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}

.task-description {
  display: block;
  margin-top: 4px;
  margin-left: 0;
}

.cancel-button {
  border: 1px solid var(--ant-color-border);
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text);
}

.cancel-button:hover {
  border-color: var(--ant-color-primary);
  color: var(--ant-color-primary);
}

.save-button {
  background: var(--ant-color-primary);
  border-color: var(--ant-color-primary);
}

.save-button:hover {
  background: var(--ant-color-primary-hover);
  border-color: var(--ant-color-primary-hover);
}

/* 表单标签样式 */
.form-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  color: var(--ant-color-text);
}

.help-icon {
  font-size: 14px;
  color: var(--ant-color-text-tertiary);
  cursor: help;
  transition: color 0.3s ease;
}

.help-icon:hover {
  color: var(--ant-color-primary);
}

/* 响应式设计 */
@media (max-width: 768px) {
  .user-edit-container {
    padding: 16px;
  }

  .user-edit-header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }

  .header-title h1 {
    font-size: 24px;
  }

  .user-edit-content {
    max-width: 100%;
  }
}

.float-button {
  width: 60px;
  height: 60px;
}
</style>