Page({
  data: {
    current: 0,
    slides: [
      {
        type: 'cover',
        title: '肌电假手管理系统',
        subtitle: '微信小程序技术方案',
        tags: ['蓝牙BLE', 'FastAPI后端', 'AI助手', '康复社区'],
      },
      {
        type: 'overview',
        title: '项目概述',
        icon: '🦾',
        desc: '面向肌电假手用户的综合管理平台',
        items: [
          '通过蓝牙低功耗（BLE）与 ESP32-S3 硬件设备通信',
          '8通道 500Hz EMG 数据实时采集与上传',
          '后端接口基于 FastAPI，支持 AI 对话与健康报告',
          '完整的降级 Mock 策略，后端未就绪也可运行',
        ],
      },
      {
        type: 'arch',
        title: '整体架构',
        icon: '🏗️',
        pages: [
          { name: 'login', label: '登录页', desc: '微信/手机号登录' },
          { name: 'index', label: '首页', desc: '设备状态+知识卡片' },
          { name: 'bind', label: '设备绑定', desc: 'BLE 扫码连接' },
          { name: 'control', label: '控制页', desc: 'EMG采集+健康报告' },
          { name: 'ai', label: 'AI 助手', desc: 'LLM 多轮对话' },
          { name: 'forum', label: '康复论坛', desc: '帖子+评论+点赞' },
        ],
        utils: ['ble_manager.js — BLE通信管道', 'protocol.js — CRC32帧协议', 'request.js — HTTP封装+分片上传'],
      },
      {
        type: 'feature',
        title: '登录页',
        icon: '🔐',
        items: [
          '微信一键登录：wx.login() → code → /auth/wechat',
          '手机号验证码：60秒倒计时，防重复提交',
          '后端不可用时自动 Mock 登录，不影响调试',
          '登录态：token + userInfo 存入本地存储',
        ],
      },
      {
        type: 'feature',
        title: '设备绑定 & BLE连接',
        icon: '📡',
        items: [
          '扫二维码或手动输入设备名/MAC地址',
          'MTU 协商 247 字节，最大化传输效率',
          '自动开启 FF02 Notify 特征接收数据',
          '4096字节环形缓冲区 + 200ms 批量解帧',
        ],
      },
      {
        type: 'feature',
        title: '控制页 — EMG 数据采集',
        icon: '📊',
        items: [
          '实时 RMS 强度计算，环形 Canvas 图表展示',
          '按手势序列引导：握拳→张手（各5秒×2轮）',
          '采集数据写入 Int16Array 二进制本地文件',
          '分片上传 256KB/片，支持进度回调',
        ],
      },
      {
        type: 'feature',
        title: '帧协议 CRC32',
        icon: '🔬',
        items: [
          '帧格式：[0xAA] [payload] [CRC32 LE 4字节] [0x55]',
          '每采样点 = 8通道 × int16 = 16字节',
          '标准 IEEE 802.3 CRC32，与Python zlib完全对齐',
          '指令帧：sendCommand(0x0A/0x0B) 控制采集开关',
        ],
      },
      {
        type: 'feature',
        title: 'AI 助手页',
        icon: '🤖',
        items: [
          '调用后端 POST /ai/chat 进行多轮对话',
          '快捷问题：报错次数、肌电数据、康复训练、电量',
          '后端不可用时按关键词匹配 Mock 回复',
          '消息列表自动滚动到最新消息',
        ],
      },
      {
        type: 'feature',
        title: '康复社区论坛',
        icon: '💬',
        items: [
          '分页加载帖子，下拉刷新 + 触底加载更多',
          '发帖支持最多9张图片，逐张上传获取URL',
          '点赞：前端乐观更新，异步同步后端',
          '评论离线缓存，后端不可用读本地 Storage',
        ],
      },
      {
        type: 'mock',
        title: '降级 Mock 策略',
        icon: '🛡️',
        rows: [
          { scene: '后端接口不可用', strategy: '展示 Mock 数据，不影响开发' },
          { scene: '无BLE硬件', strategy: 'startMock() 模拟500Hz数据流' },
          { scene: '论坛后端不可用', strategy: '读本地缓存→无则Mock评论' },
          { scene: '登录后端不可用', strategy: '写Mock token，直接进首页' },
          { scene: '发评论失败', strategy: '本地追加+提示"已暂存"' },
        ],
      },
      {
        type: 'storage',
        title: '本地存储 Key 一览',
        icon: '💾',
        rows: [
          { key: 'token', type: 'string', desc: 'Bearer 令牌' },
          { key: 'userInfo', type: 'object', desc: '{ id, name, phone }' },
          { key: 'avatarUrl', type: 'string', desc: '用户头像本地路径' },
          { key: 'boundDevice', type: 'object', desc: '{ name, hardware_id, deviceId, bindTime }' },
          { key: 'local_comments_{id}', type: 'object', desc: '评论离线缓存' },
          { key: 'customGestures', type: 'array', desc: '个性化手势列表' },
        ],
      },
      {
        type: 'end',
        title: '谢谢观看',
        subtitle: '肌电假手管理系统',
        items: ['蓝牙BLE实时通信', '8通道EMG数据采集', 'AI健康助手', '康复交流社区'],
      },
    ],
  },

  onSwiperChange(e) {
    this.setData({ current: e.detail.current });
  },

  goTo(e) {
    const index = e.currentTarget.dataset.index;
    this.setData({ current: index });
  },

  prev() {
    const cur = this.data.current;
    if (cur > 0) this.setData({ current: cur - 1 });
  },

  next() {
    const cur = this.data.current;
    if (cur < this.data.slides.length - 1) this.setData({ current: cur + 1 });
  },
});
