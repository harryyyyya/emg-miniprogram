const ble = require('../../utils/ble_manager');
const { request, uploadImage } = require('../../utils/request');

Page({
  data: {
    avatarUrl: '',
    userName: '',
    userPhone: '',
    boundDevice: null,
    bindTimeStr: '',
    isConnected: false,
    connectionText: '未连接',
  },

  onShow() {
    const userInfo = wx.getStorageSync('userInfo') || {};
    this.setData({
      userName: userInfo.name || '用户',
      userPhone: userInfo.phone || '',
      avatarUrl: userInfo.avatar_url || '',
    });
    this.loadDeviceInfo();
  },

  async loadDeviceInfo() {
    const device = wx.getStorageSync('boundDevice');
    if (!device) {
      this.setData({
        boundDevice: null,
        bindTimeStr: '',
        isConnected: false,
        connectionText: '未连接',
      });
      return;
    }

    const bindDate = new Date(device.bindTime || Date.now());
    const bindTimeStr = `${bindDate.getFullYear()}-${String(bindDate.getMonth() + 1).padStart(2, '0')}-${String(bindDate.getDate()).padStart(2, '0')}`;

    if ((device.transport || 'ble') === 'wifi') {
      this.setData({
        boundDevice: device,
        bindTimeStr,
        isConnected: false,
        connectionText: 'Wi-Fi 状态检查中',
      });
      try {
        const res = await request({
          url: `/devices/${encodeURIComponent(device.hardware_id)}/status`,
          method: 'GET',
        });
        const info = res.device || {};
        const online = info.status === 'online';
        this.setData({
          boundDevice: {
            ...device,
            name: info.device_name || device.name || device.hardware_id,
            transport: info.transport || 'wifi',
          },
          bindTimeStr,
          isConnected: online,
          connectionText: online ? 'Wi-Fi 在线' : 'Wi-Fi 离线',
        });
      } catch (e) {
        this.setData({
          boundDevice: device,
          bindTimeStr,
          isConnected: false,
          connectionText: 'Wi-Fi 离线',
        });
      }
      return;
    }

    this.setData({
      boundDevice: device,
      bindTimeStr,
      isConnected: ble.isConnected(),
      connectionText: ble.isConnected() ? '蓝牙已连接' : '蓝牙未连接',
    });
  },

  async changeAvatar() {
    try {
      const mediaRes = await new Promise((resolve, reject) => {
        wx.chooseMedia({
          count: 1,
          mediaType: ['image'],
          sizeType: ['compressed'],
          sourceType: ['album', 'camera'],
          success: resolve,
          fail: reject,
        });
      });

      const tempPath = mediaRes.tempFiles[0].tempFilePath;
      const avatarUrl = await uploadImage(tempPath);
      const result = await request({
        url: '/auth/profile',
        method: 'PUT',
        data: { avatar_url: avatarUrl },
      });
      const oldInfo = wx.getStorageSync('userInfo') || {};
      const nextInfo = { ...oldInfo, ...(result.user || {}), avatar_url: avatarUrl };
      wx.setStorageSync('userInfo', nextInfo);
      getApp().globalData.userInfo = nextInfo;
      this.setData({ avatarUrl: nextInfo.avatar_url || avatarUrl });
      wx.showToast({ title: '头像已更新', icon: 'success' });
    } catch (err) {
      if (err && err.errMsg && err.errMsg.includes('cancel')) return;
      wx.showToast({
        title: (err && (err.detail || err.message)) || '头像更新失败',
        icon: 'none',
      });
    }
  },

  editUserName() {
    wx.showModal({
      title: '修改用户名',
      editable: true,
      placeholderText: '请输入新的用户名',
      content: this.data.userName || '',
      success: async (res) => {
        if (!res.confirm) return;

        const nextName = (res.content || '').trim();
        if (!nextName) {
          wx.showToast({ title: '用户名不能为空', icon: 'none' });
          return;
        }

        try {
          const result = await request({
            url: '/auth/profile',
            method: 'PUT',
            data: { name: nextName },
          });
          const user = result.user || {};
          const oldInfo = wx.getStorageSync('userInfo') || {};
          const nextInfo = { ...oldInfo, ...user };
          wx.setStorageSync('userInfo', nextInfo);
          getApp().globalData.userInfo = nextInfo;
          this.setData({ userName: nextInfo.name || nextName });
          wx.showToast({ title: '修改成功', icon: 'success' });
        } catch (err) {
          wx.showToast({
            title: (err && (err.detail || err.message)) || '修改失败',
            icon: 'none',
          });
        }
      },
    });
  },

  goTo(e) {
    const url = e.currentTarget.dataset.url;
    wx.navigateTo({ url });
  },

  logout() {
    wx.showModal({
      title: '确认退出',
      content: '退出后需要重新登录',
      success: (res) => {
        if (!res.confirm) return;
        ble.disconnect();
        wx.clearStorageSync();
        wx.reLaunch({ url: '/pages/login/login' });
      },
    });
  },
});
