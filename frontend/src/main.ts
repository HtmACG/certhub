import App from './App.vue'
import { createApp } from 'vue'
import { initStore } from './store'                 // Store
import { initRouter } from './router'               // Router
import language from './locales'                    // 国际化
import '@styles/core/tailwind.css'                  // tailwind
import '@styles/index.scss'                         // 样式
import '@utils/sys/console.ts'                      // 控制台输出内容
import { setupGlobDirectives } from './directives'
import { setupErrorHandle } from './utils/sys/error-handle'
import { useSettingStore } from '@/store/modules/setting'

/**
 * 一次性迁移：老版本把圆角写死在按钮上（胶囊 / 圆形），用户并没能真正选过「0.75rem」。
 * 这里把存量的 0.75 改成 0（直角），之后圆角只由「设置抽屉 → 自定义圆角」控制。
 */
function migrateRadiusDefault(): void {
  const KEY = 'sys-radius-square-v1'
  try {
    if (localStorage.getItem(KEY)) return
    localStorage.setItem(KEY, '1')
    const settingStore = useSettingStore()
    if (settingStore.customRadius === '0.75') {
      settingStore.setCustomRadius('0')
    }
  } catch {
    // localStorage 不可用（隐私模式）时忽略，不影响启动
  }
}

document.addEventListener(
  'touchstart',
  function () {},
  { passive: false }
)

const app = createApp(App)
initStore(app)
migrateRadiusDefault()
initRouter(app)
setupGlobDirectives(app)
setupErrorHandle(app)

app.use(language)
app.mount('#app')