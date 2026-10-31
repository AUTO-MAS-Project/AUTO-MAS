<template>
  <div class="user-edit-container">
    <div class="user-edit-header">
      <div class="header-nav">
        <a-breadcrumb class="breadcrumb">
          <a-breadcrumb-item>
            <router-link to="/scripts">{{ t('core.edit.scripts') }}</router-link>
          </a-breadcrumb-item>
          <a-breadcrumb-item>
            <router-link :to="`/scripts/${scriptId}/edit/zzzod`" class="breadcrumb-link">
              {{ scriptName }}
            </router-link>
          </a-breadcrumb-item>
          <a-breadcrumb-item>
            {{ isEdit ? t('core.comp.editUser') : t('core.comp.addUser2') }}
          </a-breadcrumb-item>
        </a-breadcrumb>
      </div>

      <a-space size="middle">
        <a-button v-if="!!userId" size="large" :loading="folderLoading" @click="handleOpenFolder">
          <template #icon>
            <FolderOpenOutlined />
          </template>
          {{ t('core.comp.openConfigFolder') }}
        </a-button>
        <a-tooltip :title="t('core.edit.zzzodOpenNativeConfigHint')">
          <a-button
            v-if="!showZzzodConfigMask && !showZzzodViewMask"
            type="primary"
            ghost
            size="large"
            :loading="zzzodConfigLoading"
            :disabled="pageLoading || nativeLoading || !userId || configLocked"
            @click="handleZzzodConfig"
          >
            <template #icon>
              <SettingOutlined />
            </template>
            {{ t('core.edit.zzzodOpenNativeConfig') }}
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
          {{ t('core.edit.configuring') }}
        </a-button>
        <a-button size="large" class="cancel-button" @click="handleCancel">
          <template #icon>
            <ArrowLeftOutlined />
          </template>
          {{ t('core.edit.back') }}
        </a-button>
      </a-space>
    </div>

    <GuiSessionMask
      :open="showZzzodConfigMask"
      :icon="SettingOutlined"
      :title="t('core.edit.zzzodConfiguringTitle')"
      :description="`${t('core.edit.zzzodConfiguringDesc')}\n${t('core.edit.zzzodConfiguringDesc2')}`"
    >
      <template #actions>
        <a-button
          v-if="zzzodWebsocketId"
          type="primary"
          size="large"
          @click="handleSaveZzzodConfig"
        >
          {{ t('core.edit.saveSettings') }}
        </a-button>
      </template>
    </GuiSessionMask>
    <GuiSessionMask
      :open="showZzzodViewMask"
      :icon="EyeOutlined"
      :title="t('core.edit.zzzodViewingTitle')"
      :description="`${t('core.edit.zzzodViewingDesc')}\n${t('core.edit.zzzodViewingDesc2')}`"
    >
      <template #actions>
        <a-button
          v-if="zzzodWebsocketId"
          type="primary"
          size="large"
          :loading="stoppingZzzodConfig"
          @click="handleCloseZzzodView"
        >
          {{ t('core.edit.zzzodViewClose') }}
        </a-button>
      </template>
    </GuiSessionMask>

    <ConfigLockPanel :script-id="scriptId" content-class="user-edit-content">
      <a-config-provider :component-disabled="configLocked || nativeLoading">
        <a-card class="config-card" :loading="pageLoading">
          <a-form :model="formData" layout="vertical" class="config-form">
            <div class="form-section">
              <div class="section-header">
                <h3>{{ t('core.edit.basicInfo') }}</h3>
              </div>

              <a-row :gutter="24">
                <a-col :span="12">
                  <UserNameField
                    v-model="formData.userName"
                    :hint="t('core.edit.zzzodUserNameHint')"
                    :placeholder="t('core.edit.enterUsername')"
                    enhanced
                    @save="handleNameBlur"
                  />
                </a-col>
                <a-col :span="12">
                  <UserStatusField
                    v-model="formData.Info.Status"
                    :hint="t('core.edit.whetherThisUserEnabled')"
                    @save="saveField('Info.Status', formData.Info.Status)"
                  />
                </a-col>
              </a-row>

              <a-row :gutter="24">
                <a-col :span="24">
                  <GeneralConfigModeSelector
                    :model-value="formData.Info.Base"
                    :options="configModeOptions"
                    :disabled="pageLoading"
                    :alert-message="configModeAlert"
                    @change="handleConfigModeChange"
                  />
                </a-col>
              </a-row>

              <!-- 一条龙启动器（原生来源/独立来源两种模式通用；未安装的启动器选项禁用变灰，悬停选项查看说明）固定在右侧；
                 左侧按模式切换：原生来源为「运行实例」，独立来源为「快速导入配置」（母版下拉选择来源实例 + 导入按钮，
                 外观与周围下拉框一致；确认后覆盖本用户配置（账号+任务编排）） -->
              <a-row :gutter="24">
                <a-col v-if="formData.Info.Base === 'native'" :span="12">
                  <a-form-item>
                    <template #label>
                      <FieldLabelWithHint
                        :text="t('core.edit.zzzodDirectInstanceRun')"
                        :hint="t('core.edit.zzzodDirectInstanceRunHint')"
                        variant="form"
                      />
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
                      <FieldLabelWithHint
                        :text="t('core.edit.zzzodQuickImport')"
                        :hint="t('core.edit.zzzodImportConfigHint')"
                        variant="form"
                      />
                    </template>
                    <div class="import-group">
                      <a-select
                        v-model:value="importSourceIdx"
                        :options="importInstanceOptions"
                        :placeholder="t('core.edit.zzzodImportPlaceholder')"
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
                        {{ t('core.edit.zzzodImport') }}
                      </a-button>
                    </div>
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item>
                    <template #label>
                      <span class="form-label">
                        {{ t('core.edit.zzzodLauncherMode') }}
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
                        <a-tooltip :title="t('core.edit.zzzodLauncherAutoHint')">
                          <span>{{ t('core.edit.zzzodLauncherAuto') }}</span>
                        </a-tooltip>
                      </a-select-option>
                      <a-select-option
                        value="原始"
                        :disabled="!launchersReady || !launchersUsable.original"
                      >
                        <a-tooltip :title="t('core.edit.zzzodLauncherOriginalHint')">
                          <span>{{ t('core.edit.zzzodLauncherOriginal') }}</span>
                        </a-tooltip>
                      </a-select-option>
                      <a-select-option
                        value="集成"
                        :disabled="!launchersReady || !launchersUsable.integrated"
                      >
                        <a-tooltip :title="t('core.edit.zzzodLauncherIntegratedHint')">
                          <span>{{ t('core.edit.zzzodLauncherIntegrated') }}</span>
                        </a-tooltip>
                      </a-select-option>
                    </a-select>
                  </a-form-item>
                </a-col>
              </a-row>

              <!-- 原生来源：实例管理（参与「全部实例」运行 / 添加 / 重命名 / 删除，实时写回 one_dragon.yml） -->
              <template v-if="formData.Info.Base === 'native'">
                <ZzzodInstancesManager
                  :instances="instances"
                  :update-instances="updateInstances"
                  :script-id="scriptId"
                  :locked="configLocked"
                  :selected="nativeInstanceIdx"
                  :select="selectManagedInstance"
                  :deleted="clearDeletedInstance"
                  :track-write="trackInstanceWrite"
                />

                <!-- 原生来源：选择配置实例（选完即编辑下方账号字段与任务配置） -->
                <a-row :gutter="24">
                  <a-col :span="12">
                    <a-form-item>
                      <template #label>
                        <FieldLabelWithHint
                          :text="t('core.edit.zzzodDirectInstance')"
                          :hint="t('core.edit.zzzodDirectInstanceHint')"
                          variant="form"
                        />
                      </template>
                      <a-select
                        :value="nativeInstanceIdx"
                        :options="instanceOptions"
                        :placeholder="t('core.edit.zzzodDirectPickInstance')"
                        :loading="instancesLoading"
                        size="large"
                        class="modern-select"
                        @change="selectManagedInstance"
                      />
                    </a-form-item>
                  </a-col>
                </a-row>

                <a-alert
                  type="info"
                  show-icon
                  class="native-bind-alert"
                  :message="t('core.edit.zzzodDirectBindAlert')"
                />

                <!-- 原生来源：所选实例的原生账号字段（保存即写回一条龙 game_account.yml） -->
                <ZzzodNativeAccountSection
                  :fields="nativeAccountFields"
                  :values="nativeAccountValues"
                  :loading="nativeLoading"
                  :saving="nativeSaving"
                  :selected="nativeInstanceIdx"
                  :save="saveNativeAccount"
                />
              </template>

              <!-- 账号配置（独立来源：MAS 字段化配置） -->
              <template v-else>
                <a-row :gutter="24">
                  <a-col :span="12">
                    <a-form-item>
                      <template #label>
                        <FieldLabelWithHint
                          :text="t('core.edit.zzzodGameRegion')"
                          :hint="t('core.edit.zzzodGameRegionHint')"
                          variant="form"
                        />
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
                        <FieldLabelWithHint
                          :text="t('core.edit.zzzodGameLanguage')"
                          :hint="t('core.edit.zzzodGameLanguageHint')"
                          variant="form"
                        />
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
                        <FieldLabelWithHint
                          :text="t('core.edit.zzzodGamePath')"
                          :hint="t('core.edit.zzzodGamePathHint')"
                          variant="form"
                        />
                      </template>
                      <PathPickerField
                        v-model="formData.Game.GamePath"
                        mode="file"
                        :placeholder="t('core.edit.zzzodGamePathPlaceholder')"
                        :pick-label="t('core.edit.pickFile')"
                        @pick="selectGamePath"
                      />
                    </a-form-item>
                  </a-col>
                </a-row>

                <a-row :gutter="24">
                  <a-col :span="12">
                    <a-form-item>
                      <template #label>
                        <FieldLabelWithHint
                          :text="t('core.edit.zzzodAccount')"
                          :hint="t('core.edit.zzzodAccountHint')"
                          variant="form"
                        />
                      </template>
                      <a-input
                        v-model:value="formData.Game.Account"
                        :placeholder="t('core.edit.zzzodEnterAccount')"
                        size="large"
                        class="modern-input"
                        @blur="saveField('Game.Account', formData.Game.Account)"
                      />
                    </a-form-item>
                  </a-col>
                  <a-col :span="12">
                    <a-form-item>
                      <template #label>
                        <FieldLabelWithHint
                          :text="t('core.edit.password')"
                          :hint="t('core.edit.zzzodPasswordHint')"
                          variant="form"
                        />
                      </template>
                      <a-input-password
                        v-model:value="formData.Game.Password"
                        :placeholder="t('core.edit.zzzodEnterPasswordPlaceholder')"
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
                        <FieldLabelWithHint
                          :text="t('core.edit.zzzodBilibiliAccount')"
                          :hint="t('core.edit.zzzodBilibiliAccountHint')"
                          variant="form"
                        />
                      </template>
                      <a-input
                        v-model:value="formData.Game.BilibiliAccountName"
                        :placeholder="t('core.edit.zzzodEnterBilibiliAccount')"
                        size="large"
                        class="modern-input"
                        @blur="
                          saveField('Game.BilibiliAccountName', formData.Game.BilibiliAccountName)
                        "
                      />
                    </a-form-item>
                  </a-col>
                </a-row>
              </template>

              <a-row :gutter="24">
                <a-col :span="12">
                  <UserRemainedDayField
                    v-model="formData.Info.RemainedDay"
                    :hint="t('core.edit.daysLeftAccount1')"
                    @save="saveField('Info.RemainedDay', formData.Info.RemainedDay)"
                  />
                </a-col>
                <a-col :span="12">
                  <a-form-item>
                    <template #label>
                      <FieldLabelWithHint
                        :text="t('core.edit.note')"
                        :hint="t('core.edit.addNoteAboutThis')"
                        variant="form"
                      />
                    </template>
                    <a-input
                      v-model:value="formData.Info.Notes"
                      :placeholder="t('core.edit.enterNote')"
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
                        {{ t('core.edit.collectNodeDetails') }}
                        <a-tooltip
                          mouse-enter-delay="0.5"
                          :title="t('core.edit.collectsKeyMomentsFrom')"
                        >
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
                <a-col :span="12">
                  <a-form-item>
                    <template #label>
                      <FieldLabelWithHint
                        :text="t('core.edit.zzzodAfterDone')"
                        :hint="t('core.edit.zzzodAfterDoneHint')"
                        variant="form"
                      />
                    </template>
                    <a-select
                      v-model:value="afterDoneValue"
                      :options="afterDoneOptions"
                      :loading="afterDoneSaving"
                      size="large"
                      class="modern-select"
                      @change="handleAfterDoneChange"
                    />
                  </a-form-item>
                </a-col>
              </a-row>
            </div>
          </a-form>
        </a-card>

        <!-- ══ 启动参数（一条龙游戏启动参数；总开关在标题行，关闭时下方参数置灰不可改）══ -->
        <a-card class="config-card" style="margin-top: 24px">
          <a-form :model="formData" layout="vertical" class="config-form">
            <div class="form-section">
              <div class="section-header">
                <h3>
                  {{ t('core.edit.zzzodLaunchArgsTitle') }}
                  <a-tooltip :title="t('core.edit.zzzodLaunchArgsSwitchHint')">
                    <QuestionCircleOutlined class="help-icon" />
                  </a-tooltip>
                </h3>
                <div class="section-header-actions">
                  <a-switch
                    v-if="formData.Info.Base === 'native'"
                    v-model:checked="nativeLaunchArgs.launch_argument"
                    size="large"
                    @change="(v: any) => saveNativeLaunchArgsField('launch_argument', v === true)"
                  />
                  <a-switch
                    v-else
                    v-model:checked="formData.Game.LaunchArgument"
                    size="large"
                    @change="(v: any) => saveField('Game.LaunchArgument', v === true)"
                  />
                </div>
              </div>
              <p class="section-desc">
                {{ t('core.edit.zzzodLaunchArgsDesc') }}
              </p>
              <a-collapse
                v-model:activeKey="launchArgsOpen"
                class="optional-section"
                :bordered="false"
              >
                <a-collapse-panel key="launch-args" :header="t('core.edit.zzzodLaunchArgsDetail')">
                  <!-- 原生来源：所选实例的原生启动参数（改动即时写回一条龙 game.yml） -->
                  <template v-if="formData.Info.Base === 'native'">
                    <a-spin :spinning="nativeLoading">
                      <template v-if="nativeInstanceIdx !== null">
                        <ZzzodLaunchArgumentFields
                          v-model:screen-size="nativeLaunchArgs.screen_size"
                          v-model:full-screen="nativeLaunchArgs.full_screen"
                          v-model:popup-window="nativeLaunchArgs.popup_window"
                          v-model:dx12="nativeLaunchArgs.dx12"
                          v-model:monitor="nativeLaunchArgs.monitor"
                          v-model:advanced-arguments="nativeLaunchArgs.launch_argument_advance"
                          :disabled="!nativeLaunchArgs.launch_argument"
                          @save-screen-size="saveNativeLaunchArgsField('screen_size', $event)"
                          @save-full-screen="saveNativeLaunchArgsField('full_screen', $event)"
                          @save-popup-window="saveNativeLaunchArgsField('popup_window', $event)"
                          @save-dx12="saveNativeLaunchArgsField('dx12', $event)"
                          @save-monitor="saveNativeLaunchArgsField('monitor', $event)"
                          @save-advanced-arguments="
                            saveNativeLaunchArgsField('launch_argument_advance', $event)
                          "
                        />
                      </template>
                      <NoData v-else :description="t('core.edit.zzzodDirectPickInstanceFirst')" />
                    </a-spin>
                  </template>
                  <!-- 用户：MAS 字段化启动参数（改动即时保存，运行时注入绑定槽） -->
                  <template v-else>
                    <ZzzodLaunchArgumentFields
                      v-model:screen-size="formData.Game.ScreenSize"
                      v-model:full-screen="formData.Game.FullScreen"
                      v-model:popup-window="formData.Game.PopupWindow"
                      v-model:dx12="formData.Game.Dx12"
                      v-model:monitor="formData.Game.Monitor"
                      v-model:advanced-arguments="formData.Game.LaunchArgumentAdvance"
                      :disabled="!formData.Game.LaunchArgument"
                      @save-screen-size="saveField('Game.ScreenSize', $event)"
                      @save-full-screen="saveField('Game.FullScreen', $event)"
                      @save-popup-window="saveField('Game.PopupWindow', $event)"
                      @save-dx12="saveField('Game.Dx12', $event)"
                      @save-monitor="saveField('Game.Monitor', $event)"
                      @save-advanced-arguments="saveField('Game.LaunchArgumentAdvance', $event)"
                    />
                  </template>
                </a-collapse-panel>
              </a-collapse>
            </div>
          </a-form>
        </a-card>

        <!-- ══ 任务配置（一条龙编排，紧跟基本信息）══ -->
        <a-card class="config-card" style="margin-top: 24px">
          <a-form :model="formData" layout="vertical" class="config-form">
            <div class="form-section">
              <ZzzodTaskBoard
                :cards="formData.Info.Base === 'native' ? nativeTasks : taskCards"
                :editable="!isInitializing && !pageLoading && !nativeLoading"
                :saving="nativeSaving"
                :editor="taskEditor"
                :commit="commitTaskBoard"
                :configure="handleZzzodConfig"
                :restore="openRestoreModal"
              >
                <p class="section-desc">
                  {{
                    formData.Info.Base === 'native'
                      ? t('core.edit.zzzodDirectTasksDesc')
                      : t('core.edit.zzzodOneDragonDesc')
                  }}
                </p>
              </ZzzodTaskBoard>

              <!-- ══ 预备编队（独立组件：team.yml 固定 20 个编队，与一条龙编队页一致）══ -->
              <ZzzOdPredefinedTeams
                v-if="formData.Info.Base !== 'native' || nativeInstanceIdx !== null"
                ref="teamsRef"
                :script-id="scriptId"
                :user-id="userId"
                :instance-idx="formData.Info.Base === 'native' ? nativeInstanceIdx : null"
              />
            </div>
          </a-form>
        </a-card>
      </a-config-provider>

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
        :disabled="configLocked || nativeLoading"
        :script-name="ZZZOD_DISPLAY_NAME"
        :targets="restoreTargets"
        :api="restoreApi"
        :field-labels="previewFieldLabels"
        :format-value="formatPreviewValue"
        :on-restored="handleRestored"
        :on-detail="handleRestoreView"
      />

      <!-- ══ 任务计划编辑弹窗（体力刷本/恶名狩猎：计划列表 + 主配置）══ -->
    </ConfigLockPanel>
  </div>
</template>

<script setup lang="ts">
import ZzzodLaunchArgumentFields from './ZzzOdUserEdit/ZzzodLaunchArgumentFields.vue'
import PathPickerField from '@/components/PathPickerField.vue'
import UserNameField from '@/views/EditView/User/components/UserNameField.vue'
import UserRemainedDayField from '@/views/EditView/User/components/UserRemainedDayField.vue'
import UserStatusField from '@/views/EditView/User/components/UserStatusField.vue'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import { useZzzodTaskConfig } from './ZzzOdUserEdit/useZzzodTaskConfig'
import ZzzodTaskBoard from './ZzzOdUserEdit/ZzzodTaskBoard.vue'

import { useZzzodNativeConfig } from './ZzzOdUserEdit/useZzzodNativeConfig'
import ZzzodNativeAccountSection from './ZzzOdUserEdit/ZzzodNativeAccountSection.vue'
import { pickZzzGameExe } from './ZzzOdUserEdit/pickZzzGameExe'
import type { TaskCard, AfterDoneValue } from './ZzzOdUserEdit/zzzodTypes'

import ZzzodInstancesManager from './ZzzOdUserEdit/ZzzodInstancesManager.vue'
import { useZzzodInstances } from './ZzzOdUserEdit/useZzzodInstances'

import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import { useScriptConfigLock } from '@/composables/useScriptConfigLock'
import { computed, h, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message, Modal } from 'ant-design-vue'
import {
  ArrowLeftOutlined,
  EyeOutlined,
  FolderOpenOutlined,
  QuestionCircleOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'
import { Service, type ZzzOdInstanceOut, type ZzzOdUserConfig } from '@/api'
import { importZzzodInstance } from '@/composables/useAdapterSetupApi'
import { buildCorruptedForceConfirm, corruptedForceConfirmContent } from '@/utils/configRestoreMode'
import ConfigRestoreSection from '@/views/EditView/User/components/ConfigRestoreSection.vue'
import GuiSessionMask from '@/components/GuiSessionMask.vue'
import ZzzOdPredefinedTeams from '@/components/ZzzOdPredefinedTeams.vue'
import { useUserApi } from '@/composables/useUserApi'
import { useScriptApi } from '@/composables/useScriptApi'
import { useZzzodGuiSession } from '@/composables/useZzzodGuiSession'
import GeneralConfigModeSelector from '@/views/EditView/User/GeneralConfigModeSelector.vue'
import UserNotifyConfig from '@/components/UserNotifyConfig.vue'
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'
import { useConfigBackupApi } from '@/composables/useConfigBackupApi'

const { t } = useI18n()
const logger = window.electronAPI.getLogger('ZZZ-OD用户编辑')
const route = useRoute()
const router = useRouter()
const {
  addUser,
  getUsers,
  updateUser,
  error: userApiError,
  openUserConfigFolder,
  loading: folderLoading,
} = useUserApi()
const { getScript, error: scriptApiError } = useScriptApi()

const scriptId = route.params.scriptId as string

const handleOpenFolder = async () => {
  if (!userId.value) return
  await openUserConfigFolder(scriptId, userId.value)
}
const userId = ref((route.params.userId as string) || '')
const isEdit = ref(!!userId.value)
const { configLocked } = useScriptConfigLock(() => scriptId)
const scriptName = ref(t('core.edit.zzzodScriptFallbackName'))

const pageLoading = ref(true)
const isInitializing = ref(true)

type FormSection<T> = { [K in keyof T]-?: NonNullable<T[K]> }

type ZzzOdUserFormData = {
  userName: string
  // Info.IfQuickConfig（快速配置开关，与配置来源独立）由生成模型 ZzzOdUserConfig_Info 提供
  Info: FormSection<NonNullable<ZzzOdUserConfig['Info']>>
  Game: FormSection<NonNullable<ZzzOdUserConfig['Game']>>
  OneDragon: FormSection<NonNullable<ZzzOdUserConfig['OneDragon']>>
  Notify: FormSection<NonNullable<ZzzOdUserConfig['Notify']>>
}

const getDefaultUserData = (): Omit<ZzzOdUserFormData, 'userName'> => ({
  Info: {
    Name: '',
    Status: true,
    Base: 'independent',
    IfQuickConfig: true,
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
    LaunchArgument: false,
    ScreenSize: '1920x1080',
    FullScreen: '0',
    PopupWindow: false,
    Dx12: false,
    Monitor: '1',
    LaunchArgumentAdvance: '',
  },
  OneDragon: {
    AppList: '[]',
    AfterDone: '关闭游戏',
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
  { label: t('core.edit.pushLogModeOff'), value: '关闭' },
  { label: t('core.edit.pushLogModeList'), value: '逐条' },
  { label: t('core.edit.pushLogModeSummary'), value: '汇总' },
]

// 游戏结束后操作（value 为后端 OneDragon.AfterDone 取值，与一条龙原生「结束后」
// 同词表；独立来源/共享来源模式经配置会话双向联动，原生来源直读写原生 after_done）
const afterDoneOptions = [
  { label: t('core.edit.zzzodAfterDoneNone'), value: '无' },
  { label: t('core.edit.zzzodAfterDoneCloseGame'), value: '关闭游戏' },
  { label: t('core.edit.zzzodAfterDoneShutdown'), value: '关机' },
]
const afterDoneValue = computed<AfterDoneValue>({
  get: () =>
    formData.Info.Base === 'native'
      ? nativeAfterDone.value
      : (formData.OneDragon.AfterDone ?? '关闭游戏'),
  set: value => {
    if (formData.Info.Base === 'native') {
      nativeAfterDone.value = value
    } else {
      formData.OneDragon.AfterDone = value
    }
  },
})

const afterDoneSaving = ref(false)
const handleAfterDoneChange = async () => {
  if (configLocked.value) return
  if (formData.Info.Base === 'native') {
    afterDoneSaving.value = true
    try {
      await saveNativeConfig({ afterDone: nativeAfterDone.value }, 'afterDone', true)
    } finally {
      afterDoneSaving.value = false
    }
    return
  }
  await saveField('OneDragon.AfterDone', formData.OneDragon.AfterDone)
}

// 配置来源三态卡片（value 为后端 Info.Base 取值，驱动逻辑需保持原样；文案走词表）
// 「共享」置灰：一条龙运行时共享来源与独立来源同分支（AutoProxy 均按该用户字段注入绑定槽），
// 不存在可共享的脚本级配置树，选了也不生效——禁用并悬停说明原因
const configModeOptions: Array<{
  label: string
  value: 'shared' | 'independent' | 'native'
  title: string
  description: string
  icon: 'database' | 'setting'
  disabled?: boolean
  disabledReason?: string
}> = [
  {
    label: t('core.edit.script'),
    value: 'shared',
    title: t('core.edit.script'),
    description: t('core.edit.useScriptS'),
    icon: 'database',
    disabled: true,
    disabledReason: t('core.edit.scriptModeDisabled'),
  },
  {
    label: t('core.edit.zzzodModeUser'),
    value: 'independent',
    title: t('core.edit.zzzodModeUser'),
    description: t('core.edit.zzzodModeUserDesc'),
    icon: 'database',
  },
  {
    label: t('core.edit.directControl'),
    value: 'native',
    title: t('core.edit.directControl'),
    description: t('core.edit.zzzodModeDirectDesc'),
    icon: 'setting',
  },
]

// 蓝色说明框随所选模式动态切换（只显示当前模式的行为，减少固定长文案）
const configModeAlert = computed(() =>
  formData.Info.Base === 'native'
    ? t('core.edit.zzzodConfigSourceDirectAlert')
    : t('core.edit.zzzodConfigSourceUserAlert')
)

// ══ 区服 / 语言选项（value 为 zzz-od YAML 原生取值，驱动逻辑需保持原样）══
const gameRegionOptions = [
  { label: t('core.edit.zzzodRegionCn'), value: 'cn' },
  { label: t('core.edit.zzzodRegionCnB'), value: 'cn_b' },
  { label: t('core.edit.zzzodRegionUs'), value: 'us' },
  { label: t('core.edit.zzzodRegionEu'), value: 'eu' },
  { label: t('core.edit.zzzodRegionAsia'), value: 'asia' },
  { label: t('core.edit.zzzodRegionTwHkMo'), value: 'twhkmo' },
]
const gameLanguageOptions = [
  { label: t('core.edit.zzzodLanguageCn'), value: 'cn' },
  { label: t('core.edit.zzzodLanguageEn'), value: 'en' },
]
// options 表派生 value→label 映射（备份预览反显共用，避免枚举双份维护）
const gameRegionLabels: Record<string, string> = Object.fromEntries(
  gameRegionOptions.map(o => [o.value, o.label])
)
const gameLanguageLabels: Record<string, string> = Object.fromEntries(
  gameLanguageOptions.map(o => [o.value, o.label])
)

// ══ 一条龙启动参数（value 为 zzz-od game.yml 原生取值；全屏/显示器落盘为字符串）══

// DX12 是独立开关字段（Game.Dx12 / nativeLaunchArgs.dx12）：与分辨率等参数同级，
// 注入/写回时由后端把 -use-d3d12 合并进一条龙的高级参数，不在前端操作文本框

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
        String((user as { Info?: { Name?: string } })?.Info?.Name ?? '').trim() === name
    )
    if (duplicate) {
      message.error(t('core.edit.zzzodDuplicateUserName'))
      return
    }
  } catch (e) {
    logger.warn(e instanceof Error ? e.message : String(e))
  }
  lastCheckedUserName = name
  await saveField('Info.Name', formData.userName)
}

const createUserImmediately = async (): Promise<boolean> => {
  if (configLocked.value) return false

  const resp = await addUser(scriptId, { showError: false })
  if (!resp?.userId) {
    message.error(userApiError.value || t('core.edit.couldNotCreateUser'))
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
  if (typeof value !== 'string' || !['independent', 'native'].includes(value)) return
  const prev = formData.Info.Base
  await flushPendingSaves()
  if (value === 'native' && prev !== 'native') {
    // 每脚本仅允许一个原生来源用户：原生来源是脚本级全局视图（实例/活跃/运行实例
    // 都是一份 one_dragon.yml），多原生来源用户共享状态互相干扰
    try {
      const resp = await getUsers(scriptId)
      const hasOtherDirect = Object.entries(resp?.data ?? {}).some(
        ([uid, user]) =>
          uid !== userId.value &&
          String((user as { Info?: { Base?: string } })?.Info?.Base ?? '') === 'native'
      )
      if (hasOtherDirect) {
        formData.Info.Base = prev
        message.error(t('core.edit.zzzodDirectModeLimit'))
        return
      }
    } catch (e) {
      logger.warn(e instanceof Error ? e.message : String(e))
    }
  }
  if (!(await saveField('Info.Base', value))) return
  formData.Info.Base = value as 'shared' | 'independent' | 'native'
  if (value === 'native') {
    // 进入原生来源：公共初始化（备份 + 默认实例 + 加载原生配置）
    await enterDirectMode()
  } else if (prev === 'native') {
    // 离开原生来源（切回独立来源）：补一份「配置完成时」的备份
    await ensureDirectBackup()
  }
}

/** 原生来源/独立来源共用的按需归档入口（通用 /backup/ensure 三时机，指纹去重）。
 * onedragon=一条龙原生配置当前状态；mas=绑定槽 MAS 终态（未绑定槽跳过） */
const {
  restoreApi: backupApi,
  restore: restoreConfigBackup,
  ensure: ensureConfigBackup,
} = useConfigBackupApi({
  scriptId,
  userId: () => userId.value,
  logger,
})

const ensurePoolBackup = async (target: string): Promise<void> => {
  if (!userId.value) return
  try {
    const resp = await ensureConfigBackup(target)
    if (resp.code !== 200) throw new Error(resp.message || t('core.edit.zzzodBackupFailed'))
  } catch (e) {
    // 备份失败不阻断使用，但向用户提示（防止误以为有恢复点）；
    // 后端诊断（配置损坏时含损坏位置）附加展示，便于用户自愈
    const detail = e instanceof Error ? e.message : String(e)
    logger.warn(detail)
    message.warning(`${t('core.edit.zzzodBackupFailed')}（${detail}）`)
  }
}

/** 一条龙原生配置按需归档（进入原生来源/独立来源编辑页、退出原生来源时调用） */
const ensureDirectBackup = () => ensurePoolBackup('onedragon')

/** 独立来源退出时机：归档绑定槽 MAS 终态 + 一条龙原生配置终态（编辑会话包络） */
const ensureUserExitBackups = () =>
  Promise.all([ensurePoolBackup('mas'), ensurePoolBackup('onedragon')])

/** 进入原生来源的公共初始化（模式切换与页面加载共用）：
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

const { instances, instancesLoading, instanceOptions, loadInstances } = useZzzodInstances(scriptId)
const updateInstances = (items: ZzzOdInstanceOut[]) => {
  instances.value = items
}

// 导入母版与原生来源实例选择独立；后端另按原生注册表校验来源。
const importInstanceOptions = computed(() =>
  instanceOptions.value.filter(item => item.value !== formData.Info.SlotIdx)
)

// ══ 快速导入配置：左侧母版下拉 + 右侧导入按钮共同构成导入功能 ══
// 当前选中的母版（来源）实例；导入成功后复位
const importSourceIdx = ref<number | null>(null)
watch(
  importInstanceOptions,
  options => {
    if (
      importSourceIdx.value !== null &&
      !options.some(item => item.value === importSourceIdx.value)
    ) {
      importSourceIdx.value = null
    }
  },
  { immediate: true }
)
const importLoading = ref(false)
// 预备编队组件引用：导入整体覆盖槽配置后需要强制刷新编队显示
const teamsRef = ref<InstanceType<typeof ZzzOdPredefinedTeams> | null>(null)

// 点击「导入」：确认将用母版实例覆盖当前独立用户配置后再执行
// （后端在覆盖前会强制归档当前 MAS 配置，可在「配置恢复」中找回）
const confirmImport = () => {
  if (importSourceIdx.value === null || configLocked.value) return
  Modal.confirm({
    title: t('core.edit.zzzodImportConfirmTitle'),
    content: t('core.edit.zzzodImportConfirmDesc'),
    okText: t('core.edit.zzzodImport'),
    onOk: () => importFromInstance(),
  })
}

const importFromInstance = async () => {
  if (configLocked.value) return
  const sourceIdx = importSourceIdx.value
  if (sourceIdx === null || !userId.value) return
  importLoading.value = true
  try {
    await flushPendingSaves()
    await importZzzodInstance({
      scriptId,
      userId: userId.value,
      instanceIdx: sourceIdx,
    })
    importSourceIdx.value = null
    // 后端已写入账号字段、任务编排与实例级配置（含预备编队），
    // 重新拉取让表单与后端一致，预备编队组件一并强制刷新
    await loadUserData()
    teamsRef.value?.reload()
    message.success(t('core.edit.zzzodImportSuccess'))
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('core.edit.zzzodImportFailed'))
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
    const resp = await Service.getZzzodLaunchersApiApiScriptsZzzodLaunchersGet(scriptId)
    if (resp.code !== 200) {
      throw new Error(resp.message || t('core.edit.zzzodLauncherLoadFailed'))
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

const {
  nativeInstanceIdx,
  nativeInstanceRun,
  nativeAfterDone,
  instanceRunOptions,
  nativeLoading,
  nativeSaving,
  nativeAccountFields,
  nativeAccountValues,
  nativeTasks,
  nativeLaunchArgs,
  loadNativeConfig,
  runModeSaving,
  handleNativeInstanceRunChange,
  toNativeTaskIn,
  saveNativeConfig,
  saveNativeLaunchArgsField,
  saveNativeAccount,
  flushNativeSaves,
  hasPendingNativeSaves,
} = useZzzodNativeConfig(scriptId, configLocked, () => formData.Info.Base === 'native')

// 启动参数折叠区：总开关开 → 自动展开，关 → 自动收起；手动展开/收起保持到
// 开关下次变化（watch 只在来源值变化时触发，手动的 activeKey 不会被覆盖）
const launchArgsOpen = ref<string[]>([])
watch(
  () =>
    [formData.Info.Base, formData.Game.LaunchArgument, nativeLaunchArgs.launch_argument] as const,
  ([mode, userOn, nativeOn]) => {
    launchArgsOpen.value = (mode === 'native' ? nativeOn : userOn) ? ['launch-args'] : []
  },
  { immediate: true }
)

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
      throw new Error(resp.message || t('core.edit.zzzodLoadOneDragonFailed'))
    }
    catalog.value = resp.data || []
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
  }
}

const taskEditor = useZzzodTaskConfig({
  scriptId,
  userId,
  nativeMode: () => formData.Info.Base === 'native',
  instanceIdx: nativeInstanceIdx,
  locked: configLocked,
})
const instanceWrites = new Set<Promise<unknown>>()
const trackInstanceWrite = <T>(operation: () => Promise<T>): Promise<T> => {
  const run = operation()
  instanceWrites.add(run)
  const done = () => {
    instanceWrites.delete(run)
  }
  void run.then(done, done)
  return run
}
const flushPendingSaves = async () => {
  let tail: Promise<boolean>
  do {
    tail = saveChain
    await Promise.all(
      [tail, flushNativeSaves(), taskEditor.flushAllTaskConfigSaves(), ...instanceWrites].map(run =>
        run.catch(() => undefined)
      )
    )
  } while (
    tail !== saveChain ||
    hasPendingNativeSaves() ||
    taskEditor.hasPendingSaves() ||
    instanceWrites.size
  )
}
onBeforeRouteLeave(async () => {
  await flushPendingSaves()
})

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
  game_region: t('core.edit.zzzodGameRegion'),
  game_path: t('core.edit.zzzodGamePath'),
  game_language: t('core.edit.zzzodGameLanguage'),
  account: t('core.edit.zzzodAccount'),
  password: t('core.edit.password'),
  bilibili_account_name: t('core.edit.zzzodBilibiliAccount'),
  use_custom_win_title: t('core.edit.zzzodUseCustomWinTitle'),
  custom_win_title: t('core.edit.zzzodCustomWinTitle'),
}

// 枚举值为后端/一条龙原生取值（驱动文案映射需保持原样），展示走词表
const formatPreviewValue = (key: string, raw: string): string => {
  switch (key) {
    case 'status':
      // 后端传 str(bool)（"True"/"False"），大小写与 YAML 表示不定，统一小写比较
      return raw.toLowerCase() === 'true' ? t('core.edit.yes') : t('core.edit.no')
    case 'base':
      return raw === 'independent'
        ? t('core.edit.zzzodModeUser')
        : raw === 'native'
          ? t('core.edit.directControl')
          : raw
    case 'launcher_mode':
      return raw === '自动'
        ? t('core.edit.zzzodLauncherAuto')
        : raw === '原始'
          ? t('core.edit.zzzodLauncherOriginal')
          : raw === '集成'
            ? t('core.edit.zzzodLauncherIntegrated')
            : raw
    case 'remained_day':
      return raw === '-1' ? t('core.edit.zzzodPreviewUnlimited') : raw
    case 'push_log_mode':
      return raw === '关闭'
        ? t('core.edit.pushLogModeOff')
        : raw === '逐条'
          ? t('core.edit.pushLogModeList')
          : raw === '汇总'
            ? t('core.edit.pushLogModeSummary')
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
const restoreAfterSaves: typeof restoreConfigBackup = async (...args) => {
  await flushPendingSaves()
  return restoreConfigBackup(...args)
}
const restoreApi = { ...backupApi, restore: restoreAfterSaves }

const openRestoreModal = async () => {
  await flushPendingSaves()
  restoreOpen.value = true
}

// 一键恢复成功：MAS 恢复含字段回填，刷新表单；一条龙恢复不回填 MAS 字段，
// 但原生来源页表单（账号/任务/运行实例读自原生文件）必须重拉，否则旧表单值在
// 下次「保存设置」时全量写回、静默撤销刚做的恢复（独立来源 AppList 同理）
const handleRestored = (target: string) => {
  restoreOpen.value = false
  if (target === 'mas') {
    void loadUserData()
  } else if (formData.Info.Base === 'native' && nativeInstanceIdx.value !== null) {
    void loadNativeConfig(nativeInstanceIdx.value)
  } else {
    void loadUserData()
  }
}

const handleRestoreView = (target: string, item: { time: string }) => {
  if (configLocked.value) return Promise.resolve(false)
  return new Promise<boolean>(resolve => {
    // 「查看详细配置」语义：恢复该时点 + 拉起对应会话查看。弹窗文案与
    // 「一键恢复」必须显式区分——预览弹窗里的「查看详细配置」按钮极易被
    // 误以为只读，实际会真覆盖当前配置并拉起查看会话；查看会话结束前
    // 切任务开关会写回旧 AppList，导致恢复被静默撤销。
    Modal.confirm({
      title: t('core.edit.configRestoreDetailView'),
      content: h(
        'p',
        { style: { color: 'var(--ant-color-error)', margin: 0 } },
        t('core.edit.configRestoreDetailConfirm', { script: ZZZOD_DISPLAY_NAME })
      ),
      okText: t('core.edit.configRestoreConfirmOk'),
      okType: 'danger',
      cancelText: t('core.edit.cancel'),
      onOk: async () => {
        if (configLocked.value) {
          message.error(t('core.edit.configLocked'))
          resolve(false)
          return
        }
        try {
          // 恢复流程（含损坏时的强制恢复确认）全部走完才 resolve，避免本入口
          // 提前放行、查看会话对着没被恢复的配置打开
          resolve(await restoreForDetailView(target, item, target === 'mas'))
        } catch (e) {
          message.error(e instanceof Error ? e.message : t('core.edit.configRestoreFailed'))
          resolve(false)
        }
      },
      onCancel: () => resolve(false),
    })
  })
}

/** 「查看详细配置」的恢复：成功后拉起对应查看会话；损坏时转强制恢复二次确认 */
const restoreForDetailView = async (
  target: string,
  item: { time: string },
  isMas: boolean,
  force = false
): Promise<boolean> => {
  const resp = await restoreAfterSaves(target, item.time, force)
  // 后端失败走 HTTP 200 + body code=400，须显式检查返回体：槽绑定守卫等
  // 抛错若被吞掉，会照常关弹窗并打开查看会话，显示的是没被恢复的当前配置
  if (resp.code === 409) {
    if (force) {
      // force 仍被拦：不再重复弹确认，直接把原因报给用户
      throw new Error(resp.message || t('core.edit.configRestoreFailed'))
    }
    // 源配置损坏：与「一键恢复」同一套二次确认，确认后带 force 重试本入口流程
    return confirmForceRestoreDetail(target, item, isMas, resp.message || '')
  }
  if (resp.code !== 200) {
    throw new Error(resp.message || t('core.edit.configRestoreFailed'))
  }
  restoreOpen.value = false
  if (isMas) {
    // MAS 备份预览：只读会话打开一条龙，合成视图下看到的是 MAS 实例
    // （槽内容即恢复的备份，不注入基线、不回读字段）
    await startSession(userId.value, true, undefined, 'user')
  } else {
    // 一条龙备份预览：脚本级原生会话，看到的是一条龙自己的原生实例，
    // 与 MAS 侧完全无关
    await startSession(scriptId, true, undefined, 'script')
  }
  return true
}

/** 损坏强制恢复二次确认（「查看详细配置」入口）：文案与渲染复用一键恢复那套 */
const confirmForceRestoreDetail = (
  target: string,
  item: { time: string },
  isMas: boolean,
  detail: string
): Promise<boolean> =>
  new Promise<boolean>(forceResolve => {
    const copy = buildCorruptedForceConfirm(t, detail)
    Modal.confirm({
      title: copy.title,
      content: corruptedForceConfirmContent(copy.detail, copy.desc),
      okText: copy.okText,
      okType: 'danger',
      cancelText: t('core.edit.cancel'),
      onOk: async () => {
        try {
          forceResolve(await restoreForDetailView(target, item, isMas, true))
        } catch (e) {
          message.error(e instanceof Error ? e.message : t('core.edit.configRestoreFailed'))
          forceResolve(false)
        }
      },
      onCancel: () => forceResolve(false),
    })
  })

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

const persistAppList = (list: { app_id: string; enabled: boolean }[]) => {
  formData.OneDragon.AppList = JSON.stringify(list)
  void saveField('OneDragon.AppList', formData.OneDragon.AppList)
}

/** 按当前模式落盘任务看板：原生来源写实例原生编排；独立来源写 AppList 字段 */
const commitTaskBoard = (list: TaskCard[]) => {
  if (formData.Info.Base === 'native') {
    nativeTasks.value = list
    void saveNativeConfig({ tasks: toNativeTaskIn(list) }, 'tasks', true)
    return
  }
  persistAppList(list.map(card => ({ app_id: card.app_id, enabled: !!card.enabled })))
}

// ══ 原生 GUI 设置会话（原生来源专用；viewOnly 为只读查看会话）══
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

const handleZzzodConfig = async () => {
  if (configLocked.value) return
  await flushPendingSaves()
  if (formData.Info.Base === 'native') {
    // 原生来源：拉起脚本级原生会话——完整原生实例列表，不隔离、不注入，
    // 界面里的改动即真实落地一条龙原始配置（会话关闭后页面自动刷新）。
    // 传当前编辑实例：会话窗口临时切活跃到它（GUI 打开即所见实例，结束还原）
    void startSession(scriptId, false, nativeInstanceIdx.value, 'script')
    return
  }
  if (!userId.value) return
  void startSession(userId.value, false, undefined, 'user')
}

const handleSaveZzzodConfig = () => {
  void saveSession()
}

const handleCloseZzzodView = () => {
  void stopSession()
}

const handleCancel = async () => {
  await flushPendingSaves()
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
    if (!scriptApiError.value) message.error(t('core.edit.zzzodScriptNotFound'))
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
    if (!userApiError.value) message.error(t('core.edit.couldNotLoadUser'))
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
    // 已是原生来源的用户：公共初始化（备份 + 默认实例 + 加载原生配置）
    if (formData.Info.Base === 'native') {
      await enterDirectMode()
    } else {
      // 独立来源进入：归档一条龙原生配置当前状态（MAS 操作前的原始态，
      // 指纹去重），保证后续 MAS 侧修改始终有可还原的进入时点
      await ensureDirectBackup()
    }
  }
})

// 「在一条龙内配置」会话结束后回读会刷新后端字段，重新拉取保持表单同步。
// 查看会话（view mask）虽不回读字段，但「查看详细配置」会先真恢复备份——
// 会话结束后表单同样需要按恢复后的配置重新拉取，否则旧表单值会在用户
// 下次保存时写回、静默撤销恢复。原生来源时以所选实例的原生配置为准。
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
  if (formData.Info.Base === 'native') {
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
  // 编辑会话退出时机：原生来源归档一条龙终态（进入时的 ensureDirectBackup 与之
  // 配对）；独立来源归档绑定槽 MAS 终态 + 一条龙终态（与进入时的
  // ensureDirectBackup 配对）。指纹去重，内容无变化不产生新条目。
  // 先停会话再归档——并行会与回写撞车，归档到半程状态
  void (async () => {
    await flushPendingSaves()
    await stopSession()
    if (formData.Info.Base === 'native') {
      await ensureDirectBackup()
    } else {
      await ensureUserExitBackups()
    }
  })()
})

const selectManagedInstance = async (idx: number) => {
  await flushPendingSaves()
  nativeInstanceIdx.value = idx
  await loadNativeConfig(idx)
}
const clearDeletedInstance = (idx: number) => {
  if (nativeInstanceIdx.value !== idx) return
  nativeInstanceIdx.value = null
  nativeAccountFields.value = []
  Object.keys(nativeAccountValues).forEach(k => delete nativeAccountValues[k])
  nativeTasks.value = []
}
</script>

<style scoped>
@import './ZzzOdUserEdit/zzzodSectionHeader.css';

@import './ZzzOdUserEdit/zzzodTaskCapsule.css';

@import './ZzzOdUserEdit/zzzodFormControls.css';

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

.section-desc {
  color: var(--ant-color-text-tertiary);
  margin: 8px 0 16px;
  font-size: 14px;
}

/* 启动参数折叠区：与可选区块同款边框卡片（总开关在所属卡片标题行） */
.optional-section {
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  scroll-margin-top: 32px;
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

/* 原生来源绑定提示与原生配置保存按钮间距 */
.native-bind-alert {
  margin-bottom: 8px;
}

.native-bind-alert + .ant-spin-nested-loading {
  margin-top: 8px;
}

/* 原生来源账号字段「保存设置」：左对齐，与下方下一区块拉开间距 */

/* 原生来源账号字段必填标记（账号切换需要完整登录信息） */

/* 原生来源：实例管理（与任务卡片同一视觉语言：同边框/底色/圆角/悬停） */

/* 非活跃实例的「设为活跃」：与「当前活跃」同为 tag 形态，灰色可点击 */

.config-form :deep(.ant-form-item) {
  margin-bottom: 24px;
}

/* 一条龙任务卡片网格（对齐任务配置区的卡片 + 开关交互语言） */

/* 单行卡片：名称 | ⚙ / 跳转 | 开关，动作紧邻开关对齐 */

/* 任务卡片 ⚙：可配置任务高亮 */

/* 计划编辑弹窗 */

/* 开关胶囊 */

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
