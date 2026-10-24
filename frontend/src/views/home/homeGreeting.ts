export interface HomeGreetingMessage {
  text: string
  author: string
}

export const HOME_GREETING_MESSAGES: HomeGreetingMessage[] = [
  { text: '坐和放宽，脚本正在为你努力运行中。', author: 'AUTO-MAS项目组' },
  {
    text: '启动前请确认脚本路径已正确，否则它将无法找到自己。',
    author: 'AUTO-MAS项目组',
  },
  { text: '请勿™强制关闭AUTO-MAS，正在处理一些事情。', author: 'AUTO-MAS项目组' },
  { text: '好东西就要来了……别来无恙啊！', author: 'AUTO-MAS项目组' },
  { text: 'AUTO-MAS正在为你的设备匹配专属脚本设置。', author: 'AUTO-MAS项目组' },
  { text: '启动AUTO-MAS脚本系统，不要说我们没有警告过你。', author: 'AUTO-MAS项目组' },
  { text: '需要重启脚本是正常现象，请不要惊慌。', author: 'AUTO-MAS项目组' },
  {
    text: '你的设备正在准备就绪，准备好迎接脚本运行了吗？',
    author: 'AUTO-MAS项目组',
  },
  { text: '运行完成后，你的游戏进度可能会发生位移。', author: 'AUTO-MAS项目组' },
  { text: '我们的脚本协议更新了，你只能同意不能不同意。', author: 'AUTO-MAS项目组' },
  { text: '请耐心等待，进度条只是看起来不动而已。', author: 'AUTO-MAS项目组' },
  { text: '感谢你使用AUTO-MAS，你永远可以相信脚本的力量。', author: 'AUTO-MAS项目组' },
  { text: '正在应用最适合当前宇宙版本的脚本设置。', author: 'AUTO-MAS项目组' },
  {
    text: '你的请求很重要，AUTO-MAS正在以看似安静的方式处理它。',
    author: 'AUTO-MAS项目组',
  },
  { text: 'AUTO-MAS检测到一切正常，除非稍后它不正常。', author: 'AUTO-MAS项目组' },
  { text: '请稍候，系统正在把复杂问题包装成一个按钮。', author: 'AUTO-MAS项目组' },
  { text: '欢迎来到大雷主人361的世界……魔↗术↘技↻巧！', author: "T'a1mer" },
  { text: '海内存知己，天涯若比邻', author: '匿名' },
  {
    text: '注意到你已经有一段时间没有使用AUTO-MAS了。现在不启用 | 关闭',
    author: '匿名',
  },
  { text: '喵→喵↓↑喵~喵→喵↓↑喵~', author: 'qsy' },
  { text: '我说SRA是神有没有懂得！', author: "T'a1mer" },
  { text: '主人，欢迎回来喵。', author: "T'a3mer" },
  { text: '↑→↓↓↓', author: "T'a3mer" },
  { text: "我睡觉去了喵，有事请找T'amer喵(´∩｡• ᵕ •｡∩`)", author: "T'a3mer" },
  { text: 'AUTO-MAS即将在114514年32月5日支持maa-meow', author: "T'a1mer" },
  { text: '很不高兴为你服务喵😑', author: "T'a3mer" },
  {
    text: '非常感谢您支持并使用正版软件喵，支持正版打击盗版喵',
    author: "T'a3mer",
  },
  { text: '系统检测到一切正常——除非下一秒它突然觉得正常很无聊', author: '匿名' },
  { text: '喵一下代表启动，再喵一下代表它还在跑', author: '匿名' },
  {
    text: '运行结束后，你的游戏进度可能发生位移——物理意义上的，或精神意义上的',
    author: '匿名',
  },
  {
    text: '进度条看起来不动，是因为它在假装优雅，其实它在后台疯狂翻抽屉',
    author: '匿名',
  },
  {
    text: '你的请求很重要，AUTO-MAS 会用最安静、最漫长、最像卡死的方式处理它',
    author: '匿名',
  },
  { text: '在世界深处寻找你所想要的答案', author: '人' },
  { text: '到下次相遇时再次启程', author: '人' },
  { text: '也许一个切面并不足矣看到事情的全貌', author: '人' },
  { text: '您的请求正在被接受，还剩10...000年进行应答', author: '人' },
  { text: '关注DLmaster_361喵，关注DLmaster_361谢谢喵', author: '匿名' },
  { text: '也许在10086年以后MAS就能管理运行所有脚本', author: '匿名' },
  { text: '这个automas有人用吗？', author: '匿名' },
  { text: '很好的bug！香香软软的小bug，嘿嘿嘿.......', author: 'aafei' },
  { text: '由SRA强力支持！', author: '' },
  { text: '一个bug是bug，一堆bug能work', author: '凉白开' },
]

/** 非中文界面用的问候语。中文那批是社区梗，直译过去只剩莫名其妙，各语言给一份自己的文案。 */
export const HOME_GREETING_MESSAGES_EN: HomeGreetingMessage[] = [
  { text: 'Sit back — the script is doing its best.', author: 'AUTO-MAS Team' },
  {
    text: 'Check your script paths first; a lost script cannot find itself.',
    author: 'AUTO-MAS Team',
  },
  {
    text: 'Please do not force-close AUTO-MAS. It is handling something.',
    author: 'AUTO-MAS Team',
  },
  { text: 'Something good is coming. Nothing has gone wrong yet.', author: 'AUTO-MAS Team' },
  { text: 'Matching this device with a dedicated script profile.', author: 'AUTO-MAS Team' },
  { text: 'Script restarts are normal. No need to panic.', author: 'AUTO-MAS Team' },
  { text: 'Your device is ready. Ready to run the script?', author: 'AUTO-MAS Team' },
  { text: 'Please be patient — the progress bar only looks stuck.', author: 'AUTO-MAS Team' },
  {
    text: 'Applying the script settings best suited to this universe version.',
    author: 'AUTO-MAS Team',
  },
  { text: 'Everything is normal, unless it stops being normal later.', author: 'AUTO-MAS Team' },
  { text: 'Thanks for using AUTO-MAS. You can always trust the script.', author: 'AUTO-MAS Team' },
  { text: 'A bug is a bug, but enough bugs and it works.', author: 'AUTO-MAS Team' },
]

/** 日本語インターフェース用のあいさつ。中国語版はコミュニティ内のネタなので直訳せず、日本語で書き直す。 */
export const HOME_GREETING_MESSAGES_JA: HomeGreetingMessage[] = [
  { text: 'そのままお待ちください。スクリプトが全力で動いています。', author: 'AUTO-MAS チーム' },
  {
    text: '起動前にスクリプトのパスを確認してください。迷子になります。',
    author: 'AUTO-MAS チーム',
  },
  { text: 'AUTO-MAS を強制終了しないでください。処理中です。', author: 'AUTO-MAS チーム' },
  { text: 'もうすぐ良いことがあります。まだ何も壊れていません。', author: 'AUTO-MAS チーム' },
  { text: 'このデバイス専用のスクリプト設定を適用しています。', author: 'AUTO-MAS チーム' },
  { text: 'スクリプトの再起動は正常な動作です。慌てないでください。', author: 'AUTO-MAS チーム' },
  { text: 'デバイスの準備ができました。スクリプトを実行しますか？', author: 'AUTO-MAS チーム' },
  {
    text: 'しばらくお待ちください。プログレスバーが止まって見えるだけです。',
    author: 'AUTO-MAS チーム',
  },
  { text: 'この宇宙バージョンに最適なスクリプト設定を適用しています。', author: 'AUTO-MAS チーム' },
  { text: 'すべて正常です。あとで正常でなくなるまでは。', author: 'AUTO-MAS チーム' },
  {
    text: 'AUTO-MAS をご利用いただきありがとうございます。スクリプトは裏切りません。',
    author: 'AUTO-MAS チーム',
  },
  { text: 'バグはバグですが、数が揃えば動きます。', author: 'AUTO-MAS チーム' },
]

/** 界面语言 → 问候语候选集。中文之外的界面不再显示中文彩蛋。 */
const GREETINGS_BY_LOCALE_PREFIX: Record<string, HomeGreetingMessage[]> = {
  zh: HOME_GREETING_MESSAGES,
  ja: HOME_GREETING_MESSAGES_JA,
  en: HOME_GREETING_MESSAGES_EN,
}

export const greetingsForLocale = (locale: string): HomeGreetingMessage[] =>
  GREETINGS_BY_LOCALE_PREFIX[locale.slice(0, 2).toLowerCase()] ?? HOME_GREETING_MESSAGES_EN

/**
 * 随机抽一条问候语
 *
 * @param locale 界面语言，决定用哪一份候选集（非中文界面不显示中文彩蛋）
 * @param excludeText 当前已在展示的文案，传入后会从候选里剔除，保证「换一句」必然换掉
 */
export const pickHomeGreeting = (locale: string, excludeText?: string): HomeGreetingMessage => {
  const all = greetingsForLocale(locale)
  const filtered = excludeText ? all.filter(message => message.text !== excludeText) : all
  const candidates = filtered.length ? filtered : all
  return candidates[Math.floor(Math.random() * candidates.length)]
}
