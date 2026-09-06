<template>
  <div
    class="bettergi-groups-settings-panel"
    :class="{ 'bettergi-groups-settings-panel-embedded': embedded }"
  >
    <!-- 主面板容器（非弹窗态）包裹 loading -->
    <a-spin :spinning="loading" size="small">
      <template v-if="sections.length">
        <!-- 分组用标签页承载；多分组/单分组都保留标签 -->
        <a-tabs v-model:activeKey="activeTabKey" class="bettergi-groups-tabs">
          <!-- 标签栏最右侧：放大按钮（弹窗态不再嵌套放大） -->
          <template v-if="!embedded" #tabBarExtraContent>
            <a-tooltip :title="t('edit.bettergiGroupSettingsZoom')" placement="top">
              <a-button
                type="text"
                size="small"
                class="bettergi-groups-zoom-btn"
                :aria-label="t('edit.bettergiGroupSettingsZoom')"
                @click="zoomed = true"
              >
                <template #icon><FullscreenOutlined /></template>
              </a-button>
            </a-tooltip>
          </template>

          <a-tab-pane
            v-for="section in sections"
            :key="section.title"
            :tab="section.title"
          >
            <!-- 每周秘境：周表（默认 + 周一~周日）表格渲染 -->
            <div v-if="section.kind === 'weekly-table'" class="bettergi-weekly-table-wrap">
              <div class="bettergi-weekly-table-top">
                <a-switch
                  :checked="weeklySectionEnabled(section)"
                  @change="(checked: boolean | string | number) =>
                    weeklySectionToggle(section, Boolean(checked))"
                />
                <span class="bettergi-weekly-table-top-label">
                  {{ section.enableField?.label }}
                </span>
                <a-tooltip v-if="section.enableField?.help" :title="section.enableField?.help">
                  <QuestionCircleOutlined class="bettergi-setting-help-icon" />
                </a-tooltip>
                <a-popconfirm
                  :title="t('edit.bettergiDomainPickerClearAllConfirm')"
                  :disabled="!weeklySectionEnabled(section)"
                  @confirm="clearWeeklyTable(section)"
                >
                  <a-button
                    size="small"
                    class="bettergi-weekly-clear-btn"
                    :disabled="!weeklySectionEnabled(section)"
                  >
                    {{ t('edit.bettergiDomainPickerClearAll') }}
                  </a-button>
                </a-popconfirm>
              </div>
              <a-table
                :data-source="section.weeklyRows || []"
                :columns="weeklyColumns"
                :pagination="false"
                size="small"
                row-key="uid"
                class="bettergi-weekly-table"
              >
                <template #bodyCell="{ column, record }">
                  <!-- 队伍：文本输入 -->
                  <a-input
                    v-if="column.key === 'party'"
                    :value="String(tableCellValue(record, 'party') ?? '')"
                    :disabled="!weeklySectionEnabled(section)"
                    :placeholder="t('edit.bettergiGroupSettingsPlaceholder')"
                    @change="(e: Event) =>
                      emit('update', tableCellField(record, 'party'), (e.target as HTMLInputElement).value)"
                  />
                  <!-- 秘境：有目录时点击弹三级级联选择；无目录数据时退回手输，避免锁死 -->
                  <a-button
                    v-else-if="column.key === 'domain' && weeklyDomainOptions.length > 0"
                    size="small"
                    class="bettergi-weekly-domain-btn"
                    :disabled="!weeklySectionEnabled(section)"
                    @click="openDomainPicker(record)"
                  >
                    {{ weeklyDomainText(record) || t('edit.bettergiGroupSettingsPlaceholder') }}
                  </a-button>
                  <a-input
                    v-else-if="column.key === 'domain'"
                    :value="String(tableCellValue(record, 'domain') ?? '')"
                    :disabled="!weeklySectionEnabled(section)"
                    :placeholder="t('edit.bettergiGroupSettingsPlaceholder')"
                    @change="(e: Event) =>
                      emit('update', tableCellField(record, 'domain'), (e.target as HTMLInputElement).value)"
                  />
                  <!-- 奖励物品：依赖秘境（未选秘境禁用）；默认=不指定，选物品名即存档位 1/2/3 -->
                  <a-select
                    v-else-if="column.key === 'reward'"
                    :value="weeklyRewardDisplayValue(record)"
                    :options="weeklyRewardOptions(record)"
                    :disabled="!weeklySectionEnabled(section) || !weeklyRewardEnabled(record)"
                    :placeholder="t('edit.bettergiGroupSettingsPlaceholder')"
                    @change="(value: unknown) =>
                      emit('update', tableCellField(record, 'reward'), value == null ? '' : String(value))"
                  />
                  <!-- 日期标签列：纯文本 -->
                  <span v-else>{{ record.label }}</span>
                </template>
              </a-table>
            </div>
            <!-- 通用周表（如地脉花「每周刷取」）：周一~周日 × 若干字段列 -->
            <div
              v-else-if="section.kind === 'weekly-field-table'"
              class="bettergi-weekly-table-wrap"
            >
              <a-table
                :data-source="section.weeklyFieldRows || []"
                :columns="weeklyFieldColumns(section)"
                :pagination="false"
                size="small"
                row-key="uid"
                class="bettergi-weekly-table"
              >
                <template #bodyCell="{ column, record }">
                  <!-- 日期标签列 -->
                  <span v-if="column.key === 'label'">{{ record.label }}</span>
                  <!-- 各字段列：复用字段类型渲染（地区/任务类型为下拉，执行为开关） -->
                  <template v-else>
                    <a-switch
                      v-if="weeklyFieldCell(record, column.key)?.type === 'bool'"
                      :checked="Boolean(fieldValue(weeklyFieldCell(record, column.key)!))"
                      @change="(checked: boolean | string | number) =>
                        emit('update', weeklyFieldCell(record, column.key)!, Boolean(checked))"
                    />
                    <a-select
                      v-else-if="weeklyFieldCell(record, column.key)?.type === 'select'"
                      :value="String(fieldValue(weeklyFieldCell(record, column.key)!) ?? '')"
                      :options="weeklyFieldCell(record, column.key)!.options"
                      :placeholder="t('edit.bettergiGroupSettingsPlaceholder')"
                      allow-clear
                      @change="(value: unknown) =>
                        emit('update', weeklyFieldCell(record, column.key)!, value == null ? '' : String(value))"
                    />
                    <a-input
                      v-else-if="weeklyFieldCell(record, column.key)"
                      :value="String(fieldValue(weeklyFieldCell(record, column.key)!) ?? '')"
                      :placeholder="t('edit.bettergiGroupSettingsPlaceholder')"
                      @change="(e: Event) =>
                        emit('update', weeklyFieldCell(record, column.key)!, (e.target as HTMLInputElement).value)"
                    />
                  </template>
                </template>
              </a-table>
            </div>
            <div v-else class="bettergi-groups-settings-fields">
              <!-- 布尔开关（invert=true 时界面勾选与存储取反）。
                   key 用 id||key：同一数据 key 可派生互斥双开关等界面字段（id 去重） -->
              <div v-for="field in section.fields" :key="field.id || field.key">
                <div v-if="field.type === 'bool'" class="bettergi-setting-row" v-show="!field.hideWhenDisabled || !fieldLocked(field)"
                  :class="{ 'bettergi-setting-locked': fieldLocked(field) }">
                  <span class="bettergi-setting-label">
                    <span class="bettergi-setting-label-text">{{ field.label }}</span>
                    <a-tooltip v-if="field.help" :title="field.help">
                      <QuestionCircleOutlined class="bettergi-setting-help-icon" />
                    </a-tooltip>
                  </span>
                  <a-switch
                    :checked="field.invert ? !Boolean(fieldValue(field)) : Boolean(fieldValue(field))"
                    :disabled="fieldLocked(field)"
                    @change="(checked: boolean | string | number) => {
                      const raw = field.invert ? !Boolean(checked) : Boolean(checked)
                      emit('update', field, raw)
                    }"
                  />
                </div>
                <!-- 数字 -->
                <div v-else-if="field.type === 'number'" class="bettergi-setting-row" v-show="!field.hideWhenDisabled || !fieldLocked(field)"
                  :class="{ 'bettergi-setting-locked': fieldLocked(field) }">
                  <span class="bettergi-setting-label">
                    <span class="bettergi-setting-label-text">{{ field.label }}</span>
                    <a-tooltip v-if="field.help" :title="field.help">
                      <QuestionCircleOutlined class="bettergi-setting-help-icon" />
                    </a-tooltip>
                  </span>
                  <a-input-number
                    :value="Number(fieldValue(field)) || 0"
                    :min="field.min ?? 0"
                    :max="field.max"
                    :step="field.step ?? 1"
                    :disabled="fieldLocked(field)"
                    @change="(value: number | string | null) => emit('update', field, Number(value) || 0)"
                  />
                </div>
                <!-- 多选：数组字段（如尘歌壶奖励对象） -->
                <div v-else-if="field.type === 'multi'" class="bettergi-setting-row" v-show="!field.hideWhenDisabled || !fieldLocked(field)"
                  :class="{ 'bettergi-setting-locked': fieldLocked(field) }">
                  <span class="bettergi-setting-label">
                    <span class="bettergi-setting-label-text">{{ field.label }}</span>
                    <a-tooltip v-if="field.help" :title="field.help">
                      <QuestionCircleOutlined class="bettergi-setting-help-icon" />
                    </a-tooltip>
                  </span>
                  <a-select
                    mode="multiple"
                    :value="Array.isArray(fieldValue(field)) ? (fieldValue(field) as string[]) : []"
                    :options="field.options"
                    :placeholder="t('edit.bettergiGroupSettingsPlaceholder')"
                    :disabled="fieldLocked(field)"
                    @change="(values: unknown) => emit('update', field, Array.isArray(values) ? values : [])"
                  />
                </div>
                <!-- 下拉（仅点击选择，不开放手输）：地区/策略等候选枚举 -->
                <div v-else-if="field.type === 'select'" class="bettergi-setting-row" v-show="!field.hideWhenDisabled || !fieldLocked(field)"
                  :class="{ 'bettergi-setting-locked': fieldLocked(field) }">
                  <span class="bettergi-setting-label">
                    <span class="bettergi-setting-label-text">{{ field.label }}</span>
                    <a-tooltip v-if="field.help" :title="field.help">
                      <QuestionCircleOutlined class="bettergi-setting-help-icon" />
                    </a-tooltip>
                  </span>
                  <a-select
                    :value="selectDisplayValue(field)"
                    :options="field.options"
                    :placeholder="t('edit.bettergiGroupSettingsPlaceholder')"
                    :show-search="field.searchable"
                    :option-filter-prop="field.searchable ? 'label' : undefined"
                    allow-clear
                    :disabled="fieldLocked(field)"
                    @change="(value: unknown) => emit('update', field, value == null ? '' : String(value))"
                  />
                </div>
                <!-- 战斗策略：点击输入框弹出候选弹窗单选（候选由父组件按后端实时加载传入） -->
                <div v-else-if="field.type === 'strategy'" class="bettergi-setting-row" v-show="!field.hideWhenDisabled || !fieldLocked(field)"
                  :class="{ 'bettergi-setting-locked': fieldLocked(field) }">
                  <span class="bettergi-setting-label">
                    <span class="bettergi-setting-label-text">{{ field.label }}</span>
                    <a-tooltip v-if="field.help" :title="field.help">
                      <QuestionCircleOutlined class="bettergi-setting-help-icon" />
                    </a-tooltip>
                  </span>
                  <a-input
                    :value="String(fieldValue(field) ?? '')"
                    readonly
                    :placeholder="t('edit.bettergiGroupSettingsPlaceholder')"
                    :disabled="fieldLocked(field)"
                    class="bettergi-setting-strategy-input"
                    @click="openStrategyFieldPicker(field)"
                  >
                    <template #suffix>
                      <CloseOutlined
                        v-if="fieldValue(field)"
                        class="bettergi-setting-strategy-clear"
                        @click.stop="emit('update', field, '')"
                      />
                      <DownOutlined v-else class="bettergi-setting-strategy-arrow" />
                    </template>
                  </a-input>
                </div>
                <!-- 讨伐首领：点击输入框弹出二级连列弹窗（地区 → 首领名称-地点） -->
                <div v-else-if="field.type === 'boss'" class="bettergi-setting-row" v-show="!field.hideWhenDisabled || !fieldLocked(field)"
                  :class="{ 'bettergi-setting-locked': fieldLocked(field) }">
                  <span class="bettergi-setting-label">
                    <span class="bettergi-setting-label-text">{{ field.label }}</span>
                    <a-tooltip v-if="field.help" :title="field.help">
                      <QuestionCircleOutlined class="bettergi-setting-help-icon" />
                    </a-tooltip>
                  </span>
                  <a-input
                    :value="bossDisplayValue(field)"
                    readonly
                    :placeholder="t('edit.bettergiGroupSettingsPlaceholder')"
                    :disabled="fieldLocked(field)"
                    class="bettergi-setting-boss-input"
                    @click="openBossFieldPicker(field)"
                  >
                    <template #suffix>
                      <CloseOutlined
                        v-if="fieldValue(field)"
                        class="bettergi-setting-strategy-clear"
                        @click.stop="emit('update', field, '')"
                      />
                      <DownOutlined v-else class="bettergi-setting-strategy-arrow" />
                    </template>
                  </a-input>
                </div>
                <!-- 纯文本 -->
                <div v-else class="bettergi-setting-row" v-show="!field.hideWhenDisabled || !fieldLocked(field)"
                  :class="{ 'bettergi-setting-locked': fieldLocked(field) }">
                  <span class="bettergi-setting-label">
                    <span class="bettergi-setting-label-text">{{ field.label }}</span>
                    <a-tooltip v-if="field.help" :title="field.help">
                      <QuestionCircleOutlined class="bettergi-setting-help-icon" />
                    </a-tooltip>
                  </span>
                  <a-input
                    :value="String(fieldValue(field) ?? '')"
                    :placeholder="t('edit.bettergiGroupSettingsPlaceholder')"
                    :disabled="fieldLocked(field)"
                    @change="(e: Event) => emit('update', field, (e.target as HTMLInputElement).value)"
                  />
                </div>
              </div>
            </div>
          </a-tab-pane>
        </a-tabs>

        <div v-if="!embedded" class="bettergi-groups-settings-actions">
          <a-button
            type="primary"
            :loading="saving"
            :disabled="!dirty"
            @click="emit('save')"
          >
            {{ t('edit.bettergiGroupSettingsSave') }}
          </a-button>
        </div>
      </template>
      <!-- 无设置项的内置组（领取邮件等）：提示空态 -->
      <div v-else-if="!embedded" class="bettergi-groups-settings-none">
        {{ t('edit.bettergiGroupSettingsNone') }}
      </div>
    </a-spin>

    <!-- 放大弹窗：把这些配置放到独立弹窗居中显示（仅主面板触发）。
         与配置组编辑器放大弹窗同为底层 z-index 1000，后弹出的弹窗以更高 z-index 盖在其上 -->
    <a-modal
      v-if="!embedded"
      v-model:open="zoomed"
      :title="zoomTitle"
      :footer="null"
      :width="760"
      centered
      :z-index="1000"
      wrap-class-name="bettergi-groups-zoom-modal"
      @cancel="zoomed = false"
    >
      <BettergiDragonGroupSettings
        v-if="zoomed"
        embedded
        :sections="sections"
        :dragon-settings="dragonSettings"
        :global-domain-settings="globalDomainSettings"
        :global-stygian-settings="globalStygianSettings"
        :domain-catalog="domainCatalog"
        :boss-catalog="bossCatalog"
        @update="(field, value) => emit('update', field, value)"
        @pick-strategy="(field) => emit('pick-strategy', field)"
      />
      <div v-if="zoomed" class="bettergi-groups-settings-actions">
        <a-button
          type="primary"
          :loading="saving"
          :disabled="!dirty"
          @click="emit('save')"
        >
          {{ t('edit.bettergiGroupSettingsSave') }}
        </a-button>
      </div>
    </a-modal>

    <!-- 秘境三级级联弹窗：地区 → 地点-秘境类型 → 奖励物品。
         与放大弹窗/配置组弹窗同为底层 z-index 1000，此弹窗用 1100 盖在其上 -->
    <a-modal
      v-if="domainPickerOpen"
      :open="domainPickerOpen"
      :title="t('edit.bettergiDomainPickerTitle')"
      :width="860"
      centered
      :z-index="1100"
      wrap-class-name="bettergi-domain-picker-modal"
      @cancel="closeDomainPicker"
    >
      <div class="bettergi-domain-picker-cols">
        <!-- 第一级：地区 -->
        <div class="bettergi-domain-picker-col">
          <div class="bettergi-domain-picker-col-title">地区</div>
          <div class="bettergi-domain-picker-list">
            <div
              v-for="region in domainRegions"
              :key="region"
              class="bettergi-domain-picker-item"
              :class="{ active: region === pickRegion }"
              @click="pickRegion = region; pickDomain = ''; pickRewardIndex = null"
            >
              {{ region }}
            </div>
          </div>
        </div>
        <!-- 第二级：该地区的秘境（地点-秘境类型） -->
        <div class="bettergi-domain-picker-col">
          <div class="bettergi-domain-picker-col-title">地点-秘境类型</div>
          <div class="bettergi-domain-picker-list">
            <div
              v-for="item in pickRegionDomains"
              :key="item.name"
              class="bettergi-domain-picker-item"
              :class="{ active: item.name === pickDomain }"
              @click="onPickDomainClick(item)"
            >
              {{ pickDomainItemLabel(item) }}
            </div>
          </div>
        </div>
        <!-- 第三级：奖励物品（圣遗物本无档位，不可选） -->
        <div class="bettergi-domain-picker-col">
          <div class="bettergi-domain-picker-col-title">奖励物品</div>
          <div class="bettergi-domain-picker-list">
            <template v-if="pickIsArtifact">
              <div class="bettergi-domain-picker-empty">
                {{ t('edit.bettergiDomainPickerNone') }}
              </div>
            </template>
            <template v-else>
              <div
                v-for="(reward, index) in pickRewards"
                :key="`${pickDomain}-${reward}`"
                class="bettergi-domain-picker-item"
                :class="{ active: pickRewardIndex === index }"
                @click="onPickRewardClick(index)"
              >
                {{ reward }}
              </div>
              <div v-if="!pickRewards.length" class="bettergi-domain-picker-note">
                先选择左侧秘境
              </div>
            </template>
          </div>
        </div>
      </div>
      <template #footer>
        <a-button @click="closeDomainPicker">取消</a-button>
        <a-button class="bettergi-domain-picker-clear" @click="onClearDomainPicker">
          {{ t('edit.bettergiDomainPickerClear') }}
        </a-button>
        <a-button type="primary" :disabled="!pickDomain" @click="onConfirmDomainPicker">
          {{ t('edit.bettergiDomainPickerOk') }}
        </a-button>
      </template>
    </a-modal>

    <!-- 讨伐首领二级连列弹窗：地区 → 首领名称-地点（BGI AutoBoss 按国家分组，无至冬） -->
    <a-modal
      v-if="bossPickerOpen"
      :open="bossPickerOpen"
      title="选择首领"
      :width="720"
      centered
      :z-index="1100"
      wrap-class-name="bettergi-boss-picker-modal"
      @cancel="closeBossPicker"
    >
      <div class="bettergi-domain-picker-cols bettergi-boss-picker-cols">
        <!-- 第一级：地区 -->
        <div class="bettergi-domain-picker-col">
          <div class="bettergi-domain-picker-col-title">地区</div>
          <div class="bettergi-domain-picker-list">
            <div
              v-for="region in bossRegions"
              :key="region"
              class="bettergi-domain-picker-item"
              :class="{ active: region === pickBossRegion }"
              @click="pickBossRegion = region; pickBossName = ''"
            >
              {{ region }}
            </div>
          </div>
        </div>
        <!-- 第二级：该地区首领（首领名称-地点） -->
        <div class="bettergi-domain-picker-col">
          <div class="bettergi-domain-picker-col-title">首领 Boss</div>
          <div class="bettergi-domain-picker-list">
            <div
              v-for="item in pickRegionBosses"
              :key="item.name"
              class="bettergi-domain-picker-item"
              :class="{ active: item.name === pickBossName }"
              @click="pickBossName = item.name"
            >
              {{ item.label }}
            </div>
            <div v-if="!pickRegionBosses.length" class="bettergi-domain-picker-note">
              先选择左侧地区
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <a-button @click="closeBossPicker">取消</a-button>
        <a-button class="bettergi-domain-picker-clear" @click="onClearBossPicker">
          {{ t('edit.bettergiDomainPickerClear') }}
        </a-button>
        <a-button type="primary" :disabled="!pickBossName" @click="onConfirmBossPicker">
          {{ t('edit.bettergiDomainPickerOk') }}
        </a-button>
      </template>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  CloseOutlined,
  DownOutlined,
  FullscreenOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons-vue'
import type { BetterGIDomainCatalogItem } from '@/api'

// 允许模板内通过文件名自引用（放大弹窗内再次渲染同组件）
defineOptions({ name: 'BettergiDragonGroupSettings' })

type SettingFieldOption = { label: string; value: string }
/** 讨伐首领目录项（后端无此目录，随 schema 由父组件静态传入） */
type BetterGIBossCatalogItem = {
  region: string
  name: string
  label: string
}
type DragonSettingField = {
  key: string
  label: string
  type: 'text' | 'number' | 'bool' | 'select' | 'multi' | 'strategy' | 'boss'
  min?: number
  max?: number
  step?: number
  options?: SettingFieldOption[]
  /** select 开启搜索过滤（首领等大候选集用） */
  searchable?: boolean
  help?: string
  invert?: boolean
  /** dragon=一条龙 per-user 副本；globalDomain=全局 config.json 秘境段；globalStygian=全局 config.json 幽境段 */
  source?: 'dragon' | 'globalDomain' | 'globalStygian'
  /** 供模板 v-for key 去重：同一数据 key 可派生出多个界面字段（如互斥双开关） */
  id?: string
  masterKey?: string
  masterValue?: unknown
  masterInvert?: boolean
  hideWhenDisabled?: boolean
}
/** 每周秘境表格行：一行 = 默认或某一天，队伍/秘境/奖励三个 key 与 BGI 一条龙顶层键一致 */
type WeeklyDomainTableRow = {
  uid: string
  label: string
  partyKey: string
  domainKey: string
  rewardKey: string
}
/** 通用周表行：每行若干字段（如地脉花每周刷取：地区/任务类型/执行） */
type WeeklyFieldRow = {
  uid: string
  label: string
  fields: DragonSettingField[]
}

type DragonSettingSection = {
  title: string
  fields: DragonSettingField[]
  /** 每周秘境表格模式：整体开关 + 周表行（默认 + 周一~周日）；
      通用周表模式：每行 = 周几 + 若干字段列（如地脉花「每周刷取」） */
  kind?: 'weekly-table' | 'weekly-field-table'
  enableField?: DragonSettingField
  weeklyRows?: WeeklyDomainTableRow[]
  /** 通用周表模式（每行 = 周几 + 若干字段列），如地脉花「每周刷取」 */
  weeklyFieldRows?: WeeklyFieldRow[]
}

const props = withDefaults(
  defineProps<{
    sections: DragonSettingSection[]
    dragonSettings: Record<string, unknown>
    globalDomainSettings?: Record<string, unknown>
    /** 全局 config.json 幽境危战段设置（autoStygianOnslaughtConfig，source: 'globalStygian'） */
    globalStygianSettings?: Record<string, unknown>
    loading?: boolean
    saving?: boolean
    dirty?: boolean
    /** true 表示当前渲染在放大弹窗内（不再展示放大按钮/保存区，由外层接管） */
    embedded?: boolean
    /** BetterGI 每周秘境秘境候选 + 每秘境三档奖励物（后端扫描产出表/tp.json） */
    domainCatalog?: BetterGIDomainCatalogItem[]
    /** 讨伐首领目录（地区 → 首领，随 schema 由父组件静态传入；供二级连列弹窗） */
    bossCatalog?: BetterGIBossCatalogItem[]
  }>(),
  {
    globalDomainSettings: () => ({}),
    globalStygianSettings: () => ({}),
    loading: false,
    saving: false,
    dirty: false,
    embedded: false,
    domainCatalog: () => [],
    bossCatalog: () => [],
  }
)

const emit = defineEmits<{
  (e: 'update', field: DragonSettingField, value: unknown): void
  (e: 'save'): void
  /** 点击 strategy 字段：由父组件弹出战斗策略选择弹窗（写入本字段） */
  (e: 'pick-strategy', field: DragonSettingField): void
}>()

const { t } = useI18n()

// 设置分组标签页当前激活项（sections 变化时重置到第一个分组）
const activeTabKey = ref<string>('')
watch(
  () => props.sections,
  (sections) => {
    activeTabKey.value = sections[0]?.title ?? ''
  },
  { immediate: true }
)

// ---- 每周秘境周表（kind: 'weekly-table'）----
// 周表启用开关的界面值（true=该模式启用、整表可编辑）。
// 支持 invert（每日秘境：勾选「开启每日」时 WeeklyDomainEnabled 存 false）。
const weeklySectionEnabled = (section: DragonSettingSection): boolean => {
  const field = section.enableField
  if (!field) return false
  const raw = Boolean(fieldValue(field))
  return field.invert ? !raw : raw
}
// 切换周表启用开关：按 invert 写回（每日秘境勾选→存 false；每周勾选→存 true）
const weeklySectionToggle = (section: DragonSettingSection, checked: boolean): void => {
  const field = section.enableField
  if (!field) return
  emit('update', field, field.invert ? !checked : checked)
}
// 表格列：日期标签 / 队伍(文本) / 秘境(下拉) / 奖励(下拉)
const weeklyColumns = [
  { title: '', key: 'label', width: 72 },
  { title: '队伍', key: 'party' },
  { title: '秘境', key: 'domain' },
  { title: '奖励', key: 'reward' },
]
// 通用周表列：日期标签 + 各行 fields 的列（列标题取该 section 首行的 field.label，
// 周一~周日结构一致时展示统一表头；字段值按“行内同下标 field”读取/写回）
const weeklyFieldColumns = (section: DragonSettingSection): { title: string; key: string; width?: number }[] => {
  const row = section.weeklyFieldRows?.[0]
  const cols: { title: string; key: string; width?: number }[] = [{ title: '', key: 'label', width: 72 }]
  if (row) {
    row.fields.forEach((f, i) => cols.push({ title: f.label, key: `col${i}` }))
  }
  return cols
}
// 通用周表：取该行第 index 列的字段（column.key = col0/col1/...）
const weeklyFieldCell = (
  record: WeeklyFieldRow,
  colKey: string
): DragonSettingField | null => {
  const match = /^col(\d+)$/.exec(colKey)
  if (!match || !record.fields) return null
  const idx = Number(match[1])
  return record.fields[idx] ?? null
}
// 读某行某列的当前值（key 即该行对应字段 key）
const tableCellValue = (row: WeeklyDomainTableRow, col: 'party' | 'domain' | 'reward'): unknown =>
  props.dragonSettings[row[`${col}Key`]]
// 构造该格子的字段描述（用于统一走 update 事件写回 per-user 设置）
const tableCellField = (row: WeeklyDomainTableRow, col: 'party' | 'domain' | 'reward'): DragonSettingField => ({
  key: row[`${col}Key`],
  label: row.label,
  type: col === 'party' ? 'text' : 'select',
  source: 'dragon',
})
// 该行当前选中秘境的目录项（无选中/不在目录中返回 undefined）
const weeklyDomainHit = (row: WeeklyDomainTableRow): BetterGIDomainCatalogItem | undefined => {
  const domainName = String(props.dragonSettings[row.domainKey] ?? '')
  return props.domainCatalog.find(item => item.name === domainName)
}
// 圣遗物本（BlessDomain）没有周日/限时档位概念，选中后奖励列冻结为默认
const weeklyIsArtifactDomain = (row: WeeklyDomainTableRow): boolean =>
  weeklyDomainHit(row)?.category === 'BlessDomain'
// tp.json 的 Domain type → 中文类型（天赋技能材料 / 武器突破材料 / 圣遗物）
const DOMAIN_CATEGORY_LABELS: Record<string, string> = {
  MasteryDomain: '天赋技能材料',
  ForgeryDomain: '武器突破材料',
  BlessDomain: '圣遗物',
}
const domainCategoryLabel = (category: string | undefined): string =>
  (category && DOMAIN_CATEGORY_LABELS[category]) || ''
// 秘境下拉候选：只显示“秘境名（地区-秘境类型）”，不带后面的奖励物文本；奖励物在奖励列展示
const weeklyDomainOptions = computed<SettingFieldOption[]>(() =>
  props.domainCatalog.map(item => {
    const parts: string[] = []
    if (item.region) parts.push(item.region)
    const typeLabel = domainCategoryLabel(item.category)
    if (typeLabel) parts.push(typeLabel)
    return {
      label: parts.length ? `${item.name}（${parts.join('-')}）` : item.name,
      value: item.name,
    }
  })
)
// 当前行秘境在按钮上的展示文本（已选秘境显示“名称（地区-类型）”，未选为空）
const weeklyDomainText = (row: WeeklyDomainTableRow): string => {
  const name = String(props.dragonSettings[row.domainKey] ?? '')
  if (!name) return ''
  const hit = props.domainCatalog.find(item => item.name === name)
  if (!hit) return name
  const parts: string[] = []
  if (hit.region) parts.push(hit.region)
  const typeLabel = domainCategoryLabel(hit.category)
  if (typeLabel) parts.push(typeLabel)
  return parts.length ? `${hit.name}（${parts.join('-')}）` : hit.name
}
// 奖励候选：下拉只显示「默认」+ 该秘境档位物品名（选中即存档位序号 1/2/3）。
// BGI 语义中 0 与空串都表示“不指定/默认”，合并为一项（value "0"）；rewards 顺序照官方 tp.json。
// 圣遗物本（BlessDomain）无档位，只给「默认」。
const weeklyRewardOptions = (row: WeeklyDomainTableRow): SettingFieldOption[] => {
  if (weeklyIsArtifactDomain(row)) return [{ label: '默认', value: '0' }]
  const hit = weeklyDomainHit(row)
  const rewards = hit?.rewards || []
  const base: SettingFieldOption[] = [{ label: '默认', value: '0' }]
  if (rewards.length > 0) {
    rewards.forEach((name, i) => {
      base.push({ label: name, value: String(i + 1) })
    })
  } else {
    // 无奖励物数据：保持原始档位
    ;['1', '2', '3'].forEach(v => base.push({ label: v, value: v }))
  }
  return base
}
// 展示归一：历史配置里 "" 与 "0" 都表示默认，渲染时统一视为 "0"
const weeklyRewardDisplayValue = (row: WeeklyDomainTableRow): string => {
  const raw = String(props.dragonSettings[row.rewardKey] ?? '')
  return raw === '' ? '0' : raw
}
// 奖励列依赖该行秘境：未选秘境或选了圣遗物本（BlessDomain）都不可选
const weeklyRewardEnabled = (row: WeeklyDomainTableRow): boolean => {
  if (!String(props.dragonSettings[row.domainKey] ?? '').trim()) return false
  return !weeklyIsArtifactDomain(row)
}
// 切换秘境：非圣遗物保留原奖励；若改成圣遗物本（无档位），奖励强制回到默认
const weeklyDomainChanged = (row: WeeklyDomainTableRow, value: unknown): void => {
  const domain = value == null ? '' : String(value)
  emit('update', tableCellField(row, 'domain'), domain)
  const hit = props.domainCatalog.find(item => item.name === domain)
  if (hit?.category === 'BlessDomain') {
    emit('update', tableCellField(row, 'reward'), '0')
  }
}

// ---- 秘境三级级联弹窗（地区 → 地点-类型 → 奖励物品）----
const domainPickerOpen = ref(false)
// 正在编辑的周表行（点击秘境列时记录）
const domainPickerRow = ref<WeeklyDomainTableRow | null>(null)
const pickRegion = ref('')
const pickDomain = ref('')
// 第三级已选档位（rewards 下标，0-based）；null=未选奖励
const pickRewardIndex = ref<number | null>(null)
// 地区列表（按目录出现顺序去重，保证与 BGI 传送点顺序接近）
const domainRegions = computed<string[]>(() => {
  const seen: string[] = []
  for (const item of props.domainCatalog) {
    const region = item.region || ''
    if (region && !seen.includes(region)) seen.push(region)
  }
  return seen
})
const pickRegionDomains = computed<BetterGIDomainCatalogItem[]>(() =>
  props.domainCatalog.filter(item => item.region === pickRegion.value)
)
const pickDomainItem = computed<BetterGIDomainCatalogItem | undefined>(() =>
  props.domainCatalog.find(item => item.name === pickDomain.value)
)
// 圣遗物本：第三级不可选（确认后奖励=默认 0）
const pickIsArtifact = computed<boolean>(() => pickDomainItem.value?.category === 'BlessDomain')
const pickRewards = computed<string[]>(() => pickDomainItem.value?.rewards || [])
// 第二级项 label：地点-秘境类型
const pickDomainItemLabel = (item: BetterGIDomainCatalogItem): string => {
  const typeLabel = domainCategoryLabel(item.category)
  return typeLabel ? `${item.name}-${typeLabel}` : item.name
}
// 当前编辑行已存奖励档位（用于弹窗回显高亮）
const weeklyRewardDisplayValueOfRow = (): string => {
  const row = domainPickerRow.value
  return row ? weeklyRewardDisplayValue(row) : ''
}
// 弹窗打开：以该行已存秘境/奖励预置高亮
const openDomainPicker = (row: WeeklyDomainTableRow): void => {
  domainPickerRow.value = row
  const domain = String(props.dragonSettings[row.domainKey] ?? '')
  const hit = props.domainCatalog.find(item => item.name === domain)
  pickRegion.value = hit?.region || ''
  pickDomain.value = hit?.name || ''
  const storedReward = weeklyRewardDisplayValue(row)
  const idx = storedReward ? Number(storedReward) - 1 : null
  pickRewardIndex.value = idx != null && idx >= 0 && idx < (hit?.rewards?.length || 0) ? idx : null
  domainPickerOpen.value = true
}
const closeDomainPicker = (): void => {
  domainPickerOpen.value = false
  domainPickerRow.value = null
}
// 点击秘境（第二级）：圣遗物第三级不可选，奖励清空等确认；否则等待选奖励
const onPickDomainClick = (item: BetterGIDomainCatalogItem): void => {
  pickDomain.value = item.name
  pickRewardIndex.value = null
}
// 点击奖励物品（第三级）：记录下标（0-based），统一由确认按钮回填
const onPickRewardClick = (index: number): void => {
  if (!pickDomain.value) return
  pickRewardIndex.value = index
}
// 底部确认：回填秘境名 + 奖励档位（选了第三级 → index+1；圣遗物/未选 → "0"）
const onConfirmDomainPicker = (): void => {
  const row = domainPickerRow.value
  if (!row || !pickDomain.value) return
  const reward = pickRewardIndex.value != null && !pickIsArtifact.value
    ? pickRewardIndex.value + 1
    : 0
  emit('update', tableCellField(row, 'domain'), pickDomain.value)
  emit('update', tableCellField(row, 'reward'), String(reward))
  closeDomainPicker()
}
// 弹窗清除：清空当前行的秘境与奖励（秘境留空=跟随全局/兜底，奖励回默认 "0"）
const onClearDomainPicker = (): void => {
  const row = domainPickerRow.value
  if (!row) return
  emit('update', tableCellField(row, 'domain'), '')
  emit('update', tableCellField(row, 'reward'), '0')
  closeDomainPicker()
}
// 整表清空：把该周表所有行的秘境/奖励逐字段清空（队伍名保留不误伤），
// 仅当整表可编辑（启用开关打开）时提供入口
const clearWeeklyTable = (section: DragonSettingSection): void => {
  if (!weeklySectionEnabled(section)) return
  const rows = section.weeklyRows || []
  for (const row of rows) {
    emit('update', tableCellField(row, 'domain'), '')
    emit('update', tableCellField(row, 'reward'), '0')
  }
}

// 放大弹窗开关
const zoomed = ref(false)
const zoomTitle = computed(() => t('edit.bettergiGroupSettingsTitle'))

// 读取字段当前值：一条龙字段走 per-user 副本；globalDomain/globalStygian 走全局 config.json 段
const fieldValue = (field: DragonSettingField): unknown => {
  if (field.source === 'globalDomain') return props.globalDomainSettings?.[field.key]
  if (field.source === 'globalStygian') return props.globalStygianSettings?.[field.key]
  return props.dragonSettings[field.key]
}

// 下拉展示值归一：BGI 奖励序号等字段历史值 "0" 与空串同义（默认），
// 当候选里只有 value="" 的「默认」项时，把存量的 "0" 归一为空串显示。
const selectDisplayValue = (field: DragonSettingField): string => {
  const raw = String(fieldValue(field) ?? '')
  const options = field.options || []
  if (raw === '0' && options.length && !options.some(o => o.value === '0') && options.some(o => o.value === '')) {
    return ''
  }
  return raw
}

// 字段是否因 master 联动被冻结（true 不可编辑；hideWhenDisabled 时整行隐藏）
const fieldLocked = (field: DragonSettingField): boolean => {
  if (!field.masterKey) return false
  const master =
    field.source === 'globalDomain'
      ? props.globalDomainSettings?.[field.masterKey]
      : field.source === 'globalStygian'
        ? props.globalStygianSettings?.[field.masterKey]
        : props.dragonSettings[field.masterKey]
  const hit = master === field.masterValue
  return field.masterInvert ? hit : !hit
}

// 点击战斗策略字段：交由父组件打开策略选择弹窗（候选由父组件实时加载）
const openStrategyFieldPicker = (field: DragonSettingField): void => {
  if (fieldLocked(field)) return
  emit('pick-strategy', field)
}

// ---- 讨伐首领二级连列弹窗（地区 → 首领名称-地点）----
const bossPickerOpen = ref(false)
/** 正在编辑的字段（打开弹窗时记录，确认后写回） */
const bossPickerField = ref<DragonSettingField | null>(null)
const pickBossRegion = ref('')
const pickBossName = ref('')
// 地区列：按目录出现顺序去重（与 BGI CountryToBosses 顺序一致）
const bossRegions = computed<string[]>(() => {
  const seen: string[] = []
  for (const item of props.bossCatalog) {
    if (item.region && !seen.includes(item.region)) seen.push(item.region)
  }
  return seen
})
// 第二级：当前地区的首领候选（首领名称-地点）
const pickRegionBosses = computed<BetterGIBossCatalogItem[]>(() =>
  props.bossCatalog.filter(item => item.region === pickBossRegion.value)
)
// 回显：存储值为首领名（如「纯水精灵」），显示为「首领名称-地点」（如「纯水精灵-璃月」）；
// 旧值可能是完整 label 或目录外文本，原样展示兜底
const bossDisplayValue = (field: DragonSettingField): string => {
  const raw = String(fieldValue(field) ?? '')
  if (!raw) return ''
  const hit = props.bossCatalog.find(item => item.name === raw)
  if (hit) return hit.label
  return raw
}
// 弹窗打开：以已存首领反查地区并预置高亮
const openBossFieldPicker = (field: DragonSettingField): void => {
  if (fieldLocked(field)) return
  bossPickerField.value = field
  const raw = String(fieldValue(field) ?? '')
  const hit = props.bossCatalog.find(item => item.name === raw)
  pickBossRegion.value = hit?.region || bossRegions.value[0] || ''
  pickBossName.value = hit?.name || ''
  bossPickerOpen.value = true
}
const closeBossPicker = (): void => {
  bossPickerOpen.value = false
  bossPickerField.value = null
}
// 清除当前首领（写回空）
const onClearBossPicker = (): void => {
  const field = bossPickerField.value
  if (!field) return
  emit('update', field, '')
  closeBossPicker()
}
// 确认：写回首领名（BGI AutoBossName 语义），显示由 bossDisplayValue 拼地区
const onConfirmBossPicker = (): void => {
  const field = bossPickerField.value
  if (!field || !pickBossName.value) return
  emit('update', field, pickBossName.value)
  closeBossPicker()
}
</script>

<style scoped>
.bettergi-groups-tabs {
  max-width: 100%;
}

/* 无设置项的内置组（领取邮件等）空态提示 */
.bettergi-groups-settings-none {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 120px;
  padding: 16px;
  font-size: 14px;
  color: var(--ant-color-text-tertiary);
}

.bettergi-groups-settings-fields {
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-height: 340px;
  overflow-y: auto;
  padding-right: 4px;
  padding-top: 4px;
}

/* 每行：左 1/3 放 label（可换行），右 2/3 放控件 */
.bettergi-setting-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 2fr);
  gap: 12px;
  align-items: center;
  transition: opacity 0.15s ease;
}
/* 受 master 开关联动的冻结行：整体灰显、控件不可点 */
.bettergi-setting-row.bettergi-setting-locked {
  opacity: 0.55;
}
.bettergi-setting-row.bettergi-setting-locked :deep(.ant-switch),
.bettergi-setting-row.bettergi-setting-locked :deep(.ant-input-number),
.bettergi-setting-row.bettergi-setting-locked :deep(.ant-select),
.bettergi-setting-row.bettergi-setting-locked :deep(.ant-input),
.bettergi-setting-row.bettergi-setting-locked :deep(.ant-input-affix-wrapper) {
  pointer-events: none;
}

.bettergi-setting-label {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  min-width: 0;
  font-size: 14px;
  font-weight: 500;
  color: var(--ant-color-text);
  line-height: 1.6;
}
/* 文字过长自动换行（不再截断省略） */
.bettergi-setting-label-text {
  flex: 0 1 auto;
  min-width: 0;
  white-space: normal;
  word-break: break-word;
  overflow-wrap: anywhere;
}
.bettergi-setting-help-icon {
  flex: 0 0 auto;
  margin-top: 3px;
  font-size: 13px;
  color: var(--ant-color-text-tertiary);
  cursor: help;
}
.bettergi-setting-help-icon:hover {
  color: var(--ant-color-primary);
}

.bettergi-setting-row :deep(.ant-input-number),
.bettergi-setting-row :deep(.ant-select),
.bettergi-setting-row :deep(.ant-input),
.bettergi-setting-row :deep(.ant-input-affix-wrapper) {
  width: 100%;
  min-width: 0;
  justify-self: stretch;
}
/* 开关列宽占满但开关本身右侧贴合（保留 antd 开关外观） */
.bettergi-setting-row :deep(.ant-switch) {
  justify-self: start;
}

.bettergi-setting-row :deep(.ant-input-number-input),
.bettergi-setting-row :deep(.ant-select-selection-item),
.bettergi-setting-row :deep(.ant-select-selection-placeholder),
.bettergi-setting-row :deep(.ant-input) {
  font-size: 14px;
}

/* 战斗策略：整框可点击弹候选；suffix 清除/箭头图标 */
.bettergi-setting-strategy-input {
  cursor: pointer;
}
.bettergi-setting-strategy-input :deep(input) {
  cursor: pointer;
}
.bettergi-setting-strategy-arrow,
.bettergi-setting-strategy-clear {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  cursor: pointer;
  transition: color 0.15s ease;
}
.bettergi-setting-strategy-arrow:hover,
.bettergi-setting-strategy-clear:hover {
  color: var(--ant-color-primary);
}
.bettergi-setting-strategy-clear {
  font-size: 12px;
}

.bettergi-groups-settings-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px dashed var(--ant-color-border-secondary);
}

.bettergi-groups-zoom-btn {
  color: var(--ant-color-text-secondary);
}
.bettergi-groups-zoom-btn:hover {
  color: var(--ant-color-primary);
}

/* 放大弹窗内（embedded 自引用实例）字段列表可更高，充分利用弹窗空间 */
.bettergi-groups-settings-panel-embedded .bettergi-groups-settings-fields {
  max-height: 60vh;
}

/* ---- 每周秘境周表 ---- */
.bettergi-weekly-table-wrap {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 340px;
  overflow-y: auto;
  padding-right: 4px;
  padding-top: 4px;
}

.bettergi-weekly-table-top {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  color: var(--ant-color-text);
}

.bettergi-weekly-table-top-label {
  font-weight: 500;
}

/* 周表顶部“清空”按钮贴右，避免误触开关/帮助 */
.bettergi-weekly-clear-btn {
  margin-left: auto;
  color: var(--ant-color-text-tertiary);
}
.bettergi-weekly-clear-btn:hover:not(:disabled) {
  color: var(--ant-color-error);
  border-color: var(--ant-color-error);
}

.bettergi-weekly-table :deep(.ant-table) {
  font-size: 13px;
}

.bettergi-weekly-table :deep(.ant-table-thead > tr > th) {
  padding: 6px 8px;
}

.bettergi-weekly-table :deep(.ant-table-tbody > tr > td) {
  padding: 5px 8px;
}

.bettergi-weekly-table :deep(.ant-select),
.bettergi-weekly-table :deep(.ant-input) {
  width: 100%;
}

.bettergi-weekly-table :deep(.ant-select-selection-item),
.bettergi-weekly-table :deep(.ant-select-selection-placeholder),
.bettergi-weekly-table :deep(.ant-input) {
  font-size: 13px;
}

/* 放大弹窗内周表可更高 */
.bettergi-groups-settings-panel-embedded .bettergi-weekly-table-wrap {
  max-height: 60vh;
}

/* 秘境单元格按钮：与下拉同宽、左对齐，便于点击唤起级联弹窗 */
.bettergi-weekly-domain-btn {
  width: 100%;
  text-align: left;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  justify-content: flex-start;
}

/* ---- 秘境三级级联弹窗 ---- */
.bettergi-domain-picker-cols {
  display: grid;
  grid-template-columns: 1fr 1.4fr 1.4fr;
  gap: 12px;
  min-height: 320px;
}
/* 讨伐首领二级连列弹窗：两列（地区 | 首领名称-地点） */
.bettergi-boss-picker-cols {
  grid-template-columns: 1fr 2fr;
  min-height: 360px;
}
.bettergi-boss-picker-cols .bettergi-domain-picker-col-title {
  white-space: nowrap;
}
.bettergi-domain-picker-col {
  display: flex;
  flex-direction: column;
  min-width: 0;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  overflow: hidden;
}
.bettergi-domain-picker-col-title {
  padding: 8px 10px;
  font-size: 13px;
  font-weight: 600;
  color: var(--ant-color-text-secondary);
  background: var(--ant-color-fill-quaternary);
  border-bottom: 1px solid var(--ant-color-border-secondary);
}
.bettergi-domain-picker-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.bettergi-domain-picker-item {
  padding: 7px 10px;
  border-radius: 6px;
  font-size: 13px;
  color: var(--ant-color-text);
  cursor: pointer;
  line-height: 1.5;
  word-break: break-word;
}
.bettergi-domain-picker-item:hover {
  background: var(--ant-color-fill-secondary);
}
.bettergi-domain-picker-item.active {
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  font-weight: 500;
}
.bettergi-domain-picker-note {
  padding: 8px 10px;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}
/* 圣遗物本（无档位）：第三级整列居中的空态提示 */
.bettergi-domain-picker-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  min-height: 120px;
  padding: 16px;
  font-size: 13px;
  color: var(--ant-color-text-tertiary);
  text-align: center;
}
</style>
