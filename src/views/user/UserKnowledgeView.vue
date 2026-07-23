<template>
  <div>
    <div class="page-header">
      <h2 class="page-title gradient-text">知识库</h2>
      <el-input v-model="searchText" placeholder="搜索文章..." prefix-icon="Search" clearable style="width: 260px" />
    </div>

    <div class="kb-grid">
      <div v-for="article in filteredArticles" :key="article.id" class="glass-card kb-card" @click="openArticle(article)">
        <div class="kb-tag-row">
          <el-tag :type="article.type === 'update' ? 'primary' : 'success'" size="small">
            {{ article.type === 'update' ? '版本更新' : '使用指南' }}
          </el-tag>
          <span class="kb-date">{{ article.date }}</span>
        </div>
        <h3 class="kb-title">{{ article.title }}</h3>
        <p class="kb-excerpt">{{ article.excerpt }}</p>
        <span class="kb-read-more">阅读全文 →</span>
      </div>
    </div>

    <!-- 文章详情弹窗 -->
    <el-dialog
      v-model="showDetail"
      :title="currentArticle?.title || ''"
      width="740"
      top="5vh"
      class="article-dialog"
      :close-on-click-modal="true"
      destroy-on-close
    >
      <div class="article-detail" v-if="currentArticle">
        <div class="article-meta">
          <el-tag :type="currentArticle.type === 'update' ? 'primary' : 'success'" size="small">
            {{ currentArticle.type === 'update' ? '版本更新' : '使用指南' }}
          </el-tag>
          <span class="article-date">{{ currentArticle.date }}</span>
        </div>
        <div class="article-body" v-html="currentArticle.fullContent"></div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

const searchText = ref('')
const showDetail = ref(false)

interface Article {
  id: number
  type: string
  title: string
  excerpt: string
  date: string
  fullContent: string
}

const currentArticle = ref<Article | null>(null)

const articles = ref<Article[]>([
  {
    id: 1,
    type: 'update',
    title: '固件 v2.1.0 发布说明',
    excerpt: '本次更新优化了 BLE 连接的稳定性，新增自适应重连延迟策略 (Exponential Backoff)。同时修复了高负载场景下电机驱动 PID 控制器偶发过流保护误触的问题...',
    date: '2026-03-22',
    fullContent: `
      <h3>更新亮点</h3>
      <ul>
        <li><strong>BLE 连接优化</strong>：新增自适应重连延迟策略 (Exponential Backoff)，在信号不稳定的环境下，设备会智能调整重连间隔，从 1 秒逐步增加到最大 30 秒，避免频繁断连重连导致的电量消耗。</li>
        <li><strong>PID 控制器修复</strong>：修复了高负载场景下电机驱动 PID 控制器偶发过流保护误触的问题。通过引入滑动窗口平均值滤波，消除了瞬间电流尖峰对保护阈值的误判。</li>
        <li><strong>推理频率提升</strong>：板端推理频率从 5Hz 提升至 10Hz，采用 200ms 窗长 + 100ms 步长的滑窗策略，动作识别的响应速度和平滑度显著提升。</li>
        <li><strong>采样链路重构</strong>：采集层从整窗生产者模式升级为单样本生产者模式，每 2ms 产出一个 8 通道样本帧，IIR 滤波器状态沿时间连续推进，消除了重叠窗口中滤波状态重复推进的问题。</li>
      </ul>
      <h3>已知问题</h3>
      <ul>
        <li>长时间运行（超过 4 小时）后，蓝牙通知频率可能出现轻微波动，预计在 v2.2.0 中修复。</li>
        <li>Arduino 兼容版固件仍在开发中，当前版本仅支持 ESP-IDF 环境。</li>
      </ul>
      <h3>升级指南</h3>
      <p>通过小程序"设备管理"页面进行 OTA 升级，升级过程约需 2 分钟。建议在电量高于 50% 时进行升级。升级后设备会自动重启并重新连接。</p>
    `,
  },
  {
    id: 2,
    type: 'guide',
    title: '新用户穿戴入门指南',
    excerpt: '欢迎使用 NeuroHand 肌电假手系统！本指南将帮助您了解设备的基本穿戴步骤、传感器安放位置以及初次校准流程...',
    date: '2026-03-20',
    fullContent: `
      <h3>设备组成</h3>
      <p>NeuroHand 假手系统由以下部分组成：</p>
      <ul>
        <li><strong>肌电传感器臂环</strong>：配备 8 个 EMG 采集通道，采样率 500Hz，通过 SPI + DMA 与主控芯片通信。</li>
        <li><strong>ESP32-S3 主控模块</strong>：负责实时信号处理、特征提取、LDA 推理和蓝牙通信。</li>
        <li><strong>假手机械结构</strong>：包含 5 个独立电机驱动的手指，支持多种抓握模式。</li>
      </ul>
      <h3>穿戴步骤</h3>
      <ol>
        <li>清洁前臂皮肤，确保传感器接触面无汗渍或油脂。</li>
        <li>将臂环套在前臂肌肉最丰满的位置（通常距肘关节约 3-5cm）。</li>
        <li>确保 8 个电极均匀分布，CH1 电极对准前臂内侧正中。</li>
        <li>调整臂环松紧度，确保贴合但不影响血液循环。</li>
        <li>通过小程序扫码绑定设备，完成蓝牙配对。</li>
      </ol>
      <h3>初次校准</h3>
      <p>首次使用需要进行个性化模型训练：</p>
      <ol>
        <li>打开小程序"控制"页面，点击"开始采集"。</li>
        <li>按照屏幕提示，依次做出握拳、展手、捏取等标准动作。</li>
        <li>每个动作重复 5 次，每次保持 3 秒。</li>
        <li>采集完成后，系统会自动训练个性化模型并下发到设备。</li>
      </ol>
      <h3>注意事项</h3>
      <ul>
        <li>避免在传感器与皮肤之间夹杂衣物。</li>
        <li>建议每次使用前先进行 1 分钟的放松-收缩热身。</li>
        <li>如遇信号异常，可尝试调整臂环位置或重新校准。</li>
      </ul>
    `,
  },
  {
    id: 3,
    type: 'guide',
    title: '肌电信号训练最佳实践',
    excerpt: '为获得最佳的控制精度，建议新用户每日进行 3 次、每次 15 分钟的标准化握力训练。训练过程中注意保持前臂放松...',
    date: '2026-03-18',
    fullContent: `
      <h3>训练原理</h3>
      <p>NeuroHand 使用 LDA（线性判别分析）算法对肌电信号进行分类。系统从 8 个通道提取 4 种特征（MAV、WL、MSV、ZC），形成 32 维特征向量。通过 Z-score 标准化后送入 LDA 分类器，输出动作类别。</p>
      <p>训练的核心目标是让系统学会您的个人肌电模式。每个人的肌肉分布、发力习惯都不同，因此个性化训练非常重要。</p>
      <h3>推荐训练计划</h3>
      <table style="width:100%;border-collapse:collapse;margin:12px 0">
        <tr style="border-bottom:1px solid rgba(99,102,241,0.15)">
          <th style="text-align:left;padding:8px;color:#94a3b8">阶段</th>
          <th style="text-align:left;padding:8px;color:#94a3b8">频率</th>
          <th style="text-align:left;padding:8px;color:#94a3b8">时长</th>
          <th style="text-align:left;padding:8px;color:#94a3b8">内容</th>
        </tr>
        <tr style="border-bottom:1px solid rgba(99,102,241,0.08)">
          <td style="padding:8px">第 1 周</td><td style="padding:8px">每日 3 次</td><td style="padding:8px">每次 10 分钟</td><td style="padding:8px">握拳/展手交替，适应传感器</td>
        </tr>
        <tr style="border-bottom:1px solid rgba(99,102,241,0.08)">
          <td style="padding:8px">第 2-3 周</td><td style="padding:8px">每日 2 次</td><td style="padding:8px">每次 15 分钟</td><td style="padding:8px">加入捏取、侧握等精细动作</td>
        </tr>
        <tr>
          <td style="padding:8px">第 4 周+</td><td style="padding:8px">每日 1 次</td><td style="padding:8px">每次 15 分钟</td><td style="padding:8px">维持训练，定期重新校准</td>
        </tr>
      </table>
      <h3>提高准确率的技巧</h3>
      <ul>
        <li>做动作前先放松 2 秒，确保基线信号平稳。</li>
        <li>每次发力保持一致的力度，避免忽大忽小。</li>
        <li>保持呼吸均匀，避免憋气导致全身肌肉紧张。</li>
        <li>训练时避免移动手臂位置，减少运动伪迹干扰。</li>
        <li>如果准确率持续低于 80%，建议重新调整电极位置后重新采集训练数据。</li>
      </ul>
    `,
  },
  {
    id: 4,
    type: 'update',
    title: '小程序 v1.5.0 更新日志',
    excerpt: '新增 AI 助手对话功能，优化了数据采集时的实时波形展示性能，修复了论坛页面在低版本微信基础库中的兼容性问题...',
    date: '2026-03-15',
    fullContent: `
      <h3>新功能</h3>
      <ul>
        <li><strong>AI 助手</strong>：新增智能对话功能，支持查询设备状态、训练数据、康复建议等。内置 4 个快捷问题，方便快速获取常见信息。</li>
        <li><strong>社区论坛</strong>：新增病友交流论坛，支持发帖、评论、点赞、图片上传等功能。鼓励用户分享康复经验。</li>
      </ul>
      <h3>优化</h3>
      <ul>
        <li>数据采集时的实时波形展示使用 LTTB 降采样算法，在保持波形特征的同时大幅降低渲染压力。</li>
        <li>BLE 连接流程增加超时重试机制，提升设备绑定成功率。</li>
        <li>个人中心页增加设备详细信息展示（固件版本、电量、绑定时间）。</li>
      </ul>
      <h3>修复</h3>
      <ul>
        <li>修复论坛页面在微信基础库 2.x 低版本中的组件兼容性问题。</li>
        <li>修复偶发的上传分片丢失问题，增加分片完整性校验。</li>
      </ul>
    `,
  },
])

const filteredArticles = computed(() => {
  if (!searchText.value) return articles.value
  const kw = searchText.value.toLowerCase()
  return articles.value.filter(a => a.title.toLowerCase().includes(kw) || a.excerpt.toLowerCase().includes(kw))
})

function openArticle(article: Article) {
  currentArticle.value = article
  showDetail.value = true
}
</script>

<style scoped>
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px; }
.page-title { font-size: 28px; font-weight: 700; }

.kb-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 20px; }

.kb-card {
  display: flex; flex-direction: column; cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
}
.kb-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 32px rgba(99, 102, 241, 0.15);
}

.kb-tag-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.kb-date { font-size: 12px; color: var(--color-text-muted); }
.kb-title { font-size: 18px; font-weight: 600; margin-bottom: 8px; }
.kb-excerpt { font-size: 14px; color: var(--color-text-muted); line-height: 1.7; flex: 1; }
.kb-read-more { margin-top: 12px; color: var(--color-primary-light); font-size: 13px; font-weight: 500; }

/* 文章详情弹窗 */
.article-meta { display: flex; align-items: center; gap: 12px; margin-bottom: 20px; padding-bottom: 16px; border-bottom: 1px solid rgba(99,102,241,0.1); }
.article-date { font-size: 13px; color: var(--color-text-muted); }

.article-body { font-size: 14px; line-height: 1.85; color: #e2e8f0; }
.article-body :deep(h3) { font-size: 17px; font-weight: 600; margin: 24px 0 12px; color: var(--color-text); }
.article-body :deep(ul), .article-body :deep(ol) { padding-left: 20px; margin: 8px 0; }
.article-body :deep(li) { margin-bottom: 6px; color: #cbd5e1; }
.article-body :deep(strong) { color: var(--color-primary-light); font-weight: 600; }
.article-body :deep(p) { margin: 8px 0; }
.article-body :deep(table) { margin: 12px 0; }
.article-body :deep(th) { color: #94a3b8; }
</style>
