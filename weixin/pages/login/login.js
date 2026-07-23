const { request, uploadImage } = require('../../utils/request');

const DEFAULT_AVATAR = '/assets/icons/default_avatar.png';

Page({
  data: {
    loginMode: 'wechat',
    phone: '',
    code: '',
    codeCooldown: 0,
    avatarUrl: '',
    patientName: '',
    amputationPart: '',
    illnessDurationMonths: '',
    loggingIn: false,
  },

  onLoad() {
    const token = wx.getStorageSync('token');
    if (token) {
      wx.switchTab({ url: '/pages/index/index' });
    }
  },

  switchMode(e) {
    this.setData({ loginMode: e.currentTarget.dataset.mode });
  },

  onChooseAvatar(e) {
    const avatarUrl = e.detail && e.detail.avatarUrl;
    if (avatarUrl) {
      this.setData({ avatarUrl });
    }
  },

  onPatientNameInput(e) {
    this.setData({ patientName: (e.detail.value || '').trim() });
  },

  onAmputationPartInput(e) {
    this.setData({ amputationPart: (e.detail.value || '').trim() });
  },

  onIllnessDurationInput(e) {
    const value = String(e.detail.value || '').replace(/[^\d]/g, '');
    this.setData({ illnessDurationMonths: value });
  },

  onPhoneInput(e) {
    this.setData({ phone: e.detail.value });
  },

  onCodeInput(e) {
    this.setData({ code: e.detail.value });
  },

  async onWechatLogin() {
    if (this.data.loggingIn || !this._validatePatientProfile()) return;

    this.setData({ loggingIn: true });
    try {
      const loginRes = await new Promise((resolve, reject) => {
        wx.login({
          success: resolve,
          fail: reject,
        });
      });

      if (!loginRes.code) {
        throw new Error('wx.login missing code');
      }

      const draftProfile = this._getDraftProfile();
      const data = await request({
        url: '/auth/wechat',
        method: 'POST',
        data: {
          code: loginRes.code,
          name: draftProfile.name,
          avatar_url: draftProfile.avatarUrl.startsWith('http') ? draftProfile.avatarUrl : '',
          amputation_part: draftProfile.amputationPart,
          illness_duration_months: draftProfile.illnessDurationMonths,
        },
      });

      await this._finishLogin(data, draftProfile);
      wx.switchTab({ url: '/pages/index/index' });
    } catch (err) {
      this._showBackendUnavailable();
      console.error('[login] wechat login failed', err);
    } finally {
      this.setData({ loggingIn: false });
    }
  },

  sendCode() {
    const { phone } = this.data;
    if (!/^1\d{10}$/.test(phone)) {
      wx.showToast({ title: '请输入正确手机号', icon: 'none' });
      return;
    }

    request({
      url: '/auth/sms/send',
      method: 'POST',
      data: { phone },
    }).catch(() => {
      this._showBackendUnavailable();
      this.setData({ codeCooldown: 0 });
    });

    this.setData({ codeCooldown: 60 });
    const timer = setInterval(() => {
      const next = this.data.codeCooldown - 1;
      if (next <= 0) {
        clearInterval(timer);
        this.setData({ codeCooldown: 0 });
        return;
      }
      this.setData({ codeCooldown: next });
    }, 1000);
  },

  async onPhoneLogin() {
    const { phone, code, loggingIn } = this.data;
    if (loggingIn || !this._validatePatientProfile()) return;

    if (!/^1\d{10}$/.test(phone)) {
      wx.showToast({ title: '请输入正确手机号', icon: 'none' });
      return;
    }
    if (!code) {
      wx.showToast({ title: '请输入验证码', icon: 'none' });
      return;
    }

    this.setData({ loggingIn: true });
    try {
      const data = await request({
        url: '/auth/sms/verify',
        method: 'POST',
        data: { phone, code },
      });
      await this._finishLogin(data, this._getDraftProfile());
      wx.switchTab({ url: '/pages/index/index' });
    } catch (err) {
      this._showBackendUnavailable();
      console.error('[login] phone login failed', err);
    } finally {
      this.setData({ loggingIn: false });
    }
  },

  async _finishLogin(data, draftProfile) {
    const user = data.user || {};
    wx.setStorageSync('token', data.token);
    wx.setStorageSync('userInfo', user);
    getApp().globalData.userInfo = user;

    try {
      await this._syncDraftProfile(draftProfile, user);
    } catch (err) {
      console.warn('[login] profile sync skipped', err);
    }
  },

  _validatePatientProfile() {
    if (!this.data.patientName.trim()) {
      wx.showToast({ title: '请填写患者姓名', icon: 'none' });
      return false;
    }
    if (!this.data.amputationPart.trim()) {
      wx.showToast({ title: '请填写截肢部位', icon: 'none' });
      return false;
    }
    return true;
  },

  _getDraftProfile() {
    return {
      name: (this.data.patientName || '').trim(),
      avatarUrl: this.data.avatarUrl || '',
      amputationPart: (this.data.amputationPart || '').trim(),
      illnessDurationMonths: Number(this.data.illnessDurationMonths || 0),
    };
  },

  async _syncDraftProfile(draftProfile, currentUser) {
    const payload = {};

    if (draftProfile.name && draftProfile.name !== currentUser.name) {
      payload.name = draftProfile.name;
    }

    if (draftProfile.amputationPart && draftProfile.amputationPart !== currentUser.amputation_part) {
      payload.amputation_part = draftProfile.amputationPart;
    }

    if (draftProfile.illnessDurationMonths !== (currentUser.illness_duration_months || 0)) {
      payload.illness_duration_months = draftProfile.illnessDurationMonths;
    }

    if (
      draftProfile.avatarUrl &&
      draftProfile.avatarUrl !== DEFAULT_AVATAR &&
      !draftProfile.avatarUrl.startsWith('http://') &&
      !draftProfile.avatarUrl.startsWith('https://')
    ) {
      payload.avatar_url = await uploadImage(draftProfile.avatarUrl);
    } else if (
      draftProfile.avatarUrl &&
      draftProfile.avatarUrl !== DEFAULT_AVATAR &&
      draftProfile.avatarUrl !== currentUser.avatar_url
    ) {
      payload.avatar_url = draftProfile.avatarUrl;
    }

    if (!Object.keys(payload).length) {
      return;
    }

    const result = await request({
      url: '/auth/profile',
      method: 'PUT',
      data: payload,
    });
    const nextUser = { ...currentUser, ...(result.user || {}) };
    wx.setStorageSync('userInfo', nextUser);
    getApp().globalData.userInfo = nextUser;
  },

  _showBackendUnavailable() {
    wx.removeStorageSync('token');
    wx.showToast({
      title: '后端连接失败，请检查服务',
      icon: 'none',
      duration: 2000,
    });
  },
});
