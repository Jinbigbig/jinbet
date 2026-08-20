// pages/index/index.js
const app = getApp()

Page({
  data: {
    src: '',
    showError: false,
    errorMsg: ''
  },

  onLoad() {
    this.loadWebView()
  },

  onShow() {
    // 每次显示时刷新一次（防止用户切后台后 web-view 空白）
    if (this.data.src) {
      this.setData({ showError: false })
    }
  },

  /**
   * 加载 web-view 地址：
   * 1. 优先用 app.globalData.devUrl（本地调试）
   * 2. 否则用 homeUrl（生产环境 GitHub Pages）
   */
  loadWebView() {
    const global = app.globalData
    const targetUrl = global.devUrl ? global.devUrl : global.homeUrl
    const finalUrl = targetUrl + (targetUrl.indexOf('?') >= 0 ? '&' : '?') + 't=' + Date.now()

    this.setData({
      src: finalUrl,
      showError: false,
      errorMsg: ''
    })
  },

  onWebViewLoad(e) {
    // web-view 加载成功
  },

  onError(e) {
    const detail = e.detail || {}
    this.setData({
      showError: true,
      errorMsg: detail.errMsg || '页面加载失败，请检查网络或域名白名单配置'
    })
  },

  onMessage(e) {
    // 接收从网页发来的消息（postMessage）
    console.log('web-view 消息:', e.detail)
  },

  reload() {
    this.loadWebView()
  },

  /**
   * 下拉刷新
   */
  onPullDownRefresh() {
    this.loadWebView()
    wx.stopPullDownRefresh()
  }
})
