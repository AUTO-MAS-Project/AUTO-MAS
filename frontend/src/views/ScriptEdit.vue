<template>
  <div class="script-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts" class="breadcrumb-link"> 脚本管理</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <div class="breadcrumb-current">
            <img
              v-if="formData.type === 'MAA'"
              src="@/assets/MAA.png"
              alt="MAA"
              class="breadcrumb-logo"
            />
            <img v-else src="@/assets/AUTO-MAS.ico" alt="AUTO_MAA" class="breadcrumb-logo" />
            编辑脚本
          </div>
        </a-breadcrumb-item>
      </a-breadcrumb>
    </div>

    <a-space size="middle">
      <a-button size="large" @click="handleCancel" class="cancel-button">
        <template #icon>
          <ArrowLeftOutlined />
        </template>
        返回
      </a-button>
      <!--      <a-button-->
      <!--        type="primary"-->
      <!--        size="large"-->
      <!--        :loading="loading"-->
      <!--        @click="handleSave"-->
      <!--        class="save-button"-->
      <!--      >-->
      <!--        <template #icon>-->
      <!--          <SaveOutlined />-->
      <!--        </template>-->
      <!--        保存配置-->
      <!--      </a-button>-->
    </a-space>
  </div>

  <div class="script-edit-content">
    <a-card :title="getCardTitle()" :loading="pageLoading" class="config-card">
      <template #extra>
        <a-tag :color="formData.type === 'MAA' ? 'blue' : 'green'" class="type-tag">
          {{ formData.type }}
        </a-tag>
      </template>

      <a-form ref="formRef" :model="formData" :rules="rules" layout="vertical" class="config-form">
        <!-- 基本信息 -->
        <div class="form-section">
          <div class="section-header">
            <h3>基本信息</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item name="name">
                <template #label>
                  <a-tooltip title="为脚本设置一个易于识别的名称">
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
                />
              </a-form-item>
            </a-col>
            <template v-if="formData.type === 'MAA'">
              <a-col :span="16">
                <a-form-item name="path">
                  <template #label>
                    <a-tooltip title="选择MAA.exe所在的文件夹路径">
                      <span class="form-label">
                        MAA路径
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-input-group compact class="path-input-group">
                    <a-input
                      v-model:value="maaConfig.Info.Path"
                      placeholder="请选择MAA.exe所在的文件夹"
                      size="large"
                      class="path-input"
                      readonly
                    />
                    <a-button size="large" @click="selectMAAPath" class="path-button">
                      <template #icon>
                        <FolderOpenOutlined />
                      </template>
                      选择文件夹
                    </a-button>
                  </a-input-group>
                </a-form-item>
              </a-col>
            </template>
            <template v-if="formData.type === 'General'">
              <a-col :span="16">
                <a-form-item name="rootPath">
                  <template #label>
                    <a-tooltip title="脚本的根目录路径，其余路径将基于此目录自动调整">
                      <span class="form-label">
                        脚本根目录
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-input-group compact class="path-input-group">
                    <a-input
                      v-model:value="generalConfig.Info.RootPath"
                      placeholder="请选择脚本根目录"
                      size="large"
                      class="path-input"
                      readonly
                    />
                    <a-button size="large" @click="selectRootPath" class="path-button">
                      <template #icon>
                        <FolderOpenOutlined />
                      </template>
                      选择文件夹
                    </a-button>
                  </a-input-group>
                </a-form-item>
              </a-col>
            </template>
          </a-row>
        </div>

        <!-- MAA脚本配置 -->
        <template v-if="formData.type === 'MAA'">
          <!-- 运行配置 -->
          <div class="form-section">
            <div class="section-header">
              <h3>运行配置</h3>
            </div>
            <a-row :gutter="24">
              <a-col :span="8">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="切换账号时需要执行的操作">
                      <span class="form-label">
                        账号切换方法
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-select v-model:value="maaConfig.Run.TaskTransitionMethod" size="large">
                    <a-select-option value="ExitEmulator">重启模拟器</a-select-option>
                    <a-select-option value="ExitGame">重启明日方舟</a-select-option>
                    <a-select-option value="NoAction">直接切换账号</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :span="8">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="使用mumu模拟器时设为3，其他模拟器设为0">
                      <span class="form-label">
                        ADB端口号搜索范围
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-input-number
                    v-model:value="maaConfig.Run.ADBSearchRange"
                    :min="0"
                    :max="3"
                    size="large"
                    class="modern-number-input"
                    style="width: 100%"
                  />
                </a-form-item>
              </a-col>

              <a-col :span="8">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="当用户本日代理成功次数达到该阀值时跳过代理，阈值为「0」时视为无代理次数上限">
                      <span class="form-label">
                        用户单日代理次数上限
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-input-number
                    v-model:value="maaConfig.Run.ProxyTimesLimit"
                    :min="0"
                    :max="999"
                    size="large"
                    class="modern-number-input"
                    style="width: 100%"
                  />
                </a-form-item>
              </a-col>
            </a-row>
            <a-row :gutter="24">
              <a-col :span="8">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="执行剿灭代理任务时，MAA日志无变化时间超过该阀值视为超时">
                      <span class="form-label">
                        剿灭代理超时限制（分钟）
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-input-number
                    v-model:value="maaConfig.Run.AnnihilationTimeLimit"
                    :min="1"
                    :max="9999"
                    size="large"
                    class="modern-number-input"
                    style="width: 100%"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="8">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="每周剿灭达到上限后，本周剩余时间不在执行剿灭任务，本功能存在误判可能，请谨慎使用">
                      <span class="form-label">
                        每周剿灭仅执行到上限
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-select v-model:value="maaConfig.Run.AnnihilationWeeklyLimit" size="large">
                    <a-select-option :value="true">是</a-select-option>
                    <a-select-option :value="false">否</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="24">
              <a-col :span="8">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="执行日常代理任务时，MAA日志无变化时间超过该阀值视为超时">
                      <span class="form-label">
                        日常代理超时限制（分钟）
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-input-number
                    v-model:value="maaConfig.Run.RoutineTimeLimit"
                    :min="1"
                    :max="9999"
                    size="large"
                    class="modern-number-input"
                    style="width: 100%"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="8">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="若重试超过该次数限制仍未完成代理，视为代理失败">
                      <span class="form-label">
                        代理重试次数限制
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-input-number
                    v-model:value="maaConfig.Run.RunTimesLimit"
                    :min="1"
                    :max="9999"
                    size="large"
                    class="modern-number-input"
                    style="width: 100%"
                  />
                </a-form-item>
              </a-col>
            </a-row>
          </div>
        </template>

        <!-- 通用脚本配置 -->
        <template v-if="formData.type === 'General'">
          <!-- 基础配置 -->
          <div class="form-section">
            <div class="section-header">
              <h3>脚本配置</h3>
            </div>
            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="脚本主程序文件路径">
                      <span class="form-label">
                        主程序路径
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-input-group compact class="path-input-group">
                    <a-input
                      v-model:value="generalConfig.Script.ScriptPath"
                      placeholder="请选择脚本主程序文件"
                      size="large"
                      class="path-input"
                      readonly
                    />
                    <a-button size="large" @click="selectScriptPath" class="path-button">
                      <template #icon>
                        <FileOutlined />
                      </template>
                      选择文件
                    </a-button>
                  </a-input-group>
                </a-form-item>
              </a-col>
              <a-col :span="6">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="启动脚本任务时需要添加的附加命令，详细语法参见官网文档">
                      <span class="form-label">
                        启动参数
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-input
                    v-model:value="generalConfig.Script.Arguments"
                    placeholder="请输入脚本启动参数"
                    size="large"
                    class="modern-input"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="6">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="开启后仅在脚本进程及其所有子进程全部结束时认定脚本进程结束">
                      <span class="form-label">
                        追踪子进程
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <!--                  <a-switch-->
                  <!--                    v-model:checked="generalConfig.Script.IfTrackProcess"-->
                  <!--                    size="default"-->
                  <!--                    class="modern-switch"-->
                  <!--                  />-->

                  <a-select v-model:value="generalConfig.Script.IfTrackProcess" size="large">
                    <a-select-option :value="true">是</a-select-option>
                    <a-select-option :value="false">否</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
            </a-row>
            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <a-tooltip :title="generalConfig.Script.ConfigPathMode === 'Folder' ? '脚本配置文件所在的文件夹路径' : '脚本配置文件的路径'">
                      <span class="form-label">
                        配置文件路径
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-input-group compact class="path-input-group">
                    <a-input
                      v-model:value="generalConfig.Script.ConfigPath"
                      :placeholder="generalConfig.Script.ConfigPathMode === 'Folder' ? '请选择配置文件夹' : '请选择配置文件'"
                      size="large"
                      class="path-input"
                      readonly
                    />
                    <a-button size="large" @click="selectConfigPath" class="path-button">
                      <template #icon>
                        <FolderOpenOutlined v-if="generalConfig.Script.ConfigPathMode === 'Folder'" />
                        <FileOutlined v-else />
                      </template>
                      {{ generalConfig.Script.ConfigPathMode === 'Folder' ? '选择文件夹' : '选择文件' }}
                    </a-button>
                  </a-input-group>
                </a-form-item>
              </a-col>
              <a-col :span="6">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="脚本配置文件类型">
                      <span class="form-label">
                        配置文件类型
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-select v-model:value="generalConfig.Script.ConfigPathMode" size="large">
                    <a-select-option value="File">单文件</a-select-option>
                    <a-select-option value="Folder">文件夹</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :span="6">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="在选定的时刻更新脚本配置文件">
                      <span class="form-label">
                        配置文件更新时机
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-select v-model:value="generalConfig.Script.UpdateConfigMode" size="large">
                    <a-select-option value="Never">从不</a-select-option>
                    <a-select-option value="Success">成功时</a-select-option>
                    <a-select-option value="Failure">失败时</a-select-option>
                    <a-select-option value="Always">总是</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
            </a-row>
            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="脚本用于存放日志信息的文件路径">
                      <span class="form-label">
                        日志文件路径
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-input-group compact class="path-input-group">
                    <a-input
                      v-model:value="generalConfig.Script.LogPath"
                      placeholder="请选择日志文件"
                      size="large"
                      class="path-input"
                      readonly
                    />
                    <a-button size="large" @click="selectLogPath" class="path-button">
                      <template #icon>
                        <FolderOpenOutlined />
                      </template>
                      选择文件
                    </a-button>
                  </a-input-group>
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="指示实时生成日志文件名的格式，日志文件名固定时留空">
                      <span class="form-label">
                        日志文件名格式
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-input
                    v-model:value="generalConfig.Script.LogPathFormat"
                    placeholder="日志文件名格式"
                    size="large"
                    class="modern-input"
                  />
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="24">
              <a-col :span="6">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="脚本日志时间戳起始位置">
                      <span class="form-label">
                        日志时间戳起始位置
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-input-number
                    v-model:value="generalConfig.Script.LogTimeStart"
                    :min="1"
                    :max="9999"
                    size="large"
                    class="modern-number-input"
                    style="width: 100%"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="6">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="脚本日志时间戳结束位置">
                      <span class="form-label">
                        日志时间戳结束位置
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-input-number
                    v-model:value="generalConfig.Script.LogTimeEnd"
                    :min="1"
                    :max="9999"
                    size="large"
                    class="modern-number-input"
                    style="width: 100%"
                  />
                </a-form-item>
              </a-col>

              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="脚本日志文件中时间戳的格式">
                      <span class="form-label">
                        日志时间戳格式
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-input
                    v-model:value="generalConfig.Script.LogTimeFormat"
                    placeholder="请输入脚本日志时间戳格式"
                    size="large"
                    class="modern-input"
                  />
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="若填写，且日志文本信息中任意任务成功日志先于任务异常日志出现，则视为任务成功，否则若脚本进程结束时，日志文本信息中不存在任何任务成功日志，则视为任务失败；若留空，且在脚本进程结束时，日志文本信息中不存在任意任务异常日志，则视为任务成功">
                      <span class="form-label">
                        任务成功日志
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-input
                    v-model:value="generalConfig.Script.SuccessLog"
                    placeholder="请输入脚本成功日志，以「 | 」进行分割"
                    size="large"
                    class="modern-input"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="若任务异常日志先于任务成功日志出现，则视为任务失败">
                      <span class="form-label">
                        任务失败日志
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-input
                    v-model:value="generalConfig.Script.ErrorLog"
                    placeholder="请输入脚本失败日志，以「 | 」进行分割"
                    size="large"
                    class="modern-input"
                  />
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="24"></a-row>

            <div class="section-header">
              <h3>游戏配置</h3>
            </div>

            <a-row :gutter="24">
              <a-col :span="8">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="是否由AUTO_MAA管理游戏/模拟器进程">
                      <span class="form-label">
                        启用游戏相关功能
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <!--                  <a-switch-->
                  <!--                    v-model:checked="generalConfig.Game.Enabled"-->
                  <!--                    size="default"-->
                  <!--                    class="modern-switch"-->
                  <!--                  />-->
                  <a-select v-model:value="generalConfig.Game.Enabled" size="large">
                    <a-select-option :value="true">是</a-select-option>
                    <a-select-option :value="false">否</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :span="8">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="游戏在哪个平台上运行">
                      <span class="form-label">
                        游戏平台类型
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-select v-model:value="generalConfig.Game.Type" size="large">
                    <a-select-option value="Emulator">安卓模拟器</a-select-option>
                    <a-select-option value="Client">PC客户端</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :span="8">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="游戏可执行文件的路径">
                      <span class="form-label">
                        游戏路径
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-input-group compact class="path-input-group">
                    <a-input
                      v-model:value="generalConfig.Game.Path"
                      placeholder="请选择游戏的可执行文件"
                      size="large"
                      class="path-input"
                      readonly
                    />
                    <a-button size="large" @click="selectGamePath" class="path-button">
                      <template #icon>
                        <FileOutlined />
                      </template>
                      选择文件
                    </a-button>
                  </a-input-group>
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="24">
              <a-col :span="8">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="启动游戏时的命令行参数">
                      <span class="form-label">
                        启动参数
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-input
                    v-model:value="generalConfig.Game.Arguments"
                    placeholder="请输入启动参数"
                    size="large"
                    class="modern-input"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="8">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="启动游戏后等待的时间">
                      <span class="form-label">
                        启动后等待时间（秒）
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-input-number
                    v-model:value="generalConfig.Game.WaitTime"
                    :min="0"
                    :max="300"
                    size="large"
                    class="modern-number-input"
                    style="width: 100%"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="8">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="脚本结束后是否强制关闭游戏进程">
                      <span class="form-label">
                        强制关闭游戏
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <!--                  <a-switch-->
                  <!--                    v-model:checked="generalConfig.Game.IfForceClose"-->
                  <!--                    size="default"-->
                  <!--                    class="modern-switch"-->
                  <!--                  />-->
                  <a-select v-model:value="generalConfig.Game.IfForceClose" size="large">
                    <a-select-option :value="true">是</a-select-option>
                    <a-select-option :value="false">否</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
            </a-row>
          </div>

          <!-- 运行配置 -->
          <div class="form-section">
            <div class="section-header">
              <h3>运行配置</h3>
            </div>
            <a-row :gutter="24">
              <a-col :span="8">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="当用户本日代理成功次数达到该阀值时跳过代理，阈值为「0」时视为无代理次数上限">
                      <span class="form-label">
                        单日代理次数上限
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-input-number
                    v-model:value="generalConfig.Run.ProxyTimesLimit"
                    :min="0"
                    :max="999"
                    size="large"
                    class="modern-number-input"
                    style="width: 100%"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="8">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="若重试超过该次数限制仍未完成代理，视为代理失败">
                      <span class="form-label">
                        代理重试次数限制
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-input-number
                    v-model:value="generalConfig.Run.RunTimesLimit"
                    :min="1"
                    :max="10"
                    size="large"
                    class="modern-number-input"
                    style="width: 100%"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="8">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="执行代理任务时，脚本日志无变化时间超过该阀值视为超时">
                      <span class="form-label">
                        代理超时限制（分钟）
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-input-number
                    v-model:value="generalConfig.Run.RunTimeLimit"
                    :min="1"
                    :max="300"
                    size="large"
                    class="modern-number-input"
                    style="width: 100%"
                  />
                </a-form-item>
              </a-col>
            </a-row>
          </div>
        </template>
      </a-form>
    </a-card>
  </div>
  <a-float-button
    type="primary"
    @click="handleSave"
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
import { onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { FormInstance } from 'ant-design-vue'
import { message } from 'ant-design-vue'
import type { GeneralScriptConfig, MAAScriptConfig, ScriptType } from '../types/script'
import { useScriptApi } from '../composables/useScriptApi'
import {
  ArrowLeftOutlined,
  FileOutlined,
  FolderOpenOutlined,
  QuestionCircleOutlined,
  SaveOutlined,
} from '@ant-design/icons-vue'

const route = useRoute()
const router = useRouter()
const { getScript, updateScript, loading } = useScriptApi()

const formRef = ref<FormInstance>()

// 路径处理工具函数
const pathUtils = {
  // 检查路径是否为绝对路径
  isAbsolute(pathStr: string): boolean {
    if (!pathStr || pathStr === '.') return false
    // Windows: C:\ 或 D:\ 等
    // Unix/Linux: /
    return /^[a-zA-Z]:[\\/]/.test(pathStr) || pathStr.startsWith('/')
  },

  // 获取相对路径
  getRelativePath(from: string, to: string): string {
    if (!from || !to || from === '.' || to === '.') return '.'
    
    // 确保都是绝对路径
    if (!this.isAbsolute(from) || !this.isAbsolute(to)) return to

    // 规范化路径分隔符为 /
    const normalizePath = (p: string) => p.replace(/\\/g, '/')
    const fromNorm = normalizePath(from)
    const toNorm = normalizePath(to)
    
    // 分割路径
    const fromParts = fromNorm.split('/').filter(Boolean)
    const toParts = toNorm.split('/').filter(Boolean)
    
    // Windows 驱动器字母处理
    if (fromParts[0] && fromParts[0].includes(':') && toParts[0] && toParts[0].includes(':')) {
      if (fromParts[0].toLowerCase() !== toParts[0].toLowerCase()) {
        // 不同驱动器，返回绝对路径
        return to
      }
    }
    
    // 找到公共前缀
    let commonLength = 0
    const minLength = Math.min(fromParts.length, toParts.length)
    for (let i = 0; i < minLength; i++) {
      if (fromParts[i].toLowerCase() === toParts[i].toLowerCase()) {
        commonLength++
      } else {
        break
      }
    }
    
    // 构建相对路径
    const upLevels = fromParts.length - commonLength
    const downParts = toParts.slice(commonLength)
    
    const relativeParts = []
    for (let i = 0; i < upLevels; i++) {
      relativeParts.push('..')
    }
    relativeParts.push(...downParts)
    
    return relativeParts.length === 0 ? '.' : relativeParts.join('/')
  },

  // 解析相对路径为绝对路径
  resolvePath(basePath: string, relativePath: string): string {
    if (!basePath || basePath === '.' || !relativePath || relativePath === '.') {
      return relativePath || '.'
    }
    
    // 如果 relativePath 已经是绝对路径，直接返回
    if (this.isAbsolute(relativePath)) {
      return relativePath
    }
    
    // 规范化路径分隔符
    const normalizePath = (p: string) => p.replace(/\\/g, '/')
    const baseNorm = normalizePath(basePath)
    const relativeNorm = normalizePath(relativePath)
    
    // 分割路径
    const baseParts = baseNorm.split('/').filter(Boolean)
    const relativeParts = relativeNorm.split('/').filter(Boolean)
    
    // 处理相对路径
    for (const part of relativeParts) {
      if (part === '..') {
        if (baseParts.length > 1 || (baseParts.length === 1 && !baseParts[0].includes(':'))) {
          baseParts.pop()
        }
      } else if (part !== '.') {
        baseParts.push(part)
      }
    }
    
    // 重新组合路径
    let result = baseParts.join('/')
    
    // 对于 Windows 路径，确保驱动器字母格式正确
    if (result.includes(':')) {
      // 移除多余的斜杠并确保正确格式
      result = result.replace(/\/+/g, '/')
      result = result.replace(/^([a-zA-Z]):\/+/, '$1:/')
      
      // 如果只有驱动器字母，添加根路径斜杠
      if (/^[a-zA-Z]:$/.test(result)) {
        result += '/'
      }
    } else if (!result.startsWith('/')) {
      // 对于非 Windows 路径，确保以 / 开头
      result = '/' + result
    }
    
    // 最终规范化处理
    return this.normalizePath(result)
  },

  // 检查路径是否在根目录下
  isSubPath(rootPath: string, targetPath: string): boolean {
    if (!rootPath || !targetPath || rootPath === '.' || targetPath === '.') return false
    
    // 确保都是绝对路径
    if (!this.isAbsolute(rootPath) || !this.isAbsolute(targetPath)) return false
    
    const normalizePath = (p: string) => p.replace(/\\/g, '/').toLowerCase()
    const rootNorm = normalizePath(rootPath)
    const targetNorm = normalizePath(targetPath)
    
    // 确保路径以 / 结尾以进行精确匹配
    const rootWithSlash = rootNorm.endsWith('/') ? rootNorm : rootNorm + '/'
    const targetWithSlash = targetNorm.endsWith('/') ? targetNorm : targetNorm + '/'
    
    return targetWithSlash.startsWith(rootWithSlash) || rootNorm === targetNorm
  },

  // 将 Windows 路径转换为标准格式
  normalizePath(pathStr: string): string {
    if (!pathStr || pathStr === '.') return pathStr
    
    // 替换反斜杠为正斜杠
    let normalized = pathStr.replace(/\\/g, '/')
    
    // 移除多余的斜杠，但保留驱动器字母后的单个冒号
    normalized = normalized.replace(/\/+/g, '/')
    
    // 确保 Windows 驱动器路径格式正确 (例如 C:/path)
    normalized = normalized.replace(/^([a-zA-Z]):\/+/, '$1:/')
    
    // 移除末尾的斜杠（除非是根目录）
    if (normalized.length > 1 && normalized.endsWith('/')) {
      normalized = normalized.slice(0, -1)
    }
    
    return normalized
  }
}

// 路径验证函数
const validatePath = (rootPath: string, targetPath: string, pathName: string): boolean => {
  if (!targetPath || targetPath === '.') return true
  if (!rootPath || rootPath === '.') {
    message.warning(`请先设置脚本根目录后再选择${pathName}`)
    return false
  }
  
  if (!pathUtils.isSubPath(rootPath, targetPath)) {
    message.error(`${pathName}必须是脚本根目录的子路径`)
    return false
  }
  
  return true
}

// 存储路径的相对关系，用于根目录变化时自动调整
const pathRelations = reactive({
  scriptPathRelative: '',
  configPathRelative: '',
  logPathRelative: ''
})

// 更新相对路径关系
const updatePathRelations = () => {
  const rootPath = generalConfig.Info.RootPath
  if (!rootPath || rootPath === '.') {
    pathRelations.scriptPathRelative = ''
    pathRelations.configPathRelative = ''
    pathRelations.logPathRelative = ''
    return
  }

  if (generalConfig.Script.ScriptPath && generalConfig.Script.ScriptPath !== '.') {
    pathRelations.scriptPathRelative = pathUtils.getRelativePath(rootPath, generalConfig.Script.ScriptPath)
  }
  
  if (generalConfig.Script.ConfigPath && generalConfig.Script.ConfigPath !== '.') {
    pathRelations.configPathRelative = pathUtils.getRelativePath(rootPath, generalConfig.Script.ConfigPath)
  }
  
  if (generalConfig.Script.LogPath && generalConfig.Script.LogPath !== '.') {
    pathRelations.logPathRelative = pathUtils.getRelativePath(rootPath, generalConfig.Script.LogPath)
  }
}

// 根据新的根目录更新所有路径
const updatePathsBasedOnRoot = (newRootPath: string) => {
  if (!newRootPath || newRootPath === '.') return

  // 根据保存的相对路径关系重新计算绝对路径
  if (pathRelations.scriptPathRelative) {
    const newScriptPath = pathUtils.resolvePath(newRootPath, pathRelations.scriptPathRelative)
    const normalizedScriptPath = pathUtils.normalizePath(newScriptPath)
    generalConfig.Script.ScriptPath = normalizedScriptPath
  }
  
  if (pathRelations.configPathRelative) {
    const newConfigPath = pathUtils.resolvePath(newRootPath, pathRelations.configPathRelative)
    const normalizedConfigPath = pathUtils.normalizePath(newConfigPath)
    generalConfig.Script.ConfigPath = normalizedConfigPath
  }
  
  if (pathRelations.logPathRelative) {
    const newLogPath = pathUtils.resolvePath(newRootPath, pathRelations.logPathRelative)
    const normalizedLogPath = pathUtils.normalizePath(newLogPath)
    generalConfig.Script.LogPath = normalizedLogPath
  }
}
const pageLoading = ref(false)
const scriptId = route.params.id as string

const formData = reactive({
  name: '',
  type: 'MAA' as ScriptType,
})

// MAA配置
const maaConfig = reactive<MAAScriptConfig>({
  Info: {
    Name: '',
    Path: '.',
  },
  Run: {
    ADBSearchRange: 0,
    AnnihilationTimeLimit: 40,
    AnnihilationWeeklyLimit: true,
    ProxyTimesLimit: 0,
    RoutineTimeLimit: 10,
    RunTimesLimit: 3,
    TaskTransitionMethod: 'ExitEmulator',
  },
  SubConfigsInfo: {
    UserData: {
      instances: [],
    },
  },
})

// General配置
const generalConfig = reactive<GeneralScriptConfig>({
  Game: {
    Arguments: '',
    Enabled: false,
    IfForceClose: false,
    Path: '.',
    Type: 'Emulator',
    WaitTime: 0,
  },
  Info: {
    Name: '',
    RootPath: '.',
  },
  Run: {
    ProxyTimesLimit: 0,
    RunTimeLimit: 10,
    RunTimesLimit: 3,
  },
  Script: {
    Arguments: '',
    ConfigPath: '.',
    ConfigPathMode: 'File',
    ErrorLog: '',
    IfTrackProcess: false,
    LogPath: '.',
    LogPathFormat: '%Y-%m-%d',
    LogTimeEnd: 1,
    LogTimeStart: 1,
    LogTimeFormat: '%Y-%m-%d %H:%M:%S',
    ScriptPath: '.',
    SuccessLog: '',
    UpdateConfigMode: 'Never',
  },
  SubConfigsInfo: {
    UserData: {
      instances: [],
    },
  },
})

const rules = {
  name: [{ required: true, message: '请输入脚本名称', trigger: 'blur' }],
  type: [{ required: true, message: '请选择脚本类型', trigger: 'change' }],
}

// 监听配置文件类型变化，重置路径为根目录
watch(
  () => generalConfig.Script.ConfigPathMode,
  (newMode, oldMode) => {
    if (newMode !== oldMode && generalConfig.Script.ConfigPath && generalConfig.Script.ConfigPath !== '.') {
      // 当配置文件类型改变时，重置为根目录路径
      const rootPath = generalConfig.Info.RootPath
      if (rootPath && rootPath !== '.') {
        generalConfig.Script.ConfigPath = rootPath
        const typeText = newMode === 'Folder' ? '文件夹' : '文件'
        message.info(`配置文件类型已切换为${typeText}，路径已重置为根目录`)
      } else {
        // 如果没有设置根目录，则清空路径
        generalConfig.Script.ConfigPath = '.'
        const typeText = newMode === 'Folder' ? '文件夹' : '文件'
        message.info(`配置文件类型已切换为${typeText}，请重新选择路径`)
      }
    }
  }
)

// 监听根目录变化，自动调整其他路径以保持相对关系
watch(
  () => generalConfig.Info.RootPath,
  (newRootPath, oldRootPath) => {
    // 只有在根目录真正改变时才触发
    if (newRootPath !== oldRootPath && oldRootPath && oldRootPath !== '.') {
      // 如果新根目录有效，根据保存的相对路径关系更新所有路径
      if (newRootPath && newRootPath !== '.') {
        updatePathsBasedOnRoot(newRootPath)
      }
    }
    
    // 无论如何都更新相对路径关系以备后用
    if (newRootPath && newRootPath !== '.') {
      updatePathRelations()
    }
  }
)

onMounted(async () => {
  await loadScript()
})

const loadScript = async () => {
  pageLoading.value = true
  try {
    // 检查是否有通过路由状态传递的数据（新建脚本时）
    const routeState = history.state as any
    if (routeState?.scriptData) {
      // 使用API返回的新建脚本数据
      const scriptData = routeState.scriptData
      formData.type = scriptData.type

      if (scriptData.type === 'MAA') {
        const config = scriptData.config as MAAScriptConfig
        formData.name = config.Info.Name || '新建MAA脚本'
        Object.assign(maaConfig, config)
        // 如果名称为空，设置默认名称
        if (!maaConfig.Info.Name) {
          maaConfig.Info.Name = '新建MAA脚本'
          formData.name = '新建MAA脚本'
        }
      } else {
        const config = scriptData.config as GeneralScriptConfig
        formData.name = config.Info.Name || '新建通用脚本'
        Object.assign(generalConfig, config)
        // 如果名称为空，设置默认名称
        if (!generalConfig.Info.Name) {
          generalConfig.Info.Name = '新建通用脚本'
          formData.name = '新建通用脚本'
        }
      }
    } else {
      // 编辑现有脚本时，从API获取数据
      const scriptDetail = await getScript(scriptId)

      if (!scriptDetail) {
        message.error('脚本不存在或加载失败')
        router.push('/scripts')
        return
      }

      formData.type = scriptDetail.type
      formData.name = scriptDetail.name

      if (scriptDetail.type === 'MAA') {
        Object.assign(maaConfig, scriptDetail.config as MAAScriptConfig)
      } else {
        Object.assign(generalConfig, scriptDetail.config as GeneralScriptConfig)
        // 对于 General 类型，在加载完成后初始化相对路径关系
        setTimeout(() => {
          updatePathRelations()
        }, 100)
      }
    }
  } catch (error) {
    console.error('加载脚本失败:', error)
    message.error('加载脚本失败')
    router.push('/scripts')
  } finally {
    pageLoading.value = false
  }
}

const handleSave = async () => {
  try {
    await formRef.value?.validate()

    const config = formData.type === 'MAA' ? maaConfig : generalConfig
    if (formData.type === 'MAA') {
      maaConfig.Info.Name = formData.name
    } else {
      generalConfig.Info.Name = formData.name
    }

    const result = await updateScript(scriptId, config)
    if (result) {
      message.success('脚本更新成功')
      router.push('/scripts')
    }
  } catch (error) {
    console.error('保存失败:', error)
  }
}

const handleCancel = () => {
  router.push('/scripts')
}

// 文件选择方法
const selectMAAPath = async () => {
  try {
    if (!window.electronAPI) {
      message.error('文件选择功能不可用，请在 Electron 环境中运行')
      return
    }

    const path = await (window.electronAPI as any).selectFolder()
    if (path) {
      maaConfig.Info.Path = path
      message.success('MAA路径选择成功')
    }
  } catch (error) {
    console.error('选择MAA路径失败:', error)
    message.error('选择文件夹失败')
  }
}

const selectRootPath = async () => {
  try {
    if (!window.electronAPI) {
      message.error('文件选择功能不可用，请在 Electron 环境中运行')
      return
    }

    const path = await (window.electronAPI as any).selectFolder()
    if (path) {
      // 保存当前根目录，用于比较
      const oldRootPath = generalConfig.Info.RootPath
      
      // 规范化新路径
      const normalizedPath = pathUtils.normalizePath(path)
      
      // 在更改根目录之前，先更新相对路径关系
      if (oldRootPath && oldRootPath !== '.' && oldRootPath !== normalizedPath) {
        updatePathRelations()
      }
      
      // 设置新的根目录
      generalConfig.Info.RootPath = normalizedPath
      
      // 如果有保存的相对路径关系，根据新根目录更新其他路径
      if (oldRootPath && oldRootPath !== '.' && oldRootPath !== normalizedPath) {
        updatePathsBasedOnRoot(generalConfig.Info.RootPath)
        message.success('根路径选择成功，其他路径已自动调整以保持相对关系')
      } else {
        message.success('根路径选择成功')
      }
    }
  } catch (error) {
    console.error('选择根路径失败:', error)
    message.error('选择文件夹失败')
  }
}

const selectGamePath = async () => {
  try {
    if (!window.electronAPI) {
      message.error('文件选择功能不可用，请在 Electron 环境中运行')
      return
    }

    const paths = await (window.electronAPI as any).selectFile([
      { name: '可执行文件', extensions: ['exe'] },
      { name: '所有文件', extensions: ['*'] },
    ])
    if (paths && paths.length > 0) {
      generalConfig.Game.Path = paths[0]
      message.success('游戏路径选择成功')
    }
  } catch (error) {
    console.error('选择游戏路径失败:', error)
    message.error('选择文件失败')
  }
}

const selectScriptPath = async () => {
  try {
    if (!window.electronAPI) {
      message.error('文件选择功能不可用，请在 Electron 环境中运行')
      return
    }

    const paths = await (window.electronAPI as any).selectFile([
      { name: '可执行文件', extensions: ['exe', 'bat'] },
      { name: '所有文件', extensions: ['*'] },
    ])
    if (paths && paths.length > 0) {
      const path = paths[0]
      // 验证路径是否在根目录下
      if (validatePath(generalConfig.Info.RootPath, path, '主程序路径')) {
        generalConfig.Script.ScriptPath = pathUtils.normalizePath(path)
        // 更新相对路径关系
        updatePathRelations()
        message.success('脚本路径选择成功')
      }
    }
  } catch (error) {
    console.error('选择脚本路径失败:', error)
    message.error('选择文件失败')
  }
}

const selectConfigPath = async () => {
  try {
    if (!window.electronAPI) {
      message.error('文件选择功能不可用，请在 Electron 环境中运行')
      return
    }

    let selectedPath: string | undefined

    // 根据配置文件类型选择不同的选择方式
    if (generalConfig.Script.ConfigPathMode === 'Folder') {
      // 选择文件夹
      selectedPath = await (window.electronAPI as any).selectFolder()
      selectedPath = selectedPath || undefined
    } else {
      // 选择文件（默认行为）
      const paths = await (window.electronAPI as any).selectFile([
        { name: '配置文件', extensions: ['json', 'yaml', 'yml', 'ini', 'conf', 'toml'] },
        { name: 'JSON 文件', extensions: ['json'] },
        { name: 'YAML 文件', extensions: ['yaml', 'yml'] },
        { name: 'INI 文件', extensions: ['ini', 'conf'] },
        { name: 'TOML 文件', extensions: ['toml'] },
        { name: '所有文件', extensions: ['*'] },
      ])
      selectedPath = paths && paths.length > 0 ? paths[0] : undefined
    }

    if (selectedPath) {
      // 验证路径是否在根目录下
      const pathType = generalConfig.Script.ConfigPathMode === 'Folder' ? '配置文件夹' : '配置文件'
      if (validatePath(generalConfig.Info.RootPath, selectedPath, `${pathType}路径`)) {
        generalConfig.Script.ConfigPath = pathUtils.normalizePath(selectedPath)
        // 更新相对路径关系
        updatePathRelations()
        message.success(`${pathType}路径选择成功`)
      }
    }
  } catch (error) {
    console.error('选择配置路径失败:', error)
    const typeText = generalConfig.Script.ConfigPathMode === 'Folder' ? '文件夹' : '文件'
    message.error(`选择${typeText}失败`)
  }
}

const selectLogPath = async () => {
  try {
    if (!window.electronAPI) {
      message.error('文件选择功能不可用，请在 Electron 环境中运行')
      return
    }

    const paths = await (window.electronAPI as any).selectFile()
    if (paths && paths.length > 0) {
      const path = paths[0]
      // 验证路径是否在根目录下
      if (validatePath(generalConfig.Info.RootPath, path, '日志文件路径')) {
        generalConfig.Script.LogPath = pathUtils.normalizePath(path)
        // 更新相对路径关系
        updatePathRelations()
        message.success('日志路径选择成功')
      }
    }
  } catch (error) {
    console.error('选择日志路径失败:', error)
    message.error('选择文件失败')
  }
}

const getCardTitle = () => {
  return formData.type === 'MAA' ? 'MAA脚本配置' : '通用脚本配置'
}
</script>

<style scoped>
/* 头部区域 */
.script-edit-header {
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

.breadcrumb-link {
  align-items: center;
  gap: 8px;
  color: var(--ant-color-text-secondary);
  text-decoration: none;
  transition: color 0.3s ease;
}

.breadcrumb-current {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--ant-color-text);
  font-weight: 600;
}

.breadcrumb-logo {
  width: 20px;
  height: 20px;
  object-fit: contain;
  transition: all 0.3s ease;
}

/* 内容区域 */
.script-edit-content {
  flex: 1;
}

.config-card {
  border-radius: 16px;
  box-shadow:
    0 4px 20px rgba(0, 0, 0, 0.08),
    0 1px 3px rgba(0, 0, 0, 0.1);
  border: 1px solid var(--ant-color-border-secondary);
  overflow: hidden;
}

.config-card :deep(.ant-card-head) {
  background: var(--ant-color-bg-container);
  border-bottom: 2px solid var(--ant-color-border-secondary);
  padding: 24px 32px;
}

.config-card :deep(.ant-card-head-title) {
  font-size: 24px;
  font-weight: 700;
  color: var(--ant-color-text);
}

.config-card :deep(.ant-card-body) {
  padding: 32px;
  background: var(--ant-color-bg-container);
}

.type-tag {
  font-size: 14px;
  font-weight: 600;
  padding: 8px 16px;
  border-radius: 8px;
  border: none;
}

/* 表单样式 */
.config-form {
  max-width: none;
}

.form-section {
  margin-bottom: 12px;
}

.form-section:last-child {
  margin-bottom: 0;
}

.section-header {
  margin-bottom: 6px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 12px;
}

.section-header h3::before {
  content: '';
  width: 4px;
  height: 24px;
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  border-radius: 2px;
}

/* 表单标签 */
.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--ant-color-text);
  font-size: 14px;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
  cursor: help;
  transition: color 0.3s ease;
}

.help-icon:hover {
  color: var(--ant-color-primary);
}

.modern-input {
  border-radius: 8px;
  border: 2px solid var(--ant-color-border);
  background: var(--ant-color-bg-container);
  transition: all 0.3s ease;
}

.modern-input:hover {
  border-color: var(--ant-color-primary-hover);
}

.modern-input:focus,
.modern-input.ant-input-focused {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.1);
}

.modern-select :deep(.ant-select-selector) {
  border: 2px solid var(--ant-color-border) !important;
  border-radius: 8px !important;
  background: var(--ant-color-bg-container) !important;
  transition: all 0.3s ease;
}

.modern-select:hover :deep(.ant-select-selector) {
  border-color: var(--ant-color-primary-hover) !important;
}

.modern-select.ant-select-focused :deep(.ant-select-selector) {
  border-color: var(--ant-color-primary) !important;
  box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.1) !important;
}

.modern-number-input {
  border-radius: 8px;
}

.modern-number-input :deep(.ant-input-number) {
  border: 2px solid var(--ant-color-border);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
  transition: all 0.3s ease;
}

.modern-number-input :deep(.ant-input-number:hover) {
  border-color: var(--ant-color-primary-hover);
}

.modern-number-input :deep(.ant-input-number-focused) {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.1);
}

/* 路径输入组 */
.path-input-group {
  display: flex;
  border-radius: 8px;
  overflow: hidden;
  border: 2px solid var(--ant-color-border);
  transition: all 0.3s ease;
}

.path-input-group:hover {
  border-color: var(--ant-color-primary-hover);
}

.path-input-group:focus-within {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.1);
}

.path-input {
  flex: 1;
  border: none !important;
  border-radius: 0 !important;
  background: var(--ant-color-bg-container) !important;
}

.path-input:focus {
  box-shadow: none !important;
}

.path-button {
  border: none;
  border-radius: 0;
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  font-weight: 600;
  padding: 0 20px;
  transition: all 0.3s ease;
  border-left: 1px solid var(--ant-color-border-secondary);
}

.path-button:hover {
  background: var(--ant-color-primary);
  color: white;
  transform: none;
}

/* 表单项间距 */
.config-form :deep(.ant-form-item) {
  margin-bottom: 24px;
}

.config-form :deep(.ant-form-item-label) {
  padding-bottom: 8px;
}

.config-form :deep(.ant-form-item-label > label) {
  font-weight: 600;
  color: var(--ant-color-text);
}

/* 深色模式适配 */
@media (prefers-color-scheme: dark) {
  .config-card {
    box-shadow:
      0 4px 20px rgba(0, 0, 0, 0.3),
      0 1px 3px rgba(0, 0, 0, 0.4);
  }

  .path-input-group:focus-within {
    box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.2);
  }

  .modern-input:focus,
  .modern-input.ant-input-focused {
    box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.2);
  }

  .modern-select.ant-select-focused :deep(.ant-select-selector) {
    box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.2) !important;
  }

  .modern-number-input :deep(.ant-input-number-focused) {
    box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.2);
  }
}

/* 响应式设计 */
@media (max-width: 1200px) {
  .config-card :deep(.ant-card-body) {
    padding: 24px;
  }

  .form-section {
    margin-bottom: 12px;
  }
}

@media (max-width: 768px) {
  .script-edit-header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }

  .config-card :deep(.ant-card-head) {
    padding: 16px 20px;
  }

  .config-card :deep(.ant-card-head-title) {
    font-size: 20px;
  }

  .config-card :deep(.ant-card-body) {
    padding: 20px;
  }

  .section-header h3 {
    font-size: 18px;
  }

  .form-section {
    margin-bottom: 12px;
  }

  .path-button {
    padding: 0 16px;
    font-size: 14px;
  }

  .cancel-button,
  .save-button {
    height: 44px;
    font-size: 14px;
    padding: 0 20px;
  }
}

/* 动画效果 */
@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.form-section {
  animation: fadeInUp 0.6s ease-out;
}

.form-section:nth-child(2) {
  animation-delay: 0.1s;
}

.form-section:nth-child(3) {
  animation-delay: 0.2s;
}

.form-section:nth-child(4) {
  animation-delay: 0.3s;
}

/* Tooltip样式优化 */
:deep(.ant-tooltip-inner) {
  background: var(--ant-color-bg-elevated);
  color: var(--ant-color-text);
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  padding: 12px 16px;
  font-size: 13px;
  line-height: 1.5;
  max-width: 300px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

:deep(.ant-tooltip-arrow::before) {
  background: var(--ant-color-bg-elevated);
  border: 1px solid var(--ant-color-border);
}

.float-button {
  width: 60px;
  height: 60px;
}
</style>
