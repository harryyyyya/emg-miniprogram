const ble = require('../../utils/ble_manager');
const { request } = require('../../utils/request');

Page({
  data: {
    banners: [
      { id: 1, image: '/assets/images/banner1.png', title: 'Smart EMG hand for daily control' },
      { id: 2, image: '/assets/images/banner2.png', title: 'Personal gesture training and recording' },
      { id: 3, image: '/assets/images/banner3.png', title: 'Device status and EMG monitoring' },
    ],
    knowledgeList: [
      {
        id: 1,
        cover: '/assets/images/banner1.png',
        title: 'First connection checklist for ESP32 hand',
        tag: 'Connection',
        desc: 'Check Wi-Fi, backend heartbeat, device id and token before binding.',
      },
      {
        id: 2,
        cover: '/assets/images/banner2.png',
        title: 'How to record stable gesture EMG data',
        tag: 'Training',
        desc: 'Use short and stable 5-second sessions to improve gesture recognition.',
      },
    ],
    deviceName: '',
    deviceOnline: false,
    deviceStatusText: 'Offline · tap to bind',
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
        deviceStatusText: 'Offline · tap to bind',
      });
      return;
    }

    const name = device.name || device.deviceName || device.hardware_id;
    if ((device.transport || 'ble') === 'wifi') {
      this.setData({
        deviceName: name,
        deviceOnline: false,
        deviceStatusText: 'Wi-Fi device · checking',
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
          deviceStatusText: status ? 'Wi-Fi online · heartbeat received' : 'Wi-Fi offline · waiting for ESP32',
        });
      } catch (e) {
        this.setData({
          deviceName: name,
          deviceOnline: false,
          deviceStatusText: 'Wi-Fi offline · status unavailable',
        });
      }
      return;
    }

    this.setData({
      deviceName: name,
      deviceOnline: ble.isConnected(),
      deviceStatusText: ble.isConnected() ? 'BLE online · connected' : 'BLE offline · tap to reconnect',
    });

    ble.onStatus((status) => {
      const online = status === 'connected';
      this.setData({
        deviceOnline: online,
        deviceStatusText: online ? 'BLE online · connected' : 'BLE offline · tap to reconnect',
      });
    });
  },

  openArticle(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/article/article?id=${id}` });
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
