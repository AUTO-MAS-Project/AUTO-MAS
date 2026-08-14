<template>
  <div class="script-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts" class="breadcrumb-link"> 脚本管理</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <div class="breadcrumb-current">
            <img src="@/assets/AUTO-MAS.ico" alt="AUTO-MAS" class="breadcrumb-logo" />
            编辑脚本
          </div>
        </a-breadcrumb-item>
      </a-breadcrumb>
    </div>

    <a-space size="middle">
      <a-button size="large" type="primary" class="upload-button" @click="showUploadModal">
        <template #icon>
          <CloudUploadOutlined />
        </template>
        分享当前配置到配置分享站
      </a-button>
      <a-button size="large" class="cancel-button" @click="handleCancel">
        <template #icon>
          <ArrowLeftOutlined />
        </template>
        返回
      </a-button>
    </a-space>
  </div>

  <div class="script-edit-content">
    <a-card title="通用脚本配置" :loading="pageLoading" class="config-card">
      <template #extra>
        <a-tag color="green" class="type-tag"> General </a-tag>
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
                  @blur="handleChange('Info', 'Name', formData.name)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="16">
              <a-form-item name="rootPath" :rules="rules.rootPath">
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
                    v-model:value="formData.rootPath"
                    placeholder="请选择脚本根目录"
                    size="large"
                    class="path-input"
                    readonly
                  />
                  <a-button size="large" class="path-button" @click="selectRootPath">
                    <template #icon>
                      <FolderOpenOutlined />
                    </template>
                    选择文件夹
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <!-- 基础配置 -->
        <div class="form-section">
          <div class="section-header">
            <h3>脚本配置</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item name="scriptPath" :rules="rules.scriptPath">
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
                    v-model:value="formData.scriptPath"
                    placeholder="请选择脚本主程序文件"
                    size="large"
                    class="path-input"
                    readonly
                  />
                  <a-button size="large" class="path-button" @click="selectScriptPath">
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
                  @blur="handleChange('Script', 'Arguments', generalConfig.Script.Arguments)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <a-tooltip title="开启后仅在脚本的子进程结束时认定脚本进程结束">
                    <span class="form-label">
                      追踪子进程
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="generalConfig.Script.IfTrackProcess"
                  size="large"
                  @change="handleChange('Script', 'IfTrackProcess', $event)"
                >
                  <a-select-option :value="true">是</a-select-option>
                  <a-select-option :value="false">否</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
          </a-row>
          <!-- 追踪子进程配置 -->
          <a-row v-if="generalConfig.Script.IfTrackProcess" :gutter="24">
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <a-tooltip
                    title="要追踪的进程名称，打开脚本后启动任务管理器，在目标脚本进程右键，选择转到详细信息，填入名称栏中的内容即可，无法确认时可以留空"
                  >
                    <span class="form-label">
                      被追踪进程的名称
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input
                  v-model:value="generalConfig.Script.TrackProcessName"
                  placeholder="请输入要追踪的进程名称"
                  size="large"
                  class="modern-input"
                  @blur="
                    handleChange(
                      'Script',
                      'TrackProcessName',
                      generalConfig.Script.TrackProcessName
                    )
                  "
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <a-tooltip
                    title="要追踪的进程可执行文件路径，打开脚本后启动任务管理器，在目标脚本进程右键，选择「打开文件所在位置」，即可定位到可执行文件路径，无法确认时可以留空"
                  >
                    <span class="form-label">
                      被追踪进程的文件路径
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="generalConfig.Script.TrackProcessExe"
                    placeholder="请选择进程可执行文件路径"
                    size="large"
                    class="path-input"
                    readonly
                  />
                  <a-button size="large" class="path-button" @click="selectTrackProcessExe">
                    <template #icon>
                      <FileOutlined />
                    </template>
                    选择文件
                  </a-button>
                  <a-button
                    size="large"
                    class="path-clear-icon-btn"
                    aria-label="清空路径"
                    @click="clearTrackProcessExe"
                  >
                    <template #icon>
                      <DeleteOutlined />
                    </template>
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <a-tooltip
                    title="要追踪的进程启动命令行参数，打开脚本后启动任务管理器，在目标脚本进程右键，选择「转到详细信息」，填入命令行栏中的内容即可，命令行栏不存在可以在标题栏右键，选择「选择列」，勾选命令行，无法确认时可以留空"
                  >
                    <span class="form-label">
                      追踪进程命令行参数
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input
                  v-model:value="generalConfig.Script.TrackProcessCmdline"
                  placeholder="请输入进程启动命令行参数"
                  size="large"
                  class="modern-input"
                  @blur="
                    handleChange(
                      'Script',
                      'TrackProcessCmdline',
                      generalConfig.Script.TrackProcessCmdline
                    )
                  "
                />
              </a-form-item>
            </a-col>
          </a-row>
          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item name="configPath" :rules="rules.configPath">
                <template #label>
                  <a-tooltip
                    :title="
                      generalConfig.Script.ConfigPathMode === 'Folder'
                        ? '脚本配置文件所在的文件夹路径'
                        : '脚本配置文件的路径'
                    "
                  >
                    <span class="form-label">
                      配置文件路径
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="formData.configPath"
                    :placeholder="
                      generalConfig.Script.ConfigPathMode === 'Folder'
                        ? '请选择配置文件夹'
                        : '请选择配置文件'
                    "
                    size="large"
                    class="path-input"
                    readonly
                  />
                  <a-button size="large" class="path-button" @click="selectConfigPath">
                    <template #icon>
                      <FolderOpenOutlined v-if="generalConfig.Script.ConfigPathMode === 'Folder'" />
                      <FileOutlined v-else />
                    </template>
                    {{
                      generalConfig.Script.ConfigPathMode === 'Folder' ? '选择文件夹' : '选择文件'
                    }}
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
                <a-select
                  v-model:value="generalConfig.Script.ConfigPathMode"
                  size="large"
                  @change="handleChange('Script', 'ConfigPathMode', $event)"
                >
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
                <a-select
                  v-model:value="generalConfig.Script.UpdateConfigMode"
                  size="large"
                  @change="handleChange('Script', 'UpdateConfigMode', $event)"
                >
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
              <a-form-item name="logPath" :rules="rules.logPath">
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
                    v-model:value="formData.logPath"
                    placeholder="请选择日志文件"
                    size="large"
                    class="path-input"
                    readonly
                  />
                  <a-button size="large" class="path-button" @click="selectLogPath">
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
                  <span class="form-label">
                    日志文件名格式
                    <a-tooltip
                      title="指示实时生成日志文件名的格式（strptime 格式），文件名固定时留空"
                    >
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                    <a-tooltip
                      title="针对 mxu 按日期+自增序号命名的日志：末尾加 ****** 启用mxu日志前缀匹配（如 %Y-%m-%d******）"
                    >
                      <QuestionCircleOutlined class="help-icon" style="margin-left: 2px" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input
                  v-model:value="generalConfig.Script.LogPathFormat"
                  placeholder="日志文件名格式，文件名固定时留空"
                  size="large"
                  class="modern-input"
                  @blur="
                    handleChange('Script', 'LogPathFormat', generalConfig.Script.LogPathFormat)
                  "
                />
              </a-form-item>
            </a-col>
          </a-row>

          <a-row :gutter="24">
            <a-col :span="12">
              <LogTimestampSelector
                :form-data="formData"
                :log-file-path="formData.logPath"
                :handle-change="handleChange"
                :rules="rules"
              />
            </a-col>
            <a-col :span="12">
              <a-form-item name="logTimeFormat" :rules="rules.logTimeFormat">
                <template #label>
                  <a-tooltip title="脚本日志文件中时间戳的格式">
                    <span class="form-label">
                      日志时间戳格式
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input
                  v-model:value="formData.logTimeFormat"
                  placeholder="请输入脚本日志时间戳格式"
                  size="large"
                  class="modern-input"
                  @blur="handleChange('Script', 'LogTimeFormat', formData.logTimeFormat)"
                />
                <div class="format-preview">
                  示例：<span class="format-preview-value">{{ logTimeFormatPreview }}</span>
                </div>
                <div v-if="hasFractionalSecondToken" class="format-preview-tip">
                  提示：%f 同时支持 3 位毫秒（如 123）和 6 位微秒（如
                  123456），会按日志中的位数自动识别。
                </div>
              </a-form-item>
            </a-col>
          </a-row>

          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <a-tooltip
                    title="若填写，且日志文本信息中任意任务成功日志先于任务异常日志出现，则视为任务成功，否则若脚本进程结束时，日志文本信息中不存在任何任务成功日志，则视为任务失败；若留空，且在脚本进程结束时，日志文本信息中不存在任意任务异常日志，则视为任务成功"
                  >
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
                  @blur="handleChange('Script', 'SuccessLog', generalConfig.Script.SuccessLog)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item name="errorLog" :rules="rules.errorLog">
                <template #label>
                  <a-tooltip title="若任务异常日志先于任务成功日志出现，则视为任务失败">
                    <span class="form-label">
                      任务失败日志
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input
                  v-model:value="formData.errorLog"
                  placeholder="请输入脚本失败日志，以「 | 」进行分割"
                  size="large"
                  class="modern-input"
                  @blur="handleChange('Script', 'ErrorLog', formData.errorLog)"
                />
              </a-form-item>
            </a-col>
          </a-row>

          <div class="section-header push-config-header">
            <h3>
              推送配置
              <a-tooltip
                title="开启后会按下列规则从脚本日志中采集任务进程信息，追加到推送报告中。支持三种提取模式：字符串切割（关键字掐头去尾）、表达式（匹配+提取）、多行聚合（跨行窗口+提取拼接）。可添加多条规则，每条规则独立执行。"
              >
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </h3>
            <div class="push-config-actions">
              <a-tooltip
                title="开启后才会按下列规则采集任务进程信息追加到推送报告；关闭时配置仍保留，但不进行采集"
              >
                <a-switch
                  v-model:checked="generalConfig.Script.PushLogEnabled"
                  class="push-log-switch"
                  :checked-children="'启用'"
                  :un-checked-children="'停用'"
                  @change="handleChange('Script', 'PushLogEnabled', $event)"
                />
              </a-tooltip>
            </div>
          </div>

          <div class="push-config-body">
            <div v-for="(item, idx) in pushLogPatterns" :key="idx" class="pattern-rule">
              <!-- 规则标识行 -->
              <div class="pattern-rule-bar">
                <a-select
                  v-model:value="item.type"
                  class="pattern-type-select"
                  size="large"
                  @change="onTypeChange(idx)"
                >
                  <a-select-option value="split">字符串切割</a-select-option>
                  <a-select-option value="regex">表达式</a-select-option>
                  <a-select-option value="multiline">多行聚合</a-select-option>
                </a-select>
                <a-tooltip :title="getPatternHint(item.type)">
                  <QuestionCircleOutlined class="pattern-rule-tip" />
                </a-tooltip>
                <div class="pattern-rule-ops">
                  <a-tooltip title="调试">
                    <span class="pattern-op-debug" @click="openDebugDialog(idx)">
                      <BugOutlined />
                      调试
                    </span>
                  </a-tooltip>
                  <a-tooltip title="删除">
                    <DeleteOutlined
                      class="pattern-op-icon pattern-op-del"
                      @click="removePattern(idx)"
                    />
                  </a-tooltip>
                </div>
              </div>

              <!-- 字符串切割 -->
              <a-row v-if="item.type === 'split'" :gutter="16">
                <a-col :span="24">
                  <a-form-item>
                    <template #label>
                      <a-tooltip
                        title="必填，留空则该规则不生效；多个关键字以「 | 」分隔，任一命中即通过"
                      >
                        <span class="form-label">
                          匹配关键字
                          <QuestionCircleOutlined class="help-icon" />
                          <span class="doc-link" @click.stop="openDocsModal('split')">
                            <BookOutlined />
                            说明文档
                          </span>
                        </span>
                      </a-tooltip>
                    </template>
                    <a-input
                      v-model:value="item.match"
                      placeholder="例如：任务完成|成功|失败"
                      size="large"
                      class="modern-input"
                      @blur="onPatternChange()"
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item class="split-item">
                    <template #label>
                      <a-tooltip
                        title="从行首截取到关键字处；勾选「包含」则连同关键字一起去除，不勾选则保留关键字"
                      >
                        <span class="form-label">
                          掐头关键字
                          <QuestionCircleOutlined class="help-icon" />
                        </span>
                      </a-tooltip>
                    </template>
                    <div class="split-input-row">
                      <a-input
                        v-model:value="item.head"
                        placeholder="留空不掐头"
                        size="large"
                        class="modern-input"
                        @blur="onPatternChange()"
                      />
                      <a-checkbox v-model:checked="item.headInclude" @change="onPatternChange()">
                        包含
                      </a-checkbox>
                    </div>
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item class="split-item">
                    <template #label>
                      <a-tooltip
                        title="从关键字处截取到行尾；勾选「包含」则连同关键字一起去除，不勾选则保留关键字"
                      >
                        <span class="form-label">
                          去尾关键字
                          <QuestionCircleOutlined class="help-icon" />
                        </span>
                      </a-tooltip>
                    </template>
                    <div class="split-input-row">
                      <a-input
                        v-model:value="item.tail"
                        placeholder="留空不去尾"
                        size="large"
                        class="modern-input"
                        @blur="onPatternChange()"
                      />
                      <a-checkbox v-model:checked="item.tailInclude" @change="onPatternChange()">
                        包含
                      </a-checkbox>
                    </div>
                  </a-form-item>
                </a-col>
              </a-row>

              <!-- 正则 -->
              <a-row v-else-if="item.type === 'regex'" :gutter="16">
                <a-col :span="24">
                  <a-form-item>
                    <template #label>
                      <a-tooltip title="必填，留空则该规则不生效；用于过滤行的正则表达式">
                        <span class="form-label">
                          匹配正则
                          <QuestionCircleOutlined class="help-icon" />
                          <span class="doc-link" @click.stop="openDocsModal('regex')">
                            <BookOutlined />
                            说明文档
                          </span>
                        </span>
                      </a-tooltip>
                    </template>
                    <a-input
                      v-model:value="item.match"
                      placeholder="例如：任务执行"
                      size="large"
                      class="modern-input"
                      @blur="onPatternChange()"
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="24">
                  <a-form-item>
                    <template #label>
                      <a-tooltip
                        title='使用 $() 包裹正则提取内容，支持 +（同行拼接）、;（换行拼接）、""（字面量）和函数链；留空则返回整行'
                      >
                        <span class="form-label">
                          提取表达式
                          <QuestionCircleOutlined class="help-icon" />
                          <span class="doc-link" @click.stop="openDocsModal('expression')">
                            <BookOutlined />
                            说明文档
                          </span>
                        </span>
                      </a-tooltip>
                    </template>
                    <a-input
                      v-model:value="item.extract"
                      placeholder="例如：$(任务执行: (\S+))"
                      size="large"
                      class="modern-input"
                      @blur="onPatternChange()"
                    />
                  </a-form-item>
                </a-col>
              </a-row>

              <!-- 多行聚合 -->
              <a-row v-else :gutter="16">
                <a-col :span="12">
                  <a-form-item>
                    <template #label>
                      <a-tooltip
                        title="必填，留空则该规则不生效；匹配到此正则的行作为窗口起始（含该行）"
                      >
                        <span class="form-label">
                          起始正则
                          <QuestionCircleOutlined class="help-icon" />
                        </span>
                      </a-tooltip>
                    </template>
                    <a-input
                      v-model:value="item.start"
                      placeholder="例如：一条龙任务执行"
                      size="large"
                      class="modern-input"
                      @blur="onPatternChange()"
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item>
                    <template #label>
                      <a-tooltip title="匹配到此正则的行作为窗口结束（含该行）；留空则不限定结束">
                        <span class="form-label">
                          结束正则
                          <QuestionCircleOutlined class="help-icon" />
                        </span>
                      </a-tooltip>
                    </template>
                    <a-input
                      v-model:value="item.end"
                      placeholder="例如：任务结束"
                      size="large"
                      class="modern-input"
                      @blur="onPatternChange()"
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="24">
                  <a-form-item>
                    <template #label>
                      <a-tooltip
                        title='提取表达式使用 $() 包裹正则，支持 +（同行拼接）、;（换行拼接）、""（字面量）和函数链（.replace/.cut/.sub/.trim）；留空则返回窗口原文'
                      >
                        <span class="form-label">
                          提取表达式
                          <QuestionCircleOutlined class="help-icon" />
                        </span>
                      </a-tooltip>
                    </template>
                    <a-input
                      v-model:value="item.extract"
                      placeholder='例如：$((一条龙任务执行: \d+/\d+))+" -> "+$((邮件：[^\n]+))|$((任务结束))'
                      size="large"
                      class="modern-input"
                      @blur="onPatternChange()"
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="24">
                  <a-form-item>
                    <template #label>
                      <a-tooltip
                        title="窗口最多收集的行数，达到上限时强制关闭窗口；防止意外匹配过多行"
                      >
                        <span class="form-label">
                          最大跨行数
                          <QuestionCircleOutlined class="help-icon" />
                          <span class="doc-link" @click.stop="openDocsModal('multiline')">
                            <BookOutlined />
                            说明文档
                          </span>
                        </span>
                      </a-tooltip>
                    </template>
                    <a-input-number
                      v-model:value="item.maxLines"
                      :min="2"
                      :max="500"
                      :step="10"
                      size="large"
                      style="width: 200px"
                      @change="onPatternChange()"
                    />
                  </a-form-item>
                </a-col>
              </a-row>
            </div>

            <!-- 底部添加行：始终在最下方 -->
            <a-dropdown trigger="click" placement="topLeft" class="pattern-add-dropdown">
              <div class="pattern-add-row">
                <PlusOutlined />
                <span>添加采集规则</span>
              </div>
              <template #overlay>
                <a-menu @click="handleAddPattern">
                  <a-menu-item key="split">
                    <template #icon>
                      <ScissorOutlined />
                    </template>
                    添加字符串切割
                  </a-menu-item>
                  <a-menu-item key="regex">
                    <template #icon>
                      <CodeOutlined />
                    </template>
                    添加表达式
                  </a-menu-item>
                  <a-menu-item key="multiline">
                    <template #icon>
                      <BlockOutlined />
                    </template>
                    添加多行聚合
                  </a-menu-item>
                </a-menu>
              </template>
            </a-dropdown>
          </div>

          <div class="section-header">
            <h3>游戏配置</h3>
          </div>

          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <a-tooltip title="是否由AUTO-MAS管理游戏/模拟器进程">
                    <span class="form-label">
                      启用游戏相关功能
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="generalConfig.Game.Enabled"
                  size="large"
                  @change="handleChange('Game', 'Enabled', $event)"
                >
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
                      启动方式
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="generalConfig.Game.Type"
                  size="large"
                  @change="handleGameTypeChange"
                >
                  <a-select-option value="Emulator">模拟器</a-select-option>
                  <a-select-option value="Client">PC客户端</a-select-option>
                  <a-select-option value="URL">URL协议(如Starward)</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <!-- PC客户端相关字段 -->
            <a-col v-if="generalConfig.Game.Type === 'Client'" :span="8">
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
                  <a-button size="large" class="path-button" @click="selectGamePath">
                    <template #icon>
                      <FileOutlined />
                    </template>
                    选择文件
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
            <!-- 模拟器相关字段 -->
            <a-col v-if="generalConfig.Game.Type === 'Emulator'" :span="8">
              <a-form-item>
                <template #label>
                  <a-tooltip title="选择要使用的模拟器">
                    <span class="form-label">
                      模拟器
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="generalConfig.Game.EmulatorId"
                  size="large"
                  placeholder="请选择模拟器"
                  :loading="emulatorLoading"
                  @change="handleEmulatorChange"
                >
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

            <a-col v-if="generalConfig.Game.Type === 'URL'" :span="8">
              <a-form-item>
                <template #label>
                  <a-tooltip title="自定义协议的URL">
                    <span class="form-label">
                      URL地址
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-group class="path-input-group">
                  <a-input
                    v-model:value="generalConfig.Game.URL"
                    placeholder="请输入URL参数，如：starward://startgame/xxxx"
                    size="large"
                    @blur="handleChange('Game', 'URL', generalConfig.Game.URL)"
                  />
                </a-input-group>
              </a-form-item>
            </a-col>

            <a-col v-if="generalConfig.Game.Type === 'Emulator'" :span="8">
              <a-form-item>
                <template #label>
                  <a-tooltip
                    :title="
                      emulatorDeviceOptions.length === 0 && !emulatorDeviceLoading
                        ? '不支持自动扫描实例的模拟器，请手动输入实例信息'
                        : '选择模拟器的具体实例'
                    "
                  >
                    <span class="form-label">
                      模拟器实例
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <!-- 当API返回空列表时显示输入框 -->
                <a-input
                  v-if="
                    emulatorDeviceOptions.length === 0 &&
                    !emulatorDeviceLoading &&
                    generalConfig.Game.EmulatorId
                  "
                  v-model:value="generalConfig.Game.EmulatorIndex"
                  size="large"
                  placeholder="请输入实例信息，格式：启动附加命令 | ADB地址"
                  class="modern-input"
                  @blur="handleChange('Game', 'EmulatorIndex', generalConfig.Game.EmulatorIndex)"
                />
                <!-- 正常情况下显示下拉框 -->
                <a-select
                  v-else
                  v-model:value="generalConfig.Game.EmulatorIndex"
                  size="large"
                  placeholder="请先选择模拟器"
                  :loading="emulatorDeviceLoading"
                  :disabled="!generalConfig.Game.EmulatorId"
                  @change="handleChange('Game', 'EmulatorIndex', $event)"
                >
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

          <!-- PC客户端独有的配置 -->
          <a-row v-if="generalConfig.Game.Type === 'Client'" :gutter="24">
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
                  @blur="handleChange('Game', 'Arguments', generalConfig.Game.Arguments)"
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
                  :max="9999"
                  size="large"
                  class="modern-number-input"
                  style="width: 100%"
                  @blur="handleChange('Game', 'WaitTime', generalConfig.Game.WaitTime)"
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
                <a-select
                  v-model:value="generalConfig.Game.IfForceClose"
                  size="large"
                  @change="handleChange('Game', 'IfForceClose', $event)"
                >
                  <a-select-option :value="true">是</a-select-option>
                  <a-select-option :value="false">否</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <!-- 自定义协议独有的选项 -->
        <a-row v-if="generalConfig.Game.Type === 'URL'" :gutter="24">
          <a-col :span="8">
            <a-form-item>
              <template #label>
                <a-tooltip
                  title="进程名称，如StarRail.exe，必须填写否则可能无法正确监测进程状态。开启游戏后，打开任务管理器查看程序详细信息即可获得。"
                >
                  <span class="form-label">
                    进程名称
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-input
                v-model:value="generalConfig.Game.ProcessName"
                placeholder="比如 StarRail.exe"
                size="large"
                class="modern-input"
                @blur="handleChange('Game', 'ProcessName', generalConfig.Game.ProcessName)"
              />
            </a-form-item>
          </a-col>
        </a-row>
        <!-- 运行配置 -->
        <div class="form-section">
          <div class="section-header">
            <h3>运行配置</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <a-tooltip
                    title="当用户本日代理成功次数达到该阀值时跳过代理，阈值为「0」时视为无代理次数上限"
                  >
                    <span class="form-label">
                      单日代理次数上限
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-number
                  v-model:value="generalConfig.Run.ProxyTimesLimit"
                  :min="0"
                  :max="9999"
                  size="large"
                  class="modern-number-input"
                  style="width: 100%"
                  @blur="handleChange('Run', 'ProxyTimesLimit', generalConfig.Run.ProxyTimesLimit)"
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
                  :max="9999"
                  size="large"
                  class="modern-number-input"
                  style="width: 100%"
                  @blur="handleChange('Run', 'RunTimesLimit', generalConfig.Run.RunTimesLimit)"
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
                  :max="9999"
                  size="large"
                  class="modern-number-input"
                  style="width: 100%"
                  @blur="handleChange('Run', 'RunTimeLimit', generalConfig.Run.RunTimeLimit)"
                />
              </a-form-item>
            </a-col>
          </a-row>
        </div>
      </a-form>
    </a-card>
  </div>

  <!-- 上传脚本弹窗 -->
  <a-modal
    v-model:open="uploadModalVisible"
    title="上传脚本配置到云端"
    :confirm-loading="uploadLoading"
    width="600px"
    :mask-closable="false"
    @ok="handleUpload"
    @cancel="handleUploadCancel"
  >
    <a-form
      ref="uploadFormRef"
      :model="uploadForm"
      :rules="uploadRules"
      layout="vertical"
      class="upload-form"
    >
      <a-form-item name="config_name" label="配置名称">
        <a-input
          v-model:value="uploadForm.config_name"
          placeholder="为您的脚本配置起一个易于识别的名称"
          size="large"
          :maxlength="50"
          show-count
          class="modern-input"
        />
      </a-form-item>

      <a-form-item name="author" label="作者">
        <a-input
          v-model:value="uploadForm.author"
          placeholder="请输入作者名称"
          size="large"
          :maxlength="30"
          show-count
          class="modern-input"
        />
      </a-form-item>

      <a-form-item name="description" label="描述">
        <a-textarea
          v-model:value="uploadForm.description"
          placeholder="请简要描述该脚本配置的功能、适用场景等信息"
          size="large"
          :rows="4"
          :maxlength="200"
          show-count
          class="modern-textarea"
        />
      </a-form-item>

      <a-alert message="分享说明" type="info">
        <template #description>
          <p>
            所有<span style="font-weight: bold"> 敏感信息 </span
            >均会在上传前自动移除，上传内容仅包含脚本配置的非敏感信息。上传且通过审核后，其他用户可以下载并使用您的脚本配置。请确保配置信息准确且描述清晰。
          </p>
        </template>
      </a-alert>
    </a-form>
  </a-modal>

  <LogPatternDocsModal v-model:open="logDocsOpen" v-model:active-key="logDocsActiveKey" />

  <!-- 规则调试弹窗 -->
  <a-modal
    v-model:open="debugModalOpen"
    title="规则调试"
    width="680px"
    :footer="null"
    :destroy-on-close="true"
  >
    <template #title>
      <span class="modal-title">
        <BugOutlined />
        规则调试
      </span>
    </template>
    <div class="debug-modal-body">
      <div class="debug-config-preview">
        <span class="debug-config-label">当前规则：</span>
        <code class="debug-config-code">{{ debugConfigPreview }}</code>
      </div>
      <div class="debug-input-section">
        <div class="debug-section-label">
          <span>粘贴日志（每行一条，支持多行批量调试）</span>
          <span class="debug-load-row">
            <a-button
              type="primary"
              size="small"
              :loading="debugLoadingLog"
              :disabled="!generalConfig.Script.LogPath || generalConfig.Script.LogPath === '.'"
              @click="loadDebugLog"
            >
              加载日志
            </a-button>
            <a-input-number
              v-model:value="debugLogLines"
              size="small"
              :min="-1"
              :step="100"
              style="width: 90px"
            />
            <span class="debug-load-hint">行</span>
          </span>
        </div>
        <a-textarea
          v-model:value="debugInput"
          :rows="6"
          placeholder="粘贴要测试的日志行，每行一条..."
          class="debug-textarea"
        />
      </div>
      <div class="debug-actions">
        <a-button
          type="primary"
          size="small"
          :loading="debugRunning"
          :disabled="!debugInput.trim()"
          @click="runDebug"
        >
          <template #icon>
            <BugOutlined />
          </template>
          调试
        </a-button>
        <a-button size="small" @click="clearDebug">清空</a-button>
      </div>
      <a-alert
        v-if="debugCompileError"
        type="error"
        show-icon
        class="debug-compile-error"
        :message="debugCompileError"
        closable
        @close="debugCompileError = null"
      />
      <div v-if="debugResults.length > 0" class="debug-results">
        <div class="debug-results-header">
          <span class="debug-section-label"
            >结果（{{ debugHitCount }}/{{ debugResults.length }}）</span
          >
          <a-checkbox v-model:checked="debugOnlyHit" size="small">仅显示已命中</a-checkbox>
        </div>
        <div class="debug-results-list">
          <div
            v-for="item in filteredDebugResults"
            :key="item.idx"
            :class="['debug-result-item', item.hit ? 'hit' : 'miss']"
          >
            <div class="debug-result-line">
              <span class="debug-result-line-num">{{ item.idx + 1 }}</span>
              <span class="debug-result-line-text">{{
                debugIsMultiline ? `窗口 ${item.idx + 1}` : item.line
              }}</span>
            </div>
            <div class="debug-result-out">
              <a-tag v-if="item.hit" color="green" class="debug-result-tag">命中</a-tag>
              <a-tag v-else color="default" class="debug-result-tag">未命中</a-tag>
              <span v-if="item.hit" class="debug-result-extracted">{{ item.extracted }}</span>
              <span v-else-if="item.error" class="debug-result-error">{{ item.error }}</span>
            </div>
          </div>
          <div v-if="filteredDebugResults.length === 0" class="debug-results-empty">无命中行</div>
        </div>
      </div>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { FormInstance } from 'ant-design-vue'
import { message } from 'ant-design-vue'
import type { GeneralScriptConfig, ScriptType } from '@/types/script.ts'
import { useEmulatorDeviceOptions } from '@/composables/useEmulatorDeviceOptions.ts'
import { useScriptApi } from '@/composables/useScriptApi.ts'
import { Service, type ComboBoxItem } from '@/api'
import type { ScriptUploadIn } from '@/api'
import {
  ArrowLeftOutlined,
  BlockOutlined,
  BookOutlined,
  BugOutlined,
  CloudUploadOutlined,
  CodeOutlined,
  DeleteOutlined,
  FileOutlined,
  FolderOpenOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
  ScissorOutlined,
} from '@ant-design/icons-vue'
import LogTimestampSelector from '@/components/LogTimestampSelector.vue'
import LogPatternDocsModal from './LogPatternDocsModal.vue'
import axios from 'axios'
import { OpenAPI } from '@/api'

// ==================== 调试类型 ====================
type PatternType = 'split' | 'regex' | 'multiline'

interface DebugPatternConfig {
  type: PatternType
  match?: string
  head?: string
  headInclude?: boolean
  tail?: string
  tailInclude?: boolean
  extract?: string
  start?: string
  end?: string
  maxLines?: number
}

interface DebugResult {
  idx: number
  hit: boolean
  extracted: string
  line: string
  error?: string | null
}

const logger = window.electronAPI.getLogger('通用脚本编辑')

const route = useRoute()
const router = useRouter()
const { getScript, updateScript } = useScriptApi()

const formRef = ref<FormInstance>()
const uploadFormRef = ref<FormInstance>()
const isInitializing = ref(true) // 标记是否正在初始化
const isSaving = ref(false) // 标记是否正在保存

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
  },
}

// AppData 路径
const appDataPath = ref('')

// 路径验证函数
const validatePath = (rootPath: string, targetPath: string, pathName: string): boolean => {
  if (!targetPath || targetPath === '.') return true
  if (!rootPath || rootPath === '.') {
    message.warning(`请先设置脚本根目录后再选择${pathName}`)
    return false
  }

  // 检查是否在根目录下
  const isUnderRoot = pathUtils.isSubPath(rootPath, targetPath)

  // 检查是否在 AppData 下
  let isUnderAppData = false
  if (appDataPath.value) {
    isUnderAppData = pathUtils.isSubPath(appDataPath.value, targetPath)
  }

  if (!isUnderRoot && !isUnderAppData) {
    message.error(`${pathName}必须是脚本根目录或 AppData 目录的子路径`)
    return false
  }

  return true
}

// 存储路径的相对关系，用于根目录变化时自动调整
const pathRelations = reactive({
  scriptPathRelative: '',
  configPathRelative: '',
  logPathRelative: '',
  trackProcessExeRelative: '',
})

// 更新相对路径关系
const updatePathRelations = () => {
  const rootPath = generalConfig.Info.RootPath
  if (!rootPath || rootPath === '.') {
    pathRelations.scriptPathRelative = ''
    pathRelations.configPathRelative = ''
    pathRelations.logPathRelative = ''
    pathRelations.trackProcessExeRelative = ''
    return
  }

  if (generalConfig.Script.ScriptPath && generalConfig.Script.ScriptPath !== '.') {
    pathRelations.scriptPathRelative = pathUtils.getRelativePath(
      rootPath,
      generalConfig.Script.ScriptPath
    )
  }

  if (generalConfig.Script.ConfigPath && generalConfig.Script.ConfigPath !== '.') {
    pathRelations.configPathRelative = pathUtils.getRelativePath(
      rootPath,
      generalConfig.Script.ConfigPath
    )
  }

  if (generalConfig.Script.LogPath && generalConfig.Script.LogPath !== '.') {
    pathRelations.logPathRelative = pathUtils.getRelativePath(
      rootPath,
      generalConfig.Script.LogPath
    )
  }

  if (generalConfig.Script.TrackProcessExe && generalConfig.Script.TrackProcessExe !== '.') {
    pathRelations.trackProcessExeRelative = pathUtils.getRelativePath(
      rootPath,
      generalConfig.Script.TrackProcessExe
    )
  }
}

// 根据新的根目录更新所有路径
// 注意：只更新原本就是根目录子目录的路径，不更新 AppData 等外部目录下的路径
const updatePathsBasedOnRoot = (newRootPath: string) => {
  if (!newRootPath || newRootPath === '.') return

  // 检查相对路径是否表示在根目录内部（不以 .. 开头）
  const isInternalPath = (relativePath: string): boolean => {
    if (!relativePath || relativePath === '.') return false
    // 如果相对路径以 .. 开头，说明该路径不在根目录下
    return !relativePath.startsWith('..')
  }

  // 根据保存的相对路径关系重新计算绝对路径
  // 只有当路径确实在原根目录内部时才更新
  if (pathRelations.scriptPathRelative && isInternalPath(pathRelations.scriptPathRelative)) {
    const newScriptPath = pathUtils.resolvePath(newRootPath, pathRelations.scriptPathRelative)
    const normalizedScriptPath = pathUtils.normalizePath(newScriptPath)
    generalConfig.Script.ScriptPath = normalizedScriptPath
  }

  if (pathRelations.configPathRelative && isInternalPath(pathRelations.configPathRelative)) {
    const newConfigPath = pathUtils.resolvePath(newRootPath, pathRelations.configPathRelative)
    const normalizedConfigPath = pathUtils.normalizePath(newConfigPath)
    generalConfig.Script.ConfigPath = normalizedConfigPath
  }

  if (pathRelations.logPathRelative && isInternalPath(pathRelations.logPathRelative)) {
    const newLogPath = pathUtils.resolvePath(newRootPath, pathRelations.logPathRelative)
    const normalizedLogPath = pathUtils.normalizePath(newLogPath)
    generalConfig.Script.LogPath = normalizedLogPath
  }

  if (
    pathRelations.trackProcessExeRelative &&
    isInternalPath(pathRelations.trackProcessExeRelative)
  ) {
    const newTrackProcessExePath = pathUtils.resolvePath(
      newRootPath,
      pathRelations.trackProcessExeRelative
    )
    const normalizedTrackProcessExePath = pathUtils.normalizePath(newTrackProcessExePath)
    generalConfig.Script.TrackProcessExe = normalizedTrackProcessExePath
  }
}
const pageLoading = ref(false)
const scriptId = route.params.id as string
const {
  emulatorDeviceLoading,
  emulatorDeviceOptions,
  clearEmulatorDeviceOptions,
  loadEmulatorDeviceOptions,
} = useEmulatorDeviceOptions()

const formData = reactive({
  name: '',
  type: 'General' as ScriptType,
  get rootPath() {
    return generalConfig.Info.RootPath
  },
  set rootPath(value) {
    generalConfig.Info.RootPath = value
  },
  get scriptPath() {
    return generalConfig.Script.ScriptPath
  },
  set scriptPath(value) {
    generalConfig.Script.ScriptPath = value
  },
  get configPath() {
    return generalConfig.Script.ConfigPath
  },
  set configPath(value) {
    generalConfig.Script.ConfigPath = value
  },
  get logPath() {
    return generalConfig.Script.LogPath
  },
  set logPath(value) {
    generalConfig.Script.LogPath = value
  },
  get logTimeStart() {
    return generalConfig.Script.LogTimeStart
  },
  set logTimeStart(value) {
    generalConfig.Script.LogTimeStart = value
  },
  get logTimeEnd() {
    return generalConfig.Script.LogTimeEnd
  },
  set logTimeEnd(value) {
    generalConfig.Script.LogTimeEnd = value
  },
  get logTimeFormat() {
    return generalConfig.Script.LogTimeFormat
  },
  set logTimeFormat(value) {
    generalConfig.Script.LogTimeFormat = value
  },
  get errorLog() {
    return generalConfig.Script.ErrorLog
  },
  set errorLog(value) {
    generalConfig.Script.ErrorLog = value
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
    EmulatorId: '',
    EmulatorIndex: '',
    URL: '',
    ProcessName: '',
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
    TrackProcessName: '',
    TrackProcessExe: '',
    TrackProcessCmdline: '',
    LogPath: '.',
    LogPathFormat: '%Y-%m-%d',
    LogTimeEnd: 1,
    LogTimeStart: 1,
    LogTimeFormat: '%Y-%m-%d %H:%M:%S',
    ScriptPath: '.',
    SuccessLog: '',
    PushLogEnabled: false,
    PushLogPatterns: '',
    UpdateConfigMode: 'Never',
  },
  SubConfigsInfo: {
    UserData: {
      instances: [],
    },
  },
})

// ==================== 推送日志：采集规则 ====================
type PushLogPatternType = 'split' | 'regex' | 'multiline'
interface PushLogPattern {
  type: PushLogPatternType
  // split
  match?: string
  head?: string
  headInclude?: boolean
  tail?: string
  tailInclude?: boolean
  // regex
  extract?: string
  // multiline
  start?: string
  end?: string
  maxLines?: number
}

// 采集规则编辑列表：与 generalConfig.Script.PushLogPatterns (JSON) 双向同步
const pushLogPatterns = ref<PushLogPattern[]>([])

const normalizePatternType = (raw: unknown): PushLogPatternType => {
  return raw === 'split' ? 'split' : raw === 'multiline' ? 'multiline' : 'regex'
}

const parsePushLogPatterns = (json: string): PushLogPattern[] => {
  if (!json) return []
  try {
    const items = JSON.parse(json)
    if (!Array.isArray(items)) return []
    return items
      .filter((item: any) => item && typeof item === 'object')
      .map((item: any) => {
        const type = normalizePatternType(item.type)
        if (type === 'split') {
          return {
            type: 'split',
            match: typeof item.match === 'string' ? item.match : '',
            head: typeof item.head === 'string' ? item.head : '',
            headInclude: !!item.headInclude,
            tail: typeof item.tail === 'string' ? item.tail : '',
            tailInclude: !!item.tailInclude,
          }
        }
        if (type === 'regex') {
          return {
            type: 'regex',
            match: typeof item.match === 'string' ? item.match : '',
            extract: typeof item.extract === 'string' ? item.extract : '',
          }
        }
        return {
          type: 'multiline',
          start: typeof item.start === 'string' ? item.start : '',
          end: typeof item.end === 'string' ? item.end : '',
          extract: typeof item.extract === 'string' ? item.extract : '',
          maxLines: typeof item.maxLines === 'number' ? item.maxLines : 50,
        }
      })
  } catch {
    return []
  }
}

const syncPushLogPatternsFromConfig = () => {
  const parsed = parsePushLogPatterns(generalConfig.Script.PushLogPatterns || '')
  pushLogPatterns.value =
    parsed.length > 0
      ? parsed
      : [{ type: 'split', match: '', head: '', headInclude: false, tail: '', tailInclude: false }]
}

const savePushLogPatterns = () => {
  const cleaned: PushLogPattern[] = []
  for (const p of pushLogPatterns.value) {
    if (p.type === 'split') {
      const match = (p.match || '').trim()
      const head = (p.head || '').trim()
      const tail = (p.tail || '').trim()
      if (!match && !head && !tail) continue
      cleaned.push({
        type: 'split',
        match,
        head,
        headInclude: !!p.headInclude,
        tail,
        tailInclude: !!p.tailInclude,
      })
    } else if (p.type === 'regex') {
      const match = (p.match || '').trim()
      const extract = (p.extract || '').trim()
      if (!match && !extract) continue
      cleaned.push({ type: 'regex', match, extract })
    } else if (p.type === 'multiline') {
      const start = (p.start || '').trim()
      const end = (p.end || '').trim()
      const extract = (p.extract || '').trim()
      if (!start && !end) continue
      cleaned.push({
        type: 'multiline',
        start,
        end,
        extract,
        maxLines: p.maxLines || 50,
      })
    }
  }
  const json = JSON.stringify(cleaned)
  generalConfig.Script.PushLogPatterns = json
  handleChange('Script', 'PushLogPatterns', json)
}

const handleAddPattern = ({ key }: { key: string }) => {
  if (key === 'split') {
    pushLogPatterns.value.push({
      type: 'split',
      match: '',
      head: '',
      headInclude: false,
      tail: '',
      tailInclude: false,
    })
  } else if (key === 'regex') {
    pushLogPatterns.value.push({ type: 'regex', match: '', extract: '' })
  } else if (key === 'multiline') {
    pushLogPatterns.value.push({
      type: 'multiline',
      start: '',
      end: '',
      extract: '',
      maxLines: 50,
    })
  }
  savePushLogPatterns()
}

// 类型切换：重置为对应类型的默认字段
const onTypeChange = (idx: number) => {
  const item = pushLogPatterns.value[idx]
  if (!item) return
  if (item.type === 'split') {
    pushLogPatterns.value[idx] = {
      type: 'split',
      match: '',
      head: '',
      headInclude: false,
      tail: '',
      tailInclude: false,
    }
  } else if (item.type === 'regex') {
    pushLogPatterns.value[idx] = { type: 'regex', match: '', extract: '' }
  } else if (item.type === 'multiline') {
    pushLogPatterns.value[idx] = {
      type: 'multiline',
      start: '',
      end: '',
      extract: '',
      maxLines: 50,
    }
  }
  savePushLogPatterns()
}

const removePattern = (idx: number) => {
  pushLogPatterns.value.splice(idx, 1)
  savePushLogPatterns()
}

const onPatternChange = () => {
  savePushLogPatterns()
}

const getPatternHint = (type: PushLogPatternType): string => {
  if (type === 'split') {
    return '按关键字过滤行，再掐头去尾提取中间内容。具体用法见：字符串切割文档'
  }
  if (type === 'regex') {
    return '匹配正则过滤行，提取表达式用 $() 提取内容并支持函数链。具体用法见：表达式文档'
  }
  return '由起始/结束正则划定多行窗口，再用提取表达式（$() 语法）提取字段并拼接。具体用法见：多行聚合文档'
}

// 日志提取表达式参考弹窗：内置字符串切割/正则/表达式/多行聚合文档
const logDocsOpen = ref(false)
const logDocsActiveKey = ref<'split' | 'regex' | 'expression' | 'multiline'>('regex')
const openDocsModal = (key: 'split' | 'regex' | 'expression' | 'multiline') => {
  logDocsActiveKey.value = key
  logDocsOpen.value = true
}

// ==================== 规则调试 ====================
const debugModalOpen = ref(false)
const debugInput = ref('')
const debugResults = ref<DebugResult[]>([])
// 配置级错误（正则/表达式语法错误、未知函数）：由后端校验返回
const debugCompileError = ref<string | null>(null)
// 当前调试的规则索引
const debugIdx = ref(-1)
// 多行聚合按窗口产出结果，不与逐行输入对齐
const debugIsMultiline = computed(() => pushLogPatterns.value[debugIdx.value]?.type === 'multiline')
// 加载日志：行数（倒序取最后 N 行，-1 为全部）
const debugLogLines = ref(500)
const debugLoadingLog = ref(false)
// 调试执行中（调用后端 API）
const debugRunning = ref(false)

// 调试弹窗中展示的当前规则预览
const debugConfigPreview = computed(() => {
  const item = pushLogPatterns.value[debugIdx.value]
  if (!item) return ''
  if (item.type === 'split') {
    return `[split] match="${item.match || ''}" head="${item.head || ''}"(含${item.headInclude ? '是' : '否'}) tail="${item.tail || ''}"(含${item.tailInclude ? '是' : '否'})`
  }
  if (item.type === 'regex') {
    return `[regex] match="${item.match || ''}" extract="${item.extract || ''}"`
  }
  return `[multiline] start="${item.start || ''}" end="${item.end || ''}" extract="${item.extract || ''}" maxLines=${item.maxLines || 50}`
})

const openDebugDialog = (idx: number) => {
  debugIdx.value = idx
  debugInput.value = ''
  debugResults.value = []
  debugCompileError.value = null
  debugModalOpen.value = true
}

const runDebug = async () => {
  const item = pushLogPatterns.value[debugIdx.value]
  if (!item) return
  const config: DebugPatternConfig = {
    type: item.type,
    match: item.match,
    head: item.head,
    headInclude: item.headInclude,
    tail: item.tail,
    tailInclude: item.tailInclude,
    extract: item.extract,
    start: item.start,
    end: item.end,
    maxLines: item.maxLines,
  }
  debugRunning.value = true
  debugCompileError.value = null
  try {
    const baseURL = OpenAPI.BASE || ''
    const resp = await axios.post(`${baseURL}/api/setting/debug_pattern`, {
      pattern: config,
      logText: debugInput.value,
    })
    const data = resp.data
    if (data.code !== 200) {
      debugCompileError.value = data.message || '调试请求失败'
      debugResults.value = []
      return
    }
    if (data.configError) {
      debugCompileError.value = data.configError
      debugResults.value = []
      return
    }
    debugResults.value = (data.results || []).map((r: DebugResult) => ({
      idx: r.idx,
      hit: r.hit,
      extracted: r.extracted || '',
      line: r.line || '',
      error: r.error || null,
    }))
  } catch (error) {
    debugCompileError.value = '调试请求失败: ' + (error as Error).message
    debugResults.value = []
  } finally {
    debugRunning.value = false
  }
}

const clearDebug = () => {
  debugInput.value = ''
  debugResults.value = []
  debugCompileError.value = null
}

// 从脚本配置的日志路径加载日志到调试输入框（倒序取最后 N 行）
const loadDebugLog = async () => {
  const logPath = generalConfig.Script.LogPath
  if (!logPath || logPath === '.') {
    message.warning('请先在脚本配置中设置日志文件路径')
    return
  }
  try {
    debugLoadingLog.value = true
    const content = await window.electronAPI.readFile(logPath)
    if (!content) {
      message.warning('日志文件为空或无法读取')
      return
    }
    const allLines = content.split('\n')
    const n = debugLogLines.value
    const lines = n < 0 ? allLines : allLines.slice(Math.max(0, allLines.length - n))
    debugInput.value = lines.join('\n')
    message.success(`已加载 ${lines.length} 行日志（共 ${allLines.length} 行）`)
  } catch (error) {
    logger.error(`加载日志文件失败: ${String(error)}`)
    message.error('加载日志文件失败: ' + (error as Error).message)
  } finally {
    debugLoadingLog.value = false
  }
}

// 仅显示已命中
const debugOnlyHit = ref(false)
const debugHitCount = computed(() => debugResults.value.filter(r => r.hit).length)
const filteredDebugResults = computed(() =>
  debugResults.value.filter(r => !debugOnlyHit.value || r.hit)
)

// 初始化时解析一次（覆盖默认空值场景，loadScript 后会再次同步）
syncPushLogPatternsFromConfig()

const rules = {
  name: [{ required: true, message: '请输入脚本名称', trigger: 'blur' }],
  type: [{ required: true, message: '请选择脚本类型', trigger: 'change' }],
  rootPath: [{ required: true, message: '请选择脚本根目录', trigger: 'blur' }],
  scriptPath: [{ required: true, message: '请选择主程序路径', trigger: 'blur' }],
  configPath: [{ required: true, message: '请选择配置文件路径', trigger: 'blur' }],
  logPath: [{ required: true, message: '请选择日志文件路径', trigger: 'blur' }],
  logTimeStart: [{ required: true, message: '请输入日志时间戳起始位置', trigger: 'blur' }],
  logTimeEnd: [{ required: true, message: '请输入日志时间戳结束位置', trigger: 'blur' }],
  logTimeFormat: [{ required: true, message: '请输入日志时间戳格式', trigger: 'blur' }],
  errorLog: [{ required: true, message: '请输入任务失败日志', trigger: 'blur' }],
}

const logTimeFormatPreview = computed(() => {
  const format = formData.logTimeFormat || ''
  if (!format.trim()) {
    return '请输入日志时间戳格式后查看示例'
  }

  const tokenMap: Record<string, string> = {
    '%Y': '2025',
    '%m': '07',
    '%d': '16',
    '%H': '14',
    '%M': '30',
    '%S': '45',
    '%f': '123456',
    '%A': 'Wednesday',
    '%a': 'Wed',
    '%B': 'July',
    '%b': 'Jul',
  }

  return format
    .replace(/%%/g, '__PERCENT__')
    .replace(/%[YmdHMSfAabB]/g, token => tokenMap[token] ?? token)
    .replace(/__PERCENT__/g, '%')
})

const hasFractionalSecondToken = computed(() => {
  const format = formData.logTimeFormat || ''
  return /(^|[^%])%f/.test(format)
})

// 模拟器相关状态
const emulatorLoading = ref(false)
const emulatorOptions = ref<ComboBoxItem[]>([])

// 延迟注册 ConfigPathMode watcher（在加载脚本并完成初始化后再注册）
// 注意：此 watcher 用于业务逻辑处理（配置文件类型切换时重置路径），而非简单的配置自动保存
let stopConfigPathModeWatcher: (() => void) | null = null

const setupConfigPathModeWatcher = () => {
  // 如果已存在 watcher，先停止
  if (stopConfigPathModeWatcher) {
    stopConfigPathModeWatcher()
    stopConfigPathModeWatcher = null
  }

  // 监听配置文件类型变化，当从"单文件"切换到"文件夹"或反之时，自动重置路径
  // 这是必要的业务逻辑，因为文件路径和文件夹路径不能混用
  stopConfigPathModeWatcher = watch(
    () => generalConfig.Script.ConfigPathMode,
    async (newMode, oldMode) => {
      if (
        newMode !== oldMode &&
        generalConfig.Script.ConfigPath &&
        generalConfig.Script.ConfigPath !== '.'
      ) {
        // 当配置文件类型改变时，重置为根目录路径
        const rootPath = generalConfig.Info.RootPath
        let newConfigPath: string
        if (rootPath && rootPath !== '.') {
          newConfigPath = rootPath
          generalConfig.Script.ConfigPath = rootPath
          const typeText = newMode === 'Folder' ? '文件夹' : '文件'
          message.info(`配置文件类型已切换为${typeText}，路径已重置为根目录`)
        } else {
          // 如果没有设置根目录，则清空路径
          newConfigPath = '.'
          generalConfig.Script.ConfigPath = '.'
          const typeText = newMode === 'Folder' ? '文件夹' : '文件'
          message.info(`配置文件类型已切换为${typeText}，请重新选择路径`)
        }

        // 保存被重置的 ConfigPath（ConfigPathMode 已经通过 @change 保存了）
        // 使用即时保存模式，而非 watch 自动保存
        if (!isInitializing.value && !isSaving.value) {
          isSaving.value = true
          try {
            const updateData = { Script: { ConfigPath: newConfigPath } }
            const success = await updateScript(scriptId, updateData)
            if (success) {
              logger.info('配置路径已重置并保存')
              await refreshScript()
            }
          } catch (error) {
            const errorMsg = error instanceof Error ? error.message : String(error)
            logger.error(`保存配置路径失败: ${errorMsg}`)
          } finally {
            isSaving.value = false
          }
        }
      }
    }
  )
}

// 即时保存函数 - 只发送修改的字段（遵循最小原则）
const handleChange = async (category: string, key: string, value: any) => {
  if (isInitializing.value || isSaving.value) return

  isSaving.value = true
  try {
    // 构建只包含单个修改字段的更新数据（遵循最小原则）
    const updateData: any = { [category]: { [key]: value } }

    const success = await updateScript(scriptId, updateData)
    if (success) {
      logger.info(`配置已保存: ${category}.${key}`)
      // 保存成功后刷新数据
      await refreshScript()
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存失败: ${errorMsg}`)
  } finally {
    isSaving.value = false
  }
}

// 刷新脚本配置
const refreshScript = async () => {
  try {
    const scriptDetail = await getScript(scriptId)
    if (scriptDetail) {
      Object.assign(generalConfig, scriptDetail.config as GeneralScriptConfig)
      formData.name = scriptDetail.name
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`刷新配置失败: ${errorMsg}`)
  }
}

// 监听根目录变化，自动调整其他路径以保持相对关系
// 注意：此 watcher 用于维护路径间的相对关系（业务逻辑），而非配置自动保存
// 实际的保存操作由用户选择路径后的 @blur/@change 事件触发
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
  // 获取 AppData 路径
  if (window.electronAPI) {
    try {
      appDataPath.value = await window.electronAPI.getAppPath('appData')
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`获取 AppData 路径失败: ${errorMsg}`)
    }
  }

  await loadScript()
  // 只有当游戏平台类型为模拟器时才加载模拟器选项
  if (generalConfig.Game.Type === 'Emulator') {
    await loadEmulatorOptions()
  }
  // 在脚本加载完成并完成初始化后，再注册 ConfigPathMode 的 watcher，避免初始化阶段触发重置逻辑
  setupConfigPathModeWatcher()
  // 初始化完成后允许自动保存
  isInitializing.value = false
})

const loadScript = async () => {
  // 标记正在初始化，阻止某些 watcher 在赋值时触发
  isInitializing.value = true
  pageLoading.value = true
  try {
    // 检查是否有通过路由状态传递的数据（新建脚本时）
    const routeState = history.state as any
    if (routeState?.scriptData) {
      // 有路由状态数据时，先使用它快速渲染，但仍然从API重新加载以确保数据完整性
      const scriptData = routeState.scriptData
      const config = scriptData.config as GeneralScriptConfig
      formData.name = config.Info.Name || '新建通用脚本'
      Object.assign(generalConfig, config)

      // 从API重新加载完整数据（确保包含所有必要的配置）
      const scriptDetail = await getScript(scriptId)
      if (scriptDetail) {
        formData.type = scriptDetail.type
        formData.name = scriptDetail.name
        Object.assign(generalConfig, scriptDetail.config as GeneralScriptConfig)
      }

      // 对于 General 类型，在加载完成后初始化相对路径关系
      setTimeout(() => {
        updatePathRelations()
      }, 100)

      // 如果已经有选择的模拟器，且游戏类型为模拟器，则加载对应的设备选项
      if (generalConfig.Game?.Type === 'Emulator' && generalConfig.Game?.EmulatorId) {
        void loadEmulatorDeviceOptions(generalConfig.Game.EmulatorId)
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

      Object.assign(generalConfig, scriptDetail.config as GeneralScriptConfig)
      // 对于 General 类型，在加载完成后初始化相对路径关系
      setTimeout(() => {
        updatePathRelations()
      }, 100)

      // 如果已经有选择的模拟器，且游戏类型为模拟器，则加载对应的设备选项
      if (generalConfig.Game?.Type === 'Emulator' && generalConfig.Game?.EmulatorId) {
        void loadEmulatorDeviceOptions(generalConfig.Game.EmulatorId)
      }
    }

    // 同步推送日志采集规则：将后端返回的 JSON 字符串解析为可编辑的列表
    syncPushLogPatternsFromConfig()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载脚本失败: ${errorMsg}`)
    message.error('加载脚本失败')
    router.push('/scripts')
  } finally {
    pageLoading.value = false
    // 初始化完成，等待一次 nextTick 以确保所有由赋值触发的 watcher
    // 在 isInitializing 为 true 时被调度并能正确跳过，然后再清除初始化标志
    await nextTick()
  }
}

const handleCancel = () => {
  router.push('/scripts')
}

// 模拟器相关方法
const loadEmulatorOptions = async () => {
  emulatorLoading.value = true
  try {
    const response = await Service.getEmulatorComboxApiInfoComboxEmulatorPost()
    if (response && response.code === 200) {
      emulatorOptions.value = response.data || []
    } else {
      message.error('加载模拟器选项失败')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载模拟器选项失败: ${errorMsg}`)
    message.error('加载模拟器选项失败')
  } finally {
    emulatorLoading.value = false
  }
}

const handleEmulatorChange = async (emulatorId: string) => {
  // 清空模拟器实例选择
  generalConfig.Game.EmulatorIndex = ''
  if (emulatorId) {
    void loadEmulatorDeviceOptions(emulatorId)
  } else {
    clearEmulatorDeviceOptions()
  }

  // 保存模拟器选择和清空的实例字段
  isSaving.value = true
  try {
    const updateData = {
      Game: {
        EmulatorId: emulatorId,
        EmulatorIndex: '',
      },
    }
    const success = await updateScript(scriptId, updateData)
    if (success) {
      logger.info('模拟器配置已保存')
      await refreshScript()
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存模拟器配置失败: ${errorMsg}`)
  } finally {
    isSaving.value = false
  }
}

const handleGameTypeChange = async (gameType: string) => {
  // 构建需要更新的字段对象
  let updateFields: Record<string, any> = { Type: gameType }
  clearEmulatorDeviceOptions()

  // 当游戏平台类型改变时，清空相关字段
  if (gameType === 'Emulator') {
    // 切换到模拟器时，清空PC客户端和URL相关字段
    generalConfig.Game.Path = '.'
    generalConfig.Game.URL = ''
    generalConfig.Game.Arguments = ''
    generalConfig.Game.WaitTime = 0
    generalConfig.Game.IfForceClose = false
    updateFields = {
      ...updateFields,
      Path: '.',
      URL: '',
      Arguments: '',
      WaitTime: 0,
      IfForceClose: false,
    }
    // 加载模拟器选项
    await loadEmulatorOptions()
  } else if (gameType === 'Client') {
    // 切换到PC客户端时，清空模拟器和URL相关字段
    generalConfig.Game.URL = ''
    generalConfig.Game.EmulatorId = ''
    generalConfig.Game.EmulatorIndex = ''
    emulatorOptions.value = []
    updateFields = {
      ...updateFields,
      URL: '',
      EmulatorId: '',
      EmulatorIndex: '',
    }
  } else if (gameType === 'URL') {
    // 切换到URL时，清空PC客户端和模拟器相关字段
    generalConfig.Game.Path = '.'
    generalConfig.Game.Arguments = ''
    generalConfig.Game.WaitTime = 0
    generalConfig.Game.IfForceClose = false
    generalConfig.Game.EmulatorId = ''
    generalConfig.Game.EmulatorIndex = ''
    emulatorOptions.value = []
    updateFields = {
      ...updateFields,
      Path: '.',
      Arguments: '',
      WaitTime: 0,
      IfForceClose: false,
      EmulatorId: '',
      EmulatorIndex: '',
    }
  }

  // 保存所有更改的字段
  isSaving.value = true
  try {
    const updateData = { Game: updateFields }
    const success = await updateScript(scriptId, updateData)
    if (success) {
      logger.info('游戏配置已保存')
      await refreshScript()
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存游戏配置失败: ${errorMsg}`)
  } finally {
    isSaving.value = false
  }
}

const selectRootPath = async () => {
  try {
    if (!window.electronAPI) {
      message.error('文件选择功能不可用，请在 Electron 环境中运行')
      return
    }

    const path = await window.electronAPI.selectFolder()
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

        // 收集所有需要更新的字段
        const updateFields: Record<string, any> = { RootPath: normalizedPath }

        // 检查哪些路径被自动调整了，将它们也加入更新
        const scriptPathUpdates: Record<string, any> = {}
        if (generalConfig.Script.ScriptPath && generalConfig.Script.ScriptPath !== '.') {
          scriptPathUpdates.ScriptPath = generalConfig.Script.ScriptPath
        }
        if (generalConfig.Script.ConfigPath && generalConfig.Script.ConfigPath !== '.') {
          scriptPathUpdates.ConfigPath = generalConfig.Script.ConfigPath
        }
        if (generalConfig.Script.LogPath && generalConfig.Script.LogPath !== '.') {
          scriptPathUpdates.LogPath = generalConfig.Script.LogPath
        }
        if (generalConfig.Script.TrackProcessExe && generalConfig.Script.TrackProcessExe !== '.') {
          scriptPathUpdates.TrackProcessExe = generalConfig.Script.TrackProcessExe
        }

        // 保存所有更改
        isSaving.value = true
        try {
          const updateData: any = { Info: updateFields }
          if (Object.keys(scriptPathUpdates).length > 0) {
            updateData.Script = scriptPathUpdates
          }
          const success = await updateScript(scriptId, updateData)
          if (success) {
            logger.info('根路径及关联路径已保存')
            await refreshScript()
          }
        } catch (error) {
          const errorMsg = error instanceof Error ? error.message : String(error)
          logger.error(`保存路径失败: ${errorMsg}`)
        } finally {
          isSaving.value = false
        }
        message.success('根路径选择成功，其他路径已自动调整以保持相对关系')
      } else {
        // 保存根目录更改
        await handleChange('Info', 'RootPath', normalizedPath)
        message.success('根路径选择成功')
      }
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`选择根路径失败: ${errorMsg}`)
    message.error('选择文件夹失败')
  }
}

const selectGamePath = async () => {
  try {
    if (!window.electronAPI) {
      message.error('文件选择功能不可用，请在 Electron 环境中运行')
      return
    }

    const paths = await window.electronAPI.selectFile([
      { name: '可执行文件', extensions: ['exe'] },
      { name: '所有文件', extensions: ['*'] },
    ])
    if (paths && paths.length > 0) {
      generalConfig.Game.Path = paths[0]
      // 保存游戏路径
      await handleChange('Game', 'Path', paths[0])
      message.success('游戏路径选择成功')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`选择游戏路径失败: ${errorMsg}`)
    message.error('选择文件失败')
  }
}

const selectScriptPath = async () => {
  try {
    if (!window.electronAPI) {
      message.error('文件选择功能不可用，请在 Electron 环境中运行')
      return
    }

    const paths = await window.electronAPI.selectFile([
      { name: '可执行文件', extensions: ['exe', 'bat'] },
      { name: '所有文件', extensions: ['*'] },
    ])
    if (paths && paths.length > 0) {
      const path = paths[0]
      // 验证路径是否在根目录下
      if (validatePath(generalConfig.Info.RootPath, path, '主程序路径')) {
        const normalizedPath = pathUtils.normalizePath(path)
        generalConfig.Script.ScriptPath = normalizedPath
        // 更新相对路径关系
        updatePathRelations()
        // 保存脚本路径
        await handleChange('Script', 'ScriptPath', normalizedPath)
        message.success('脚本路径选择成功')
      }
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`选择脚本路径失败: ${errorMsg}`)
    message.error('选择文件失败')
  }
}

const selectTrackProcessExe = async () => {
  try {
    if (!window.electronAPI) {
      message.error('文件选择功能不可用，请在 Electron 环境中运行')
      return
    }

    const paths = await window.electronAPI.selectFile([
      { name: '可执行文件', extensions: ['exe'] },
      { name: '所有文件', extensions: ['*'] },
    ])
    if (paths && paths.length > 0) {
      const path = paths[0]
      // 验证路径是否在根目录下（可选）
      if (validatePath(generalConfig.Info.RootPath, path, '被追踪进程可执行文件路径')) {
        const normalizedPath = pathUtils.normalizePath(path)
        generalConfig.Script.TrackProcessExe = normalizedPath
        // 保存被追踪进程可执行文件路径
        await handleChange('Script', 'TrackProcessExe', normalizedPath)
        message.success('被追踪进程可执行文件选择成功')
      }
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`选择被追踪进程可执行文件失败: ${errorMsg}`)
    message.error('选择文件失败')
  }
}

const clearTrackProcessExe = async () => {
  generalConfig.Script.TrackProcessExe = ''
  updatePathRelations()
  await handleChange('Script', 'TrackProcessExe', '')
  message.success('被追踪进程可执行文件路径已清空')
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
      const folderPath = await window.electronAPI.selectFolder()
      selectedPath = folderPath || undefined
    } else {
      // 选择文件（默认行为）
      const paths = await window.electronAPI.selectFile([
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
        const normalizedPath = pathUtils.normalizePath(selectedPath)
        generalConfig.Script.ConfigPath = normalizedPath
        // 更新相对路径关系
        updatePathRelations()
        // 保存配置路径
        await handleChange('Script', 'ConfigPath', normalizedPath)
        message.success(`${pathType}路径选择成功`)
      }
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`选择配置路径失败: ${errorMsg}`)
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

    const paths = await window.electronAPI.selectFile()
    if (paths && paths.length > 0) {
      const path = paths[0]
      // 验证路径是否在根目录下
      if (validatePath(generalConfig.Info.RootPath, path, '日志文件路径')) {
        const normalizedPath = pathUtils.normalizePath(path)
        generalConfig.Script.LogPath = normalizedPath
        // 更新相对路径关系
        updatePathRelations()
        // 保存日志路径
        await handleChange('Script', 'LogPath', normalizedPath)
        message.success('日志路径选择成功')
      }
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`选择日志路径失败: ${errorMsg}`)
    message.error('选择文件失败')
  }
}

// 上传脚本配置相关
const uploadModalVisible = ref(false)
const uploadLoading = ref(false)

const uploadForm = reactive({
  config_name: '',
  author: '',
  description: '',
})

// 上传表单验证规则
const uploadRules = {
  config_name: [{ required: true, message: '请输入配置名称', trigger: 'blur' }],
  author: [{ required: true, message: '请输入作者名称', trigger: 'blur' }],
  description: [{ required: true, message: '请输入描述', trigger: 'blur' }],
}

// 显示上传弹窗
const showUploadModal = () => {
  uploadModalVisible.value = true
}

// 隐藏上传弹窗
const handleUploadCancel = () => {
  uploadModalVisible.value = false
}

// 处理上传脚本配置
const handleUpload = async () => {
  try {
    await uploadFormRef.value?.validate()

    uploadLoading.value = true

    // 构建上传数据
    const uploadData: ScriptUploadIn = {
      scriptId: scriptId,
      config_name: uploadForm.config_name,
      author: uploadForm.author,
      description: uploadForm.description,
    }

    // 调用上传API
    await Service.uploadScriptToWebApiScriptsUploadWebPost(uploadData)

    message.success('脚本配置上传成功，等待审核通过后即可向所有用户展示~')
    uploadModalVisible.value = false

    // 重置表单
    uploadForm.config_name = ''
    uploadForm.author = ''
    uploadForm.description = ''
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`上传失败: ${errorMsg}`)
    message.error('上传失败，请检查网络连接或稍后重试')
  } finally {
    uploadLoading.value = false
  }
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

/* 字段标题旁的文档入口：蓝色书形图标 + 文字，区别于灰色问号 */
.doc-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--ant-color-primary);
  cursor: pointer;
  transition: color 0.3s ease;
}

.doc-link:hover {
  color: var(--ant-color-primary-hover);
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

.path-clear-icon-btn {
  width: 44px;
  min-width: 44px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border: none;
  border-radius: 0;
  border-left: 1px solid var(--ant-color-border-secondary);
  background: var(--ant-color-bg-container);
  color: var(--ant-color-error);
  transition: all 0.3s ease;
}

.path-clear-icon-btn:hover {
  background: var(--ant-color-error) !important;
  color: white !important;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.18);
}

.path-clear-icon-btn :deep(.anticon) {
  font-size: 16px;
  color: inherit;
}

.path-clear-icon-btn :deep(.anticon svg) {
  fill: currentColor;
  stroke: currentColor;
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

.format-preview {
  margin-top: 8px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

.format-preview-value {
  color: var(--ant-color-text);
  font-family:
    ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New',
    monospace;
}

.format-preview-tip {
  margin-top: 8px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  line-height: 1.5;
  padding: 8px 10px;
  border-radius: 6px;
  border-left: 3px solid var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
}

/* ==================== 推送配置区 ==================== */
.push-config-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}

.push-config-header h3 {
  margin: 0;
}

.push-config-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}

/* 启停按钮放大，移除头部文档链接后腾出空间 */
.push-log-switch {
  transform: scale(1.25);
  transform-origin: center;
}

.push-config-body {
  padding: 16px 0 4px;
}

/* 底部添加行 */
.pattern-add-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px 0 0;
  color: var(--ant-color-text-tertiary);
  font-size: 13px;
  cursor: pointer;
  transition: color 0.2s ease;
  user-select: none;
}

.pattern-add-row:hover {
  color: var(--ant-color-primary);
}

/* ==================== 推送配置-规则列表 ==================== */
/* 规则分组：扁平化，与其他表单 section 风格一致，仅用分隔线区分多条规则 */
.pattern-rule {
  padding: 24px 0 12px;
  border-top: 1px solid var(--ant-color-border);
}

.pattern-rule:first-of-type {
  border-top: none;
  padding-top: 0;
}

/* 规则标识行：类型选择器 + 提示图标 + 操作图标 */
.pattern-rule-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.pattern-type-select {
  width: 130px;
  flex-shrink: 0;
}

.pattern-rule-tip {
  font-size: 14px;
  color: var(--ant-color-text-tertiary);
  cursor: help;
  flex-shrink: 0;
}

.pattern-rule-ops {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-shrink: 0;
  margin-left: auto;
  height: 40px;
}

/* 调试按钮：做成可见的蓝色小按钮，hover 实心填充 */
.pattern-op-debug {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  padding: 2px 10px;
  border-radius: 4px;
  border: 1px solid var(--ant-color-primary-border);
  color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
  cursor: pointer;
  user-select: none;
  transition: all 0.2s ease;
}

.pattern-op-debug:hover {
  color: #fff;
  background: var(--ant-color-primary);
  border-color: var(--ant-color-primary);
}

.pattern-op-icon {
  font-size: 16px;
  color: var(--ant-color-text-tertiary);
  cursor: pointer;
  transition: color 0.2s ease;
}

.pattern-op-icon:hover {
  color: var(--ant-color-primary);
}

.pattern-op-icon.pattern-op-del {
  color: var(--ant-color-error);
  opacity: 0.75;
}

.pattern-op-icon.pattern-op-del:hover {
  opacity: 1;
}

/* 字符串切割：输入框 + 包含复选框同行排列 */
.split-input-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.split-input-row .modern-input {
  flex: 1;
  min-width: 0;
}

.split-input-row :deep(.ant-checkbox-wrapper) {
  flex-shrink: 0;
  font-size: 14px;
  color: var(--ant-color-text-secondary);
}

/* 规则内的 form-item 间距，与游戏配置/运行配置保持一致 */
.pattern-rule :deep(.ant-form-item) {
  margin-bottom: 20px;
}

.pattern-rule :deep(.ant-form-item:last-child) {
  margin-bottom: 4px;
}

/* form-item label 字号与其他模块对齐 */
.pattern-rule :deep(.ant-form-item-label > label) {
  font-size: 13px;
}

/* 暗色模式下规则分隔线 */
@media (prefers-color-scheme: dark) {
  .pattern-rule {
    border-top-color: var(--ant-color-border);
  }
}

/* ==================== 调试弹窗 ==================== */
.debug-modal-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.debug-config-preview {
  padding: 8px 12px;
  background: var(--ant-color-fill-tertiary);
  border-radius: 6px;
  font-size: 12px;
  display: flex;
  align-items: flex-start;
  gap: 6px;
  border: 1px solid var(--ant-color-border-secondary);
}

.debug-config-label {
  color: var(--ant-color-text-tertiary);
  flex-shrink: 0;
}

.debug-config-code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  color: var(--ant-color-text-secondary);
  word-break: break-all;
}

.debug-section-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 500;
  color: var(--ant-color-text);
  margin-bottom: 8px;
}

.debug-load-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.debug-load-hint {
  font-size: 12px;
  font-weight: 400;
  color: var(--ant-color-text-tertiary);
}

.debug-textarea {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
}

.debug-actions {
  display: flex;
  gap: 8px;
}

.debug-compile-error {
  margin-top: 12px;
  white-space: pre-wrap;
  word-break: break-all;
}

.debug-results {
  border-top: 1px solid var(--ant-color-border-secondary);
  padding-top: 12px;
}

.debug-results-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.debug-results-list {
  max-height: 320px;
  overflow-y: auto;
  padding-right: 4px;
}

.debug-results-empty {
  padding: 20px 8px;
  text-align: center;
  color: var(--ant-color-text-tertiary);
  font-size: 13px;
}

.debug-result-item {
  padding: 8px 10px;
  margin-bottom: 6px;
  border-radius: 6px;
  border: 1px solid var(--ant-color-border-secondary);
  background: var(--ant-color-bg-container);
}

.debug-result-item.hit {
  background: var(--ant-color-success-bg);
  border-color: var(--ant-color-success-border);
}

.debug-result-item.miss {
  background: var(--ant-color-fill-quaternary);
  opacity: 0.75;
}

.debug-result-line {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 4px;
}

.debug-result-line-num {
  flex-shrink: 0;
  min-width: 18px;
  height: 18px;
  border-radius: 9px;
  background: var(--ant-color-fill-tertiary);
  color: var(--ant-color-text-tertiary);
  font-size: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 4px;
}

.debug-result-line-text {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  color: var(--ant-color-text);
  word-break: break-all;
  line-height: 1.5;
}

.debug-result-out {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-left: 26px;
}

.debug-result-tag {
  flex-shrink: 0;
  margin: 0;
}

.debug-result-extracted {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  color: var(--ant-color-success);
  word-break: break-all;
  font-weight: 500;
}

.debug-result-error {
  font-size: 12px;
  color: var(--ant-color-error);
}
</style>
