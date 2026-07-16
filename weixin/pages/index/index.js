const ble = require('../../utils/ble_manager');
const { request } = require('../../utils/request');

Page({
  data: {
    banners: [
      { id: 1, image: '/assets/images/banner1.png', title: '智能肌电假手，重塑日常能力' },
      { id: 2, image: '/assets/images/banner2.png', title: '个性化动作录入，让控制更贴合你' },
      { id: 3, image: '/assets/images/banner3.png', title: '持续监测设备与肌电状态' },
    ],
    knowledgeList: [
      {
        id: 1,
        cover: '/assets/images/banner1.png',
        title: '新手第一次连接假手：先确认这 3 件事',
        tag: '设备连接',
        desc: '确认 ESP32 已连上 Wi-Fi、串口出现 heartbeat status=200，再在小程序里一键绑定默认设备。',
      },
      {
        id: 2,
        cover: '/assets/images/banner2.png',
        title: '动作录入怎么练：每次 5 秒更稳定',
        tag: '训练建议',
        desc: '录入握拳、张手、捏取等动作时保持姿势稳定，观察原始肌电波形和 RMS，逐步提高识别准确度。',
      },
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
          deviceStatusText: status ? 'Wi-Fi 在线 · 后端已收到心跳' : 'Wi-Fi 离线 · 等待 ESP32 回连',
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
