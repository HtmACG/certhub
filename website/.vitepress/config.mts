import { defineConfig } from 'vitepress'

const SITE = 'https://certhub.htmacg.com'
const REPO = 'https://github.com/HtmACG/certhub'
const AUTHOR = 'https://github.com/HtmACG'

export default defineConfig({
  lang: 'zh-CN',
  title: 'CertHub',
  titleTemplate: ':title · CertHub',
  description:
    'CertHub 是完全免费的 SSL 证书自动化管理系统：把证书申请、DNS 验证、自动部署与到期续期编排成一条可视化流水线，支持主流 CA 与 75 个部署目标。',

  // GitHub Pages 直接托管 .html，不做 URL 重写，最稳
  cleanUrls: false,
  lastUpdated: true,
  metaChunk: true,

  // README.md 是给仓库看的说明，不要生成页面
  srcExclude: ['README.md', '_tools/**', 'scripts/**'],

  sitemap: {
    hostname: SITE,
    lastmodDateOnly: true
  },

  head: [
    ['link', { rel: 'icon', href: '/assets/favicon.ico', sizes: 'any' }],
    ['link', { rel: 'icon', type: 'image/png', sizes: '32x32', href: '/assets/favicon-32.png' }],
    ['link', { rel: 'icon', type: 'image/png', sizes: '16x16', href: '/assets/favicon-16.png' }],
    ['link', { rel: 'apple-touch-icon', href: '/assets/apple-touch-icon.png' }],
    ['meta', { name: 'author', content: '墨韵先知' }],
    ['meta', { name: 'theme-color', content: '#1a73e8' }],
    ['meta', { name: 'robots', content: 'index,follow,max-image-preview:large' }],
    ['meta', { property: 'og:type', content: 'website' }],
    ['meta', { property: 'og:site_name', content: 'CertHub' }],
    ['meta', { property: 'og:locale', content: 'zh_CN' }],
    ['meta', { property: 'og:image', content: `${SITE}/assets/og-cover.png` }],
    ['meta', { property: 'og:image:width', content: '1200' }],
    ['meta', { property: 'og:image:height', content: '630' }],
    ['meta', { name: 'twitter:card', content: 'summary_large_image' }],
    ['meta', { name: 'twitter:image', content: `${SITE}/assets/og-cover.png` }]
  ],

  transformHead({ pageData, siteConfig }) {
    const path = pageData.relativePath.replace(/(index)?\.md$/, '')
    const url = `${SITE}/${path}`
    const title = pageData.frontmatter.title || pageData.title || siteConfig.site.title
    const desc = pageData.frontmatter.description || pageData.description || siteConfig.site.description
    return [
      ['link', { rel: 'canonical', href: url }],
      ['meta', { property: 'og:url', content: url }],
      ['meta', { property: 'og:title', content: title.includes('CertHub') ? title : `${title} · CertHub` }],
      ['meta', { property: 'og:description', content: desc }],
      ['meta', { name: 'description', content: desc }]
    ]
  },

  themeConfig: {
    logo: { src: '/assets/logo.png', alt: 'CertHub' },
    siteTitle: 'CertHub',

    nav: [
      { text: '首页', link: '/' },
      { text: '帮助文档', link: '/docs/', activeMatch: '^/docs/' },
      { text: '生态集成', link: '/ecosystem', activeMatch: '^/ecosystem' },
      { text: '常见问题', link: '/faq', activeMatch: '^/faq' },
      { text: '更新日志', link: '/changelog', activeMatch: '^/changelog' }
    ],

    sidebar: {
      '/docs/': [
        {
          text: '开始使用',
          items: [
            { text: '快速开始', link: '/docs/' },
            { text: '安装部署', link: '/docs/install' },
            { text: '核心概念', link: '/docs/concept' }
          ]
        },
        {
          text: '配置证书流程',
          items: [
            { text: '授权管理', link: '/docs/access' },
            { text: '证书签发', link: '/docs/issue' },
            { text: '部署目标', link: '/docs/deploy' },
            { text: '监控与续期', link: '/docs/monitor' },
            { text: '通知渠道', link: '/docs/notify' }
          ]
        },
        {
          text: '运维与安全',
          items: [
            { text: '安全与权限', link: '/docs/security' },
            { text: '备份与升级', link: '/docs/ops' },
            { text: '故障排查', link: '/docs/troubleshoot' }
          ]
        },
        {
          text: '开发',
          items: [
            { text: '架构与目录', link: '/docs/dev' },
            { text: '新增插件', link: '/docs/plugin-dev' }
          ]
        }
      ]
    },

    socialLinks: [{ icon: 'github', link: REPO, ariaLabel: 'GitHub 仓库' }],

    search: {
      provider: 'local',
      options: {
        translations: {
          button: { buttonText: '搜索文档', buttonAriaLabel: '搜索文档' },
          modal: {
            noResultsText: '没有找到相关内容',
            resetButtonTitle: '清除条件',
            footer: {
              selectText: '选择',
              navigateText: '切换',
              closeText: '关闭'
            }
          }
        }
      }
    },

    outline: { level: [2, 3], label: '本页目录' },

    docFooter: { prev: '上一篇', next: '下一篇' },
    lastUpdated: {
      text: '最后更新',
      formatOptions: { dateStyle: 'short', timeStyle: 'short' }
    },

    darkModeSwitchLabel: '主题',
    lightModeSwitchTitle: '切换到浅色模式',
    darkModeSwitchTitle: '切换到深色模式',
    returnToTopLabel: '回到顶部',
    sidebarMenuLabel: '目录',
    skipToContentLabel: '跳到正文',

    footer: {
      message:
        '基于 GPL-3.0 开源许可发布 · 本站与产品均不含任何付费、套餐或数量限制',
      copyright: `© 2026 CertHub · <a href="${AUTHOR}" target="_blank" rel="noopener">墨韵先知</a>`
    }
  }
})
