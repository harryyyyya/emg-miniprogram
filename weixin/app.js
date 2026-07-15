App({
  onLaunch: function () {
    // 启动时从本地缓存恢复用户信息，供各页面通过 getApp().globalData 直接读取
    const userInfo = wx.getStorageSync('userInfo');
    if (userInfo) {
      this.globalData.userInfo = userInfo;
    }
  },
  globalData: {
    userInfo: null,
    connectedDevice: null, // 当前连接的硬件设备信息概览
  }
});
