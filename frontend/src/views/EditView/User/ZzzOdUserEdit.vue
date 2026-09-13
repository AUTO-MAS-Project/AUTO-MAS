<template>
  <div class="user-edit-container">
    <div class="user-edit-header">
      <div class="header-nav">
        <a-breadcrumb class="breadcrumb">
          <a-breadcrumb-item>
            <router-link to="/scripts">{{ t('edit.scripts') }}</router-link>
          </a-breadcrumb-item>
          <a-breadcrumb-item>
            <router-link :to="`/scripts/${scriptId}/edit/zzzod`" class="breadcrumb-link">
              {{ scriptName }}
            </router-link>
          </a-breadcrumb-item>
          <a-breadcrumb-item>
            {{ isEdit ? t('comp.editUser') : t('comp.addUser2') }}
          </a-breadcrumb-item>
        </a-breadcrumb>
      </div>

      <a-space size="middle">
        <a-tooltip :title="t('edit.zzzodOpenNativeConfigHint')">
          <a-button
            v-if="!showZzzodConfigMask && !showZzzodViewMask"
            type="primary"
            ghost
            size="large"
            :loading="zzzodConfigLoading"
            :disabled="pageLoading || !userId"
            @click="handleZzzodConfig"
          >
            <template #icon>
              <SettingOutlined />
            </template>
            {{ t('edit.zzzodOpenNativeConfig') }}
          </a-button>
        </a-tooltip>
        <a-button
          v-if="showZzzodConfigMask"
          type="default"
          size="large"
          disabled
          class="configuring-button"
        >
          <template #icon>
            <SettingOutlined />
          </template>
          {{ t('edit.configuring') }}
        </a-button>
        <a-button size="large" class="cancel-button" @click="handleCancel">
          <template #icon>
            <ArrowLeftOutlined />
          </template>
          {{ t('edit.back') }}
        </a-button>
      </a-space>
    </div>

    <GuiSessionMask
      :open="showZzzodConfigMask"
      :icon="SettingOutlined"
      :title="t('edit.zzzodConfiguringTitle')"
      :description="`${t('edit.zzzodConfiguringDesc')}\n${t('edit.zzzodConfiguringDesc2')}`"
    >
      <template #actions>
        <a-button
          v-if="zzzodWebsocketId"
          type="primary"
          size="large"
          @click="handleSaveZzzodConfig"
        >
          {{ t('edit.saveSettings') }}
        </a-button>
      </template>
    </GuiSessionMask>
    <GuiSessionMask
      :open="showZzzodViewMask"
      :icon="EyeOutlined"
      :title="t('edit.zzzodViewingTitle')"
      :description="`${t('edit.zzzodViewingDesc')}\n${t('edit.zzzodViewingDesc2')}`"
    >
      <template #actions>
        <a-button
          v-if="zzzodWebsocketId"
          type="primary"
          size="large"
          :loading="stoppingZzzodConfig"
          @click="handleCloseZzzodView"
        >
          {{ t('edit.zzzodViewClose') }}
        </a-button>
      </template>
    </GuiSessionMask>

    <div class="user-edit-content">
      <a-card class="config-card" :loading="pageLoading">
        <a-form :model="formData" layout="vertical" class="config-form">
          <div class="form-section">
            <div class="section-header">
              <h3>{{ t('edit.basicInfo') }}</h3>
            </div>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.username') }}
                      <a-tooltip :title="t('edit.zzzodUserNameHint')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-input
                    v-model:value="formData.userName"
                    :placeholder="t('edit.enterUsername')"
                    size="large"
                    class="modern-input"
                    @blur="handleNameBlur"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.enabled') }}
                      <a-tooltip :title="t('edit.whetherThisUserEnabled')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-select
                    v-model:value="formData.Info.Status"
                    size="large"
                    class="modern-select"
                    @change="saveField('Info.Status', formData.Info.Status)"
                  >
                    <a-select-option :value="true">{{ t('edit.yes') }}</a-select-option>
                    <a-select-option :value="false">{{ t('edit.no') }}</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="24">
              <a-col :span="24">
                <GeneralConfigModeSelector
                  :model-value="formData.Info.Mode"
                  :options="configModeOptions"
                  :disabled="pageLoading"
                  :alert-message="configModeAlert"
                  @change="handleConfigModeChange"
                />
              </a-col>
            </a-row>

            <!-- 一条龙启动器（直控/用户两种模式通用；未安装的启动器选项禁用变灰，悬停选项查看说明）固定在右侧；
                 左侧按模式切换：直控为「运行实例」，用户为「快速导入配置」（母版下拉选择来源实例 + 导入按钮，
                 外观与周围下拉框一致；确认后覆盖本用户配置（账号+任务编排）） -->
            <a-row :gutter="24">
              <a-col v-if="formData.Info.Mode === '直控'" :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.zzzodDirectInstanceRun') }}
                      <a-tooltip :title="t('edit.zzzodDirectInstanceRunHint')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-select
                    v-model:value="nativeInstanceRun"
                    :options="instanceRunOptions"
                    :loading="runModeSaving"
                    size="large"
                    class="modern-select"
                    @change="handleNativeInstanceRunChange"
                  />
                </a-form-item>
              </a-col>
              <a-col v-else :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.zzzodQuickImport') }}
                      <a-tooltip :title="t('edit.zzzodImportConfigHint')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <div class="import-group">
                    <a-select
                      v-model:value="importSourceIdx"
                      :options="instanceOptions"
                      :placeholder="t('edit.zzzodImportPlaceholder')"
                      :loading="instancesLoading"
                      size="large"
                      class="modern-select import-source-select"
                    />
                    <a-button
                      size="large"
                      class="import-select-button"
                      :loading="importLoading"
                      :disabled="importSourceIdx === null"
                      @click="confirmImport"
                    >
                      {{ t('edit.zzzodImport') }}
                    </a-button>
                  </div>
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.zzzodLauncherMode') }}
                    </span>
                  </template>
                  <a-select
                    v-model:value="formData.Info.LauncherMode"
                    size="large"
                    class="modern-select"
                    :loading="launchersLoading"
                    @change="saveField('Info.LauncherMode', formData.Info.LauncherMode)"
                  >
                    <a-select-option
                      value="自动"
                      :disabled="!launchersReady || !launchersUsable.smart"
                    >
                      <a-tooltip :title="t('edit.zzzodLauncherAutoHint')">
                        <span>{{ t('edit.zzzodLauncherAuto') }}</span>
                      </a-tooltip>
                    </a-select-option>
                    <a-select-option
                      value="原始"
                      :disabled="!launchersReady || !launchersUsable.original"
                    >
                      <a-tooltip :title="t('edit.zzzodLauncherOriginalHint')">
                        <span>{{ t('edit.zzzodLauncherOriginal') }}</span>
                      </a-tooltip>
                    </a-select-option>
                    <a-select-option
                      value="集成"
                      :disabled="!launchersReady || !launchersUsable.integrated"
                    >
                      <a-tooltip :title="t('edit.zzzodLauncherIntegratedHint')">
                        <span>{{ t('edit.zzzodLauncherIntegrated') }}</span>
                      </a-tooltip>
                    </a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
            </a-row>

            <!-- 直控：实例管理（参与「全部实例」运行 / 添加 / 重命名 / 删除，实时写回 one_dragon.yml） -->
            <template v-if="formData.Info.Mode === '直控'">
              <div class="instance-manage">
                <div class="instance-manage-header">
                  <span class="form-label">
                    {{ t('edit.zzzodInstancesManage') }}
                    <a-tooltip :title="t('edit.zzzodInstancesManageHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                  <a-button
                    type="primary"
                    size="small"
                    :loading="instanceOpLoading"
                    @click="openAddInstance"
                  >
                    <template #icon><PlusOutlined /></template>
                    {{ t('edit.zzzodAddInstance') }}
                  </a-button>
                </div>
                <div v-if="instances.length" class="instance-manage-list">
                  <div
                    v-for="inst in instances"
                    :key="inst.idx"
                    class="instance-manage-row"
                    :class="{ selected: inst.idx === nativeInstanceIdx }"
                  >
                    <div class="instance-manage-info">
                      <span
                        class="instance-manage-name"
                        :title="`${String(inst.idx).padStart(2, '0')} - ${inst.name}`"
                      >
                        {{ String(inst.idx).padStart(2, '0') }} - {{ inst.name }}
                      </span>
                      <a-tooltip
                        v-if="inst.active"
                        :title="t('edit.zzzodInstanceActiveTagHint')"
                      >
                        <a-tag color="processing" class="instance-manage-tag">
                          {{ t('edit.zzzodInstanceActiveTag') }}
                        </a-tag>
                      </a-tooltip>
                      <a-tooltip v-else :title="t('edit.zzzodSetInstanceActive')">
                        <a-tag
                          class="instance-manage-tag instance-manage-tag-set"
                          @click="setActiveInstance(inst)"
                        >
                          {{ t('edit.zzzodInstanceSetActiveTag') }}
                        </a-tag>
                      </a-tooltip>
                    </div>
                    <div class="instance-manage-ops">
                      <span class="instance-manage-switch-label">
                        {{ t('edit.zzzodInstanceRunAllSwitch') }}
                      </span>
                      <a-tooltip :title="t('edit.zzzodInstanceActiveInOd')">
                        <a-switch
                          size="small"
                          :checked="inst.active_in_od"
                          @change="(checked: boolean) => toggleInstanceActiveInOd(inst, checked)"
                        />
                      </a-tooltip>
                      <span class="instance-manage-switch-label">
                        {{ t('edit.zzzodInstanceForceLoginSwitch') }}
                      </span>
                      <a-tooltip :title="t('edit.zzzodInstanceForceLoginHint')">
                        <a-switch
                          size="small"
                          :checked="inst.force_login_before_run"
                          @change="(checked: boolean) => toggleInstanceForceLogin(inst, checked)"
                        />
                      </a-tooltip>
                      <a-divider type="vertical" class="instance-manage-divider" />
                      <a-tooltip :title="t('edit.zzzodRenameInstance')">
                        <a-button
                          size="small"
                          type="text"
                          aria-label="重命名实例"
                          @click="openRenameInstance(inst)"
                        >
                          <template #icon><EditOutlined /></template>
                        </a-button>
                      </a-tooltip>
                      <a-tooltip :title="t('edit.zzzodDeleteInstance')">
                        <a-button
                          size="small"
                          type="text"
                          danger
                          aria-label="删除实例"
                          @click="openDeleteInstance(inst)"
                        >
                          <template #icon><DeleteOutlined /></template>
                        </a-button>
                      </a-tooltip>
                    </div>
                  </div>
                </div>
              </div>

              <!-- 直控：选择配置实例（选完即编辑下方账号字段与任务配置） -->
              <a-row :gutter="24">
                <a-col :span="12">
                  <a-form-item>
                    <template #label>
                      <span class="form-label">
                        {{ t('edit.zzzodDirectInstance') }}
                        <a-tooltip :title="t('edit.zzzodDirectInstanceHint')">
                          <QuestionCircleOutlined class="help-icon" />
                        </a-tooltip>
                      </span>
                    </template>
                    <a-select
                      v-model:value="nativeInstanceIdx"
                      :options="instanceOptions"
                      :placeholder="t('edit.zzzodDirectPickInstance')"
                      :loading="instancesLoading"
                      size="large"
                      class="modern-select"
                      @change="handleNativeInstanceChange"
                    />
                  </a-form-item>
                </a-col>
              </a-row>

              <a-alert
                type="info"
                show-icon
                class="native-bind-alert"
                :message="t('edit.zzzodDirectBindAlert')"
              />

              <!-- 直控：所选实例的原生账号字段（保存即写回一条龙 game_account.yml） -->
              <a-spin :spinning="nativeLoading">
                <template v-if="nativeInstanceIdx !== null">
                  <a-row :gutter="24">
                    <a-col
                      v-for="f in nativeAccountFields"
                      :key="f.key"
                      :span="12"
                    >
                      <a-form-item>
                        <template #label>
                          <span class="form-label">
                            <span
                              v-if="isRequiredAccountKey(f.key)"
                              class="required-mark"
                              aria-hidden="true"
                              >*</span
                            >
                            {{ f.title }}
                            <a-tooltip
                              v-if="isRequiredAccountKey(f.key)"
                              :title="t('edit.zzzodAccountRequiredTip')"
                            >
                              <QuestionCircleOutlined class="help-icon" />
                            </a-tooltip>
                          </span>
                        </template>
                        <a-input-group
                          v-if="f.key === 'game_path'"
                          compact
                          class="path-input-group"
                        >
                          <a-input
                            v-model:value="nativeAccountValues[f.key]"
                            :placeholder="t('edit.zzzodGamePathPlaceholder')"
                            size="large"
                            class="path-input"
                            readonly
                          />
                          <a-button
                            size="large"
                            class="path-button"
                            @click="selectDirectGamePath"
                          >
                            <template #icon>
                              <FolderOpenOutlined />
                            </template>
                            {{ t('edit.pickFile') }}
                          </a-button>
                        </a-input-group>
                        <a-input-password
                          v-else-if="f.key === 'password'"
                          v-model:value="nativeAccountValues[f.key]"
                          :placeholder="t('edit.zzzodDirectPasswordPlaceholder')"
                          size="large"
                          class="modern-input"
                        />
                        <a-select
                          v-else-if="(f.options?.length ?? 0) > 0"
                          v-model:value="nativeAccountValues[f.key]"
                          :options="f.options"
                          size="large"
                          class="modern-select"
                        />
                        <a-input
                          v-else
                          v-model:value="nativeAccountValues[f.key]"
                          size="large"
                          class="modern-input"
                        />
                      </a-form-item>
                    </a-col>
                  </a-row>
                  <div class="native-save-row">
                    <a-button
                      type="primary"
                      size="large"
                      :loading="nativeSaving"
                      @click="saveNativeAccount"
                    >
                      {{ t('edit.saveSettings') }}
                    </a-button>
                  </div>
                </template>
                <a-empty
                  v-else
                  :description="t('edit.zzzodDirectPickInstanceFirst')"
                />
              </a-spin>
            </template>

            <!-- 账号配置（用户模式：MAS 字段化配置） -->
            <template v-else>
              <a-row :gutter="24">
                <a-col :span="12">
                  <a-form-item>
                    <template #label>
                      <span class="form-label">
                        {{ t('edit.zzzodGameRegion') }}
                        <a-tooltip :title="t('edit.zzzodGameRegionHint')">
                          <QuestionCircleOutlined class="help-icon" />
                        </a-tooltip>
                      </span>
                    </template>
                    <a-select
                      v-model:value="formData.Game.GameRegion"
                      :options="gameRegionOptions"
                      size="large"
                      class="modern-select"
                      @change="saveField('Game.GameRegion', formData.Game.GameRegion)"
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item>
                    <template #label>
                      <span class="form-label">
                        {{ t('edit.zzzodGameLanguage') }}
                        <a-tooltip :title="t('edit.zzzodGameLanguageHint')">
                          <QuestionCircleOutlined class="help-icon" />
                        </a-tooltip>
                      </span>
                    </template>
                    <a-select
                      v-model:value="formData.Game.GameLanguage"
                      :options="gameLanguageOptions"
                      size="large"
                      class="modern-select"
                      @change="saveField('Game.GameLanguage', formData.Game.GameLanguage)"
                    />
                  </a-form-item>
                </a-col>
              </a-row>

              <a-row :gutter="24">
                <a-col :span="24">
                  <a-form-item>
                    <template #label>
                      <span class="form-label">
                        {{ t('edit.zzzodGamePath') }}
                        <a-tooltip :title="t('edit.zzzodGamePathHint')">
                          <QuestionCircleOutlined class="help-icon" />
                        </a-tooltip>
                      </span>
                    </template>
                    <a-input-group compact class="path-input-group">
                      <a-input
                        v-model:value="formData.Game.GamePath"
                        :placeholder="t('edit.zzzodGamePathPlaceholder')"
                        size="large"
                        class="path-input"
                        readonly
                      />
                      <a-button size="large" class="path-button" @click="selectGamePath">
                        <template #icon>
                          <FolderOpenOutlined />
                        </template>
                        {{ t('edit.pickFile') }}
                      </a-button>
                    </a-input-group>
                  </a-form-item>
                </a-col>
              </a-row>

              <a-row :gutter="24">
                <a-col :span="12">
                  <a-form-item>
                    <template #label>
                      <span class="form-label">
                        {{ t('edit.zzzodAccount') }}
                        <a-tooltip :title="t('edit.zzzodAccountHint')">
                          <QuestionCircleOutlined class="help-icon" />
                        </a-tooltip>
                      </span>
                    </template>
                    <a-input
                      v-model:value="formData.Game.Account"
                      :placeholder="t('edit.zzzodEnterAccount')"
                      size="large"
                      class="modern-input"
                      @blur="saveField('Game.Account', formData.Game.Account)"
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item>
                    <template #label>
                      <span class="form-label">
                        {{ t('edit.password') }}
                        <a-tooltip :title="t('edit.zzzodPasswordHint')">
                          <QuestionCircleOutlined class="help-icon" />
                        </a-tooltip>
                      </span>
                    </template>
                    <a-input-password
                      v-model:value="formData.Game.Password"
                      :placeholder="t('edit.zzzodEnterPasswordPlaceholder')"
                      size="large"
                      class="modern-input"
                      @blur="saveField('Game.Password', formData.Game.Password)"
                    />
                  </a-form-item>
                </a-col>
              </a-row>

              <a-row v-if="formData.Game.GameRegion === 'cn_b'" :gutter="24">
                <a-col :span="12">
                  <a-form-item>
                    <template #label>
                      <span class="form-label">
                        {{ t('edit.zzzodBilibiliAccount') }}
                        <a-tooltip :title="t('edit.zzzodBilibiliAccountHint')">
                          <QuestionCircleOutlined class="help-icon" />
                        </a-tooltip>
                      </span>
                    </template>
                    <a-input
                      v-model:value="formData.Game.BilibiliAccountName"
                      :placeholder="t('edit.zzzodEnterBilibiliAccount')"
                      size="large"
                      class="modern-input"
                      @blur="saveField('Game.BilibiliAccountName', formData.Game.BilibiliAccountName)"
                    />
                  </a-form-item>
                </a-col>
              </a-row>
            </template>

            <!-- 直控：添加 / 重命名实例弹窗（放在模式分支之后，避免打断 v-if/v-else 配对） -->
            <a-modal
              v-model:open="addInstanceOpen"
              :title="t('edit.zzzodAddInstance')"
              :ok-text="t('edit.zzzodAddInstance')"
              :cancel-text="t('edit.cancel')"
              :confirm-loading="instanceOpLoading"
              @ok="confirmAddInstance"
            >
              <a-form layout="vertical" class="config-form">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.zzzodInstanceName') }}
                      <a-tooltip :title="t('edit.zzzodInstanceNameHint')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-input
                    v-model:value="instanceName"
                    :placeholder="t('edit.zzzodInstanceNamePlaceholder')"
                    size="large"
                    class="modern-input"
                    @press-enter="confirmAddInstance"
                  />
                </a-form-item>
              </a-form>
            </a-modal>
            <a-modal
              v-model:open="renameInstanceOpen"
              :title="t('edit.zzzodRenameInstance')"
              :ok-text="t('edit.zzzodRenameInstance')"
              :cancel-text="t('edit.cancel')"
              :confirm-loading="instanceOpLoading"
              @ok="confirmRenameInstance"
            >
              <a-form layout="vertical" class="config-form">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.zzzodInstanceName') }}
                      <a-tooltip :title="t('edit.zzzodInstanceNameHint')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-input
                    v-model:value="instanceName"
                    :placeholder="t('edit.zzzodInstanceNamePlaceholder')"
                    size="large"
                    class="modern-input"
                    @press-enter="confirmRenameInstance"
                  />
                </a-form-item>
              </a-form>
            </a-modal>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.daysLeft') }}
                      <a-tooltip :title="t('edit.daysLeftAccount1')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-input-number
                    v-model:value="formData.Info.RemainedDay"
                    :min="-1"
                    :max="9999"
                    size="large"
                    style="width: 100%"
                    @blur="saveField('Info.RemainedDay', formData.Info.RemainedDay)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.note') }}
                      <a-tooltip :title="t('edit.addNoteAboutThis')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-input
                    v-model:value="formData.Info.Notes"
                    :placeholder="t('edit.enterNote')"
                    size="large"
                    class="modern-input"
                    @blur="saveField('Info.Notes', formData.Info.Notes)"
                  />
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.collectNodeDetails') }}
                      <a-tooltip :title="t('edit.zzzodPushLogModeHint')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-select
                    v-model:value="formData.Notify.PushLogMode"
                    :options="pushLogModeOptions"
                    size="large"
                    class="modern-select"
                    @change="saveField('Notify.PushLogMode', formData.Notify.PushLogMode)"
                  />
                </a-form-item>
              </a-col>
            </a-row>
          </div>
        </a-form>
      </a-card>

      <!-- ══ 任务配置（一条龙编排，紧跟基本信息）══ -->
      <a-card class="config-card" style="margin-top: 24px">
        <a-form :model="formData" layout="vertical" class="config-form">
          <div class="form-section">
            <div class="section-header">
              <h3>
                {{ t('edit.zzzodOneDragonConfig') }}
                <a-tooltip :title="t('edit.zzzodOneDragonConfigHint')">
                  <QuestionCircleOutlined class="help-icon" />
                </a-tooltip>
              </h3>
              <div class="section-header-actions">
                <a-tooltip :title="t('edit.zzzodSortTasksHint')">
                  <a-button size="small" class="restore-entry" @click="handleSortTasks">
                    <template #icon><SortAscendingOutlined /></template>
                    {{ t('edit.zzzodSortTasks') }}
                  </a-button>
                </a-tooltip>
                <a-button size="small" class="restore-entry" @click="openRestoreModal">
                  <template #icon><HistoryOutlined /></template>
                  {{ t('edit.configRestoreTitle') }}
                </a-button>
              </div>
            </div>

            <p class="section-desc">
              {{
                formData.Info.Mode === '直控'
                  ? t('edit.zzzodDirectTasksDesc')
                  : t('edit.zzzodOneDragonDesc')
              }}
            </p>

            <draggable
              v-model="taskDragCards"
              item-key="app_id"
              :animation="200"
              ghost-class="task-card-ghost"
              chosen-class="task-card-chosen"
              drag-class="task-card-drag"
              handle=".drag-handle"
              :disabled="pageLoading || isInitializing || nativeSaving"
              class="task-grid"
              @end="handleTaskDragEnd"
            >
              <template #item="{ element: card }">
                <div class="task-card" :class="{ inactive: !card.enabled }">
                  <div class="task-card-main">
                    <span
                      class="drag-handle"
                      :title="t('edit.zzzodDragSortHint')"
                      :aria-label="t('edit.zzzodDragSortHint')"
                    >
                      <span class="drag-dots" aria-hidden="true"></span>
                    </span>
                    <span class="task-name" :title="card.app_name">{{ card.app_name }}</span>
                    <div v-if="card.enabled" class="task-card-actions">
                      <a-popover
                        v-if="card.configurable"
                        :open="taskPopoverOpen[card.app_id] === true"
                        trigger="click"
                        placement="top"
                        @open-change="(o: boolean) => handleTaskPopoverChange(card, o)"
                      >
                        <template #content>
                          <div
                            v-for="f in taskConfigData[card.app_id] ?? []"
                            :key="f.field"
                            class="task-config-field"
                          >
                            <span class="task-config-field-title">{{ f.title }}</span>
                            <a-select
                              v-if="f.type === 'select' || f.type === 'team'"
                              :value="f.value ?? undefined"
                              size="small"
                              style="min-width: 150px"
                              @change="(v: any) => saveTaskConfigField(card, f, v)"
                            >
                              <a-select-option
                                v-for="o in f.options"
                                :key="o.value"
                                :value="o.value"
                              >
                                {{ o.label }}
                              </a-select-option>
                            </a-select>
                            <a-switch
                              v-else-if="f.type === 'bool'"
                              :checked="f.value === true"
                              size="small"
                              @change="(v: any) => saveTaskConfigField(card, f, v)"
                            />
                            <a-input-number
                              v-else
                              :value="f.value"
                              size="small"
                              style="min-width: 100px"
                              @change="(v: any) => scheduleTaskConfigSave(card, f, v)"
                              @blur="() => flushTaskConfigSave(card, f)"
                            />
                          </div>
                        </template>
                        <a-tooltip
                          :title="t('edit.zzzodTaskConfigHint')"
                          :open="taskTipVisible[card.app_id] === true"
                          @open-change="(o: boolean) => (taskTipVisible[card.app_id] = o)"
                        >
                          <a-button
                            size="small"
                            type="text"
                            class="task-config-gear"
                            :loading="taskConfigLoading[card.app_id] === true"
                            @click="taskTipVisible[card.app_id] = false"
                          >
                            <template #icon><SettingOutlined /></template>
                          </a-button>
                        </a-tooltip>
                      </a-popover>
                      <a-tooltip
                        v-if="card.jump"
                        :title="t('edit.zzzodTaskJumpHint')"
                        :open="jumpTipVisible[card.app_id] === true"
                        @open-change="(o: boolean) => (jumpTipVisible[card.app_id] = o)"
                      >
                        <a-button
                          size="small"
                          type="text"
                          class="task-config-gear"
                          @click="jumpTipVisible[card.app_id] = false; handleZzzodConfig()"
                        >
                          <template #icon><ExportOutlined /></template>
                        </a-button>
                      </a-tooltip>
                    </div>
                    <div
                      class="config-group-item-capsule"
                      :class="{ active: card.enabled }"
                      @click="toggleTask(card)"
                    >
                      <span class="config-group-item-dot"></span>
                    </div>
                  </div>
                </div>
              </template>
            </draggable>

            <!-- ══ 预备编队（独立组件：team.yml 固定 20 个编队，与一条龙编队页一致）══ -->
            <ZzzOdPredefinedTeams
              v-if="formData.Info.Mode !== '直控' || nativeInstanceIdx !== null"
              ref="teamsRef"
              :script-id="scriptId"
              :user-id="userId"
              :instance-idx="formData.Info.Mode === '直控' ? nativeInstanceIdx : null"
            />
          </div>
        </a-form>
      </a-card>

      <a-card class="config-card" style="margin-top: 24px">
        <a-form :model="formData" layout="vertical" class="config-form">
          <ExtraScriptSection :form-data="formData" :loading="pageLoading" @save="saveField" />
        </a-form>
      </a-card>

      <a-card class="config-card" style="margin-top: 24px">
        <a-form :model="formData" layout="vertical" class="config-form">
          <UserNotifyConfig
            v-model="formData.Notify"
            :loading="pageLoading"
            :script-id="scriptId"
            :user-id="userId"
            @save="saveField"
          />
        </a-form>
      </a-card>

      <!-- ══ 配置恢复（通用组件：列表 / 预览 / 查看详细 / 一键恢复）══ -->
      <ConfigRestoreSection
        v-model:open="restoreOpen"
        :script-name="ZZZOD_DISPLAY_NAME"
        :targets="restoreTargets"
        :api="restoreApi"
        :field-labels="previewFieldLabels"
        :format-value="formatPreviewValue"
        :on-restored="handleRestored"
        :on-detail="handleRestoreView"
      />

      <!-- ══ 任务计划编辑弹窗（体力刷本/恶名狩猎：计划列表 + 主配置）══ -->
      <a-modal
        v-model:open="planModal.open"
        :title="planModal.title"
        :width="760"
        :confirm-loading="planModal.saving"
        :mask-closable="false"
        :body-style="{ maxHeight: '70vh', overflowY: 'auto' }"
        @ok="savePlanModal"
      >
        <a-spin :spinning="planModal.loading">
          <div class="plan-modal-body">
            <ZzzOdPlanListEditor
              v-if="planModalField"
              v-model="planModal.draft"
              :columns="planModalField.columns ?? []"
              :new-item="planModalField.newItem ?? {}"
              :train-categories="planModal.trainCategories"
            />
            <div
              v-for="f in planModalOtherFields"
              :key="f.field"
              class="plan-modal-field"
            >
              <span class="plan-modal-field-title">{{ f.title }}</span>
              <a-switch
                v-if="f.type === 'bool'"
                :checked="f.value === true"
                @change="(v: any) => (f.value = v)"
              />
              <a-input-number
                v-else-if="f.type === 'number'"
                :value="f.value"
                style="min-width: 120px"
                @change="(v: any) => (f.value = v)"
              />
              <a-select
                v-else
                :value="f.value ?? undefined"
                :options="f.options"
                style="min-width: 220px"
                @change="(v: any) => (f.value = v)"
              />
            </div>
          </div>
        </a-spin>
      </a-modal>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, h, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message, Modal } from 'ant-design-vue'
import {
  ArrowLeftOutlined,
  DeleteOutlined,
  EditOutlined,
  ExportOutlined,
  EyeOutlined,
  FolderOpenOutlined,
  HistoryOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
  SettingOutlined,
  SortAscendingOutlined,
} from '@ant-design/icons-vue'
import draggable from 'vuedraggable'
import { useZzzOdTaskBoard, type ZzzOdTaskCard } from '@/composables/useZzzOdTaskBoard'
import {
  Service,
  type ZzzOdInstanceOut,
  type ZzzOdNativeAccountField,
  type ZzzOdNativeConfigOut,
  type ZzzOdUserConfig,
} from '@/api'
import ConfigRestoreSection from '@/views/EditView/User/components/ConfigRestoreSection.vue'
import GuiSessionMask from '@/components/GuiSessionMask.vue'
import ZzzOdPlanListEditor from '@/components/ZzzOdPlanListEditor.vue'
import ZzzOdPredefinedTeams from '@/components/ZzzOdPredefinedTeams.vue'
import { useUserApi } from '@/composables/useUserApi'
import { useScriptApi } from '@/composables/useScriptApi'
import { useZzzodGuiSession } from '@/composables/useZzzodGuiSession'
import GeneralConfigModeSelector from '@/views/EditView/User/GeneralConfigModeSelector.vue'
import UserNotifyConfig from '@/components/UserNotifyConfig.vue'
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'

const { t } = useI18n()
const logger = window.electronAPI.getLogger('ZZZ-OD用户编辑')
const route = useRoute()
const router = useRouter()
const { addUser, getUsers, updateUser, error: userApiError } = useUserApi()
const { getScript } = useScriptApi()

const scriptId = route.params.scriptId as string
const userId = ref((route.params.userId as string) || '')
const isEdit = ref(!!userId.value)
const scriptName = ref(t('edit.zzzodScriptFallbackName'))

const pageLoading = ref(true)
const isInitializing = ref(true)

type FormSection<T> = { [K in keyof T]-?: NonNullable<T[K]> }

type ZzzOdUserFormData = {
  userName: string
  Info: FormSection<NonNullable<ZzzOdUserConfig['Info']>>
  Game: FormSection<NonNullable<ZzzOdUserConfig['Game']>>
  OneDragon: FormSection<NonNullable<ZzzOdUserConfig['OneDragon']>>
  Notify: FormSection<NonNullable<ZzzOdUserConfig['Notify']>>
}

const getDefaultUserData = (): Omit<ZzzOdUserFormData, 'userName'> => ({
  Info: {
    Name: '',
    Status: true,
    Mode: '用户',
    SlotIdx: -1,
    LauncherMode: '自动',
    RemainedDay: -1,
    IfScriptBeforeTask: false,
    ScriptBeforeTask: '',
    IfScriptAfterTask: false,
    ScriptAfterTask: '',
    Notes: '',
    Tag: '',
  },
  Game: {
    GameRegion: 'cn',
    GamePath: '',
    GameLanguage: 'cn',
    Account: '',
    Password: '',
    BilibiliAccountName: '',
    Platform: 'PC',
    UseCustomWinTitle: false,
    CustomWinTitle: '',
  },
  OneDragon: {
    AppList: '[]',
  },
  Notify: {
    Enabled: false,
    PushLogMode: '汇总',
    IfSendStatistic: false,
    IfSendMail: false,
    ToAddress: '',
    IfServerChan: false,
    ServerChanKey: '',
  },
})

const formData = reactive<ZzzOdUserFormData>({
  userName: '',
  ...getDefaultUserData(),
})

// 节点详情推送模式（value 为后端 Notify.PushLogMode 取值，驱动逻辑需保持原样；label 走词表）
const pushLogModeOptions = [
  { label: t('edit.pushLogModeOff'), value: '关闭' },
  { label: t('edit.pushLogModeList'), value: '逐条' },
  { label: t('edit.pushLogModeSummary'), value: '汇总' },
]

// 配置来源两态卡片（value 为后端 Info.Mode 取值，驱动逻辑需保持原样；文案走词表）
const configModeOptions: Array<{
  label: string
  value: '用户' | '直控'
  title: string
  description: string
  icon: 'database' | 'setting'
}> = [
  {
    label: t('edit.zzzodModeUser'),
    value: '用户',
    title: t('edit.zzzodModeUser'),
    description: t('edit.zzzodModeUserDesc'),
    icon: 'database',
  },
  {
    label: t('edit.directControl'),
    value: '直控',
    title: t('edit.directControl'),
    description: t('edit.zzzodModeDirectDesc'),
    icon: 'setting',
  },
]

// 蓝色说明框随所选模式动态切换（只显示当前模式的行为，减少固定长文案）
const configModeAlert = computed(() =>
  formData.Info.Mode === '直控'
    ? t('edit.zzzodConfigSourceDirectAlert')
    : t('edit.zzzodConfigSourceUserAlert')
)

// ══ 区服 / 语言选项（value 为 zzz-od YAML 原生取值，驱动逻辑需保持原样）══
const gameRegionOptions = [
  { label: t('edit.zzzodRegionCn'), value: 'cn' },
  { label: t('edit.zzzodRegionCnB'), value: 'cn_b' },
  { label: t('edit.zzzodRegionUs'), value: 'us' },
  { label: t('edit.zzzodRegionEu'), value: 'eu' },
  { label: t('edit.zzzodRegionAsia'), value: 'asia' },
  { label: t('edit.zzzodRegionTwHkMo'), value: 'twhkmo' },
]
const gameLanguageOptions = [
  { label: t('edit.zzzodLanguageCn'), value: 'cn' },
  { label: t('edit.zzzodLanguageEn'), value: 'en' },
]
// options 表派生 value→label 映射（备份预览反显共用，避免枚举双份维护）
const gameRegionLabels: Record<string, string> = Object.fromEntries(
  gameRegionOptions.map(o => [o.value, o.label])
)
const gameLanguageLabels: Record<string, string> = Object.fromEntries(
  gameLanguageOptions.map(o => [o.value, o.label])
)

// 用户名失焦：同脚本内禁止重名（绑定槽名与统计都依赖名字区分）
// 上次查重并写回过的用户名；值没变时不再重复拉全部用户查重
let lastCheckedUserName = ''
const handleNameBlur = async () => {
  const name = formData.userName.trim()
  if (!name || name === lastCheckedUserName) return
  try {
    const resp = await getUsers(scriptId)
    const duplicate = Object.entries(resp?.data ?? {}).some(
      ([uid, user]) =>
        uid !== userId.value &&
        String((user as { Info?: { Name?: string } })?.Info?.Name ?? '').trim() ===
          name
    )
    if (duplicate) {
      message.error(t('edit.zzzodDuplicateUserName'))
      return
    }
  } catch (e) {
    logger.warn(e instanceof Error ? e.message : String(e))
  }
  lastCheckedUserName = name
  await saveField('Info.Name', formData.userName)
}

const createUserImmediately = async (): Promise<boolean> => {
  const resp = await addUser(scriptId, { showError: false })
  if (!resp?.userId) {
    message.error(userApiError.value || t('edit.couldNotCreateUser'))
    handleCancel()
    return false
  }
  userId.value = resp.userId
  isEdit.value = true
  await router.replace({
    name: 'ZzzOdUserEdit',
    params: { scriptId, userId: userId.value },
  })
  return true
}

// 保存串行化队列：以 promise 链取代布尔互斥，连续保存按序写回不丢
let saveChain: Promise<boolean> = Promise.resolve(true)

const saveField = (key: string, value: unknown): Promise<boolean> => {
  if (isInitializing.value || !userId.value) return Promise.resolve(false)

  const parts = key.split('.')
  const patch: Record<string, any> = {}
  let current = patch
  for (let i = 0; i < parts.length - 1; i += 1) {
    current[parts[i]] = {}
    current = current[parts[i]]
  }
  current[parts[parts.length - 1]] = value

  if (key === 'Info.Name') {
    formData.userName = String(value || '')
  }

  const persist = async (): Promise<boolean> => {
    try {
      const ok = await updateUser(scriptId, userId.value, patch)
      if (!ok) {
        logger.error(`保存字段「${key}」失败: ${userApiError.value || '未知错误'}`)
      }
      return ok
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
      return false
    }
  }

  const run = saveChain.then(persist, persist)
  saveChain = run
  return run
}

const handleConfigModeChange = async (value: boolean | string) => {
  if (typeof value !== 'string' || !['用户', '直控'].includes(value)) return
  const prev = formData.Info.Mode
  if (value === '直控' && prev !== '直控') {
    // 每脚本仅允许一个直控用户：直控是脚本级全局视图（实例/活跃/运行实例
    // 都是一份 one_dragon.yml），多直控用户共享状态互相干扰
    try {
      const resp = await getUsers(scriptId)
      const hasOtherDirect = Object.entries(resp?.data ?? {}).some(
        ([uid, user]) =>
          uid !== userId.value &&
          String((user as { Info?: { Mode?: string } })?.Info?.Mode ?? '') ===
            '直控'
      )
      if (hasOtherDirect) {
        formData.Info.Mode = prev
        message.error(t('edit.zzzodDirectModeLimit'))
        return
      }
    } catch (e) {
      logger.warn(e instanceof Error ? e.message : String(e))
    }
  }
  formData.Info.Mode = value as '用户' | '直控'
  await saveField('Info.Mode', formData.Info.Mode)
  if (value === '直控') {
    // 进入直控：公共初始化（备份 + 默认实例 + 加载原生配置）
    await enterDirectMode()
  } else if (prev === '直控') {
    // 离开直控（切回用户）：补一份「配置完成时」的备份
    await ensureDirectBackup()
  }
}

/** 直控/用户共用的按需归档入口（通用 /backup/ensure 三时机，指纹去重）。
 * onedragon=一条龙原生配置当前状态；mas=绑定槽 MAS 终态（未绑定槽跳过） */
const ensurePoolBackup = async (target: string): Promise<void> => {
  if (!userId.value) return
  try {
    const resp = await Service.ensureConfigBackupApiApiScriptsBackupEnsurePost({
      scriptId,
      userId: userId.value,
      target,
    })
    if (resp.code !== 200) throw new Error(resp.message || t('edit.zzzodBackupFailed'))
  } catch (e) {
    // 备份失败不阻断使用，但向用户提示（防止误以为有恢复点）
    logger.warn(e instanceof Error ? e.message : String(e))
    message.warning(t('edit.zzzodBackupFailed'))
  }
}

/** 一条龙原生配置按需归档（进入直控/用户编辑页、退出直控时调用） */
const ensureDirectBackup = () => ensurePoolBackup('onedragon')

/** 用户模式退出时机：归档绑定槽 MAS 终态 + 一条龙原生配置终态（编辑会话包络） */
const ensureUserExitBackups = () =>
  Promise.all([ensurePoolBackup('mas'), ensurePoolBackup('onedragon')])

/** 进入直控的公共初始化（模式切换与页面加载共用）：
 * 补「改动前」备份 → 默认选第一个实例 → 加载所选实例原生配置 */
const enterDirectMode = async () => {
  await ensureDirectBackup()
  if (nativeInstanceIdx.value === null && instances.value.length) {
    nativeInstanceIdx.value = instances.value[0].idx
  }
  if (nativeInstanceIdx.value !== null) {
    await loadNativeConfig(nativeInstanceIdx.value)
  }
}

// ══ 实例列表（直控「选择实例」来源）══
const instances = ref<ZzzOdInstanceOut[]>([])
const instancesLoading = ref(false)

const instanceOptions = computed(() =>
  instances.value.map(item => ({
    label: `${String(item.idx).padStart(2, '0')} - ${item.name}`,
    value: item.idx,
  }))
)

const loadInstances = async () => {
  instancesLoading.value = true
  try {
    const resp = await Service.getZzzodInstancesApiApiScriptsZzzodInstancesGet(scriptId)
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.zzzodLoadInstancesFailed'))
    }
    instances.value = resp.data || []
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
  } finally {
    instancesLoading.value = false
  }
}

// ══ 实例管理（直控：添加 / 重命名 / 删除 / 参与「全部实例」开关，实时写回 one_dragon.yml）══
const instanceName = ref('')
const addInstanceOpen = ref(false)
const renameInstanceOpen = ref(false)
const renameTarget = ref<ZzzOdInstanceOut | null>(null)
const instanceOpLoading = ref(false)

const openAddInstance = () => {
  instanceName.value = ''
  addInstanceOpen.value = true
}

const confirmAddInstance = async () => {
  const name = instanceName.value.trim()
  if (!name) {
    message.error(t('edit.zzzodInstanceNameRequired'))
    return
  }
  instanceOpLoading.value = true
  try {
    const resp = await Service.addZzzodInstanceApiApiScriptsZzzodInstancesAddPost({
      scriptId,
      name,
    })
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.zzzodAddInstanceFailed'))
    }
    instances.value = resp.data || []
    addInstanceOpen.value = false
    // 选中新实例并加载其原生配置（账号/任务区跟随切换）
    const added = [...instances.value].reverse().find(item => item.name === name)
    if (added) {
      nativeInstanceIdx.value = added.idx
      await loadNativeConfig(added.idx)
    }
    message.success(t('edit.zzzodAddInstanceSuccess'))
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('edit.zzzodAddInstanceFailed'))
  } finally {
    instanceOpLoading.value = false
  }
}

const openRenameInstance = (inst: ZzzOdInstanceOut) => {
  renameTarget.value = inst
  instanceName.value = inst.name
  renameInstanceOpen.value = true
}

const confirmRenameInstance = async () => {
  const target = renameTarget.value
  const name = instanceName.value.trim()
  if (!target || !name) {
    message.error(t('edit.zzzodInstanceNameRequired'))
    return
  }
  instanceOpLoading.value = true
  try {
    const resp = await Service.renameZzzodInstanceApiApiScriptsZzzodInstancesRenamePost({
      scriptId,
      instanceIdx: target.idx,
      name,
    })
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.zzzodRenameInstanceFailed'))
    }
    instances.value = resp.data || []
    renameInstanceOpen.value = false
    renameTarget.value = null
    message.success(t('edit.zzzodRenameInstanceSuccess'))
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('edit.zzzodRenameInstanceFailed'))
  } finally {
    instanceOpLoading.value = false
  }
}

const openDeleteInstance = (inst: ZzzOdInstanceOut) => {
  Modal.confirm({
    title: t('edit.zzzodDeleteInstance'),
    content: h(
      'p',
      { style: { color: 'var(--ant-color-error)', margin: 0 } },
      t('edit.zzzodDeleteInstanceConfirm', {
        inst: `${String(inst.idx).padStart(2, '0')} - ${inst.name}`,
      })
    ),
    okText: t('edit.zzzodDeleteInstance'),
    okButtonProps: { danger: true },
    onOk: () => deleteInstance(inst),
  })
}

const deleteInstance = async (inst: ZzzOdInstanceOut) => {
  instanceOpLoading.value = true
  try {
    const resp = await Service.deleteZzzodInstanceApiApiScriptsZzzodInstancesDeletePost({
      scriptId,
      instanceIdx: inst.idx,
    })
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.zzzodDeleteInstanceFailed'))
    }
    instances.value = resp.data || []
    if (nativeInstanceIdx.value === inst.idx) {
      // 所选实例被删：清空原生配置编辑区（运行实例是全局设置，不重置）
      nativeInstanceIdx.value = null
      nativeAccountFields.value = []
      Object.keys(nativeAccountValues).forEach(k => delete nativeAccountValues[k])
      nativeTasks.value = []
    }
    message.success(t('edit.zzzodDeleteInstanceSuccess'))
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('edit.zzzodDeleteInstanceFailed'))
  } finally {
    instanceOpLoading.value = false
  }
}

const toggleInstanceActiveInOd = async (inst: ZzzOdInstanceOut, value: boolean) => {
  try {
    const resp = await Service.setZzzodInstanceActiveInOdApiApiScriptsZzzodInstancesActiveInOdPost({
      scriptId,
      instanceIdx: inst.idx,
      activeInOd: value,
    })
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.zzzodInstanceFlagFailed'))
    }
    instances.value = resp.data || []
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('edit.zzzodInstanceFlagFailed'))
  }
}

/** 切换实例「运行前切换账号」：一条龙原生能力（force_login_before_run），MAS 不干涉 */
const toggleInstanceForceLogin = async (inst: ZzzOdInstanceOut, value: boolean) => {
  try {
    const resp = await Service.setZzzodInstanceForceLoginApiApiScriptsZzzodInstancesForceLoginPost({
      scriptId,
      instanceIdx: inst.idx,
      forceLogin: value,
    })
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.zzzodInstanceForceLoginFailed'))
    }
    instances.value = resp.data || []
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('edit.zzzodInstanceForceLoginFailed'))
  }
}

/** 运行前切换账号/多账号切换需要完整登录信息；B服实例用 B服账号名，其余用账号+密码 */
const isRequiredAccountKey = (key: string) => {
  if (nativeAccountValues.game_region === 'cn_b') {
    return key === 'bilibili_account_name'
  }
  return key === 'account' || key === 'password'
}

/** 显式设为当前活跃：「仅运行当前」运行时跑的就是它；直控页编辑不自动改活跃 */
const setActiveInstance = async (inst: ZzzOdInstanceOut) => {
  instanceOpLoading.value = true
  try {
    const resp = await Service.setZzzodActiveInstanceApiApiScriptsZzzodInstancesSetActivePost({
      scriptId,
      instanceIdx: inst.idx,
    })
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.zzzodSetActiveInstanceFailed'))
    }
    instances.value = resp.data || []
    message.success(t('edit.zzzodSetInstanceActiveSuccess', { name: inst.name }))
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('edit.zzzodSetActiveInstanceFailed'))
  } finally {
    instanceOpLoading.value = false
  }
}

// ══ 快速导入配置：左侧母版下拉 + 右侧导入按钮共同构成导入功能 ══
// 当前选中的母版（来源）实例；导入成功后复位
const importSourceIdx = ref<number | null>(null)
const importLoading = ref(false)
// 预备编队组件引用：导入整体覆盖槽配置后需要强制刷新编队显示
const teamsRef = ref<InstanceType<typeof ZzzOdPredefinedTeams> | null>(null)

// 点击「导入」：确认将用母版实例覆盖当前独立用户配置后再执行
// （后端在覆盖前会强制归档当前 MAS 配置，可在「配置恢复」中找回）
const confirmImport = () => {
  if (importSourceIdx.value === null) return
  Modal.confirm({
    title: t('edit.zzzodImportConfirmTitle'),
    content: t('edit.zzzodImportConfirmDesc'),
    okText: t('edit.zzzodImport'),
    onOk: () => importFromInstance(),
  })
}

const importFromInstance = async () => {
  const sourceIdx = importSourceIdx.value
  if (sourceIdx === null || !userId.value) return
  importLoading.value = true
  try {
    const resp = await Service.importZzzodConfigApiApiScriptsZzzodImportPost({
      scriptId,
      userId: userId.value,
      instanceIdx: sourceIdx,
    })
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.zzzodImportFailed'))
    }
    importSourceIdx.value = null
    // 后端已写入账号字段、任务编排与实例级配置（含预备编队），
    // 重新拉取让表单与后端一致，预备编队组件一并强制刷新
    await loadUserData()
    teamsRef.value?.reload()
    message.success(t('edit.zzzodImportSuccess'))
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('edit.zzzodImportFailed'))
  } finally {
    importLoading.value = false
  }
}

// ══ 一条龙启动器安装情况（两态通用下拉：未安装的选项禁用变灰）══
const launchersLoading = ref(false)
// 安装信息是否已拉取完成（拉失败视为都未安装，选项全部禁用）
const launchersReady = ref(false)
const launcherOriginal = ref(false)
const launcherIntegrated = ref(false)
const launchersUsable = computed(() => ({
  smart: launcherOriginal.value || launcherIntegrated.value,
  original: launcherOriginal.value,
  integrated: launcherIntegrated.value,
}))

const loadLaunchers = async () => {
  launchersLoading.value = true
  try {
    const resp = await Service.getZzzodLaunchersApiApiScriptsZzzodLaunchersGet(
      scriptId
    )
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.zzzodLauncherLoadFailed'))
    }
    launcherOriginal.value = resp.original_available
    launcherIntegrated.value = resp.integrated_available
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
  } finally {
    launchersLoading.value = false
    launchersReady.value = true
  }
}

// ══ 直控：所选实例的原生配置（强绑定一条龙原始 YAML，页面即改原生）══
const nativeInstanceIdx = ref<number | null>(null)
// 运行实例（value 为一条龙原生中文取值，label 走词表；初始值对齐上游
// InstanceRun.ALL 默认，加载后由后端返回值覆盖）
const nativeInstanceRun = ref('全部实例')
const instanceRunOptions = [
  { label: t('edit.zzzodInstanceRunCurrent'), value: '仅运行当前' },
  { label: t('edit.zzzodInstanceRunAll'), value: '全部实例' },
]
const nativeLoading = ref(false)
const nativeSaving = ref(false)
const nativeAccountFields = ref<ZzzOdNativeAccountField[]>([])
const nativeAccountValues = reactive<Record<string, string>>({})
const nativeTasks = ref<TaskCard[]>([])

const applyNativeConfig = (data: ZzzOdNativeConfigOut) => {
  nativeAccountFields.value = data.account ?? []
  const values: Record<string, string> = {}
  for (const f of data.account ?? []) {
    if (f.value != null) values[f.key] = String(f.value)
  }
  Object.keys(nativeAccountValues).forEach(k => delete nativeAccountValues[k])
  Object.assign(nativeAccountValues, values)
  nativeInstanceRun.value = data.instanceRun || '全部实例'
  nativeTasks.value = toTaskCards(data.tasks ?? [])
}

const loadNativeConfig = async (instanceIdx: number) => {
  nativeLoading.value = true
  try {
    const resp = await Service.getZzzodNativeConfigApiApiScriptsZzzodNativeConfigGet(
      scriptId,
      instanceIdx
    )
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.zzzodNativeLoadFailed'))
    }
    applyNativeConfig(resp)
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('edit.zzzodNativeLoadFailed'))
    nativeAccountFields.value = []
    nativeTasks.value = []
  } finally {
    nativeLoading.value = false
  }
}

const handleNativeInstanceChange = async (instanceIdx: number) => {
  if (instanceIdx == null) {
    nativeAccountFields.value = []
    nativeTasks.value = []
    return
  }
  await loadNativeConfig(instanceIdx)
}

/** 运行实例（仅运行当前/全部启用实例）是 one_dragon.yml 全局设置，
 * 与直控页当前编辑哪个实例无关，独立保存 */
const runModeSaving = ref(false)
const handleNativeInstanceRunChange = async () => {
  runModeSaving.value = true
  try {
    const resp = await Service.setZzzodInstanceRunModeApiApiScriptsZzzodInstancesRunModePost({
      scriptId,
      instanceRun: nativeInstanceRun.value,
    })
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.zzzodNativeSaveFailed'))
    }
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('edit.zzzodNativeSaveFailed'))
  } finally {
    runModeSaving.value = false
  }
}

/** 直控按需保存：只提交指定区块并只回读该区块。
 *
 *  - 账号字段（「保存设置」按钮）：全量提交 account + tasks + instanceRun；
 *  - 任务开关/排序、运行实例：即时增量提交对应字段——不把未保存的账号
 *    草稿一并落盘或覆盖。
 */
type NativeSaveSection = 'all' | 'tasks'
/** 提交给后端的任务条目（后端只认 app_id/enabled） */
const toNativeTaskIn = (list: TaskCard[]): { app_id: string; enabled: boolean }[] =>
  list.map(t => ({ app_id: t.app_id, enabled: !!t.enabled }))

/** 后端任务条目 → 卡片（加载与保存回读共用） */
const toTaskCards = (tasks: NonNullable<ZzzOdNativeConfigOut['tasks']>) =>
  tasks.map(
    t =>
      ({
        app_id: t.app_id,
        app_name: t.app_name,
        enabled: !!t.enabled,
        configurable: t.configurable,
        jump: t.jump,
      }) as TaskCard
  )
const saveNativeConfig = async (
  payload: {
    account?: Record<string, string>
    tasks?: { app_id: string; enabled: boolean }[]
    instanceRun?: string
  },
  section: NativeSaveSection = 'all',
  silent = false
): Promise<boolean> => {
  if (nativeInstanceIdx.value === null) return false
  nativeSaving.value = true
  try {
    const resp = await Service.saveZzzodNativeConfigApiApiScriptsZzzodNativeConfigSavePost({
      scriptId,
      instanceIdx: nativeInstanceIdx.value,
      ...payload,
    })
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.zzzodNativeSaveFailed'))
    }
    if (section === 'tasks') {
      nativeTasks.value = toTaskCards(resp.tasks ?? [])
    } else {
      applyNativeConfig(resp)
    }
    if (!silent) message.success(t('edit.zzzodNativeSaved'))
    return true
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('edit.zzzodNativeSaveFailed'))
    return false
  } finally {
    nativeSaving.value = false
  }
}

/** 「保存设置」：账号字段全量写回（连同当前任务编排与运行实例，保持表单一致） */
const saveNativeAccount = () =>
  saveNativeConfig(
    {
      account: { ...nativeAccountValues },
      tasks: toNativeTaskIn(nativeTasks.value),
      instanceRun: nativeInstanceRun.value,
    },
    'all'
  )

/** 弹出文件选择并校验为 ZenlessZoneZero.exe，取消/选错返回 null（两处共用） */
const pickZzzGameExe = async (): Promise<string | null> => {
  const paths = await window.electronAPI?.selectFile([
    {
      name: 'ZenlessZoneZero.exe',
      extensions: ['exe'],
    },
  ])
  const path = paths?.[0]
  if (!path) return null
  const fileName = path.split(/[\\/]/).pop()
  if (fileName?.toLowerCase() !== 'zenlesszonezero.exe') {
    message.error(t('edit.zzzodPickGameExe'))
    return null
  }
  return path
}

const selectDirectGamePath = async () => {
  const path = await pickZzzGameExe()
  if (path) nativeAccountValues.game_path = path
}

// ══ 任务目录（中文名渲染；一条龙系列 = zzz-od 默认编组应用）══
interface ZzzOdCatalogItem {
  app_id: string
  app_name: string
  default_group: boolean
  configurable?: boolean
  jump?: boolean
  priority: number
}

const catalog = ref<ZzzOdCatalogItem[]>([])

const loadCatalog = async () => {
  try {
    const resp = await Service.getZzzodCatalogApiApiScriptsZzzodCatalogGet(scriptId)
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.zzzodLoadOneDragonFailed'))
    }
    catalog.value = resp.data || []
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
  }
}

// ══ 任务卡片 ⚙：可配置任务弹出选项编辑（数据驱动元数据表）══
// 字段类型决定渲染：select/team 下拉 / bool 开关 / number 数字；
// plan_list（体力刷本/恶名狩猎）不走弹层，⚙ 打开计划编辑弹窗
interface TaskConfigField {
  field: string
  title: string
  type: 'select' | 'bool' | 'number' | 'team' | 'plan_list'
  value: any
  options: { label: string; value: string }[]
  columns?: any[]
  newItem?: Record<string, any>
}

const taskConfigData = ref<Record<string, TaskConfigField[]>>({})
const taskConfigLoading = ref<Record<string, boolean>>({})
const taskPopoverOpen = ref<Record<string, boolean>>({})
// 提示框受控：点击按钮后隐藏，避免盖住弹出的选项框（再次悬停恢复）
const taskTipVisible = ref<Record<string, boolean>>({})
const jumpTipVisible = ref<Record<string, boolean>>({})

const setTaskLoading = (appId: string, loading: boolean) => {
  taskConfigLoading.value = { ...taskConfigLoading.value, [appId]: loading }
}

const setPopoverOpen = (appId: string, open: boolean) => {
  taskPopoverOpen.value = { ...taskPopoverOpen.value, [appId]: open }
}

/** 拉取任务配置字段（直控读所选实例原生 yml；用户读绑定槽） */
const loadTaskConfig = async (card: TaskCard): Promise<TaskConfigField[]> => {
  const instanceIdx = formData.Info.Mode === '直控' ? nativeInstanceIdx.value : null
  const resp = await Service.getZzzodAppConfigApiApiScriptsZzzodAppConfigGet(
    scriptId,
    userId.value,
    card.app_id,
    instanceIdx
  )
  if (resp.code !== 200) {
    throw new Error(resp.message || t('edit.zzzodTaskConfigLoadFailed'))
  }
  const fields = (resp.fields ?? []) as TaskConfigField[]
  taskConfigData.value = { ...taskConfigData.value, [card.app_id]: fields }
  return fields
}

/** ⚙ 点击（popover 受控模式）：plan_list 或字段较多（大设置）打开编辑弹窗，否则弹出层 */
const handleTaskPopoverChange = async (card: TaskCard, open: boolean) => {
  if (!open) {
    setPopoverOpen(card.app_id, false)
    return
  }
  // 隐藏悬停提示，避免盖住弹出的选项框
  taskTipVisible.value = { ...taskTipVisible.value, [card.app_id]: false }
  setTaskLoading(card.app_id, true)
  try {
    const fields = await loadTaskConfig(card)
    const useModal =
      fields.some(f => f.type === 'plan_list') || fields.length > 6
    if (useModal) {
      void openPlanModal(card, fields)
    } else {
      setPopoverOpen(card.app_id, true)
    }
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('edit.zzzodTaskConfigLoadFailed'))
  } finally {
    setTaskLoading(card.app_id, false)
  }
}

/** 数值框保存策略：@change 防抖合并（stepper 连点/长按自动步进/键入各合并
 * 为一次请求），失焦立即落盘待保存值；清空/纯空白/值未变由
 * saveTaskConfigField 守卫拦下 */
const TASK_CONFIG_SAVE_DELAY = 600
interface PendingTaskConfigSave {
  timer: ReturnType<typeof setTimeout>
  card: TaskCard
  field: TaskConfigField
  value: any
}
const taskConfigPending = new Map<string, PendingTaskConfigSave>()

const taskConfigKey = (card: TaskCard, field: TaskConfigField) =>
  `${card.app_id}::${field.field}`

const scheduleTaskConfigSave = (
  card: TaskCard,
  field: TaskConfigField,
  value: any
) => {
  const key = taskConfigKey(card, field)
  const existing = taskConfigPending.get(key)
  if (existing) clearTimeout(existing.timer)
  const timer = setTimeout(() => {
    taskConfigPending.delete(key)
    void saveTaskConfigField(card, field, value)
  }, TASK_CONFIG_SAVE_DELAY)
  taskConfigPending.set(key, { timer, card, field, value })
}

const flushTaskConfigSave = (card: TaskCard, field: TaskConfigField) => {
  const pending = taskConfigPending.get(taskConfigKey(card, field))
  if (!pending) return
  clearTimeout(pending.timer)
  taskConfigPending.delete(taskConfigKey(card, field))
  void saveTaskConfigField(pending.card, pending.field, pending.value)
}

const flushAllTaskConfigSaves = () => {
  for (const pending of [...taskConfigPending.values()]) {
    clearTimeout(pending.timer)
    void saveTaskConfigField(pending.card, pending.field, pending.value)
  }
  taskConfigPending.clear()
}

const saveTaskConfigField = async (
  card: TaskCard,
  field: TaskConfigField,
  value: any
) => {
  // 数值框清空（change 拿到 null/空串/纯空白）与 NaN 一律不发请求（后端
  // int(null/'' ) 报 400）；值未变跳过——Tab 经过或步进回原值时不发多余请求
  if (value === null || value === undefined || Number.isNaN(value)) return
  if (typeof value === 'string' && value.trim() === '') return
  if (Number(value) === Number(field.value)) return
  try {
    const resp = await Service.saveZzzodAppConfigApiApiScriptsZzzodAppConfigSavePost({
      scriptId,
      userId: userId.value,
      appId: card.app_id,
      values: { [field.field]: value },
      instanceIdx: formData.Info.Mode === '直控' ? nativeInstanceIdx.value : undefined,
    })
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.zzzodTaskConfigSaveFailed'))
    }
    field.value = value
    message.success(t('edit.zzzodTaskConfigSaved'))
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('edit.zzzodTaskConfigSaveFailed'))
  }
}

// ══ 任务计划编辑弹窗（plan_list 大设置）══
const planModal = reactive({
  open: false,
  loading: false,
  saving: false,
  appId: '',
  title: '',
  fields: [] as TaskConfigField[],
  draft: [] as Record<string, any>[],
  trainCategories: [] as any[],
})

const planModalField = computed(
  () => planModal.fields.find(f => f.type === 'plan_list') ?? null
)
const planModalOtherFields = computed(() =>
  planModal.fields.filter(f => f.type !== 'plan_list')
)

const openPlanModal = async (card: TaskCard, fields?: TaskConfigField[]) => {
  planModal.appId = card.app_id
  planModal.title = card.app_name
  planModal.open = true
  planModal.loading = true
  try {
    const loaded = fields ?? (await loadTaskConfig(card))
    planModal.fields = loaded
    const planField = loaded.find(f => f.type === 'plan_list')
    planModal.draft = ((planField?.value as any[]) ?? []).map(p => ({ ...p }))
    if (planField) {
      const resp = await Service.getZzzodTaskOptionsApiApiScriptsZzzodOptionsGet(
        scriptId,
        card.app_id
      )
      if (resp.code !== 200) {
        throw new Error(resp.message || t('edit.zzzodTaskConfigLoadFailed'))
      }
      planModal.trainCategories = resp.trainCategories ?? []
    }
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('edit.zzzodTaskConfigLoadFailed'))
    planModal.open = false
  } finally {
    planModal.loading = false
  }
}

/** 弹窗保存：plan_list 提交整表（后端按 plan_id 保留已运行进度），其余字段提交当前值 */
const savePlanModal = async () => {
  planModal.saving = true
  try {
    const values: Record<string, any> = {}
    for (const f of planModal.fields) {
      if (f.type === 'plan_list') {
        values[f.field] = planModal.draft.map(({ __key, ...rest }) => rest)
      } else {
        values[f.field] = f.value
      }
    }
    const resp = await Service.saveZzzodAppConfigApiApiScriptsZzzodAppConfigSavePost({
      scriptId,
      userId: userId.value,
      appId: planModal.appId,
      values,
      instanceIdx: formData.Info.Mode === '直控' ? nativeInstanceIdx.value : undefined,
    })
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.zzzodTaskConfigSaveFailed'))
    }
    planModal.open = false
    message.success(t('edit.zzzodTaskConfigSaved'))
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('edit.zzzodTaskConfigSaveFailed'))
  } finally {
    planModal.saving = false
  }
}

// ══ 配置恢复（通用组件 props 供给：双目标 MAS 在前脚本在后）══
// 专项统一名（文案参数化用）：zzz-od 统一叫「一条龙」，其他适配器各自传自己的名字
const ZZZOD_DISPLAY_NAME = '一条龙'
const restoreOpen = ref(false)

// 目标池顺序 = segmented 展示顺序：MAS 用户配置（在前）、一条龙原生配置（在后）
const restoreTargets: Array<{ key: 'mas' | 'onedragon'; kind: 'user' | 'script' }> = [
  { key: 'mas', kind: 'user' },
  { key: 'onedragon', kind: 'script' },
]

// 预览字段标签（组件展示账号明细用）
const previewFieldLabels: Record<string, string> = {
  game_region: t('edit.zzzodGameRegion'),
  game_path: t('edit.zzzodGamePath'),
  game_language: t('edit.zzzodGameLanguage'),
  account: t('edit.zzzodAccount'),
  password: t('edit.password'),
  bilibili_account_name: t('edit.zzzodBilibiliAccount'),
}

// 枚举值为后端/一条龙原生取值（驱动文案映射需保持原样），展示走词表
const formatPreviewValue = (key: string, raw: string): string => {
  switch (key) {
    case 'status':
      // 后端传 str(bool)（"True"/"False"），大小写与 YAML 表示不定，统一小写比较
      return raw.toLowerCase() === 'true' ? t('edit.yes') : t('edit.no')
    case 'mode':
      return raw === '用户'
        ? t('edit.zzzodModeUser')
        : raw === '直控'
          ? t('edit.directControl')
          : raw
    case 'launcher_mode':
      return raw === '自动'
        ? t('edit.zzzodLauncherAuto')
        : raw === '原始'
          ? t('edit.zzzodLauncherOriginal')
          : raw === '集成'
            ? t('edit.zzzodLauncherIntegrated')
            : raw
    case 'remained_day':
      return raw === '-1' ? t('edit.zzzodPreviewUnlimited') : raw
    case 'push_log_mode':
      return raw === '关闭'
        ? t('edit.pushLogModeOff')
        : raw === '逐条'
          ? t('edit.pushLogModeList')
          : raw === '汇总'
            ? t('edit.pushLogModeSummary')
            : raw
    case 'game_region':
      return gameRegionLabels[raw] ?? raw
    case 'game_language':
      return gameLanguageLabels[raw] ?? raw
    default:
      return raw || '—'
  }
}

// 组件调用后端：通用 /backup/* 端点（脚本/用户上下文在此闭包捕获）
const restoreApi = {
  list: async (target: string) =>
    Service.listConfigBackupsApiApiScriptsBackupListGet(
      scriptId,
      userId.value,
      target
    ),
  preview: async (target: string, time: string) =>
    Service.getConfigBackupPreviewApiApiScriptsBackupPreviewGet(
      scriptId,
      userId.value,
      time,
      target
    ),
  restore: async (target: string, time: string) =>
    Service.restoreConfigBackupApiApiScriptsBackupRestorePost({
      scriptId,
      userId: userId.value,
      time,
      target,
    }),
}

const openRestoreModal = () => {
  restoreOpen.value = true
}

// 一键恢复成功：MAS 恢复含字段回填，刷新表单；一条龙恢复不回填 MAS 字段，
// 但直控页表单（账号/任务/运行实例读自原生文件）必须重拉，否则旧表单值在
// 下次「保存设置」时全量写回、静默撤销刚做的恢复（用户模式 AppList 同理）
const handleRestored = (target: string) => {
  restoreOpen.value = false
  if (target === 'mas') {
    void loadUserData()
  } else if (formData.Info.Mode === '直控' && nativeInstanceIdx.value !== null) {
    void loadNativeConfig(nativeInstanceIdx.value)
  } else {
    void loadUserData()
  }
}

const handleRestoreView = (target: string, item: { time: string }) => {
  const isMas = target === 'mas'
  // 「查看详细配置」语义：恢复该时点 + 拉起对应会话查看。弹窗文案与
  // 「一键恢复」必须显式区分——预览弹窗里的「查看详细配置」按钮极易被
  // 误以为只读，实际会真覆盖当前配置并拉起查看会话；查看会话结束前
  // 切任务开关会写回旧 AppList，导致恢复被静默撤销。
  Modal.confirm({
    title: t('edit.configRestoreDetailView'),
    content: h(
      'p',
      { style: { color: 'var(--ant-color-error)', margin: 0 } },
      t('edit.configRestoreDetailConfirm', { script: ZZZOD_DISPLAY_NAME })
    ),
    okText: t('edit.configRestoreConfirmOk'),
    cancelText: t('edit.cancel'),
    onOk: async () => {
      try {
        const resp = await Service.restoreConfigBackupApiApiScriptsBackupRestorePost({
          scriptId,
          userId: userId.value,
          time: item.time,
          target,
        })
        // 后端失败走 HTTP 200 + body code=400，须显式检查返回体：槽绑定守卫等
        // 抛错若被吞掉，会照常关弹窗并打开查看会话，显示的是没被恢复的当前配置
        if (resp.code !== 200) {
          throw new Error(resp.message || t('edit.configRestoreFailed'))
        }
        restoreOpen.value = false
        if (isMas) {
          // MAS 备份预览：只读会话打开一条龙，合成视图下看到的是 MAS 实例
          // （槽内容即恢复的备份，不注入基线、不回读字段）
          await startSession(userId.value, true)
        } else {
          // 一条龙备份预览：脚本级原生会话，看到的是一条龙自己的原生实例，
          // 与 MAS 侧完全无关
          await startSession(scriptId, true)
        }
      } catch (e) {
        message.error(e instanceof Error ? e.message : t('edit.configRestoreFailed'))
      }
    },
  })
}

// ══ 一条龙任务（OneDragon.AppList JSON 字段，打开页面即可开关）══
// 卡片结构与操作封装见 useZzzOdTaskBoard（用户模式与直控模式共用）
type TaskCard = ZzzOdTaskCard

const savedApps = computed<{ app_id: string; enabled: boolean }[]>(() => {
  try {
    const parsed = JSON.parse(formData.OneDragon.AppList || '[]')
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
})

const taskCards = computed<TaskCard[]>(() => {
  const nameBook = new Map(
    catalog.value.map(item => [
      item.app_id,
      { name: item.app_name, configurable: item.configurable, jump: item.jump },
    ])
  )
  // AppList 全量条目按原顺序渲染（含未启用项原位保留，对齐原生队列语义）
  const cards: TaskCard[] = savedApps.value
    .filter(item => item && typeof item.app_id === 'string')
    .map(item => ({
      app_id: item.app_id,
      app_name: nameBook.get(item.app_id)?.name ?? item.app_id,
      enabled: !!item.enabled,
      configurable: nameBook.get(item.app_id)?.configurable,
      jump: nameBook.get(item.app_id)?.jump,
    }))
  // 只把一条龙系列（zzz-od 默认编组）任务作为可选项；独立工具应用不入列
  const known = new Set(cards.map(card => card.app_id))
  for (const item of catalog.value) {
    if (item.default_group && !known.has(item.app_id)) {
      cards.push({
        app_id: item.app_id,
        app_name: item.app_name,
        enabled: false,
        configurable: item.configurable,
        jump: item.jump,
      })
    }
  }
  return cards
})

/** 当前模式展示的任务卡片：用户=MAS 字段编排；直控=所选实例的原生编排 */
const activeTaskCards = computed<TaskCard[]>(() =>
  formData.Info.Mode === '直控' ? nativeTasks.value : taskCards.value
)

/** 拖拽排序的渲染数据源：跟随当前模式任务列表，拖拽过程由 vuedraggable 就地更新 */
const taskDragCards = ref<TaskCard[]>([])

watch(
  activeTaskCards,
  cards => {
    taskDragCards.value = cards
  },
  { immediate: true }
)

const persistAppList = (list: { app_id: string; enabled: boolean }[]) => {
  formData.OneDragon.AppList = JSON.stringify(list)
  void saveField('OneDragon.AppList', formData.OneDragon.AppList)
}

/** 按当前模式落盘任务看板：直控写实例原生编排；用户模式写 AppList 字段 */
const commitTaskBoard = (list: TaskCard[]) => {
  if (formData.Info.Mode === '直控') {
    nativeTasks.value = list
    void saveNativeConfig({ tasks: toNativeTaskIn(list) }, 'tasks', true)
    return
  }
  persistAppList(list.map(card => ({ app_id: card.app_id, enabled: !!card.enabled })))
}

// 任务看板共用操作（开关/拖拽/一键整理），两种模式仅落盘方式不同
const {
  toggle: toggleTask,
  commitDragOrder: handleTaskDragEnd,
  sortEnabledFirst: handleSortTasks,
} = useZzzOdTaskBoard(taskDragCards, {
  editable: () => !isInitializing.value && !pageLoading.value,
  commit: commitTaskBoard,
})

// ══ 原生 GUI 设置会话（直控模式专用；viewOnly 为只读查看会话）══
const {
  zzzodConfigLoading,
  zzzodWebsocketId,
  showZzzodConfigMask,
  showZzzodViewMask,
  stoppingZzzodConfig,
  startSession,
  saveSession,
  stopSession,
} = useZzzodGuiSession()

const handleZzzodConfig = () => {
  if (formData.Info.Mode === '直控') {
    // 直控：拉起脚本级原生会话——完整原生实例列表，不隔离、不注入，
    // 界面里的改动即真实落地一条龙原始配置（会话关闭后页面自动刷新）。
    // 传当前编辑实例：会话窗口临时切活跃到它（GUI 打开即所见实例，结束还原）
    void startSession(scriptId, false, nativeInstanceIdx.value)
    return
  }
  if (!userId.value) return
  void startSession(userId.value)
}

const handleSaveZzzodConfig = () => {
  void saveSession()
}

const handleCloseZzzodView = () => {
  void stopSession()
}

const handleCancel = async () => {
  await stopSession()
  await router.push('/scripts')
}

const selectGamePath = async () => {
  const path = await pickZzzGameExe()
  if (!path) return
  formData.Game.GamePath = path
  void saveField('Game.GamePath', path)
}

const loadScriptInfo = async (): Promise<boolean> => {
  const detail = await getScript(scriptId)
  if (!detail || detail.type !== 'ZzzOd') {
    message.error(t('edit.zzzodScriptNotFound'))
    handleCancel()
    return false
  }

  scriptName.value = detail.name
  return true
}

const applyUserData = (userData: ZzzOdUserConfig) => {
  Object.assign(formData, {
    Info: { ...getDefaultUserData().Info, ...(userData.Info || {}) },
    Game: { ...getDefaultUserData().Game, ...(userData.Game || {}) },
    OneDragon: { ...getDefaultUserData().OneDragon, ...(userData.OneDragon || {}) },
    Notify: { ...getDefaultUserData().Notify, ...(userData.Notify || {}) },
  })
}

const loadUserData = async () => {
  const resp = await getUsers(scriptId, userId.value)
  const userIndex = resp?.index?.find(i => i.uid === userId.value)
  const data = resp?.data?.[userId.value]
  if (!userIndex || !data) {
    throw new Error('用户不存在或加载失败')
  }
  applyUserData(data as ZzzOdUserConfig)
  await nextTick()
  formData.userName = formData.Info.Name || ''
  lastCheckedUserName = formData.userName.trim()
}

const loadUser = async () => {
  pageLoading.value = true
  try {
    if (!userId.value) {
      if (!(await createUserImmediately())) return
    }
    await loadUserData()
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
    message.error(t('edit.couldNotLoadUser'))
    handleCancel()
  } finally {
    isInitializing.value = false
    pageLoading.value = false
  }
}

onMounted(async () => {
  if (await loadScriptInfo()) {
    await loadUser()
    // 三个请求互不依赖，并行发出
    await Promise.all([loadInstances(), loadLaunchers(), loadCatalog()])
    // 已是直控模式的用户：公共初始化（备份 + 默认实例 + 加载原生配置）
    if (formData.Info.Mode === '直控') {
      await enterDirectMode()
    } else {
      // 用户模式进入：归档一条龙原生配置当前状态（MAS 操作前的原始态，
      // 指纹去重），保证后续 MAS 侧修改始终有可还原的进入时点
      await ensureDirectBackup()
    }
  }
})

// 「在一条龙内配置」会话结束后回读会刷新后端字段，重新拉取保持表单同步。
// 查看会话（view mask）虽不回读字段，但「查看详细配置」会先真恢复备份——
// 会话结束后表单同样需要按恢复后的配置重新拉取，否则旧表单值会在用户
// 下次保存时写回、静默撤销恢复。直控时以所选实例的原生配置为准。
watch(showZzzodConfigMask, (now, before) => {
  if (before && !now && !showZzzodViewMask.value && userId.value) {
    refreshAfterSession()
  }
})
watch(showZzzodViewMask, (now, before) => {
  if (before && !now && userId.value) {
    refreshAfterSession()
  }
})

const refreshAfterSession = () => {
  if (formData.Info.Mode === '直控') {
    if (nativeInstanceIdx.value !== null) {
      void loadNativeConfig(nativeInstanceIdx.value).catch(e => {
        logger.error(e instanceof Error ? e.message : String(e))
      })
    }
  } else {
    void loadUserData().catch(e => {
      logger.error(e instanceof Error ? e.message : String(e))
    })
  }
}

onUnmounted(() => {
  // 卸载前把防抖中的数值变更立即落盘，避免「改完步进直接离开」丢改动
  flushAllTaskConfigSaves()
  // 编辑会话退出时机：直控归档一条龙终态（进入时的 ensureDirectBackup 与之
  // 配对）；用户模式归档绑定槽 MAS 终态 + 一条龙终态（与进入时的
  // ensureDirectBackup 配对）。指纹去重，内容无变化不产生新条目
  if (formData.Info.Mode === '直控') {
    void ensureDirectBackup()
  } else {
    void ensureUserExitBackups()
  }
  void stopSession()
})
</script>

<style scoped>
.user-edit-container {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
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

.breadcrumb-link {
  align-items: center;
  gap: 8px;
  color: var(--ant-color-text-secondary);
  text-decoration: none;
}

.user-edit-content {
  display: flex;
  flex-direction: column;
  gap: 0;
  flex: 1;
  min-height: 0;
  padding-bottom: 24px;
}

.config-card {
  overflow: hidden;
}

.config-card :deep(.ant-card-head) {
  background: var(--ant-color-bg-container);
  padding: 24px 32px;
}

.config-card :deep(.ant-card-body) {
  padding: 32px;
}

.form-section {
  margin-bottom: 12px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.section-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.section-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-desc {
  color: var(--ant-color-text-tertiary);
  margin: 8px 0 16px;
  font-size: 14px;
}

.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  cursor: help;
}

/* 快速导入配置：母版下拉（左）+ 导入按钮（右）同排，外观对齐周围下拉框 */
.import-group {
  display: flex;
  gap: 12px;
}

.import-group .import-source-select {
  flex: 1;
  min-width: 0;
}

/* 导入按钮：与下拉框同高同圆角同边框，悬停描边与文字变主题色 */
.import-select-button {
  flex-shrink: 0;
  border-color: var(--ant-color-border);
  color: var(--ant-color-text);
}

.import-select-button:hover:not(:disabled),
.import-select-button:focus-visible:not(:disabled) {
  border-color: var(--ant-color-primary);
  color: var(--ant-color-primary);
}

/* 直控绑定提示与原生配置保存按钮间距 */
.native-bind-alert {
  margin-bottom: 8px;
}

.native-bind-alert + .ant-spin-nested-loading {
  margin-top: 8px;
}

/* 直控账号字段「保存设置」：左对齐，与下方下一区块拉开间距 */
.native-save-row {
  display: flex;
  justify-content: flex-start;
  margin-top: 4px;
  margin-bottom: 24px;
}

/* 直控账号字段必填标记（账号切换需要完整登录信息） */
.required-mark {
  color: var(--ant-color-error);
  margin-right: 2px;
}

/* 直控：实例管理（与任务卡片同一视觉语言：同边框/底色/圆角/悬停） */
.instance-manage {
  margin-bottom: 16px;
}

.instance-manage-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.instance-manage-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.instance-manage-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
  transition:
    border-color 0.2s,
    background 0.2s;
}

.instance-manage-row:hover {
  background: var(--ant-color-fill-tertiary);
}

.instance-manage-row.selected {
  border-color: var(--ant-color-primary);
}

.instance-manage-info {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.instance-manage-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
  font-size: 14px;
}

.instance-manage-tag {
  flex-shrink: 0;
  margin-inline-end: 0;
}

/* 非活跃实例的「设为活跃」：与「当前活跃」同为 tag 形态，灰色可点击 */
.instance-manage-tag-set {
  cursor: pointer;
  color: var(--ant-color-text-tertiary);
  background: var(--ant-color-fill-tertiary);
  border-color: transparent;
  transition:
    color 0.2s,
    background 0.2s;
}

.instance-manage-tag-set:hover {
  color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
}

.instance-manage-ops {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.instance-manage-switch-label {
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  white-space: nowrap;
  margin-right: 4px;
}

.instance-manage-divider {
  margin: 0 4px;
  border-color: var(--ant-color-border-secondary);
}

.path-input-group {
  display: flex;
  overflow: hidden;
  border: 1px solid var(--ant-color-border);
}

.path-input {
  flex: 1;
  min-width: 0;
  border: none !important;
  border-radius: 0 !important;
}

.path-button {
  flex-shrink: 0;
  border: none;
  border-radius: 0;
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  font-weight: 600;
  padding: 0 20px;
  border-left: 1px solid var(--ant-color-border-secondary);
}

.config-form :deep(.ant-form-item) {
  margin-bottom: 24px;
}

/* 一条龙任务卡片网格（对齐任务配置区的卡片 + 开关交互语言） */
.task-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}

.task-card {
  display: flex;
  align-items: center;
  padding: 10px 14px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
  transition:
    background 0.2s,
    border-color 0.2s;
}

.task-card:hover {
  background: var(--ant-color-fill-tertiary);
}

.task-card.inactive {
  opacity: 0.6;
}

.task-card-main {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 24px;
}

.task-name {
  flex: 1;
  min-width: 0;
  font-weight: 600;
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 单行卡片：名称 | ⚙ / 跳转 | 开关，动作紧邻开关对齐 */
.task-card-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}

/* 拖拽排序：手柄（所有卡片常显，含未启用的灰色卡片）与拖拽进行状态 */
.drag-handle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--ant-color-text-tertiary);
  cursor: grab;
  user-select: none;
  touch-action: none;
}

.drag-handle:active {
  cursor: grabbing;
}

.drag-dots {
  width: 12px;
  height: 14px;
  display: block;
  background-image: radial-gradient(currentColor 1.2px, transparent 1.2px);
  background-size: 5px 5px;
  opacity: 0.65;
}

.drag-handle:hover .drag-dots {
  opacity: 0.85;
}

.task-card-ghost {
  opacity: 0.4;
}

.task-card-chosen {
  cursor: grabbing !important;
}

.task-card-drag {
  transform: rotate(3deg);
  opacity: 1 !important;
}

/* 任务卡片 ⚙：可配置任务高亮 */
.task-config-gear {
  color: var(--ant-color-primary);
}

.task-config-field {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-width: 260px;
  padding: 4px 0;
}

.task-config-field-title {
  color: var(--ant-color-text);
  font-size: 13px;
}

/* 计划编辑弹窗 */
.plan-modal-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-top: 4px;
}

.plan-modal-field {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 2px 0;
}

.plan-modal-field-title {
  color: var(--ant-color-text);
  font-size: 13px;
  min-width: 120px;
}

.restore-entry {
  flex-shrink: 0;
}

/* 开关胶囊 */
.config-group-item-capsule {
  width: 40px;
  height: 22px;
  border-radius: 11px;
  border: 1px solid var(--ant-color-border);
  background: var(--ant-color-bg-container);
  position: relative;
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.config-group-item-capsule .config-group-item-dot {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--ant-color-text-quaternary);
  transition: all 0.2s ease;
}

.config-group-item-capsule.active {
  border-color: var(--ant-color-primary);
  background: var(--ant-color-primary);
}

.config-group-item-capsule.active .config-group-item-dot {
  left: 20px;
  background: #fff;
}

/* 遮罩样式已抽至通用组件 GuiSessionMask */

@media (max-width: 768px) {
  .user-edit-header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }

  .config-card :deep(.ant-card-body) {
    padding: 20px;
  }
}
</style>
