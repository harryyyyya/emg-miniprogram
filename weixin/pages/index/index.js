const ble = require('../../utils/ble_manager');
const { request } = require('../../utils/request');

Page({
  data: {
    banners: [
      { id: 1, image: '/assets/images/banner1.png', title: '智能肌电假手 · 重塑生活' },
      { id: 2, image: '/assets/images/banner2.png', title: '个性化训练 · 精准控制' },
      { id: 3, image: '/assets/images/banner3.png', title: '康复指导 · 连续监测' },
    ],
    knowledgeList: [
      { id: 1, cover: '/assets/images/banner1.png', title: '肌电假手使用入门指南', desc: '从佩戴到基础动作控制，快速建立使用路径。' },
      { id: 2, cover: '/assets/images/banner2.png', title: '日常康复训练建议', desc: '结合训练节奏和状态反馈，逐步提升适应能力。' },
    ],
    deviceName: '',
    deviceOnline: false,
    deviceStatusText: '离线 · 点击绑定',
  },

  onShow() {
    this.loadDeviceStatus();
  },

  onPullDownRefresh() {
    this.loadDeviceStatus().finally(() => {
      wx.stopPullDownRefresh();
    });
  },

  async loadDeviceStatus() {
    const device = wx.getStorageSync('boundDevice');
    if (!device || !device.hardware_id) {
      this.setData({
        deviceName: '',
        deviceOnline: false,
        deviceStatusText: '离线 · 点击绑定',
      });
      return;
    }

    const name = device.name || device.deviceName || device.hardware_id;
    if ((device.transport || 'ble') === 'wifi') {
      this.setData({
        deviceName: name,
        deviceOnline: false,
        deviceStatusText: 'Wi-Fi 设备 · 正在检查',
      });
      try {
        const res = await request({
          url: `/devices/${encodeURIComponent(device.hardware_id)}/status`,
          method: 'GET',
        });
        const status = ((res.device || {}).status || 'offline') === 'online';
        this.setData({
          deviceName: name,
          deviceOnline: status,
          deviceStatusText: status ? 'Wi-Fi 在线 · 后端已收到心跳' : 'Wi-Fi 离线 · 等待 Duo S 回连',
        });
      } catch (e) {
        this.setData({
          deviceName: name,
          deviceOnline: false,
          deviceStatusText: 'Wi-Fi 离线 · 无法获取设备状态',
        });
      }
      return;
    }

    this.setData({
      deviceName: name,
      deviceOnline: ble.isConnected(),
      deviceStatusText: ble.isConnected() ? '蓝牙在线 · 已连接' : '蓝牙离线 · 点击重新绑定',
    });

    ble.onStatus((status) => {
      const online = status === 'connected';
      this.setData({
        deviceOnline: online,
        deviceStatusText: online ? '蓝牙在线 · 已连接' : '蓝牙离线 · 点击重新绑定',
      });
    });
  },

  goToBind() {
    wx.navigateTo({ url: '/pages/bind/bind' });
  },

  goTo(e) {
    const url = e.currentTarget.dataset.url;
    if (url.startsWith('/pages/ai/')) {
      wx.switchTab({ url: '/pages/ai/ai' });
    } else {
      wx.navigateTo({ url });
    }
  },
});
