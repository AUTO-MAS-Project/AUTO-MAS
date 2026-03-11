<template>
  <div class="form-section">
    <div class="section-header">
      <h3>关卡配置</h3>
    </div>

    <!-- 第一行：刷取类型 | 当前生效关卡 -->
    <a-row :gutter="24">
      <a-col :span="12">
        <a-form-item name="Channel">
          <template #label>
            <a-tooltip title="选择要刷取的关卡类型">
              <span class="form-label">
                刷取类型
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select v-model:value="formData.Stage.Channel" size="large" placeholder="请选择刷取类型"
            @change="emitSave('Stage.Channel', formData.Stage.Channel)">
            <a-select-option value="Relic">遗器</a-select-option>
            <a-select-option value="Materials">材料</a-select-option>
            <a-select-option value="Ornament">饰品</a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <a-form-item>
          <template #label>
            <a-tooltip title="从Tag中获取的当前生效关卡">
              <span class="form-label">
                当前生效关卡
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <div class="current-stage-display">
            <a-tag :color="getCurrentStageColor()" size="large" class="stage-tag">
              {{ getCurrentStage() }}
            </a-tag>
          </div>
        </a-form-item>
      </a-col>
    </a-row>

    <!-- 第二行：遗器关卡 | 饰品关卡 -->
    <a-row :gutter="24">
      <a-col :span="12">
        <a-form-item name="Relic">
          <template #label>
            <a-tooltip title="选择要刷取的遗器关卡">
              <span class="form-label">
                遗器关卡
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select v-model:value="formData.Stage.Relic" size="large" placeholder="请选择遗器关卡" show-search
            :filter-option="filterOption" @change="emitSave('Stage.Relic', formData.Stage.Relic)">
            <a-select-option value="-">沿用原始配置</a-select-option>
            <a-select-option value="Cavern_of_Corrosion_Path_of_Possession">遗器：魔法少女 & 卜者（魔占之径）</a-select-option>
            <a-select-option value="Cavern_of_Corrosion_Path_of_Hidden_Salvation">遗器：救世主 & 隐士（隐救之径）</a-select-option>
            <a-select-option value="Cavern_of_Corrosion_Path_of_Thundersurge">遗器：烈阳 & 船长（雳涌之径）</a-select-option>
            <a-select-option value="Cavern_of_Corrosion_Path_of_Aria">遗器：英豪 & 诗人（弦歌之径）</a-select-option>
            <a-select-option value="Cavern_of_Corrosion_Path_of_Uncertainty">遗器：司铎 & 学者（迷识之径）</a-select-option>
            <a-select-option value="Cavern_of_Corrosion_Path_of_Cavalier">遗器：铁骑 & 勇烈（勇骑之径）</a-select-option>
            <a-select-option value="Cavern_of_Corrosion_Path_of_Dreamdive">遗器：死水 & 钟表匠（梦潜之径）</a-select-option>
            <a-select-option value="Cavern_of_Corrosion_Path_of_Darkness">遗器：大公 & DoT套（幽冥之径）</a-select-option>
            <a-select-option value="Cavern_of_Corrosion_Path_of_Elixir_Seekers">遗器：莳者 & 信使（药使之径）</a-select-option>
            <a-select-option value="Cavern_of_Corrosion_Path_of_Conflagration">遗器：火套 & 虚数套（野焰之径）</a-select-option>
            <a-select-option value="Cavern_of_Corrosion_Path_of_Holy_Hymn">遗器：防御套 & 雷套（圣颂之径）</a-select-option>
            <a-select-option value="Cavern_of_Corrosion_Path_of_Providence">遗器：铁卫 & 量子套（睿治之径）</a-select-option>
            <a-select-option value="Cavern_of_Corrosion_Path_of_Drifting">遗器：治疗套 & 快枪手（漂泊之径）</a-select-option>
            <a-select-option value="Cavern_of_Corrosion_Path_of_Jabbing_Punch">遗器：物理套 & 怪盗（迅拳之径）</a-select-option>
            <a-select-option value="Cavern_of_Corrosion_Path_of_Gelid_Wind">遗器：冰套 & 风套（霜风之径）</a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <a-form-item name="Ornament">
          <template #label>
            <a-tooltip title="选择要刷取的饰品关卡">
              <span class="form-label">
                饰品关卡
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select v-model:value="formData.Stage.Ornament" size="large" placeholder="请选择饰品关卡" show-search
            :filter-option="filterOption" @change="emitSave('Stage.Ornament', formData.Stage.Ornament)">
            <a-select-option value="-">沿用原始配置</a-select-option>
            <a-select-option value="Divergent_Universe_Within_the_West_Wind">饰品：翁法罗斯 & 天国（西风丛中）</a-select-option>
            <a-select-option value="Divergent_Universe_Moonlit_Blood">饰品：妖精 & 沉醉（月下朱殷）</a-select-option>
            <a-select-option value="Divergent_Universe_Unceasing_Strife">饰品：拾骨地 & 巨树（纷争不休）</a-select-option>
            <a-select-option value="Divergent_Universe_Famished_Worker">饰品：海域 & 奇想（蠹役饥肠）</a-select-option>
            <a-select-option value="Divergent_Universe_Eternal_Comedy">饰品：奔狼 & 火宫（永恒笑剧）</a-select-option>
            <a-select-option value="Divergent_Universe_To_Sweet_Dreams">饰品：茨冈尼亚 & 出云（伴你入眠）</a-select-option>
            <a-select-option value="Divergent_Universe_Pouring_Blades">饰品：苍穹 & 匹诺康尼（天剑如雨）</a-select-option>
            <a-select-option value="Divergent_Universe_Fruit_of_Evil">饰品：繁星 & 龙骨（孽果盘生）</a-select-option>
            <a-select-option value="Divergent_Universe_Permafrost">饰品：贝洛伯格 & 萨尔索图（百年冻土）</a-select-option>
            <a-select-option value="Divergent_Universe_Gentle_Words">饰品：商业公司 & 差分机（温柔话语）</a-select-option>
            <a-select-option value="Divergent_Universe_Smelted_Heart">饰品：盗贼 & 翁瓦克（浴火钢心）</a-select-option>
            <a-select-option value="Divergent_Universe_Untoppled_Walls">饰品：太空 & 仙舟（坚城不倒）</a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
    </a-row>

    <!-- 第三行：材料关类别 | 材料关卡 -->
    <a-row :gutter="24">
      <a-col :span="12">
        <a-form-item>
          <template #label>
            <a-tooltip title="根据材料关卡前缀筛选，该字段不保存">
              <span class="form-label">
                材料关类别
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select v-model:value="materialCategory" size="large" placeholder="全部">
            <a-select-option value="">全部</a-select-option>
            <a-select-option value="Calyx_Golden">拟造花萼（金）</a-select-option>
            <a-select-option value="Calyx_Crimson">拟造花萼（赤）</a-select-option>
            <a-select-option value="Stagnant_Shadow">凝滞虚影</a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <a-form-item name="Materials">
          <template #label>
            <a-tooltip title="选择要刷取的材料关卡">
              <span class="form-label">
                材料关卡
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select v-model:value="formData.Stage.Materials" size="large" placeholder="请选择材料关卡" show-search
            :filter-option="filterOption" @change="emitSave('Stage.Materials', formData.Stage.Materials)">
            <a-select-option value="-">沿用原始配置</a-select-option>
            <template v-for="option in filteredMaterialOptions" :key="option.value">
              <a-select-option :value="option.value">{{ option.label }}</a-select-option>
            </template>
          </a-select>
        </a-form-item>
      </a-col>
    </a-row>

    <!-- 第四行：历战余响 | 模拟宇宙 -->
    <a-row :gutter="24">
      <a-col :span="12">
        <a-form-item name="EchoOfWar">
          <template #label>
            <a-tooltip title="选择要挑战的历战余响关卡">
              <span class="form-label">
                历战余响
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select v-model:value="formData.Stage.EchoOfWar" size="large" placeholder="请选择历战余响" show-search
            :filter-option="filterOption" @change="emitSave('Stage.EchoOfWar', formData.Stage.EchoOfWar)">
            <a-select-option value="-">禁用</a-select-option>
            <a-select-option value="Echo_of_War_Rusted_Crypt_of_the_Iron_Carcass">铁骸的锈冢（翁法罗斯）</a-select-option>
            <a-select-option value="Echo_of_War_Glance_of_Twilight">晨昏的回眸（翁法罗斯）</a-select-option>
            <a-select-option value="Echo_of_War_Inner_Beast_Battlefield">心兽的战场（仙舟「罗浮」）</a-select-option>
            <a-select-option value="Echo_of_War_Salutations_of_Ashen_Dreams">尘梦的赞礼（匹诺康尼）</a-select-option>
            <a-select-option value="Echo_of_War_Borehole_Planet_Past_Nightmares">蛀星的旧魇（空间站「黑塔」）</a-select-option>
            <a-select-option value="Echo_of_War_Divine_Seed">不死的神实（仙舟「罗浮」）</a-select-option>
            <a-select-option value="Echo_of_War_End_of_the_Eternal_Freeze">寒潮的落幕（雅利洛-Ⅵ）</a-select-option>
            <a-select-option value="Echo_of_War_Destruction_Beginning">毁灭的开端（空间站「黑塔」）</a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <a-form-item name="SimulatedUniverseWorld">
          <template #label>
            <a-tooltip title="选择要挑战的模拟宇宙世界">
              <span class="form-label">
                模拟宇宙
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select v-model:value="formData.Stage.SimulatedUniverseWorld" size="large" placeholder="请选择模拟宇宙" show-search
            :filter-option="filterOption"
            @change="emitSave('Stage.SimulatedUniverseWorld', formData.Stage.SimulatedUniverseWorld)">
            <a-select-option value="-">禁用</a-select-option>
            <a-select-option value="Simulated_Universe_World_3">第三世界</a-select-option>
            <a-select-option value="Simulated_Universe_World_4">第四世界</a-select-option>
            <a-select-option value="Simulated_Universe_World_5">第五世界</a-select-option>
            <a-select-option value="Simulated_Universe_World_6">第六世界</a-select-option>
            <a-select-option value="Simulated_Universe_World_8">第八世界</a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
    </a-row>

    <!-- 第五行：使用储备开拓力 | 使用燃料 | 保留的燃料数量 -->
    <a-row :gutter="24">
      <a-col :span="formData.Stage.UseFuel ? 8 : 12">
        <a-form-item name="ExtractReservedTrailblazePower">
          <template #label>
            <a-tooltip title="是否使用储备开拓力">
              <span class="form-label">
                使用储备开拓力
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select v-model:value="formData.Stage.ExtractReservedTrailblazePower" size="large"
            @change="emitSave('Stage.ExtractReservedTrailblazePower', formData.Stage.ExtractReservedTrailblazePower)">
            <a-select-option :value="true">是</a-select-option>
            <a-select-option :value="false">否</a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
      <a-col :span="formData.Stage.UseFuel ? 8 : 12">
        <a-form-item name="UseFuel">
          <template #label>
            <a-tooltip title="是否使用燃料">
              <span class="form-label">
                使用燃料
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select v-model:value="formData.Stage.UseFuel" size="large"
            @change="emitSave('Stage.UseFuel', formData.Stage.UseFuel)">
            <a-select-option :value="true">是</a-select-option>
            <a-select-option :value="false">否</a-select-option>
          </a-select>
        </a-form-item>
      </a-col>
      <a-col v-if="formData.Stage.UseFuel" :span="8">
        <a-form-item name="FuelReserve">
          <template #label>
            <a-tooltip title="保留的燃料数量，使用燃料时会保留此数量">
              <span class="form-label">
                保留的燃料数量
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-input-number v-model:value="formData.Stage.FuelReserve" :min="0" :max="9999" placeholder="5" size="large"
            style="width: 100%" @blur="emitSave('Stage.FuelReserve', formData.Stage.FuelReserve)" />
        </a-form-item>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'

const props = defineProps<{
  formData: any
  loading: boolean
}>()

const emit = defineEmits<{
  save: [key: string, value: any]
}>()

const emitSave = (key: string, value: any) => {
  emit('save', key, value)
}

// 材料关类别筛选
const materialCategory = ref('')

// 材料关卡选项
const materialOptions = [
  // 拟造花萼（金）
  { value: 'Calyx_Golden_Memories_Planarcadia', label: '材料：角色经验（回忆之蕾 二相乐园）', category: 'Calyx_Golden' },
  { value: 'Calyx_Golden_Aether_Planarcadia', label: '材料：武器经验（以太之蕾 二相乐园）', category: 'Calyx_Golden' },
  { value: 'Calyx_Golden_Treasures_Planarcadia', label: '材料：信用点（藏珍之蕾 二相乐园）', category: 'Calyx_Golden' },
  { value: 'Calyx_Golden_Memories_Amphoreus', label: '材料：角色经验（回忆之蕾 翁法罗斯）', category: 'Calyx_Golden' },
  { value: 'Calyx_Golden_Aether_Amphoreus', label: '材料：武器经验（以太之蕾 翁法罗斯）', category: 'Calyx_Golden' },
  { value: 'Calyx_Golden_Treasures_Amphoreus', label: '材料：信用点（藏珍之蕾 翁法罗斯）', category: 'Calyx_Golden' },
  { value: 'Calyx_Golden_Memories_Penacony', label: '材料：角色经验（回忆之蕾 匹诺康尼）', category: 'Calyx_Golden' },
  { value: 'Calyx_Golden_Aether_Penacony', label: '材料：武器经验（以太之蕾 匹诺康尼）', category: 'Calyx_Golden' },
  { value: 'Calyx_Golden_Treasures_Penacony', label: '材料：信用点（藏珍之蕾 匹诺康尼）', category: 'Calyx_Golden' },
  { value: 'Calyx_Golden_Memories_The_Xianzhou_Luofu', label: '材料：角色经验（回忆之蕾 仙舟罗浮）', category: 'Calyx_Golden' },
  { value: 'Calyx_Golden_Aether_The_Xianzhou_Luofu', label: '材料：武器经验（以太之蕾 仙舟罗浮）', category: 'Calyx_Golden' },
  { value: 'Calyx_Golden_Treasures_The_Xianzhou_Luofu', label: '材料：信用点（藏珍之蕾 仙舟罗浮）', category: 'Calyx_Golden' },
  { value: 'Calyx_Golden_Memories_Jarilo_VI', label: '材料：角色经验（回忆之蕾 雅利洛-Ⅵ）', category: 'Calyx_Golden' },
  { value: 'Calyx_Golden_Aether_Jarilo_VI', label: '材料：武器经验（以太之蕾 雅利洛-Ⅵ）', category: 'Calyx_Golden' },
  { value: 'Calyx_Golden_Treasures_Jarilo_VI', label: '材料：信用点（藏珍之蕾 雅利洛-Ⅵ）', category: 'Calyx_Golden' },
  // 拟造花萼（赤）
  { value: 'Calyx_Crimson_Destruction_Herta_StorageZone', label: '行迹材料：毁灭（收容舱段）', category: 'Calyx_Crimson' },
  { value: 'Calyx_Crimson_Destruction_Luofu_ScalegorgeWaterscape', label: '行迹材料：毁灭（鳞渊境）', category: 'Calyx_Crimson' },
  { value: 'Calyx_Crimson_Preservation_Herta_SupplyZone', label: '行迹材料：存护（支援舱段）', category: 'Calyx_Crimson' },
  { value: 'Calyx_Crimson_Preservation_Penacony_ClockStudiosThemePark', label: '行迹材料：存护（克劳克影视乐园）', category: 'Calyx_Crimson' },
  { value: 'Calyx_Crimson_The_Hunt_Jarilo_OutlyingSnowPlains', label: '行迹材料：巡猎（城郊雪原）', category: 'Calyx_Crimson' },
  { value: 'Calyx_Crimson_The_Hunt_Penacony_SoulGladScorchsandAuditionVenue', label: '行迹材料：巡猎（苏乐达热砂海选会场）', category: 'Calyx_Crimson' },
  { value: 'Calyx_Crimson_The_Hunt_Amphoreus_MemortisShoreRuinsofTime', label: '行迹材料：巡猎（葬忆彼岸时光归墟）', category: 'Calyx_Crimson' },
  { value: 'Calyx_Crimson_Abundance_Jarilo_BackwaterPass', label: '行迹材料：丰饶（边缘通路）', category: 'Calyx_Crimson' },
  { value: 'Calyx_Crimson_Abundance_Luofu_FyxestrollGarden', label: '行迹材料：丰饶（绥园）', category: 'Calyx_Crimson' },
  { value: 'Calyx_Crimson_Erudition_Jarilo_RivetTown', label: '行迹材料：智识（铆钉镇）', category: 'Calyx_Crimson' },
  { value: 'Calyx_Crimson_Erudition_Penacony_PenaconyGrandTheater', label: '行迹材料：智识（匹诺康尼大剧院）', category: 'Calyx_Crimson' },
  { value: 'Calyx_Crimson_Harmony_Jarilo_RobotSettlement', label: '行迹材料：同谐（机械聚落）', category: 'Calyx_Crimson' },
  { value: 'Calyx_Crimson_Harmony_Penacony_TheReverieDreamscape', label: '行迹材料：同谐（白日梦酒店-梦境）', category: 'Calyx_Crimson' },
  { value: 'Calyx_Crimson_Nihility_Jarilo_GreatMine', label: '行迹材料：虚无（大矿区）', category: 'Calyx_Crimson' },
  { value: 'Calyx_Crimson_Nihility_Luofu_AlchemyCommission', label: '行迹材料：虚无（丹鼎司）', category: 'Calyx_Crimson' },
  { value: 'Calyx_Crimson_Remembrance_Amphoreus_StrifeRuinsCastrumKremnos', label: '行迹材料：记忆（纷争荒墟悬锋城）', category: 'Calyx_Crimson' },
  { value: 'Calyx_Crimson_Elation_Planarcadia_WorldEndTavern', label: '行迹材料：欢愉（世界尽头酒馆）', category: 'Calyx_Crimson' },
  // 凝滞虚影
  { value: 'Stagnant_Shadow_Quanta', label: '晋阶材料：量子（银狼 / 希儿 / 青雀）', category: 'Stagnant_Shadow' },
  { value: 'Stagnant_Shadow_Gust', label: '晋阶材料：风（丹恒 / 布洛妮娅 / 桑博）', category: 'Stagnant_Shadow' },
  { value: 'Stagnant_Shadow_Fulmination', label: '晋阶材料：雷（阿兰 / 希露瓦 / 停云 / 白露）', category: 'Stagnant_Shadow' },
  { value: 'Stagnant_Shadow_Blaze', label: '晋阶材料：火（姬子 / 艾丝妲 / 虎克）', category: 'Stagnant_Shadow' },
  { value: 'Stagnant_Shadow_Spike', label: '晋阶材料：物理（娜塔莎 / 克拉拉 / 卢卡 / 素裳）', category: 'Stagnant_Shadow' },
  { value: 'Stagnant_Shadow_Rime', label: '晋阶材料：冰（三月七 / 黑塔 / 杰帕德 / 佩拉）', category: 'Stagnant_Shadow' },
  { value: 'Stagnant_Shadow_Mirage', label: '晋阶材料：虚数（瓦尔特 / 罗刹 / 驭空）', category: 'Stagnant_Shadow' },
  { value: 'Stagnant_Shadow_Icicle', label: '晋阶材料：冰（彦卿 / 镜流 / 阮•梅）', category: 'Stagnant_Shadow' },
  { value: 'Stagnant_Shadow_Doom', label: '晋阶材料：雷（卡芙卡 / 景元 / 黄泉）', category: 'Stagnant_Shadow' },
  { value: 'Stagnant_Shadow_Puppetry', label: '晋阶材料：虚数（丹恒•饮月 / 砂金 / 真理医生）', category: 'Stagnant_Shadow' },
  { value: 'Stagnant_Shadow_Abomination', label: '晋阶材料：量子（玲可 / 符玄 / 雪衣）', category: 'Stagnant_Shadow' },
  { value: 'Stagnant_Shadow_Scorch', label: '晋阶材料：火（托帕&账账 / 桂乃芬 / 忘归人）', category: 'Stagnant_Shadow' },
  { value: 'Stagnant_Shadow_Celestial', label: '晋阶材料：风（刃 / 藿藿 / 黑天鹅）', category: 'Stagnant_Shadow' },
  { value: 'Stagnant_Shadow_Perdition', label: '晋阶材料：物理（寒鸦 / 银枝）', category: 'Stagnant_Shadow' },
  { value: 'Stagnant_Shadow_Nectar', label: '晋阶材料：冰（米沙 / 大黑塔）', category: 'Stagnant_Shadow' },
  { value: 'Stagnant_Shadow_Roast', label: '晋阶材料：量子（花火 / 翡翠）', category: 'Stagnant_Shadow' },
  { value: 'Stagnant_Shadow_Ire', label: '晋阶材料：火（椒丘 / 灵砂 / 加拉赫 / 流萤）', category: 'Stagnant_Shadow' },
  { value: 'Stagnant_Shadow_Duty', label: '晋阶材料：物理（云璃 / 知更鸟 / 波提欧）', category: 'Stagnant_Shadow' },
  { value: 'Stagnant_Shadow_Timbre', label: '晋阶材料：虚数（星期日 / 乱破）', category: 'Stagnant_Shadow' },
  { value: 'Stagnant_Shadow_Mechwolf', label: '晋阶材料：雷（貊泽 / 阿格莱雅）', category: 'Stagnant_Shadow' },
  { value: 'Stagnant_Shadow_Gloam', label: '晋阶材料：风（飞霄 / 那刻夏 / 风堇 / Saber）', category: 'Stagnant_Shadow' },
  { value: 'Stagnant_Shadow_Sloggyre', label: '晋阶材料：虚数（万敌）', category: 'Stagnant_Shadow' },
  { value: 'Stagnant_Shadow_Gelidmoon', label: '晋阶材料：量子（缇宝 / 赛飞儿 / 遐蝶 / Archer）', category: 'Stagnant_Shadow' },
  { value: 'Stagnant_Shadow_Deepsheaf', label: '晋阶材料：物理（白厄 / 海瑟音 / 丹恒•腾荒 / 爻光）', category: 'Stagnant_Shadow' },
  { value: 'Stagnant_Shadow_Cinders', label: '晋阶材料：风（刻律德菈）', category: 'Stagnant_Shadow' },
  { value: 'Stagnant_Shadow_Sirens', label: '晋阶材料：冰（长夜月 / 昔涟）', category: 'Stagnant_Shadow' },
  { value: 'Stagnant_Shadow_Ashes', label: '晋阶材料：火（大丽花 / 火花）', category: 'Stagnant_Shadow' },
]

// 筛选后的材料关卡选项
const filteredMaterialOptions = computed(() => {
  if (!materialCategory.value) {
    return materialOptions
  }
  return materialOptions.filter(option => option.category === materialCategory.value)
})

// 获取当前生效关卡
const getCurrentStage = () => {
  const channel = props.formData.Stage.Channel
  if (channel === 'Relic') {
    return getStageLabel(props.formData.Stage.Relic, 'Relic')
  } else if (channel === 'Materials') {
    return getStageLabel(props.formData.Stage.Materials, 'Materials')
  } else if (channel === 'Ornament') {
    return getStageLabel(props.formData.Stage.Ornament, 'Ornament')
  }
  return '未配置'
}

// 获取当前生效关卡的颜色（根据前缀）
const getCurrentStageColor = () => {
  const channel = props.formData.Stage.Channel
  let value = ''

  if (channel === 'Relic') {
    value = props.formData.Stage.Relic
  } else if (channel === 'Materials') {
    value = props.formData.Stage.Materials
  } else if (channel === 'Ornament') {
    value = props.formData.Stage.Ornament
  }

  if (!value || value === '-') return 'default'

  // 根据关卡前缀返回颜色
  if (value.startsWith('Cavern_of_Corrosion')) return 'purple'
  if (value.startsWith('Divergent_Universe')) return 'cyan'
  if (value.startsWith('Calyx_Golden')) return 'gold'
  if (value.startsWith('Calyx_Crimson')) return 'red'
  if (value.startsWith('Stagnant_Shadow')) return 'volcano'
  if (value.startsWith('Echo_of_War')) return 'magenta'
  if (value.startsWith('Simulated_Universe')) return 'geekblue'

  return 'blue'
}

// 获取关卡标签
const getStageLabel = (value: string, type: string) => {
  if (!value || value === '-') return '禁用'

  const stageMap: Record<string, string> = {
    // 遗器
    'Cavern_of_Corrosion_Path_of_Possession': '遗器：魔法少女 & 卜者（魔占之径）',
    'Cavern_of_Corrosion_Path_of_Hidden_Salvation': '遗器：救世主 & 隐士（隐救之径）',
    'Cavern_of_Corrosion_Path_of_Thundersurge': '遗器：烈阳 & 船长（雳涌之径）',
    'Cavern_of_Corrosion_Path_of_Aria': '遗器：英豪 & 诗人（弦歌之径）',
    'Cavern_of_Corrosion_Path_of_Uncertainty': '遗器：司铎 & 学者（迷识之径）',
    'Cavern_of_Corrosion_Path_of_Cavalier': '遗器：铁骑 & 勇烈（勇骑之径）',
    'Cavern_of_Corrosion_Path_of_Dreamdive': '遗器：死水 & 钟表匠（梦潜之径）',
    'Cavern_of_Corrosion_Path_of_Darkness': '遗器：大公 & DoT套（幽冥之径）',
    'Cavern_of_Corrosion_Path_of_Elixir_Seekers': '遗器：莳者 & 信使（药使之径）',
    'Cavern_of_Corrosion_Path_of_Conflagration': '遗器：火套 & 虚数套（野焰之径）',
    'Cavern_of_Corrosion_Path_of_Holy_Hymn': '遗器：防御套 & 雷套（圣颂之径）',
    'Cavern_of_Corrosion_Path_of_Providence': '遗器：铁卫 & 量子套（睿治之径）',
    'Cavern_of_Corrosion_Path_of_Drifting': '遗器：治疗套 & 快枪手（漂泊之径）',
    'Cavern_of_Corrosion_Path_of_Jabbing_Punch': '遗器：物理套 & 怪盗（迅拳之径）',
    'Cavern_of_Corrosion_Path_of_Gelid_Wind': '遗器：冰套 & 风套（霜风之径）',
    // 饰品
    'Divergent_Universe_Within_the_West_Wind': '饰品：翁法罗斯 & 天国（西风丛中）',
    'Divergent_Universe_Moonlit_Blood': '饰品：妖精 & 沉醉（月下朱殷）',
    'Divergent_Universe_Unceasing_Strife': '饰品：拾骨地 & 巨树（纷争不休）',
    'Divergent_Universe_Famished_Worker': '饰品：海域 & 奇想（蠹役饥肠）',
    'Divergent_Universe_Eternal_Comedy': '饰品：奔狼 & 火宫（永恒笑剧）',
    'Divergent_Universe_To_Sweet_Dreams': '饰品：茨冈尼亚 & 出云（伴你入眠）',
    'Divergent_Universe_Pouring_Blades': '饰品：苍穹 & 匹诺康尼（天剑如雨）',
    'Divergent_Universe_Fruit_of_Evil': '饰品：繁星 & 龙骨（孽果盘生）',
    'Divergent_Universe_Permafrost': '饰品：贝洛伯格 & 萨尔索图（百年冻土）',
    'Divergent_Universe_Gentle_Words': '饰品：商业公司 & 差分机（温柔话语）',
    'Divergent_Universe_Smelted_Heart': '饰品：盗贼 & 翁瓦克（浴火钢心）',
    'Divergent_Universe_Untoppled_Walls': '饰品：太空 & 仙舟（坚城不倒）',
  }

  // 材料关卡从materialOptions中查找
  if (type === 'Materials') {
    const option = materialOptions.find(opt => opt.value === value)
    return option ? option.label : value
  }

  return stageMap[value] || value
}

// 下拉框过滤函数
const filterOption = (input: string, option: any) => {
  const text = option.children?.[0]?.children || option.label || ''
  return text.toLowerCase().indexOf(input.toLowerCase()) >= 0
}
</script>

<style scoped>
.form-section {
  margin-bottom: 32px;
}

.section-header {
  margin-bottom: 20px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--ant-color-border-secondary);
  display: flex;
  justify-content: space-between;
  align-items: center;
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

.current-stage-display {
  display: flex;
  align-items: center;
  min-height: 40px;
}

.stage-tag {
  padding: 8px 16px;
  font-size: 14px;
  font-weight: 500;
  border-radius: 6px;
  margin: 0;
}
</style>
