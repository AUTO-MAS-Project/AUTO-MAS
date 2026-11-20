<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { BannerWatchService } from '@/api'
import {
  handoff,
  opening,
  sameRegion,
  shanghai,
  type Banner,
  type BannerState,
  type Region,
} from '../bannerWatch'

const { t, locale } = useI18n()
const label = (key: string) => t('bootstrap.banners.' + key)
const state = ref<BannerState>()
const busy = ref(false)
const error = ref('')
const settings = ref(false)
const draft = ref<Region[]>([])
const selected = ref('')
const form = ref(false)
const CONTEXT_FIELDS = ['inventory', 'pity', 'roster', 'nextGoal'] as const
const context = ref<Record<(typeof CONTEXT_FIELDS)[number], string>>({
  inventory: '',
  pity: '',
  roster: '',
  nextGoal: '',
})
const preview = ref('')
const result = ref('')
const submitting = ref(false)
const analysis = ref('')
const previewOpen = ref(false)
const followed = computed(
  () =>
    state.value?.banners.filter(b => state.value?.subscriptions.some(s => sameRegion(s, b))) ?? []
)
const current = computed(
  () => followed.value.find(b => b.id === selected.value) ?? followed.value[0]
)
watch(current, () => {
  analysis.value = ''
  previewOpen.value = false
  form.value = false
  for (const field of CONTEXT_FIELDS) context.value[field] = ''
  preview.value = ''
  result.value = ''
})
const format = (v: string | null) => shanghai(v, locale.value, label('unknown'))
const starts = (b: Banner) => opening(b, format, label)
const status = (b: Banner) =>
  label(b.status === 'open' && !b.confirmed_open_at ? 'scheduledTimeReached' : b.status)
const KINDS = new Set(['banner', 'character', 'weapon', 'rerun', 'permanent', 'standard', 'mixed'])
const kindOf = (b: Banner) => (KINDS.has(b.kind) ? label('kind_' + b.kind) : b.kind)
const ends = (b: Banner) => (b.end_kind === 'permanent' ? label('permanentEnd') : format(b.ends_at))
function openOfficial(event: MouseEvent, url: string | null) {
  const link = officialLink(url)
  if (link && window.electronAPI?.openUrl) {
    event.preventDefault()
    void window.electronAPI.openUrl(link)
  }
}
function officialLink(value: string | null) {
  if (!value) return undefined
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && !url.username && !url.password ? url.href : undefined
  } catch {
    return undefined
  }
}
const source = (r: Region) => state.value?.sources.find(s => sameRegion(r, s))
function regionName(r: Region) {
  const game = state.value?.games.find(g => g.id === r.game)
  return [game?.name ?? r.game, game?.servers.find(s => s.id === r.server)?.name ?? r.server].join(
    ' · '
  )
}
async function sync(save = false) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    state.value = save
      ? await BannerWatchService.updateBannerSubscriptions({
          subscriptions: draft.value,
          subscriptionRevision: state.value?.subscriptionRevision ?? 0,
        })
      : await BannerWatchService.getBannerWatch()
    settings.value = false
  } catch {
    error.value = label(save ? 'saveFailed' : 'failed')
  } finally {
    busy.value = false
  }
}
function edit() {
  draft.value = [...(state.value?.subscriptions ?? [])]
  if (state.value?.subscriptionRevision === 0 && draft.value.length === 0) {
    draft.value = state.value.games.flatMap(game =>
      game.servers
        .filter(server => server.managed && server.covered)
        .map(server => ({ game: game.id, server: server.id }))
    )
  }
  settings.value = true
}
const checked = (r: Region) => draft.value.some(s => sameRegion(s, r))
function toggle(r: Region) {
  draft.value = checked(r) ? draft.value.filter(s => !sameRegion(s, r)) : [...draft.value, r]
}
function clearAnalysisResult() {
  result.value = ''
  analysis.value = ''
}
function invalidatePreview() {
  previewOpen.value = false
  clearAnalysisResult()
}
function buildPreview(b: Banner) {
  previewOpen.value = true
  analysis.value = ''
  preview.value = [
    label('instruction'),
    JSON.stringify(
      {
        region: regionName(b),
        title: b.title,
        kind: kindOf(b),
        status: status(b),
        timeZone: 'Asia/Shanghai',
        opens: starts(b),
        ends: ends(b),
        official_url: b.official_url,
        verified: format(b.verified_at),
        stale: b.stale,
        lastSuccessfulSync: format(source(b)?.last_success_at ?? null),
        sourceError: source(b)?.error,
      },
      null,
      2
    ),
    label('context'),
    ...CONTEXT_FIELDS.map(
      field => label(field) + ' · ' + (context.value[field].trim() || label('unknown'))
    ),
  ].join('\n')
  result.value = ''
}
async function confirmAnalysis() {
  if (submitting.value || !preview.value.trim()) return
  const prompt = preview.value
  submitting.value = true
  analysis.value = ''
  result.value = label('waiting')
  try {
    const reply = await handoff(prompt, window.electronAPI?.analyzeBannerWithCodex, text =>
      navigator.clipboard.writeText(text)
    )
    analysis.value = reply.analysis ?? ''
    result.value = label(reply.message)
  } finally {
    submitting.value = false
  }
}
onMounted(() => sync())
</script>

<template>
  <section class="watch" :aria-busy="busy">
    <header>
      <div>
        <h2>{{ label('title') }}</h2>
        <small>{{ label('zone') }}</small>
      </div>
      <a-button :disabled="settings || busy || submitting" @click="sync()">{{
        label('reload')
      }}</a-button>
      <a-button :disabled="!state || busy || settings || submitting" @click="edit">{{
        label('settings')
      }}</a-button>
    </header>
    <p v-if="error" role="alert">{{ error }}</p>
    <a-alert
      v-if="state?.hasNotificationChannels === false"
      type="info"
      show-icon
      :message="label('noChannels')"
      class="channel-status"
    />
    <fieldset v-if="settings && state" :disabled="busy">
      <legend>{{ label('settings') }}</legend>
      <div v-for="g in state.games" :key="g.id" class="regions">
        <strong>{{ g.name }}</strong>
        <label v-for="s in g.servers" :key="s.id">
          <input
            type="checkbox"
            :disabled="!s.covered"
            :checked="checked({ game: g.id, server: s.id })"
            @change="toggle({ game: g.id, server: s.id })"
          />
          {{ s.name }} {{ !s.covered ? label('uncovered') : s.managed ? label('managed') : '' }}
        </label>
      </div>
      <a-button :disabled="busy" @click="sync(true)">{{ label('save') }}</a-button>
      <a-button :disabled="busy" @click="settings = false">{{ label('cancel') }}</a-button>
    </fieldset>
    <div v-if="current" class="columns">
      <div>
        <button
          v-for="b in followed"
          :key="b.id"
          class="row"
          :disabled="submitting"
          :aria-pressed="current.id === b.id"
          @click="selected = b.id"
        >
          <small>{{ regionName(b) }} · {{ status(b) }}</small>
          <strong>{{ b.title }}</strong>
          <span>{{ starts(b) }}</span>
          <small>{{ label('verified') }} · {{ format(b.verified_at) }}</small>
          <small>{{ label('source') }} · {{ format(source(b)?.last_success_at ?? null) }}</small>
          <small v-if="b.stale || source(b)?.error">{{ label('stale') }}</small>
        </button>
      </div>
      <article>
        <small>{{ regionName(current) }} · {{ kindOf(current) }} · {{ status(current) }}</small>
        <h3>{{ current.title }}</h3>
        <dl>
          <dt>{{ label('start') }}</dt>
          <dd>{{ starts(current) }}</dd>
          <dt>{{ label('end') }}</dt>
          <dd>{{ ends(current) }}</dd>
          <dt>{{ label('verified') }}</dt>
          <dd>{{ format(current.verified_at) }} {{ current.stale ? label('stale') : '' }}</dd>
          <dt>{{ label('source') }}</dt>
          <dd>
            {{ format(source(current)?.last_success_at ?? null) }} {{ source(current)?.error }}
          </dd>
          <dt>{{ label('official') }}</dt>
          <dd>
            <a
              v-if="officialLink(current.official_url)"
              :href="officialLink(current.official_url)"
              target="_blank"
              rel="noopener noreferrer"
              @click="openOfficial($event, current.official_url)"
              >{{ label('officialLink') }}</a
            >
            <span v-else>{{ current.official_url ?? label('unknown') }}</span>
          </dd>
        </dl>
        <a-button :disabled="submitting" :aria-expanded="form" @click="form = !form">{{
          label('agent')
        }}</a-button>
        <div v-if="form" class="analysis">
          <fieldset class="analysis-context" :disabled="submitting">
            <legend>{{ label('context') }}</legend>
            <label v-for="field in CONTEXT_FIELDS" :key="field">
              {{ label(field) }}
              <textarea
                v-model="context[field]"
                rows="2"
                maxlength="2000"
                @input="invalidatePreview"
              />
            </label>
          </fieldset>
          <a-button :disabled="submitting" @click="buildPreview(current)">{{
            label('preview')
          }}</a-button>
          <template v-if="previewOpen">
            <label
              >{{ label('request')
              }}<textarea
                :disabled="submitting"
                v-model="preview"
                rows="9"
                @input="clearAnalysisResult"
              />
            </label>
            <small>{{ label('fallback') }}</small>
            <a-button
              :disabled="submitting || settings || busy || !preview.trim()"
              @click="confirmAnalysis"
              >{{ label('confirm') }}</a-button
            >
            <span role="status">{{ result }}</span>
            <div class="answer" v-if="analysis">{{ analysis }}</div>
          </template>
        </div>
      </article>
    </div>
    <template v-else-if="state">
      <p>{{ label('empty') }}</p>
      <small v-for="r in state.subscriptions" :key="r.game + '/' + r.server" class="sync">
        {{ regionName(r) }} · {{ label('source') }} ·
        {{ format(source(r)?.last_success_at ?? null) }} {{ source(r)?.error }}
      </small>
    </template>
  </section>
</template>

<style scoped>
.watch {
  color: var(--ant-color-text);
  overflow-wrap: anywhere;
}
header,
.regions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-bottom: 0.8rem;
}
header div {
  margin-right: auto;
}
h2,
h3 {
  margin: 0;
}
.columns {
  display: grid;
  grid-template-columns: minmax(12rem, 2fr) minmax(0, 3fr);
  gap: 1rem;
}
.row,
article,
fieldset {
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  padding: 1rem;
}
.row {
  display: grid;
  gap: 0.25rem;
  text-align: start;
  width: 100%;
  margin-bottom: 0.4rem;
  font: inherit;
  color: inherit;
  cursor: pointer;
}
.row[aria-pressed='true'] {
  border-color: var(--ant-color-primary);
}
article {
  align-self: start;
}
fieldset {
  margin-bottom: 1rem;
}
dl {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0.5rem 1rem;
}
dd {
  margin: 0;
}
.analysis {
  display: grid;
  gap: 0.6rem;
  margin-top: 0.8rem;
}
textarea {
  display: block;
  width: 100%;
  color: inherit;
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border);
  border-radius: 6px;
  padding: 0.35rem 0.5rem;
  resize: vertical;
}
.channel-status {
  margin-bottom: 0.8rem;
}
.analysis-context {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.6rem;
  margin: 0;
}
.answer {
  white-space: pre-wrap;
}
.sync {
  display: block;
}
@media (max-width: 750px) {
  .columns,
  .analysis-context {
    grid-template-columns: 1fr;
  }
}
</style>
