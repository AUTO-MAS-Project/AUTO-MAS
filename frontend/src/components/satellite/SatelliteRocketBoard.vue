<template>
  <aside class="board" @click.stop>
    <header>{{ t('home.satelliteEgg.rocketBoardTitle') }}</header>
    <small>{{ t('home.satelliteEgg.rocketBoardLive', { time: fetchedAt }) }}</small>
    <ol>
      <li v-for="(item, index) in list.slice(0, 10)" :key="item.login">
        <span class="board-rank">{{ index + 1 }}</span>
        <img
          v-if="item.avatarUrl"
          :src="sizedAvatar(item.avatarUrl, 48)"
          alt=""
          referrerpolicy="no-referrer"
        />
        <span v-else class="board-initial">{{ item.login.slice(0, 1) }}</span>
        <span class="board-name">{{ item.login }}</span>
        <span class="board-bar" :style="{ '--ratio': item.commits / max }"></span>
        <b>{{ item.commits }}</b>
      </li>
    </ol>
  </aside>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { sizedAvatar, type Contributor } from './contributors'

/** 火箭乱飞赛右边的本周 commit 榜，倒数结束时滑进来 */
defineProps<{
  list: readonly Contributor[]
  /** 第一名的提交数，进度条按它算比例 */
  max: number
  /** 拉到榜单的时刻 */
  fetchedAt: string
}>()

const { t } = useI18n()
</script>

<style scoped>
.board {
  position: absolute;
  top: 50%;
  right: 14px;
  width: 262px;
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(15, 23, 42, 0.82);
  border: 1px solid rgba(255, 255, 255, 0.16);
  box-shadow: 0 14px 36px rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(6px);
  cursor: default;
  transform: translate(120%, -50%);
  animation: board-in 600ms 2.2s cubic-bezier(0.2, 0.9, 0.3, 1.1) forwards;
}

@keyframes board-in {
  to {
    transform: translate(0, -50%);
  }
}

.board header {
  font-size: 14px;
  font-weight: 800;
}

.board small {
  display: block;
  margin: 1px 0 8px;
  color: #94a3b8;
  font-size: 11px;
}

.board ol {
  margin: 0;
  padding: 0;
  list-style: none;
}

.board li {
  display: grid;
  grid-template-columns: 16px 20px minmax(0, 1fr) 54px 34px;
  align-items: center;
  gap: 6px;
  padding: 2px 0;
  font-size: 12px;
}

.board-rank {
  color: #ffd36b;
  font-weight: 800;
  text-align: center;
}

.board li img,
.board-initial {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #1f2937;
}

/* 提交没关联 GitHub 账号时没有头像，显示名字首字 */
.board-initial {
  display: grid;
  place-items: center;
  font-size: 10px;
  font-weight: 800;
}

.board-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.board-bar {
  height: 5px;
  border-radius: 3px;
  background: linear-gradient(90deg, #ffb347, #ffd36b);
  transform-origin: left center;
  transform: scaleX(0);
  animation: board-bar 900ms 2.6s ease-out forwards;
}

@keyframes board-bar {
  to {
    transform: scaleX(var(--ratio));
  }
}

.board li b {
  text-align: right;
  color: #ffd36b;
}
</style>
