<template>
  <div class="user-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts">脚本管理</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <router-link :to="`/scripts/${scriptId}/edit`" class="breadcrumb-link">
            {{ scriptName }}
          </router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          {{ isEdit ? '编辑用户' : '添加用户' }}
        </a-breadcrumb-item>
      </a-breadcrumb>
    </div>

    <a-space size="middle">
      <a-button
        v-if="scriptType === 'MAA' && formData.Info.Mode !== '简洁'"
        type="primary"
        ghost
        size="large"
        @click="handleMAAConfig"
        :loading="maaConfigLoading"
      >
        <template #icon>
          <SettingOutlined />
        </template>
        MAA配置
      </a-button>
      <a-button
        v-if="scriptType === 'General'"
        type="primary"
        ghost
        size="large"
        @click="handleGeneralConfig"
        :loading="generalConfigLoading"
      >
        <template #icon>
          <SettingOutlined />
        </template>
        通用配置
      </a-button>
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
      <!-- MAA脚本用户配置 -->
      <template v-if="scriptType === 'MAA'">
        <a-card title="基本信息" class="form-card">
          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item name="userName" required>
                <template #label>
                  <a-tooltip title="用于区分用户的名称，相同名称的用户将被视为同一用户进行统计">
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
              <a-form-item name="userId">
                <template #label>
                  <a-tooltip title="用于切换账号，官服输入手机号，B服输入B站ID，无需切换则留空">
                    <span class="form-label">
                      账号ID
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input
                  v-model:value="formData.userId"
                  placeholder="请输入账号ID"
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
                  <a-tooltip title="用户密码，仅用于存储以防遗忘，此外无任何作用">
                    <span class="form-label">
                      密码
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-password
                  v-model:value="formData.Info.Password"
                  placeholder="密码仅用于储存以防遗忘，此外无任何作用"
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
                  <a-tooltip title="账号剩余的有效天数，「-1」表示无限">
                    <span class="form-label">
                      剩余天数
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-number
                  v-model:value="formData.Info.RemainedDay"
                  :min="-1"
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
                  <a-tooltip title="简洁模式下配置沿用脚本全局配置，详细模式下沿用用户自定义配置">
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
                  <a-tooltip title="选择基建模式，自定义基建模式需要自行选择自定义基建配置文件">
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

          <!-- 自定义基建配置文件选择 -->
          <a-row :gutter="24" v-if="scriptType === 'MAA' && formData.Info.InfrastMode === 'Custom'">
            <a-col :span="24">
              <a-form-item name="infrastructureConfigFile">
                <template #label>
                  <a-tooltip title="选择自定义基建配置JSON文件">
                    <span class="form-label">
                      基建配置文件
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <div style="display: flex; gap: 12px; align-items: center">
                  <a-input
                    v-model:value="formData.Info.InfrastPath"
                    placeholder="请选择基建配置JSON文件"
                    readonly
                    size="large"
                    style="flex: 1"
                  />
                  <a-button
                    type="primary"
                    ghost
                    @click="selectInfrastructureConfig"
                    :disabled="loading"
                    size="large"
                  >
                    选择文件
                  </a-button>
                  <a-button
                    type="primary"
                    @click="importInfrastructureConfig"
                    :disabled="loading || !infrastructureConfigPath || !isEdit"
                    :loading="infrastructureImporting"
                    size="large"
                  >
                    导入配置
                  </a-button>
                </div>
                <div style="color: #999; font-size: 12px; margin-top: 4px">
                  请选择有效的基建配置JSON文件，点击「导入配置」按钮将其应用到当前用户。如果已经导入，可以忽略此选择框。
                </div>
              </a-form-item>
            </a-col>
          </a-row>

          <a-form-item name="notes">
            <template #label>
              <a-tooltip title="为用户添加备注信息">
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
                  <a-tooltip title="剿灭代理关卡选择">
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
            <a-col :span="12">
              <a-form-item name="mode">
                <template #label>
                  <a-tooltip title="可选择「固定」或「计划表」">
                    <span class="form-label">
                      关卡配置模式
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="formData.Info.StageMode"
                  :options="stageModeOptions"
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
                  <a-tooltip
                    title="AUTO：自动识别关卡最大代理倍率，保持最大代理倍率且使用理智药后理智不溢出；数值（1~6）：按设定倍率执行代理；不切换：不调整游戏内代理倍率设定"
                  >
                    <span class="form-label">
                      连战次数
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="formData.Info.SeriesNumb"
                  :options="[
                    { label: 'AUTO', value: '0' },
                    { label: '1', value: '1' },
                    { label: '2', value: '2' },
                    { label: '3', value: '3' },
                    { label: '4', value: '4' },
                    { label: '5', value: '5' },
                    { label: '6', value: '6' },
                    { label: '不切换', value: '-1' },
                  ]"
                  :disabled="loading"
                  size="large"
                />
              </a-form-item>
            </a-col>

            <a-col :span="12">
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
                  :options="stageOptions"
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
                  <a-tooltip
                    title="备选关卡-1，所有备选关卡均选择「当前/上次」时视为不使用备选关卡"
                  >
                    <span class="form-label">
                      备选关卡-1
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="formData.Info.Stage_1"
                  :options="stageOptions"
                  :disabled="loading"
                  size="large"
                />
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item name="mode">
                <template #label>
                  <a-tooltip
                    title="备选关卡-2，所有备选关卡均选择「当前/上次」时视为不使用备选关卡"
                  >
                    <span class="form-label">
                      备选关卡-2
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="formData.Info.Stage_2"
                  :options="stageOptions"
                  :disabled="loading"
                  size="large"
                />
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item name="mode">
                <template #label>
                  <a-tooltip
                    title="备选关卡-3，所有备选关卡均选择「当前/上次」时视为不使用备选关卡"
                  >
                    <span class="form-label">
                      备选关卡-3
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="formData.Info.Stage_3"
                  :options="stageOptions"
                  :disabled="loading"
                  size="large"
                />
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item name="mode">
                <template #label>
                  <a-tooltip title="剩余理智，选择「当前/上次」时视为不使用剩余理智">
                    <span class="form-label">
                      剩余理智
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="formData.Info.Stage_Remain"
                  :options="stageOptions"
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
                  <a-tooltip title="未完全适配，请谨慎使用">
                    <span>自动肉鸽 </span>
                    <QuestionCircleOutlined class="help-icon" />
                  </a-tooltip>
                </template>
                <a-switch v-model:checked="formData.Task.IfAutoRoguelike" :disabled="true" />
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item name="ifReclamation">
                <template #label>
                  <a-tooltip title="暂不支持，等待适配中~">
                    <span>生息演算 </span>
                    <QuestionCircleOutlined class="help-icon" />
                  </a-tooltip>
                </template>
                <a-switch v-model:checked="formData.Task.IfReclamation" :disabled="true" />
              </a-form-item>
            </a-col>
          </a-row>
        </a-card>

        <a-card title="森空岛配置" class="form-card">
          <a-row :gutter="24" align="middle">
            <a-col :span="6">
              <span style="font-weight: 500">森空岛签到</span>
            </a-col>
            <a-col :span="18">
              <a-switch v-model:checked="formData.Info.IfSkland" :disabled="loading" />
              <span class="switch-description">开启后将启用森空岛签到功能</span>
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
                请在森空岛官网获取您的专属Token并粘贴到此处，详细教程见
                <a
                  href="https://doc.auto-mas.top/docs/advanced-features.html#%E8%8E%B7%E5%8F%96%E9%B9%B0%E8%A7%92%E7%BD%91%E7%BB%9C%E9%80%9A%E8%A1%8C%E8%AF%81%E7%99%BB%E5%BD%95%E5%87%AD%E8%AF%81"
                  target="_blank"
                  style="color: #409eff"
                  >获取鹰角网络通行证登录凭证</a
                >
                文档
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
              <span class="switch-description">启用后将发送此用户的任务通知到选中的渠道</span>
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
                >统计信息
              </a-checkbox>
              <a-checkbox
                v-model:checked="formData.Notify.IfSendSixStar"
                :disabled="loading || !formData.Notify.Enabled"
                >公开招募高资喜报
              </a-checkbox>
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
                placeholder="请输入SENDKEY"
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
        </a-card>
      </template>

      <!-- 通用脚本用户配置 -->
      <template v-else>
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
          </a-row>

          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item name="remainedDay">
                <template #label>
                  <a-tooltip title="账号剩余的有效天数，「-1」表示无限">
                    <span class="form-label">
                      剩余天数
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-number
                  v-model:value="formData.Info.RemainedDay"
                  :min="-1"
                  :max="9999"
                  placeholder="-1"
                  :disabled="loading"
                  size="large"
                  style="width: 100%"
                />
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <!-- 占位列 -->
            </a-col>
          </a-row>

          <a-form-item name="notes">
            <template #label>
              <a-tooltip title="为用户添加备注信息">
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

        <a-card title="脚本配置" class="form-card">
          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item name="ifScriptBeforeTask">
                <template #label>
                  <a-tooltip title="是否在任务执行前运行自定义脚本">
                    <span class="form-label">
                      任务前执行脚本
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-switch
                  v-model:checked="formData.Info.IfScriptBeforeTask"
                  :disabled="loading"
                  size="default"
                />
                <span class="switch-description">启用后将在任务执行前运行指定脚本</span>
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item name="ifScriptAfterTask">
                <template #label>
                  <a-tooltip title="是否在任务执行后运行自定义脚本">
                    <span class="form-label">
                      任务后执行脚本
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-switch
                  v-model:checked="formData.Info.IfScriptAfterTask"
                  :disabled="loading"
                  size="default"
                />
                <span class="switch-description">启用后将在任务执行后运行指定脚本</span>
              </a-form-item>
            </a-col>
          </a-row>

          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item name="scriptBeforeTask">
                <template #label>
                  <a-tooltip title="任务执行前要运行的脚本路径">
                    <span class="form-label">
                      任务前脚本
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input
                  v-model:value="formData.Info.ScriptBeforeTask"
                  placeholder="请输入脚本路径"
                  :disabled="loading || !formData.Info.IfScriptBeforeTask"
                  size="large"
                />
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item name="scriptAfterTask">
                <template #label>
                  <a-tooltip title="任务执行后要运行的脚本路径">
                    <span class="form-label">
                      任务后脚本
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input
                  v-model:value="formData.Info.ScriptAfterTask"
                  placeholder="请输入脚本路径"
                  :disabled="loading || !formData.Info.IfScriptAfterTask"
                  size="large"
                />
              </a-form-item>
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

          <!-- 发送统计 -->
          <a-row :gutter="24" style="margin-top: 16px">
            <a-col :span="6">
              <span style="font-weight: 500">通知内容</span>
            </a-col>
            <a-col :span="18">
              <a-checkbox
                v-model:checked="formData.Notify.IfSendStatistic"
                :disabled="loading || !formData.Notify.Enabled"
                >统计信息
              </a-checkbox>
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
            <a-col :span="18">
              <a-input
                v-model:value="formData.Notify.ServerChanKey"
                placeholder="请输入SENDKEY"
                :disabled="loading || !formData.Notify.Enabled || !formData.Notify.IfServerChan"
                size="large"
                style="width: 100%"
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
        </a-card>
      </template>
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
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  ArrowLeftOutlined,
  QuestionCircleOutlined,
  SaveOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'
import type { FormInstance, Rule } from 'ant-design-vue/es/form'
import { useUserApi } from '@/composables/useUserApi'
import { useScriptApi } from '@/composables/useScriptApi'
import { useWebSocket } from '@/composables/useWebSocket'
import { Service } from '@/api'

const router = useRouter()
const route = useRoute()
const { addUser, updateUser, getUsers, loading: userLoading } = useUserApi()
const { getScript } = useScriptApi()
const { connect, disconnect } = useWebSocket()

const formRef = ref<FormInstance>()
const loading = computed(() => userLoading.value)

// 路由参数
const scriptId = route.params.scriptId as string
const userId = route.params.userId as string
const isEdit = computed(() => !!userId)

// 脚本信息
const scriptName = ref('')
const scriptType = ref<'MAA' | 'General'>('MAA')

// MAA配置相关
const maaConfigLoading = ref(false)
const maaWebsocketId = ref<string | null>(null)

// 通用配置相关
const generalConfigLoading = ref(false)
const generalWebsocketId = ref<string | null>(null)

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
    Routine: true,
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

// 通用脚本默认用户数据
const getDefaultGeneralUserData = () => ({
  Info: {
    Name: '',
    Notes: '',
    Status: true,
    RemainedDay: -1,
    IfScriptBeforeTask: false,
    IfScriptAfterTask: false,
    ScriptBeforeTask: '',
    ScriptAfterTask: '',
  },
  Notify: {
    Enabled: false,
    ToAddress: '',
    IfSendMail: false,
    IfSendStatistic: false,
    IfServerChan: false,
    IfCompanyWebHookBot: false,
    ServerChanKey: '',
    ServerChanChannel: '',
    ServerChanTag: '',
    CompanyWebHookBotUrl: '',
  },
  Data: {
    LastProxyDate: '2000-01-01',
    ProxyTimes: 0,
  },
})

// 根据脚本类型获取默认数据
const getDefaultUserData = () => {
  return scriptType.value === 'MAA' ? getDefaultMAAUserData() : getDefaultGeneralUserData()
}

// 创建扁平化的表单数据，用于表单验证
const formData = reactive({
  // 扁平化的验证字段
  userName: '',
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
      scriptType.value = script.type // 设置脚本类型

      // 重新初始化表单数据（根据脚本类型）
      const defaultData =
        scriptType.value === 'MAA' ? getDefaultMAAUserData() : getDefaultGeneralUserData()

      // 清空现有数据并重新赋值
      Object.keys(formData).forEach(key => {
        if (key !== 'userName' && key !== 'userId') {
          delete formData[key]
        }
      })

      Object.assign(formData, {
        userName: '',
        userId: '',
        ...defaultData,
      })

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

        // 根据脚本类型填充用户数据
        if (scriptType.value === 'MAA' && userIndex.type === 'MaaUserConfig') {
          Object.assign(formData, {
            Info: { ...getDefaultMAAUserData().Info, ...userData.Info },
            Task: { ...getDefaultMAAUserData().Task, ...userData.Task },
            Notify: { ...getDefaultMAAUserData().Notify, ...userData.Notify },
            Data: { ...getDefaultMAAUserData().Data, ...userData.Data },
            QFluentWidgets: {
              ...getDefaultMAAUserData().QFluentWidgets,
              ...userData.QFluentWidgets,
            },
          })
        } else if (scriptType.value === 'General' && userIndex.type === 'GeneralUserConfig') {
          Object.assign(formData, {
            Info: { ...getDefaultGeneralUserData().Info, ...userData.Info },
            Notify: { ...getDefaultGeneralUserData().Notify, ...userData.Notify },
            Data: { ...getDefaultGeneralUserData().Data, ...userData.Data },
          })
        }

        // 同步扁平化字段 - 使用nextTick确保数据更新完成后再同步
        await nextTick()
        formData.userName = formData.Info.Name || ''
        formData.userId = formData.Info.Id || ''

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
    let notifyData = { ...formData.Notify }
    
    // 如果是通用脚本，移除MAA专用的通知字段
    if (scriptType.value === 'General') {
      const { IfSendSixStar, ...generalNotify } = notifyData
      notifyData = generalNotify
    }
    
    const userData = {
      Info: { ...infoWithoutInfrastPath },
      Task: { ...formData.Task },
      Notify: notifyData,
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
    if (maaWebsocketId.value) {
      disconnect(maaWebsocketId.value)
      maaWebsocketId.value = null
    }

    // 建立WebSocket连接进行MAA配置
    const websocketId = await connect({
      taskId: userId, // 使用用户ID进行配置
      mode: '设置脚本',
      showNotifications: true,
      onStatusChange: status => {
        console.log(`用户 ${formData.userName} MAA配置状态: ${status}`)
      },
      onMessage: data => {
        console.log(`用户 ${formData.userName} MAA配置消息:`, data)
        // 这里可以根据需要处理特定的消息
      },
      onError: error => {
        console.error(`用户 ${formData.userName} MAA配置错误:`, error)
        message.error(`MAA配置连接失败: ${error}`)
        maaWebsocketId.value = null
      },
    })

    if (websocketId) {
      maaWebsocketId.value = websocketId
      message.success(`已开始配置用户 ${formData.userName} 的MAA设置`)
    }
  } catch (error) {
    console.error('MAA配置失败:', error)
    message.error('MAA配置失败')
  } finally {
    maaConfigLoading.value = false
  }
}

const handleGeneralConfig = async () => {
  if (!isEdit.value) {
    message.warning('请先保存用户后再进行通用配置')
    return
  }

  try {
    generalConfigLoading.value = true

    // 如果已有连接，先断开
    if (generalWebsocketId.value) {
      disconnect(generalWebsocketId.value)
      generalWebsocketId.value = null
    }

    // 建立WebSocket连接进行通用配置
    const websocketId = await connect({
      taskId: userId, // 使用用户ID进行配置
      mode: '设置脚本',
      showNotifications: true,
      onStatusChange: status => {
        console.log(`用户 ${formData.userName} 通用配置状态: ${status}`)
      },
      onMessage: data => {
        console.log(`用户 ${formData.userName} 通用配置消息:`, data)
        // 这里可以根据需要处理特定的消息
      },
      onError: error => {
        console.error(`用户 ${formData.userName} 通用配置错误:`, error)
        message.error(`通用配置连接失败: ${error}`)
        generalWebsocketId.value = null
      },
    })

    if (websocketId) {
      generalWebsocketId.value = websocketId
      message.success(`已开始配置用户 ${formData.userName} 的通用设置`)
    }
  } catch (error) {
    console.error('通用配置失败:', error)
    message.error('通用配置失败')
  } finally {
    generalConfigLoading.value = false
  }
}

const stageModeOptions = ref([{ label: '固定', value: 'Fixed' }])

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

const stageOptions = ref([{ label: '不选择', value: '' }])

const loadStageOptions = async () => {
  try {
    const response = await Service.getStageComboxApiInfoComboxStagePost({
      type: 'Today',
    })
    if (response && response.code === 200 && response.data) {
      const sorted = [...response.data].sort((a, b) => {
        if (a.value === '-') return -1
        if (b.value === '-') return 1
        return 0
      })
      stageOptions.value = sorted
    }
  } catch (error) {
    console.error('加载关卡选项失败:', error)
    // 保持默认选项
  }
}

// 选择基建配置文件
const selectInfrastructureConfig = async () => {
  try {
    const path = await window.electronAPI?.selectFile([
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

    // 调用API导入基建配置
    const result = await Service.importInfrastructureApiScriptsUserInfrastructurePost({
      scriptId: scriptId,
      userId: userId,
      jsonFile: infrastructureConfigPath.value[0],
    })

    if (result && result.code === 200) {
      message.success('基建配置导入成功')
      // 清空文件路径
      infrastructureConfigPath.value = ''
    } else {
      message.error(result?.msg || '基建配置导入失败')
    }
  } catch (error) {
    console.error('基建配置导入失败:', error)
    message.error('基建配置导入失败')
  } finally {
    infrastructureImporting.value = false
  }
}

const handleCancel = () => {
  // 清理WebSocket连接
  if (maaWebsocketId.value) {
    disconnect(maaWebsocketId.value)
    maaWebsocketId.value = null
  }
  if (generalWebsocketId.value) {
    disconnect(generalWebsocketId.value)
    generalWebsocketId.value = null
  }
  router.push('/scripts')
}

onMounted(() => {
  if (!scriptId) {
    message.error('缺少脚本ID参数')
    handleCancel()
    return
  }

  loadScriptInfo()
  loadStageModeOptions()
  loadStageOptions()
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

.header-nav {
  flex: 1;
}

.breadcrumb {
  margin: 0;
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
