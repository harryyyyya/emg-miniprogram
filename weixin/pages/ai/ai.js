const { request, getBaseUrl } = require('../../utils/request');

let msgId = 0;

Page({
  data: {
    messages: [],
    inputValue: '',
    isTyping: false,
    scrollToId: '',
    boundDevice: null,
    quickQuestions: [
      '设备现在还有多少电量？',
      '最近肌电数据怎么样？',
      '设备现在在线吗？',
      '给我一个康复训练建议',
    ],
  },

  onShow() {
    const device = wx.getStorageSync('boundDevice');
    if (device) {
      this.setData({ boundDevice: device });
    }
  },

  onInput(e) {
    this.setData({ inputValue: e.detail.value });
  },

  quickAsk(e) {
    if (this.data.isTyping) return;
    const question = e.currentTarget.dataset.q;
    this.setData({ inputValue: question });
    this.sendMessage(question);
  },

  sendMessage(presetContent) {
    if (this.data.isTyping) return;

    const content = (typeof presetContent === 'string' ? presetContent : this.data.inputValue).trim();
    if (!content) return;

    const userMsg = { id: ++msgId, role: 'user', content };
    const history = this._buildHistory();

    this.setData({
      messages: [...this.data.messages, userMsg],
      inputValue: '',
      isTyping: true,
      scrollToId: `msg-${userMsg.id}`,
    });

    const device = this.data.boundDevice;
    request({
      url: '/ai/chat',
      method: 'POST',
      data: {
        message: content,
        hardware_id: device ? device.hardware_id : null,
        history,
      },
    })
      .then((res) => {
        this._addAIReply(
          res.reply || res.message || '后端没有返回内容',
          this._formatReplyMeta(res)
        );
      })
      .catch((err) => {
        const text = this._getErrorMessage(err);
        this._addAIReply(text, '连接失败');
      });
  },

  _addAIReply(content, meta = '') {
    const aiMsg = { id: ++msgId, role: 'ai', content, meta };
    this.setData({
      messages: [...this.data.messages, aiMsg],
      isTyping: false,
      scrollToId: `msg-${aiMsg.id}`,
    });
  },

  _buildHistory() {
    return this.data.messages
      .filter((item) => item.role === 'user' || item.role === 'ai')
      .slice(-10)
      .map((item) => ({
        role: item.role === 'ai' ? 'assistant' : 'user',
        content: item.content,
      }));
  },

  _formatReplyMeta(res) {
    if (!res || !res.source) return '后端智能体';
    if (res.source === 'deepseek') {
      return res.model ? `DeepSeek · ${res.model}` : 'DeepSeek';
    }
    if (res.source === 'local_fallback') {
      return '本地规则智能体';
    }
    return res.source;
  },

  _getErrorMessage(err) {
    if (err && typeof err === 'object') {
      if (err.detail) return err.detail;
      if (err.message) return err.message;
    }
    const baseUrl = getBaseUrl();
    if (baseUrl.includes('127.0.0.1') || baseUrl.includes('localhost')) {
      return '当前后端地址是本机回环地址。开发者工具里可用，但真机调试时需要把 baseUrl 改成你电脑的局域网 IP。';
    }
    return '连接后端失败，请确认服务已启动，并检查小程序里的后端地址配置。';
  },
});
