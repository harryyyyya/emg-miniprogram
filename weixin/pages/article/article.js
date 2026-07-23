const { request } = require('../../utils/request');

const FALLBACK_ARTICLES = {
  1: {
    tag: '设备连接',
    title: '新手第一次连接假手：先确认这 3 件事',
    summary: '如果小程序绑定成功但设备仍然显示离线，可以按这份清单逐项检查。',
    sections: [
      {
        heading: '1. 先检查 ESP32 程序配置',
        items: [
          'BACKEND_HOST 应该是 api.handemglsh.cloud。',
          'BACKEND_PORT 应该是 443。',
          'HARDWARE_ID 要和小程序绑定的设备编号一致。',
          'BOARD_TOKEN 要和小程序绑定时填写的设备密钥一致。',
        ],
      },
      {
        heading: '2. 再看串口监视器',
        items: [
          '串口波特率选择 115200。',
          '看到 WiFi connected, IP=... 说明 ESP32 已连上 Wi-Fi。',
          '看到 registerBoard status=200 说明设备已注册到后端。',
          '看到 heartbeat status=200 说明后端已收到设备心跳。',
        ],
      },
      {
        heading: '3. 最后检查小程序',
        items: [
          '如果使用默认固件，直接绑定 ESP32-HAND-001。',
          '进入控制页后点击刷新设备状态。',
          '如果仍然离线，优先核对设备编号和设备密钥。',
        ],
      },
    ],
    tips: [
      '绑定成功只代表后端保存了设备信息，真正在线要看 ESP32 是否持续上报心跳。',
      '换新板子也可以继续使用，只要烧录同一份程序，并保持设备编号和密钥一致。',
    ],
  },
  2: {
    tag: '训练建议',
    title: '动作录入怎么练：每次 5 秒更稳定',
    summary: '肌电训练不一定越久越好，稳定、干净、可重复的数据更重要。',
    sections: [
      {
        heading: '1. 录入前准备',
        items: [
          '固定臂环位置，避免每次佩戴位置差异过大。',
          '确认蓝牙臂环或 ESP32 状态在线。',
          '开始前让手臂放松几秒，减少无关肌肉紧张。',
        ],
      },
      {
        heading: '2. 每个动作怎么做',
        items: [
          '先保持 3 秒放松，再保持 3 秒目标动作。',
          '动作过程中尽量不要大幅移动手臂。',
          '波形应该有明显变化，但不要长期贴顶或贴底。',
        ],
      },
      {
        heading: '3. 录入后判断质量',
        items: [
          '查看 RMS、峰值、MIN、MAX 是否异常跳变。',
          '如果波形几乎是一条直线，可能没有采到有效信号。',
          '如果某次数据明显异常，可以删除后重新录入。',
        ],
      },
    ],
    tips: [
      '短时间稳定样本通常比长时间噪声样本更适合训练。',
      '识别不稳定时，先检查数据质量，再考虑调整模型。',
    ],
  },
  3: {
    tag: '心理支持',
    theme: 'warm',
    title: '假手适应期心理疏导：慢慢来，也是一种进步',
    summary: '适应假手不只是训练动作，也是在重新建立安全感、自信和生活节奏。',
    sections: [
      {
        heading: '1. 先允许自己有情绪',
        items: [
          '刚开始使用假手时，出现烦躁、紧张、失落或害怕被关注都很常见。',
          '把目标拆小：今天完成一次连接、一次佩戴、一次动作练习，都算有效进步。',
          '可以每天用一句话记录感受，帮助自己看见变化。',
        ],
      },
      {
        heading: '2. 用身体放松降低压力',
        items: [
          '训练前先做 1 到 3 分钟慢呼吸，让肩膀和前臂尽量放松。',
          '如果训练中明显紧张，可以暂停、伸展、喝水或短暂离开屏幕。',
          '保持规律睡眠、轻量活动和低压力爱好，有助于训练更稳定。',
        ],
      },
      {
        heading: '3. 建立支持网络',
        items: [
          '把训练计划告诉家人或朋友，请他们多记录事实和进步，少做评价。',
          '遇到挫败时，可以向康复治疗师、医生、心理咨询师说明具体困难。',
          '如果情绪低落、焦虑或失眠持续影响生活，请及时寻求专业帮助。',
        ],
      },
    ],
    tips: [
      '心理疏导不是“想开点”，而是给自己一个更安全、更可持续的训练环境。',
      '本页内容只作康复陪伴和健康教育参考，不能替代专业诊断或治疗。',
    ],
  },
};

const contentToSections = (content) => {
  const lines = String(content || '').split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  if (!lines.length) return [];
  return [{ heading: '正文', items: lines }];
};

const normalizeArticle = (article) => {
  const sections = Array.isArray(article.sections) && article.sections.length
    ? article.sections
    : contentToSections(article.content || article.full_content);
  return {
    tag: article.tag || article.type || '康复建议',
    title: article.title || '未命名文章',
    summary: article.summary || article.desc || article.excerpt || '',
    sections,
    tips: Array.isArray(article.tips) ? article.tips : [],
    theme: article.theme || '',
  };
};

Page({
  data: {
    article: null,
  },

  onLoad(options) {
    const id = Number(options.id || 1);
    this.articleId = id;
    this.setData({ article: FALLBACK_ARTICLES[id] || FALLBACK_ARTICLES[1] });
    this.loadRemoteArticle(id);
  },

  async loadRemoteArticle(id) {
    try {
      const article = await request({
        url: `/knowledge/articles/${id}`,
        method: 'GET',
        timeout: 4000,
        silent: true,
      });
      this.setData({ article: normalizeArticle(article) });
    } catch (e) {
      // 保留本地兜底文章，避免弱网时详情页空白。
    }
  },
});
