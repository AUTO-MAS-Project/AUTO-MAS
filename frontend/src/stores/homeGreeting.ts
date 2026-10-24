import { ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { i18n } from '@/i18n'
import { pickHomeGreeting } from '@/views/home/homeGreeting'

export const useHomeGreetingStore = defineStore('homeGreeting', () => {
  // 问候语按当前界面语言取；语言切过去之后必须重抽，否则中文彩蛋会留在英文界面上。
  const greeting = ref(pickHomeGreeting(i18n.global.locale.value))

  watch(
    () => i18n.global.locale.value,
    locale => {
      greeting.value = pickHomeGreeting(locale)
    }
  )

  const refreshGreeting = () => {
    greeting.value = pickHomeGreeting(i18n.global.locale.value, greeting.value.text)
  }

  return { greeting, refreshGreeting }
})
