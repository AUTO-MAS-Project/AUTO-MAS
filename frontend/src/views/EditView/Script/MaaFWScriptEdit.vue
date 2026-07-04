<template>
  <div class="script-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts" class="breadcrumb-link">脚本管理</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <div class="breadcrumb-current">
            <img src="@/assets/AUTO-MAS.ico" alt="MaaFramework" class="breadcrumb-logo" />
            编辑 MaaFramework 项目
          </div>
        </a-breadcrumb-item>
      </a-breadcrumb>
    </div>

    <a-space size="middle">
      <a-button size="large" class="cancel-button" @click="handleCancel">
        <template #icon>
          <ArrowLeftOutlined />
        </template>
        返回
      </a-button>
    </a-space>
  </div>

  <div class="script-edit-content">
    <a-card title="MaaFramework 项目配置" :loading="pageLoading" class="config-card">
      <template #extra>
        <a-tag color="geekblue" class="type-tag">MaaFW</a-tag>
      </template>

      <a-form ref="formRef" :model="formData" :rules="rules" layout="vertical" class="config-form">
        <div class="form-section">
          <div class="section-header">
            <h3>基本信息</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item name="name">
                <template #label>
                  <a-tooltip title="为项目设置一个易于识别的名称">
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
                  @blur="handleChange('Info', 'Name', formData.name)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="16">
              <a-form-item name="path" :rules="rules.path">
                <template #label>
                  <a-tooltip title="选择包含 interface.json 的 MaaFramework 项目目录">
                    <span class="form-label">
                      项目目录
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="formData.path"
                    placeholder="请选择 MaaFramework 项目目录"
                    size="large"
                    class="path-input"
                    readonly
                  />
                  <a-button size="large" class="path-button" @click="selectMaaFWPath">
                    <template #icon>
                      <FolderOpenOutlined />
                    </template>
                    选择文件夹
                  </a-button>
                  <a-button
                    size="large"
                    class="path-button"
                    :loading="interfaceLoading"
                    :disabled="!maafwConfig.Info.Path"
                    @click="handlePreviewInterface"
                  >
                    <template #icon>
                      <FileSearchOutlined />
                    </template>
                    读取 interface
                  </a-button>
                  <a-button
                    size="large"
                    class="path-button"
                    :loading="agentEnvLoading"
                    :disabled="!maafwConfig.Info.Path"
                    @click="handlePrepareAgentEnv"
                  >
                    <template #icon>
                      <ToolOutlined />
                    </template>
                    准备运行环境
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
          </a-row>

          <div v-if="previewData" class="interface-summary">
            <a-descriptions :column="4" size="small" bordered>
              <a-descriptions-item label="项目">
                {{ previewProjectTitle }}
              </a-descriptions-item>
              <a-descriptions-item label="版本">
                {{ previewData.project.version || '-' }}
              </a-descriptions-item>
              <a-descriptions-item label="控制器">
                {{ previewData.controllers.length }}
              </a-descriptions-item>
              <a-descriptions-item label="资源">
                {{ previewData.resources.length }}
              </a-descriptions-item>
              <a-descriptions-item label="任务">
                {{ previewData.tasks.length }}
              </a-descriptions-item>
              <a-descriptions-item label="预设">
                {{ previewData.presets.length }}
              </a-descriptions-item>
              <a-descriptions-item label="导入">
                {{ previewData.importCount }}
              </a-descriptions-item>
              <a-descriptions-item label="Agent">
                {{ previewData.agentCount }}
              </a-descriptions-item>
            </a-descriptions>
          </div>
          <div v-else-if="interfaceLoading" class="interface-loading">
            <a-spin tip="正在读取 interface.json...">
              <a-alert
                type="info"
                show-icon
                message="正在加载 MaaFW 项目接口"
                description="请稍候，正在解析 interface.json 中的控制器、资源、任务和选项定义"
              />
            </a-spin>
          </div>
          <a-empty v-else class="interface-empty" description="尚未读取 interface.json" />

          <div v-if="agentEnvLoading || agentEnvResult" class="agent-env-panel">
            <a-spin :spinning="agentEnvLoading" tip="正在准备 MaaFW 运行环境...">
              <a-alert
                v-if="agentEnvLoading"
                type="info"
                show-icon
                message="正在准备 MaaFW 运行环境"
                description="将预热 AUTO-MAS Runner 隔离 venv，并检查或准备项目 Agent Python 环境。"
              />
              <template v-else-if="agentEnvResult">
                <a-alert
                  :type="agentEnvAlertType"
                  show-icon
                  :message="agentEnvSummary"
                  :description="agentEnvDescription"
                />
                <div v-if="agentEnvResult.agents.length" class="agent-env-agent-list">
                  <div
                    v-for="(agent, index) in agentEnvResult.agents"
                    :key="`${agent.childExec}-${index}`"
                    class="agent-env-agent-item"
                  >
                    <div class="agent-env-agent-header">
                      <span class="agent-env-agent-title">{{ agent.childExec }}</span>
                      <a-tag :color="getAgentRuntimeColor(agent.runtimeKind)">
                        {{ getAgentRuntimeLabel(agent.runtimeKind) }}
                      </a-tag>
                    </div>
                    <div class="agent-env-agent-line">
                      <span>解释器</span>
                      <code>{{ agent.executable }}</code>
                    </div>
                    <div v-if="agent.isolatedVenvPath" class="agent-env-agent-line">
                      <span>隔离 venv</span>
                      <code>{{ agent.isolatedVenvPath }}</code>
                    </div>
                    <div v-if="agent.fallbackReason" class="agent-env-agent-line">
                      <span>准备说明</span>
                      <code>{{ agent.fallbackReason }}</code>
                    </div>
                  </div>
                </div>
                <div v-if="agentEnvResult.logs.length" class="agent-env-log-box">
                  <div
                    v-for="(log, index) in agentEnvResult.logs"
                    :key="`${index}-${log}`"
                    class="agent-env-log-line"
                  >
                    {{ log }}
                  </div>
                </div>
              </template>
            </a-spin>
          </div>
        </div>

        <div class="form-section">
          <div class="section-header">
            <h3>控制方式与游戏资源</h3>
          </div>

          <a-row :gutter="24" class="controller-resource-row">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <a-tooltip title="选择 MaaFW Controller，决定使用 ADB、Win32 等控制方式">
                    <span class="form-label">
                      控制方式
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="maafwConfig.Info.Controller"
                  size="large"
                  placeholder="自动选择"
                  allow-clear
                  :disabled="interfaceDependentDisabled"
                  @change="handleControllerChange"
                >
                  <a-select-option
                    v-for="item in controllerOptions"
                    :key="item.name"
                    :value="item.name"
                    :disabled="!isDirectControllerType(item.type)"
                  >
                    {{ item.label || item.name }} · {{ item.type }}
                    <span v-if="!isDirectControllerType(item.type)"> · 建议使用原 UI</span>
                  </a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <a-tooltip
                    title="选择 MaaFW Resource，留空时自动选择匹配当前控制方式的第一个 Resource"
                  >
                    <span class="form-label">
                      游戏资源
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="maafwConfig.Info.Resource"
                  size="large"
                  placeholder="自动选择"
                  allow-clear
                  :disabled="interfaceDependentDisabled"
                  @change="handleResourceChange"
                >
                  <a-select-option
                    v-for="item in resourceOptions"
                    :key="item.name"
                    :value="item.name"
                  >
                    {{ item.label || item.name }}
                  </a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
          </a-row>
          <a-alert
            v-if="unsupportedControllerOptions.length"
            class="control-strategy-alert"
            type="info"
            show-icon
            :message="unsupportedControllerMessage"
          />

          <template v-if="isAdbController">
            <a-row :gutter="24" class="control-detail-row">
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="MaaFW ADB controller 运行时使用该模拟器配置">
                      <span class="form-label">
                        模拟器
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-select
                    v-model:value="maafwConfig.Emulator.Id"
                    size="large"
                    placeholder="请选择模拟器"
                    :loading="emulatorLoading"
                    @change="handleEmulatorSelectChange"
                  >
                    <a-select-option value="-">不指定</a-select-option>
                    <a-select-option
                      v-for="item in emulatorOptions"
                      :key="item.value"
                      :value="item.value"
                    >
                      {{ item.label }}
                    </a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="选择模拟器的具体实例，运行时会传递给 MaaFW ADB controller">
                      <span class="form-label">
                        模拟器实例
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-input
                    v-if="
                      emulatorDeviceOptions.length === 0 &&
                      !emulatorDeviceLoading &&
                      maafwConfig.Emulator.Id &&
                      maafwConfig.Emulator.Id !== '-'
                    "
                    v-model:value="maafwConfig.Emulator.Index"
                    size="large"
                    placeholder="请输入模拟器实例索引"
                    class="modern-input"
                    @blur="handleChange('Emulator', 'Index', maafwConfig.Emulator.Index)"
                  />
                  <a-select
                    v-else
                    v-model:value="maafwConfig.Emulator.Index"
                    size="large"
                    placeholder="请先选择模拟器"
                    :loading="emulatorDeviceLoading"
                    :disabled="!maafwConfig.Emulator.Id || maafwConfig.Emulator.Id === '-'"
                    @change="handleChange('Emulator', 'Index', $event)"
                  >
                    <a-select-option value="-">不指定</a-select-option>
                    <a-select-option
                      v-for="item in emulatorDeviceOptions"
                      :key="item.value"
                      :value="item.value"
                    >
                      {{ item.label }}
                    </a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
            </a-row>

            <a-alert
              class="control-strategy-alert"
              type="info"
              show-icon
              :message="adbControlStrategyMessage"
            />
            <a-descriptions :column="3" size="small" bordered class="control-strategy-summary">
              <a-descriptions-item
                v-for="item in adbControlStrategyItems"
                :key="item.label"
                :label="item.label"
              >
                {{ item.value }}
              </a-descriptions-item>
            </a-descriptions>
          </template>

          <template v-else-if="isDesktopController">
            <a-row :gutter="24" class="control-detail-row">
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="选择由 MAS 启动并管理生命周期的实际游戏 exe 文件">
                      <span class="form-label">
                        游戏可执行文件
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-input-group compact class="path-input-group">
                    <a-input
                      v-model:value="maafwConfig.Game.Path"
                      placeholder="请选择实际启动的游戏 exe"
                      size="large"
                      class="path-input"
                      readonly
                    />
                    <a-button size="large" class="path-button" @click="selectGamePath">
                      <template #icon>
                        <FolderOpenOutlined />
                      </template>
                      选择文件
                    </a-button>
                  </a-input-group>
                </a-form-item>
              </a-col>
              <a-col :span="6">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="启动游戏时传入的命令行参数">
                      <span class="form-label">
                        启动参数
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-input
                    v-model:value="maafwConfig.Game.Arguments"
                    placeholder="可选"
                    size="large"
                    class="modern-input"
                    @blur="handleChange('Game', 'Arguments', maafwConfig.Game.Arguments)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="6">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="启动游戏后等待窗口就绪的时间，单位秒">
                      <span class="form-label">
                        等待时间
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-input-number
                    v-model:value="maafwConfig.Game.WaitTime"
                    :min="0"
                    :max="9999"
                    size="large"
                    style="width: 100%"
                    @blur="handleChange('Game', 'WaitTime', maafwConfig.Game.WaitTime)"
                  />
                </a-form-item>
              </a-col>
            </a-row>
            <a-row :gutter="24" class="control-detail-row">
              <a-col :span="8">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="任务结束后关闭由 MAS 启动的游戏进程">
                      <span class="form-label">
                        结束后关闭游戏
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-switch
                    v-model:checked="maafwConfig.Game.CloseOnFinish"
                    checked-children="开启"
                    un-checked-children="关闭"
                    @change="handleChange('Game', 'CloseOnFinish', maafwConfig.Game.CloseOnFinish)"
                  />
                </a-form-item>
              </a-col>
            </a-row>
            <a-row :gutter="24" class="control-detail-row">
              <a-col :span="18">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="扫描并选择 MaaFW Win32 controller 要连接的游戏客户端窗口">
                      <span class="form-label">
                        游戏客户端
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-select
                    v-model:value="maafwConfig.Device.HWnd"
                    size="large"
                    placeholder="请选择游戏客户端窗口"
                    :loading="windowLoading"
                    :disabled="interfaceDependentDisabled"
                    @change="handleDesktopWindowChange"
                  >
                    <a-select-option :value="0">自动匹配</a-select-option>
                    <a-select-option
                      v-for="item in desktopWindowOptions"
                      :key="item.value"
                      :value="item.value"
                    >
                      {{ item.label }}
                    </a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :span="6">
                <a-form-item label="窗口扫描">
                  <a-button
                    size="large"
                    block
                    :loading="windowLoading"
                    :disabled="interfaceDependentDisabled"
                    @click="() => handlePreviewWindows()"
                  >
                    <template #icon>
                      <FileSearchOutlined />
                    </template>
                    扫描客户端
                  </a-button>
                </a-form-item>
              </a-col>
            </a-row>

            <a-alert
              class="control-strategy-alert"
              type="info"
              show-icon
              message="Win32 控制方式会连接已打开的游戏客户端；未选择时按 interface 规则自动匹配。"
            />
          </template>
        </div>

        <div class="form-section">
          <div class="section-header">
            <h3>项目更新</h3>
          </div>
          <a-alert
            v-if="isAutoUpdateDisabled"
            class="update-alert"
            type="warning"
            show-icon
            message="当前脚本未声明版本，无法判断更新"
          />
          <a-row :gutter="24" class="update-config-row">
            <a-col :span="8">
              <a-form-item label="更新源">
                <a-select
                  v-model:value="maafwConfig.Update.Source"
                  size="large"
                  :options="updateSourceOptions"
                  @change="handleChange('Update', 'Source', $event)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item label="渠道">
                <a-select
                  v-model:value="maafwConfig.Update.Channel"
                  size="large"
                  :options="updateChannelOptions"
                  @change="handleChange('Update', 'Channel', $event)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <a-tooltip
                    title="填写后优先使用脚本自己的 Mirror 酱 CDK；留空时使用 MAS 全局更新配置中的 CDK"
                  >
                    <span class="form-label">
                      Mirror 酱 CDK
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-password
                  v-model:value="maafwConfig.Update.MirrorChyanCDK"
                  placeholder="留空时使用全局 Mirror 酱 CDK"
                  size="large"
                  class="modern-input"
                  @blur="
                    handleChange('Update', 'MirrorChyanCDK', maafwConfig.Update.MirrorChyanCDK)
                  "
                />
              </a-form-item>
            </a-col>
          </a-row>
          <a-row :gutter="24" class="update-action-row">
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <a-tooltip
                    title="运行 MaaFW 任务前先检查项目更新，更新完成后再读取 interface 与加载资源"
                  >
                    <span class="form-label">
                      运行前自动更新
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-switch
                  v-model:checked="maafwConfig.Update.IfAutoUpdate"
                  :disabled="isAutoUpdateDisabled"
                  checked-children="开启"
                  un-checked-children="关闭"
                  @change="handleChange('Update', 'IfAutoUpdate', maafwConfig.Update.IfAutoUpdate)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item label="手动更新">
                <a-button
                  type="primary"
                  size="large"
                  class="manual-update-button"
                  :loading="projectUpdateLoading"
                  :disabled="projectUpdateDisabled"
                  @click="handleManualProjectUpdate"
                >
                  <template #icon>
                    <SyncOutlined />
                  </template>
                  立即更新资源
                </a-button>
              </a-form-item>
            </a-col>
          </a-row>
          <div v-if="projectUpdateLogs.length" class="agent-env-log-box project-update-log-box">
            <div
              v-for="(log, index) in projectUpdateLogs"
              :key="`${index}-${log}`"
              class="agent-env-log-line"
            >
              {{ log }}
            </div>
          </div>
          <div v-if="previewData" class="update-info-grid">
            <div class="update-info-item">
              <div class="update-info-label">当前版本</div>
              <div class="update-info-value">{{ previewData.project.version || '未声明' }}</div>
            </div>
            <div class="update-info-item">
              <div class="update-info-label">GitHub</div>
              <div class="update-info-value">{{ previewData.project.github || '未声明' }}</div>
            </div>
            <div class="update-info-item">
              <div class="update-info-label">MirrorChyan RID</div>
              <div class="update-info-value">
                {{ previewData.project.mirrorchyanRid || '未声明' }}
              </div>
            </div>
            <div class="update-info-item">
              <div class="update-info-label">多平台</div>
              <div class="update-info-value">
                {{ previewData.project.mirrorchyanMultiplatform ? '是' : '否' }}
              </div>
            </div>
          </div>
        </div>

        <div class="form-section">
          <div class="section-header">
            <h3>运行配置</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item label="用户单日代理次数上限">
                <a-input-number
                  v-model:value="maafwConfig.Run.ProxyTimesLimit"
                  :min="0"
                  :max="9999"
                  size="large"
                  class="modern-number-input"
                  style="width: 100%"
                  @blur="handleChange('Run', 'ProxyTimesLimit', maafwConfig.Run.ProxyTimesLimit)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item label="代理重试次数限制">
                <a-input-number
                  v-model:value="maafwConfig.Run.RunTimesLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  class="modern-number-input"
                  style="width: 100%"
                  @blur="handleChange('Run', 'RunTimesLimit', maafwConfig.Run.RunTimesLimit)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item label="单次运行时间限制（分钟）">
                <a-input-number
                  v-model:value="maafwConfig.Run.RunTimeLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  class="modern-number-input"
                  style="width: 100%"
                  @blur="handleChange('Run', 'RunTimeLimit', maafwConfig.Run.RunTimeLimit)"
                />
              </a-form-item>
            </a-col>
          </a-row>

          <a-row :gutter="24" class="period-task-row">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <a-tooltip title="任务在本周正常完成一次后，本周后续运行会自动跳过">
                    <span class="form-label">
                      每周完成后跳过
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="weeklyOnceTasks"
                  mode="multiple"
                  size="large"
                  :options="periodTaskOptions"
                  :disabled="interfaceDependentDisabled"
                  option-filter-prop="label"
                  show-search
                  :max-tag-count="'responsive'"
                  placeholder="先读取 interface 后选择任务"
                  @change="handlePeriodTaskChange('WeeklyOnceTasks', $event as string[])"
                />
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <a-tooltip title="任务在本月正常完成一次后，本月后续运行会自动跳过">
                    <span class="form-label">
                      每月完成后跳过
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="monthlyOnceTasks"
                  mode="multiple"
                  size="large"
                  :options="periodTaskOptions"
                  :disabled="interfaceDependentDisabled"
                  option-filter-prop="label"
                  show-search
                  :max-tag-count="'responsive'"
                  placeholder="先读取 interface 后选择任务"
                  @change="handlePeriodTaskChange('MonthlyOnceTasks', $event as string[])"
                />
              </a-form-item>
            </a-col>
          </a-row>
        </div>
      </a-form>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { FormInstance } from 'ant-design-vue'
import { message } from 'ant-design-vue'
import {
  ArrowLeftOutlined,
  FileSearchOutlined,
  FolderOpenOutlined,
  QuestionCircleOutlined,
  SyncOutlined,
  ToolOutlined,
} from '@ant-design/icons-vue'
import { Service, type ComboBoxItem } from '@/api'
import { useMaaFWApi } from '@/composables/useMaaFWApi'
import { useScriptApi } from '@/composables/useScriptApi'
import { useSettingsApi } from '@/composables/useSettingsApi'
import type {
  MaaFWAgentEnvPrepareData,
  MaaFWDesktopWindowInfo,
  MaaFWInterfacePreviewData,
  MaaFWScriptConfig,
  ScriptType,
} from '@/types/script'

const logger = window.electronAPI.getLogger('MaaFW脚本编辑')

const route = useRoute()
const router = useRouter()
const { getScript, updateScript } = useScriptApi()
const { getSettings } = useSettingsApi()
const { loading: interfaceLoading, previewInterface } = useMaaFWApi()
const { loading: windowLoading, previewWindows } = useMaaFWApi()
const { loading: agentEnvLoading, prepareAgentEnv } = useMaaFWApi()
const { loading: projectUpdateLoading, updateProjectResources } = useMaaFWApi()

const formRef = ref<FormInstance>()
const pageLoading = ref(false)
const scriptId = route.params.id as string
const isInitializing = ref(true)
const isSaving = ref(false)
const previewData = ref<MaaFWInterfacePreviewData | null>(null)
const agentEnvResult = ref<MaaFWAgentEnvPrepareData | null>(null)
const projectUpdateLogs = ref<string[]>([])
const desktopWindows = ref<MaaFWDesktopWindowInfo[]>([])
const weeklyOnceTasks = ref<string[]>([])
const monthlyOnceTasks = ref<string[]>([])
const globalUpdateSource = ref<string>('')
const globalUpdateChannel = ref<string>('')
const isAutoUpdateDisabled = computed(() =>
  Boolean(previewData.value && !previewData.value.project.version)
)
const projectUpdateDisabled = computed(
  () =>
    !maafwConfig.Info.Path ||
    !previewData.value ||
    isAutoUpdateDisabled.value ||
    isSaving.value ||
    interfaceLoading.value ||
    projectUpdateLoading.value
)
const periodTaskOptions = computed(() =>
  (previewData.value?.tasks || []).map(task => ({
    label: task.label ? `${task.label}（${task.name}）` : task.name,
    value: task.name,
  }))
)

type MaaFWConcreteUpdateSource = Exclude<MaaFWScriptConfig['Update']['Source'], ''>
type MaaFWConcreteUpdateChannel = Exclude<MaaFWScriptConfig['Update']['Channel'], ''>

const MAAFW_UPDATE_SOURCES: MaaFWConcreteUpdateSource[] = ['MirrorChyan']
const MAAFW_UPDATE_CHANNELS: MaaFWConcreteUpdateChannel[] = ['stable', 'beta']
const MAAFW_DIRECT_CONTROLLER_TYPES = ['Adb', 'Win32'] as const

type MaaFWDirectControllerType = (typeof MAAFW_DIRECT_CONTROLLER_TYPES)[number]

const isDirectControllerType = (
  controllerType?: string | null
): controllerType is MaaFWDirectControllerType =>
  MAAFW_DIRECT_CONTROLLER_TYPES.includes(controllerType as MaaFWDirectControllerType)

const updateSourceOptions = MAAFW_UPDATE_SOURCES.map(value => ({ label: value, value }))

const updateChannelOptions = [
  { label: '稳定版', value: 'stable' as MaaFWConcreteUpdateChannel },
  { label: '测试版', value: 'beta' as MaaFWConcreteUpdateChannel },
]

const isMaaFWUpdateSource = (value: string): value is MaaFWConcreteUpdateSource =>
  MAAFW_UPDATE_SOURCES.includes(value as MaaFWConcreteUpdateSource)

const isMaaFWUpdateChannel = (value: string): value is MaaFWConcreteUpdateChannel =>
  MAAFW_UPDATE_CHANNELS.includes(value as MaaFWConcreteUpdateChannel)

type EmulatorType = 'general' | 'mumu' | 'ldplayer'

const EMULATOR_TYPE_LABELS: Record<EmulatorType, string> = {
  general: '通用模拟器',
  mumu: 'MuMu 模拟器',
  ldplayer: '雷电模拟器',
}

const getDefaultMaaFWScriptConfig = (): MaaFWScriptConfig => ({
  Info: {
    Name: '',
    ProjectLabel: '',
    Path: '',
    Controller: '',
    Resource: '',
  },
  Emulator: {
    Id: '-',
    Index: '-',
  },
  Device: {
    AdbPath: '',
    AdbAddress: '',
    AdbScreencapMethods: -57,
    AdbInputMethods: -1,
    HWnd: 0,
    Win32ScreencapMethod: 0,
    Win32MouseMethod: 0,
    Win32KeyboardMethod: 0,
    GamepadType: 0,
    PlayCoverAddress: '',
    PlayCoverUuid: '',
  },
  Game: {
    Path: '',
    Arguments: '',
    WaitTime: 60,
    CloseOnFinish: true,
  },
  Update: {
    IfAutoUpdate: true,
    Source: 'MirrorChyan',
    Channel: 'stable',
    MirrorChyanCDK: '',
  },
  Run: {
    ProxyTimesLimit: 0,
    RunTimesLimit: 1,
    RunTimeLimit: 30,
    WeeklyOnceTasks: '[ ]',
    MonthlyOnceTasks: '[ ]',
  },
})

const maafwConfig = reactive<MaaFWScriptConfig>(getDefaultMaaFWScriptConfig())

const formData = reactive({
  type: 'MaaFW' as ScriptType,
  get name() {
    return maafwConfig.Info.Name
  },
  set name(value) {
    maafwConfig.Info.Name = value
  },
  get path() {
    return maafwConfig.Info.Path
  },
  set path(value) {
    maafwConfig.Info.Path = value
  },
})

const rules = {
  name: [{ required: true, message: '请输入脚本名称', trigger: 'blur' }],
  path: [{ required: true, message: '请选择 MaaFramework 项目目录', trigger: 'blur' }],
}

const emulatorLoading = ref(false)
const emulatorDeviceLoading = ref(false)
const emulatorOptions = ref<ComboBoxItem[]>([])
const emulatorDeviceOptions = ref<ComboBoxItem[]>([])
const emulatorTypeById = ref<Record<string, EmulatorType>>({})

const previewProjectTitle = computed(() => {
  if (!previewData.value) return '-'
  const project = previewData.value.project
  return project.title || project.label || project.name
})

const normalizeProjectScriptName = (rawName?: string | null) => {
  if (!rawName) return ''

  const primaryName = rawName
    .split(/[|｜]/)[0]
    .trim()
    .replace(/\s+(?:版本号\s*[:：]?\s*)?v?\d+(?:\.\d+)+(?:[-+][\w.]+)?$/i, '')
    .trim()

  return primaryName || rawName.trim()
}

const resolveProjectScriptName = (data: MaaFWInterfacePreviewData) => {
  const project = data.project
  return (
    normalizeProjectScriptName(project.title) ||
    normalizeProjectScriptName(project.label) ||
    normalizeProjectScriptName(project.name)
  )
}

const resolveProjectLabel = (data: MaaFWInterfacePreviewData) => {
  return resolveProjectScriptName(data)
}

const syncScriptNameFromProject = async (data: MaaFWInterfacePreviewData) => {
  const nextName = resolveProjectScriptName(data)
  if (!nextName || nextName === maafwConfig.Info.Name) return

  maafwConfig.Info.Name = nextName
  await handleChange('Info', 'Name', nextName, true)
}

const syncProjectLabelFromProject = async (data: MaaFWInterfacePreviewData) => {
  const nextLabel = resolveProjectLabel(data)
  if (!nextLabel || nextLabel === maafwConfig.Info.ProjectLabel) return

  maafwConfig.Info.ProjectLabel = nextLabel
  await handleChange('Info', 'ProjectLabel', nextLabel, true)
}

const getAgentRuntimeLabel = (runtimeKind?: string | null) => {
  if (runtimeKind === 'embedded') return '主进程内嵌'
  if (runtimeKind === 'project_python') return '项目自带 Python'
  if (runtimeKind === 'project_binary') return '项目自带程序'
  if (runtimeKind === 'isolated_venv') return '隔离 venv'
  if (runtimeKind === 'external') return '外部环境'
  return runtimeKind || '未知环境'
}

const getAgentRuntimeColor = (runtimeKind?: string | null) => {
  if (runtimeKind === 'embedded') return 'purple'
  if (runtimeKind === 'project_python') return 'green'
  if (runtimeKind === 'project_binary') return 'cyan'
  if (runtimeKind === 'isolated_venv') return 'blue'
  if (runtimeKind === 'external') return 'orange'
  return 'default'
}

const agentEnvAlertType = computed(() => {
  if (agentEnvResult.value?.status === 'error') return 'error'
  if (agentEnvResult.value?.agentCount === 0) return 'info'
  return 'success'
})

const agentEnvSummary = computed(() => {
  if (!agentEnvResult.value) return ''
  if (agentEnvResult.value.status === 'error') return 'MaaFW 运行环境准备失败'
  if (agentEnvResult.value.agentCount === 0) return 'MaaFW Runner 环境已准备完成'
  return `MaaFW 运行环境已准备完成，共 ${agentEnvResult.value.agentCount} 个 Agent`
})

const agentEnvDescription = computed(() => {
  if (!agentEnvResult.value) return ''
  if (agentEnvResult.value.status === 'error') {
    return agentEnvResult.value.message || '请查看下方准备日志定位失败步骤'
  }
  if (agentEnvResult.value.agentCount === 0) {
    return '当前 MaaFW 项目没有声明 Agent，无需准备 Agent 子进程环境。'
  }
  return 'Runner 隔离 venv 已预热；项目内二进制 Agent 直接使用；项目自带 Python 只做健康检查；缺少项目 Python 时使用项目专属隔离 venv。'
})

const controllerOptions = computed(() => previewData.value?.controllers || [])
const directControllerOptions = computed(() =>
  controllerOptions.value.filter(controller => isDirectControllerType(controller.type))
)
const unsupportedControllerOptions = computed(() =>
  controllerOptions.value.filter(controller => !isDirectControllerType(controller.type))
)
const unsupportedControllerMessage = computed(() => {
  const names = unsupportedControllerOptions.value
    .map(controller => `${controller.label || controller.name}(${controller.type})`)
    .join('、')
  return `AUTO-MAS MaaFW Direct 只联动 ADB / Win32；${names} 建议使用项目原 UI。`
})

const getDefaultControllerName = () => {
  const wantsAdb = maafwConfig.Emulator.Id && maafwConfig.Emulator.Id !== '-'
  if (wantsAdb) {
    const adbController = directControllerOptions.value.find(c => c.type === 'Adb')
    if (adbController) return adbController.name
  }
  return directControllerOptions.value[0]?.name || ''
}

const resolveControllerName = (controllerName?: string) => {
  if (controllerName && directControllerOptions.value.some(c => c.name === controllerName)) {
    return controllerName
  }
  return getDefaultControllerName()
}

const effectiveControllerName = computed(() => resolveControllerName(maafwConfig.Info.Controller))
const effectiveController = computed(
  () => controllerOptions.value.find(item => item.name === effectiveControllerName.value) || null
)
const effectiveControllerType = computed(() => effectiveController.value?.type || '')
const isAdbController = computed(() => effectiveControllerType.value === 'Adb')
const isDesktopController = computed(() => effectiveControllerType.value === 'Win32')

const getResourceOptionsByController = (controllerName: string) => {
  const resources = previewData.value?.resources || []
  if (!controllerName) return resources
  return resources.filter(r => r.controller.length === 0 || r.controller.includes(controllerName))
}

const resourceOptions = computed(() =>
  getResourceOptionsByController(effectiveControllerName.value)
)

const desktopWindowOptions = computed(() =>
  desktopWindows.value.map(item => {
    const windowTitle = item.windowName || '未命名窗口'
    const className = item.className || '未知类名'
    return {
      value: item.hWnd,
      label: `${windowTitle} · ${className} · ${item.hWnd}`,
    }
  })
)

const resolveResourceName = (
  resourceName?: string,
  controllerName = effectiveControllerName.value
) => {
  const resources = getResourceOptionsByController(controllerName)
  if (resourceName && resources.some(r => r.name === resourceName)) {
    return resourceName
  }
  return resources[0]?.name || ''
}

const interfaceDependentDisabled = computed(() => interfaceLoading.value || !previewData.value)

const handleControllerChange = async () => {
  maafwConfig.Info.Resource = ''
  const nextController = resolveControllerName(maafwConfig.Info.Controller)
  const nextResource = resolveResourceName('', nextController)
  maafwConfig.Info.Controller = nextController
  maafwConfig.Info.Resource = nextResource
  await handleChange('Info', 'Controller', maafwConfig.Info.Controller)
  await handleChange('Info', 'Resource', maafwConfig.Info.Resource)
  if (isDesktopController.value) {
    await handlePreviewWindows(false)
  }
}

const handleResourceChange = async () => {
  maafwConfig.Info.Resource = resolveResourceName(maafwConfig.Info.Resource)
  await handleChange('Info', 'Resource', maafwConfig.Info.Resource)
}

const syncControllerResourceSelection = (persist = false) => {
  if (!previewData.value) return
  const nextController = resolveControllerName(maafwConfig.Info.Controller)
  const nextResource = resolveResourceName(maafwConfig.Info.Resource, nextController)
  const controllerChanged = maafwConfig.Info.Controller !== nextController
  const resourceChanged = maafwConfig.Info.Resource !== nextResource
  maafwConfig.Info.Controller = nextController
  maafwConfig.Info.Resource = nextResource
  if (persist && (controllerChanged || resourceChanged)) {
    handleChange('Info', 'Controller', nextController)
    handleChange('Info', 'Resource', nextResource)
  }
}

const handleDesktopWindowChange = async (value: number) => {
  maafwConfig.Device.HWnd = Number(value) || 0
  await handleChange('Device', 'HWnd', maafwConfig.Device.HWnd)
}

const selectedEmulatorType = computed(() => emulatorTypeById.value[maafwConfig.Emulator.Id])

const selectedEmulatorLabel = computed(() => {
  if (!maafwConfig.Emulator.Id || maafwConfig.Emulator.Id === '-') return '未选择模拟器'
  const emulatorType = selectedEmulatorType.value
  return emulatorType ? EMULATOR_TYPE_LABELS[emulatorType] : '模拟器类型加载中'
})

const selectedEmulatorCapability = computed(() => {
  const emulatorType = selectedEmulatorType.value
  if (!emulatorType) return null
  return previewData.value?.controlCapabilities.emulatorExtras[emulatorType] || null
})

const adbControlStrategyMessage = computed(() => {
  if (!maafwConfig.Emulator.Id || maafwConfig.Emulator.Id === '-') {
    return '未选择模拟器时，ADB controller 将使用 MaaFW 默认 ADB 控制策略'
  }
  if (!previewData.value) {
    return '读取 interface 后会展示当前 MaaFW 包可用的模拟器增强能力'
  }

  const capability = selectedEmulatorCapability.value
  if (capability?.screencap || capability?.input) {
    return `已根据 ${selectedEmulatorLabel.value} 和当前 MaaFW 包能力启用可用的 EmulatorExtras`
  }
  return `${selectedEmulatorLabel.value} 当前没有可用的 EmulatorExtras 能力，运行时使用 MaaFW 默认 ADB 控制策略`
})

const adbControlStrategyItems = computed(() => {
  const capability = selectedEmulatorCapability.value
  const screencapWithExtras = Boolean(capability?.screencap)
  const inputWithExtras = Boolean(capability?.input)

  return [
    {
      label: '模拟器',
      value: selectedEmulatorLabel.value,
    },
    {
      label: '截图',
      value: screencapWithExtras
        ? 'MaaFW 默认截图集合（包含 EmulatorExtras）'
        : 'MaaFW 默认截图集合（不启用 EmulatorExtras）',
    },
    {
      label: '输入',
      value: inputWithExtras
        ? 'MaaFW 全量输入集合（优先 EmulatorExtras）'
        : 'MaaFW 默认输入集合（不启用 EmulatorExtras）',
    },
  ]
})

const normalizeScriptConfig = (config: Partial<MaaFWScriptConfig> | null | undefined) => {
  const defaults = getDefaultMaaFWScriptConfig()
  return {
    Info: { ...defaults.Info, ...config?.Info },
    Emulator: { ...defaults.Emulator, ...config?.Emulator },
    Device: { ...defaults.Device, ...config?.Device },
    Game: { ...defaults.Game, ...config?.Game },
    Update: normalizeUpdateConfig({ ...defaults.Update, ...config?.Update }),
    Run: { ...defaults.Run, ...config?.Run },
  }
}

const resolveUpdateSource = (value?: string | null): MaaFWConcreteUpdateSource => {
  if (value && isMaaFWUpdateSource(value)) return value
  if (globalUpdateSource.value && isMaaFWUpdateSource(globalUpdateSource.value)) {
    return globalUpdateSource.value
  }
  return MAAFW_UPDATE_SOURCES[0]
}

const resolveUpdateChannel = (value?: string | null): MaaFWConcreteUpdateChannel => {
  if (value && isMaaFWUpdateChannel(value)) return value
  if (globalUpdateChannel.value && isMaaFWUpdateChannel(globalUpdateChannel.value)) {
    return globalUpdateChannel.value
  }
  return MAAFW_UPDATE_CHANNELS[0]
}

const normalizeUpdateConfig = (
  update: MaaFWScriptConfig['Update']
): MaaFWScriptConfig['Update'] => ({
  ...update,
  Source: resolveUpdateSource(update.Source),
  Channel: resolveUpdateChannel(update.Channel),
})

const parseTaskNameList = (raw: string | string[] | null | undefined): string[] => {
  if (Array.isArray(raw)) {
    return Array.from(new Set(raw.map(String).filter(Boolean)))
  }
  if (typeof raw === 'string' && raw.trim()) {
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) {
        return Array.from(new Set(parsed.map(String).filter(Boolean)))
      }
    } catch {
      return []
    }
  }
  return []
}

const stringifyTaskNameList = (value: string[]): string => JSON.stringify(value)

const applyScriptConfig = (config: Partial<MaaFWScriptConfig> | null | undefined) => {
  const normalized = normalizeScriptConfig(config)
  Object.assign(maafwConfig.Info, normalized.Info)
  Object.assign(maafwConfig.Emulator, normalized.Emulator)
  Object.assign(maafwConfig.Device, normalized.Device)
  Object.assign(maafwConfig.Game, normalized.Game)
  Object.assign(maafwConfig.Update, normalized.Update)
  Object.assign(maafwConfig.Run, normalized.Run)
  weeklyOnceTasks.value = parseTaskNameList(normalized.Run.WeeklyOnceTasks)
  monthlyOnceTasks.value = parseTaskNameList(normalized.Run.MonthlyOnceTasks)
  maafwConfig.Run.WeeklyOnceTasks = stringifyTaskNameList(weeklyOnceTasks.value)
  maafwConfig.Run.MonthlyOnceTasks = stringifyTaskNameList(monthlyOnceTasks.value)
}

const handleChange = async (
  category: keyof MaaFWScriptConfig,
  key: string,
  value: unknown,
  force = false
) => {
  if ((!force && isInitializing.value) || isSaving.value) return

  isSaving.value = true
  try {
    const success = await updateScript(scriptId, { [category]: { [key]: value } })
    if (success) {
      logger.info(`配置已保存: ${category}.${key}`)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存失败: ${errorMsg}`)
  } finally {
    isSaving.value = false
  }
}

const handlePeriodTaskChange = async (
  key: 'WeeklyOnceTasks' | 'MonthlyOnceTasks',
  values: string[]
) => {
  const normalized = Array.from(new Set(values.filter(Boolean)))
  if (key === 'WeeklyOnceTasks') {
    weeklyOnceTasks.value = normalized
  } else {
    monthlyOnceTasks.value = normalized
  }

  maafwConfig.Run[key] = stringifyTaskNameList(normalized)
  await handleChange('Run', key, maafwConfig.Run[key])
}

const prunePeriodTaskSelections = async () => {
  if (!previewData.value) return

  const availableTasks = new Set(previewData.value.tasks.map(task => task.name))
  const nextWeeklyTasks = weeklyOnceTasks.value.filter(taskName => availableTasks.has(taskName))
  const nextMonthlyTasks = monthlyOnceTasks.value.filter(taskName => availableTasks.has(taskName))
  const weeklyChanged = nextWeeklyTasks.length !== weeklyOnceTasks.value.length
  const monthlyChanged = nextMonthlyTasks.length !== monthlyOnceTasks.value.length

  if (weeklyChanged) {
    await handlePeriodTaskChange('WeeklyOnceTasks', nextWeeklyTasks)
  }
  if (monthlyChanged) {
    await handlePeriodTaskChange('MonthlyOnceTasks', nextMonthlyTasks)
  }
}

const handlePreviewInterface = async () => {
  if (!maafwConfig.Info.Path) {
    message.warning('请先选择 MaaFramework 项目目录')
    return
  }

  const data = await previewInterface(maafwConfig.Info.Path)
  if (data) {
    previewData.value = data
    await syncScriptNameFromProject(data)
    await syncProjectLabelFromProject(data)
    syncControllerResourceSelection(!isInitializing.value)
    await prunePeriodTaskSelections()
    if (isDesktopController.value) {
      await handlePreviewWindows(false)
    }
    message.success(`已读取 ${previewProjectTitle.value}`)
  }
}

const handlePrepareAgentEnv = async () => {
  if (!maafwConfig.Info.Path) {
    message.warning('璇峰厛閫夋嫨 MaaFramework 椤圭洰鐩綍')
    return
  }

  agentEnvResult.value = null
  const data = await prepareAgentEnv(maafwConfig.Info.Path)
  if (!data) return

  agentEnvResult.value = data
  if (data.status === 'error') {
    message.error(data.message || 'MaaFW 运行环境准备失败')
    return
  }
  if (data.agentCount === 0) {
    message.info('MaaFW Runner 环境已准备完成，当前项目没有声明 Agent')
    return
  }
  message.success(`MaaFW 运行环境已准备完成，共 ${data.agentCount} 个 Agent`)
}

const handleManualProjectUpdate = async () => {
  if (!maafwConfig.Info.Path) {
    message.warning('请先选择 MaaFramework 项目目录')
    return
  }
  if (!previewData.value) {
    message.warning('请先读取 interface')
    return
  }
  if (isAutoUpdateDisabled.value) {
    message.warning('当前脚本未声明版本，无法判断更新')
    return
  }
  if (isSaving.value || projectUpdateLoading.value) return

  projectUpdateLogs.value = []
  isSaving.value = true
  try {
    const saved = await updateScript(scriptId, {
      Update: { ...maafwConfig.Update },
    })
    if (!saved) return
  } finally {
    isSaving.value = false
  }

  const response = await updateProjectResources(scriptId)
  projectUpdateLogs.value = response?.data?.logs ?? []
  if (!response?.data || response.code !== 200) return

  await refreshPreviewIfPossible()
  if (response.data.updated) {
    message.success(response.message || 'MaaFW 项目资源已更新')
    return
  }

  message.info(response.message || 'MaaFW 项目已是最新')
}

const refreshPreviewIfPossible = async () => {
  if (!maafwConfig.Info.Path) return
  const data = await previewInterface(maafwConfig.Info.Path)
  if (data) {
    previewData.value = data
    await syncScriptNameFromProject(data)
    await syncProjectLabelFromProject(data)
    syncControllerResourceSelection(!isInitializing.value)
    await prunePeriodTaskSelections()
    if (isDesktopController.value) {
      await handlePreviewWindows(false)
    }
  }
}

const handlePreviewWindows = async (showMessage = true) => {
  if (!maafwConfig.Info.Path) {
    if (showMessage) message.warning('请先选择 MaaFramework 项目目录')
    return
  }
  if (!isDesktopController.value) return

  const data = await previewWindows(maafwConfig.Info.Path, effectiveControllerName.value)
  if (!data) return

  desktopWindows.value = data.windows
  if (
    maafwConfig.Device.HWnd &&
    !data.windows.some(item => item.hWnd === maafwConfig.Device.HWnd)
  ) {
    maafwConfig.Device.HWnd = 0
  }

  if (!showMessage) return
  if (data.windows.length === 0) {
    message.info('未扫描到匹配的游戏客户端窗口')
    return
  }
  message.success(`已扫描到 ${data.windows.length} 个游戏客户端窗口`)
}

const loadScript = async () => {
  pageLoading.value = true
  try {
    await loadGlobalUpdateDefaults()

    const routeState = history.state as any
    if (routeState?.scriptData) {
      applyScriptConfig(routeState.scriptData.config as MaaFWScriptConfig)
    }

    const scriptDetail = await getScript(scriptId)
    if (!scriptDetail) {
      message.error('脚本不存在或加载失败')
      router.push('/scripts')
      return
    }

    formData.type = scriptDetail.type
    applyScriptConfig(scriptDetail.config as MaaFWScriptConfig)

    if (maafwConfig.Emulator.Id && maafwConfig.Emulator.Id !== '-') {
      await loadEmulatorDeviceOptions(maafwConfig.Emulator.Id)
    }
    await refreshPreviewIfPossible()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载脚本失败: ${errorMsg}`)
    message.error('加载脚本失败')
    router.push('/scripts')
  } finally {
    pageLoading.value = false
  }
}

const loadGlobalUpdateDefaults = async () => {
  const settings = await getSettings()
  globalUpdateSource.value = settings?.Update?.Source || ''
  globalUpdateChannel.value = settings?.Update?.Channel || ''
}

const loadEmulatorOptions = async () => {
  emulatorLoading.value = true
  try {
    const [response, detailResponse] = await Promise.all([
      Service.getEmulatorComboxApiInfoComboxEmulatorPost(),
      Service.getEmulatorApiEmulatorGetPost({}),
    ])
    if (response?.code === 200) {
      emulatorOptions.value = response.data || []
    }
    if (detailResponse?.code === 200) {
      const typeMap: Record<string, EmulatorType> = {}
      Object.entries(detailResponse.data || {}).forEach(([emulatorId, config]) => {
        const emulatorType = config.Info?.Type
        if (emulatorType) typeMap[emulatorId] = emulatorType
      })
      emulatorTypeById.value = typeMap
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载模拟器选项失败: ${errorMsg}`)
  } finally {
    emulatorLoading.value = false
  }
}

const loadEmulatorDeviceOptions = async (emulatorId: string) => {
  if (!emulatorId || emulatorId === '-') return

  emulatorDeviceLoading.value = true
  try {
    const response = await Service.getEmulatorDevicesComboxApiInfoComboxEmulatorDevicesPost({
      emulatorId,
    })
    if (response?.code === 200) {
      emulatorDeviceOptions.value = response.data || []
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载模拟器实例选项失败: ${errorMsg}`)
  } finally {
    emulatorDeviceLoading.value = false
  }
}

const handleEmulatorSelectChange = async (emulatorId: string) => {
  maafwConfig.Emulator.Index = '-'
  emulatorDeviceOptions.value = []
  await handleChange('Emulator', 'Id', emulatorId)
  await handleChange('Emulator', 'Index', '-')
  await loadEmulatorDeviceOptions(emulatorId)
}

const selectMaaFWPath = async () => {
  try {
    const path = await window.electronAPI?.selectFolder()
    if (path) {
      maafwConfig.Info.Path = path
      agentEnvResult.value = null
      await handleChange('Info', 'Path', path)
      await handlePreviewInterface()
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`选择 MaaFW 项目目录失败: ${errorMsg}`)
    message.error('选择文件夹失败')
  }
}

const selectGamePath = async () => {
  try {
    const paths = await window.electronAPI?.selectFile([
      {
        name: 'Executable',
        extensions: ['exe'],
      },
    ])
    const path = paths?.[0]
    if (!path) return

    const fileName = path.split(/[\\/]/).pop() || ''
    if (!fileName.toLowerCase().endsWith('.exe')) {
      message.error('请选择游戏 exe 文件')
      return
    }

    maafwConfig.Game.Path = path
    await handleChange('Game', 'Path', path)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`选择游戏可执行文件失败: ${errorMsg}`)
    message.error('选择游戏可执行文件失败')
  }
}

const handleCancel = () => {
  router.push('/scripts')
}

onMounted(async () => {
  await loadScript()
  await loadEmulatorOptions()
  isInitializing.value = false
})
</script>

<style scoped>
.script-edit-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
  padding: 0 8px;
}

.header-nav {
  flex: 1;
  min-width: 0;
}

.breadcrumb :deep(ol) {
  display: flex;
  align-items: center;
  flex-wrap: nowrap;
}

.breadcrumb :deep(.ant-breadcrumb-link),
.breadcrumb :deep(.ant-breadcrumb-separator) {
  display: inline-flex;
  align-items: center;
}

.breadcrumb-current,
.breadcrumb-link {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}

.breadcrumb-link {
  color: var(--ant-color-text-secondary);
  text-decoration: none;
}

.breadcrumb-current {
  color: var(--ant-color-text);
  font-weight: 600;
}

.breadcrumb-logo {
  width: 20px;
  height: 20px;
  object-fit: contain;
}

.script-edit-content {
  flex: 1;
}

.config-card {
  border-radius: 12px;
  border: 1px solid var(--ant-color-border-secondary);
  background: var(--ant-color-bg-container);
}

.config-card :deep(.ant-card-head) {
  background: var(--ant-color-bg-container);
  border-bottom: 1px solid var(--ant-color-border-secondary);
  padding: 20px 24px;
}

.config-card :deep(.ant-card-body) {
  padding: 24px;
}

.type-tag {
  font-size: 14px;
  font-weight: 600;
  padding: 6px 12px;
  border-radius: 6px;
}

.form-section {
  margin-bottom: 24px;
}

.form-section:last-child {
  margin-bottom: 0;
}

.update-alert {
  margin-bottom: 16px;
}

.manual-update-button {
  min-width: 160px;
}

.project-update-log-box {
  margin-bottom: 16px;
}

.update-info-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px 24px;
  margin-top: 4px;
}

.update-info-item {
  min-width: 0;
}

.update-info-label {
  margin-bottom: 6px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  font-weight: 600;
}

.update-info-value {
  min-height: 22px;
  color: var(--ant-color-text);
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.control-strategy-alert {
  margin-bottom: 12px;
}

.control-strategy-summary {
  margin-top: 8px;
}

.period-task-row {
  margin-top: 8px;
}

.section-header {
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 10px;
}

.section-header h3::before {
  content: '';
  width: 4px;
  height: 20px;
  background: var(--ant-color-primary);
  border-radius: 2px;
}

.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
}

.modern-input,
.modern-number-input {
  border-radius: 8px;
}

.path-input-group {
  display: flex;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--ant-color-border);
}

.path-input {
  flex: 1;
  border: none !important;
  border-radius: 0 !important;
}

.path-input:focus {
  box-shadow: none !important;
}

.path-button {
  border: none;
  border-left: 1px solid var(--ant-color-border-secondary);
  border-radius: 0;
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  font-weight: 600;
}

.interface-summary {
  margin-top: 8px;
}

.interface-empty {
  margin-top: 8px;
  padding: 16px;
  border: 1px dashed var(--ant-color-border);
  border-radius: 8px;
}

.interface-loading {
  margin-top: 8px;
  padding: 16px;
}

.interface-loading :deep(.ant-spin-container) {
  opacity: 1;
}

.agent-env-panel {
  margin-top: 16px;
}

.agent-env-agent-list {
  display: grid;
  gap: 8px;
  margin-top: 12px;
}

.agent-env-agent-item {
  padding: 12px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
}

.agent-env-agent-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.agent-env-agent-title {
  min-width: 0;
  color: var(--ant-color-text);
  font-weight: 600;
  overflow-wrap: anywhere;
}

.agent-env-agent-line {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 8px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.agent-env-agent-line code {
  color: var(--ant-color-text);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.agent-env-log-box {
  max-height: 220px;
  margin-top: 12px;
  padding: 10px 12px;
  overflow: auto;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
  font-family: var(--font-mono, Consolas, 'Courier New', monospace);
  font-size: 12px;
  line-height: 1.6;
}

.agent-env-log-line {
  color: var(--ant-color-text-secondary);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.controller-resource-row,
.control-detail-row {
  margin-top: 16px;
}

.config-form :deep(.ant-form-item) {
  margin-bottom: 20px;
}

@media (max-width: 768px) {
  .script-edit-header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }

  .config-card :deep(.ant-card-body) {
    padding: 16px;
  }

  .update-info-grid {
    grid-template-columns: 1fr;
  }
}
</style>
