<template>
  <div class="analysis-dashboard">
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><DataAnalysis /></el-icon>
        分析结果看板
      </h1>
      <p class="page-description">
        按股票与研究深度筛选分析记录；切换 T+x 偏移时在前端本地计算，无需重新请求。
      </p>
    </div>

    <el-card class="filter-card" shadow="never">
      <el-form :inline="true" @submit.prevent="handleSearch">
        <el-form-item label="股票">
          <el-input
            v-model="query.symbol"
            clearable
            placeholder="代码或名称"
            style="width: 160px"
            @keyup.enter="handleSearch"
          />
        </el-form-item>

        <el-form-item label="研究深度">
          <el-select v-model="query.research_depth" clearable placeholder="全部" style="width: 120px">
            <el-option v-for="d in depthOptions" :key="d" :label="d" :value="d" />
          </el-select>
        </el-form-item>

        <el-form-item label="分析日期">
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 250px"
          />
        </el-form-item>

        <el-form-item label="T+x 偏移">
          <el-input-number
            v-model="offset"
            :min="1"
            :max="250"
            :step="1"
            controls-position="right"
            style="width: 120px"
          />
          <span class="offset-tip">交易日，切换即时生效</span>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="loading" @click="handleSearch">
            <el-icon><Search /></el-icon>
            查询
          </el-button>
          <el-button @click="handleReset">
            <el-icon><Refresh /></el-icon>
            重置
          </el-button>
          <el-button :loading="accuracyLoading" @click="handleAccuracy">
            <el-icon><TrendCharts /></el-icon>
            预测准确率
          </el-button>
          <el-button :loading="backtestLoading" @click="openBacktest">
            <el-icon><TrendCharts /></el-icon>
            回测分析
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="table-card" shadow="never">
      <el-table v-loading="loading" :data="displayRecords" stripe>
        <el-table-column label="股票" min-width="140" fixed="left">
          <template #default="{ row }">
            <div class="stock-cell">
              <span class="stock-name">{{ row.stock_name || row.stock_symbol }}</span>
              <span class="stock-code">{{ row.stock_symbol }}</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="analysis_date" label="分析日期" width="110" />
        <el-table-column prop="research_depth" label="研究深度" width="90" />

        <el-table-column label="分析时价格" width="100" align="right">
          <template #default="{ row }">{{ fmtPrice(row.analysis_price) }}</template>
        </el-table-column>

        <el-table-column label="结论" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.action" :type="actionTag(row.action)" size="small">
              {{ row.action }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>

        <el-table-column label="目标价" width="90" align="right">
          <template #default="{ row }">{{ fmtPrice(row.target_price) }}</template>
        </el-table-column>

        <el-table-column label="实时价" width="110" align="right">
          <template #default="{ row }">
            <template v-if="row.latest_close != null">
              <div class="price-cell">
                <span>{{ fmtPrice(row.latest_close) }}</span>
                <span class="price-date">{{ row.latest_trade_date || '-' }}</span>
              </div>
            </template>
            <span v-else class="muted">暂无行情数据</span>
          </template>
        </el-table-column>

        <el-table-column label="实时涨跌幅" width="100" align="right">
          <template #default="{ row }">
            <span :class="pctClass(row.latest_pct_change)">{{ fmtPct(row.latest_pct_change) }}</span>
          </template>
        </el-table-column>

        <el-table-column :label="`T+${offset}收盘价`" width="115" align="right">
          <template #default="{ row }">
            <template v-if="row.tPlus.close != null">
              <div class="price-cell">
                <span>{{ fmtPrice(row.tPlus.close) }}</span>
                <span class="price-date">{{ row.tPlus.trade_date }}</span>
              </div>
            </template>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>

        <el-table-column :label="`T+${offset}涨跌幅`" width="105" align="right">
          <template #default="{ row }">
            <span v-if="row.tPlus.pct != null" :class="pctClass(row.tPlus.pct)">
              {{ fmtPct(row.tPlus.pct) }}
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>

        <el-table-column label="T+x 状态" width="105" align="center">
          <template #default="{ row }">
            <span :class="{ muted: row.tPlus.status !== 'ok' }">{{ statusText(row.tPlus.status) }}</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          background
          layout="total, sizes, prev, pager, next, jumper"
          :total="total"
          v-model:current-page="query.page"
          v-model:page-size="query.page_size"
          :page-sizes="[10, 20, 50, 100]"
          @current-change="load"
          @size-change="handleSizeChange"
        />
      </div>
    </el-card>

    <el-dialog v-model="accuracyVisible" title="预测准确率" width="560px">
      <template v-if="accuracyData">
        <div class="accuracy-summary">
          筛选命中报告 {{ accuracyData.total_reports }} 份，其中含明确买卖方向 {{ accuracyData.spot.total }} 份
        </div>

        <div class="accuracy-block">
          <div class="accuracy-block-title">基于现价（最新收盘价）</div>
          <div class="accuracy-row">
            <span>准确率</span>
            <strong :class="pctClass(accuracyData.spot.accuracy)">
              {{ fmtAccuracy(accuracyData.spot.accuracy) }}
            </strong>
          </div>
          <div class="accuracy-row muted">
            可评估 {{ accuracyData.spot.evaluated }} / 正确 {{ accuracyData.spot.correct }} /
            错误 {{ accuracyData.spot.wrong }} / 平盘 {{ accuracyData.spot.flat ?? 0 }} /
            无行情 {{ accuracyData.spot.no_price }}
          </div>
        </div>

        <div class="accuracy-block">
          <div class="accuracy-block-title">基于 T+{{ accuracyData.offset }} 收盘价</div>
          <div class="accuracy-row">
            <span>准确率</span>
            <strong :class="pctClass(accuracyData.t_plus_x.accuracy)">
              {{ fmtAccuracy(accuracyData.t_plus_x.accuracy) }}
            </strong>
          </div>
          <div class="accuracy-row muted">
            可评估 {{ accuracyData.t_plus_x.evaluated }} / 正确 {{ accuracyData.t_plus_x.correct }} /
            错误 {{ accuracyData.t_plus_x.wrong }} / 平盘 {{ accuracyData.t_plus_x.flat ?? 0 }} /
            待更新 {{ accuracyData.t_plus_x.pending }} / 无行情 {{ accuracyData.t_plus_x.no_price }}
          </div>
        </div>

        <div v-if="accuracyData.by_action && Object.keys(accuracyData.by_action).length" class="accuracy-block">
          <div class="accuracy-block-title">按结论方向</div>
          <div v-for="(item, key) in accuracyData.by_action" :key="key" class="accuracy-row">
            <span>{{ key }}</span>
            <span class="muted">
              共 {{ item.total }} 条，现价正确 {{ item.spot_correct }}/{{ item.spot_evaluated }}（平盘 {{ item.spot_flat ?? 0 }}），
              T+{{ accuracyData.offset }} 正确 {{ item.t_plus_correct }}/{{ item.t_plus_evaluated }}（平盘 {{ item.t_plus_flat ?? 0 }}）
            </span>
          </div>
        </div>
      </template>
      <el-empty v-else description="暂无数据" />
    </el-dialog>

    <el-dialog v-model="backtestVisible" title="回测分析" width="860px">
      <el-form :inline="true" label-width="82px">
        <el-form-item label="策略">
          <el-select v-model="backtestForm.strategy" style="width: 270px">
            <el-option label="策略一：买入信号持有 T+x 卖出" :value="1" />
            <el-option label="策略二：买卖信号加减仓" :value="2" />
          </el-select>
        </el-form-item>
        <el-form-item label="执行价">
          <el-select v-model="backtestForm.entry_mode" style="width: 150px">
            <el-option label="次日开盘价" value="next_open" />
            <el-option label="分析时价格" value="analysis_price" />
          </el-select>
        </el-form-item>
        <el-form-item label="每笔金额">
          <el-input-number v-model="backtestForm.budget" :min="0" :step="10000" controls-position="right" style="width: 150px" />
        </el-form-item>
        <el-form-item v-if="backtestForm.strategy === 1" label="T+x 偏移">
          <el-input-number v-model="backtestForm.offset" :min="1" :max="250" :step="1" controls-position="right" style="width: 120px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="backtestLoading" @click="runBacktest">
            <el-icon><Search /></el-icon>
            开始回测
          </el-button>
        </el-form-item>
      </el-form>

      <template v-if="backtestData">
        <div class="backtest-summary">
          策略{{ backtestData.config.strategy }} ·
          执行价：{{ backtestData.config.entry_mode === 'next_open' ? '次日开盘价' : '分析时价格' }}<template v-if="backtestData.config.strategy === 1"> · T+{{ backtestData.config.offset }}</template> ·
          命中报告 {{ backtestData.stats.total_reports }} 份
        </div>

        <div class="backtest-stat-grid">
          <div class="backtest-stat"><span>买入信号</span><strong>{{ backtestData.stats.buy_signals }}</strong></div>
          <div class="backtest-stat"><span>卖出信号</span><strong>{{ backtestData.stats.sell_signals }}</strong></div>
          <div class="backtest-stat"><span>已执行买入</span><strong>{{ backtestData.stats.executed_buys }}</strong></div>
          <div class="backtest-stat"><span>已执行卖出</span><strong>{{ backtestData.stats.executed_sells }}</strong></div>
          <div class="backtest-stat"><span>跳过买入</span><strong>{{ backtestData.stats.skipped_buys }}</strong></div>
          <div class="backtest-stat"><span>忽略卖出</span><strong>{{ backtestData.stats.ignored_sell_signals }}</strong></div>
          <div class="backtest-stat"><span>总投入</span><strong>{{ fmtMoney(backtestData.stats.total_buy_amount) }}</strong></div>
          <div class="backtest-stat"><span>实现盈亏</span><strong :class="pctClass(backtestData.stats.total_realized_pnl)">{{ fmtMoney(backtestData.stats.total_realized_pnl) }}</strong></div>
          <div class="backtest-stat"><span>浮动盈亏</span><strong :class="pctClass(backtestData.stats.total_floating_pnl)">{{ fmtMoney(backtestData.stats.total_floating_pnl) }}</strong></div>
          <div class="backtest-stat"><span>总盈亏</span><strong :class="pctClass(backtestData.stats.total_pnl)">{{ fmtMoney(backtestData.stats.total_pnl) }}</strong></div>
          <div class="backtest-stat"><span>已平仓</span><strong>{{ backtestData.stats.closed_trades }}</strong></div>
          <div class="backtest-stat"><span>胜率</span><strong>{{ fmtAccuracy(backtestData.stats.win_rate) }}</strong></div>
          <div class="backtest-stat"><span>平均收益率</span><strong :class="pctClass(backtestData.stats.avg_return_pct)">{{ fmtPct(backtestData.stats.avg_return_pct) }}</strong></div>
        </div>

        <div v-if="backtestData.open_positions.length" class="backtest-block">
          <div class="backtest-block-title">当前持仓</div>
          <el-table :data="backtestData.open_positions" size="small" max-height="240">
            <el-table-column label="股票" min-width="130">
              <template #default="{ row }">
                <div class="stock-cell">
                  <span class="stock-name">{{ row.name || row.code }}</span>
                  <span class="stock-code">{{ row.code }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="units" label="份数" width="70" align="right" />
            <el-table-column prop="shares" label="股数" width="80" align="right" />
            <el-table-column label="成本价" width="90" align="right">
              <template #default="{ row }">{{ fmtPrice(row.avg_cost) }}</template>
            </el-table-column>
            <el-table-column label="最新价" width="90" align="right">
              <template #default="{ row }">{{ fmtPrice(row.latest_price) }}</template>
            </el-table-column>
            <el-table-column label="市值" width="110" align="right">
              <template #default="{ row }">{{ fmtMoney(row.market_value) }}</template>
            </el-table-column>
            <el-table-column label="浮动盈亏" width="110" align="right">
              <template #default="{ row }">
                <span :class="pctClass(row.floating_pnl)">{{ fmtMoney(row.floating_pnl) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="收益率" width="90" align="right">
              <template #default="{ row }">
                <span :class="pctClass(row.floating_pnl_pct)">{{ fmtPct(row.floating_pnl_pct) }}</span>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <div v-if="backtestData.config.strategy === 1 && backtestData.legs.length" class="backtest-block">
          <div class="backtest-block-title">策略一交易腿</div>
          <el-table :data="backtestData.legs" size="small" max-height="320">
            <el-table-column label="股票" min-width="130">
              <template #default="{ row }">
                <div class="stock-cell">
                  <span class="stock-name">{{ row.name || row.code }}</span>
                  <span class="stock-code">{{ row.code }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="signal_date" label="信号日" width="100" />
            <el-table-column prop="entry_date" label="入场日" width="100" />
            <el-table-column label="入场价" width="90" align="right">
              <template #default="{ row }">{{ fmtPrice(row.entry_price) }}</template>
            </el-table-column>
            <el-table-column prop="shares" label="股数" width="80" align="right" />
            <el-table-column label="买入金额" width="110" align="right">
              <template #default="{ row }">{{ fmtMoney(row.buy_amount) }}</template>
            </el-table-column>
            <el-table-column prop="exit_date" label="卖出日" width="100" />
            <el-table-column label="卖出价" width="90" align="right">
              <template #default="{ row }">{{ fmtPrice(row.exit_price) }}</template>
            </el-table-column>
            <el-table-column label="实现盈亏" width="110" align="right">
              <template #default="{ row }">
                <span :class="pctClass(row.realized_pnl)">{{ fmtMoney(row.realized_pnl) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="收益率" width="90" align="right">
              <template #default="{ row }">
                <span :class="pctClass(row.pnl_pct)">{{ fmtPct(row.pnl_pct) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="80" align="center">
              <template #default="{ row }">{{ backtestStatusText(row.status) }}</template>
            </el-table-column>
          </el-table>
        </div>

        <div v-if="backtestData.config.strategy === 2 && backtestData.trades.length" class="backtest-block">
          <div class="backtest-block-title">策略二成交记录</div>
          <el-table :data="backtestData.trades" size="small" max-height="320">
            <el-table-column prop="side" label="方向" width="70" align="center" />
            <el-table-column label="股票" min-width="120">
              <template #default="{ row }">
                <div class="stock-cell">
                  <span class="stock-name">{{ row.name || row.code }}</span>
                  <span class="stock-code">{{ row.code }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="signal_date" label="信号日" width="100" />
            <el-table-column prop="exec_date" label="成交日" width="100" />
            <el-table-column label="成交价" width="90" align="right">
              <template #default="{ row }">{{ fmtPrice(row.exec_price) }}</template>
            </el-table-column>
            <el-table-column prop="shares" label="股数" width="80" align="right" />
            <el-table-column label="金额" width="110" align="right">
              <template #default="{ row }">{{ fmtMoney(row.amount) }}</template>
            </el-table-column>
            <el-table-column label="成本价" width="90" align="right">
              <template #default="{ row }">{{ row.avg_cost == null ? '-' : fmtPrice(row.avg_cost) }}</template>
            </el-table-column>
            <el-table-column label="实现盈亏" width="110" align="right">
              <template #default="{ row }">
                <span v-if="row.realized_pnl != null" :class="pctClass(row.realized_pnl)">{{ fmtMoney(row.realized_pnl) }}</span>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column label="收益率" width="90" align="right">
              <template #default="{ row }">
                <span v-if="row.pnl_pct != null" :class="pctClass(row.pnl_pct)">{{ fmtPct(row.pnl_pct) }}</span>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="80" align="center">
              <template #default="{ row }">{{ backtestStatusText(row.status) }}</template>
            </el-table-column>
          </el-table>
        </div>
      </template>
      <el-empty v-else description="点击开始回测" />
    </el-dialog>

  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { DataAnalysis, Refresh, Search, TrendCharts } from '@element-plus/icons-vue'
import {
  getAnalysisDashboard,
  getAnalysisDashboardAccuracy,
  getAnalysisDashboardBacktest,
  type AnalysisDashboardRecord,
  type AnalysisDashboardAccuracyResponse,
  type AnalysisDashboardBacktestResponse,
  type DashboardPricePoint
} from '@/api/analysis'

const depthOptions = ['快速', '基础', '标准', '深度', '全面']

const query = reactive({
  symbol: '',
  research_depth: '',
  page: 1,
  page_size: 20
})
const dateRange = ref<[string, string] | null>(null)
const offset = ref(5)
const loading = ref(false)
const records = ref<AnalysisDashboardRecord[]>([])
const prices = ref<Record<string, DashboardPricePoint[]>>({})
const total = ref(0)
const accuracyVisible = ref(false)
const accuracyLoading = ref(false)
const accuracyData = ref<AnalysisDashboardAccuracyResponse | null>(null)
const backtestVisible = ref(false)
const backtestLoading = ref(false)
const backtestForm = reactive({
  strategy: 1,
  budget: 50000,
  entry_mode: 'next_open' as 'next_open' | 'analysis_price',
  offset: 5
})
const backtestData = ref<AnalysisDashboardBacktestResponse | null>(null)

function computeTPlus(record: AnalysisDashboardRecord, x: number) {
  const seq = prices.value[record.stock_symbol] || []
  if (!seq.length) {
    return { close: null, trade_date: null, pct: null, status: '暂无行情数据' }
  }

  const future = seq.filter((p) => p.trade_date > record.analysis_date)
  if (future.length >= x) {
    const point = future[x - 1]
    if (point.close == null) {
      return { close: null, trade_date: point.trade_date, pct: null, status: '待更新' }
    }

    const pct = record.analysis_price
      ? ((point.close - record.analysis_price) / record.analysis_price) * 100
      : null
    return {
      close: point.close,
      trade_date: point.trade_date,
      pct: pct == null ? null : Number(pct.toFixed(2)),
      status: 'ok'
    }
  }

  return { close: null, trade_date: null, pct: null, status: '待更新' }
}

const displayRecords = computed(() => {
  return records.value.map((record) => ({
    ...record,
    tPlus: computeTPlus(record, offset.value)
  }))
})

async function load() {
  loading.value = true
  try {
    const params: Record<string, any> = {
      page: query.page,
      page_size: query.page_size,
      offset: offset.value
    }
    if (query.symbol.trim()) params.symbol = query.symbol.trim()
    if (query.research_depth) params.research_depth = query.research_depth
    if (dateRange.value && dateRange.value[0] && dateRange.value[1]) {
      params.start_date = dateRange.value[0]
      params.end_date = dateRange.value[1]
    }

    const data = await getAnalysisDashboard(params)
    records.value = data.records || []
    prices.value = data.prices || {}
    total.value = data.total || 0
  } catch (error: any) {
    ElMessage.error(error?.message || '加载分析看板失败')
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  query.page = 1
  load()
}

function handleSizeChange() {
  query.page = 1
  load()
}

function handleReset() {
  query.symbol = ''
  query.research_depth = ''
  query.page = 1
  query.page_size = 20
  dateRange.value = null
  offset.value = 5
  load()
}

async function handleAccuracy() {
  accuracyLoading.value = true
  try {
    const params: Record<string, any> = { offset: offset.value }
    if (query.symbol.trim()) params.symbol = query.symbol.trim()
    if (query.research_depth) params.research_depth = query.research_depth
    if (dateRange.value && dateRange.value[0] && dateRange.value[1]) {
      params.start_date = dateRange.value[0]
      params.end_date = dateRange.value[1]
    }

    accuracyData.value = await getAnalysisDashboardAccuracy(params)
    accuracyVisible.value = true
  } catch (error: any) {
    ElMessage.error(error?.message || '获取预测准确率失败')
  } finally {
    accuracyLoading.value = false
  }
}

function openBacktest() {
  backtestForm.offset = offset.value
  backtestData.value = null
  backtestVisible.value = true
}

async function runBacktest() {
  backtestLoading.value = true
  try {
    const params: Record<string, any> = {
      offset: backtestForm.offset,
      strategy: backtestForm.strategy,
      budget: backtestForm.budget,
      entry_mode: backtestForm.entry_mode
    }
    if (query.symbol.trim()) params.symbol = query.symbol.trim()
    if (query.research_depth) params.research_depth = query.research_depth
    if (dateRange.value && dateRange.value[0] && dateRange.value[1]) {
      params.start_date = dateRange.value[0]
      params.end_date = dateRange.value[1]
    }

    backtestData.value = await getAnalysisDashboardBacktest(params)
  } catch (error: any) {
    ElMessage.error(error?.message || '获取回测分析失败')
  } finally {
    backtestLoading.value = false
  }
}

function fmtMoney(value: number | null | undefined): string {
  if (value == null || Number.isNaN(Number(value))) return '-'
  return Number(value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function backtestStatusText(status: string): string {
  if (status === 'closed') return '已平仓'
  if (status === 'open') return '持仓'
  return status
}

function fmtAccuracy(value: number | null | undefined): string {
  return value == null ? '暂无数据' : `${Number(value).toFixed(1)}%`
}

function fmtPrice(value: number | null | undefined): string {
  return value == null ? '-' : Number(value).toFixed(2)
}

function fmtPct(value: number | null | undefined): string {
  if (value == null) return '-'
  const n = Number(value)
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`
}

function pctClass(value: number | null | undefined): string {
  if (value == null) return 'muted'
  return Number(value) >= 0 ? 'pct-up' : 'pct-down'
}

function actionTag(action: string): 'danger' | 'success' | 'warning' | 'info' {
  if (action.includes('买入')) return 'danger'
  if (action.includes('卖出')) return 'success'
  if (action.includes('持有') || action.includes('观望')) return 'warning'
  return 'info'
}

function statusText(status: string): string {
  if (status === 'ok') return '已到期'
  if (status === '待更新') return '待更新'
  return '暂无行情数据'
}

onMounted(load)
</script>

<style lang="scss" scoped>
.page-header {
  margin-bottom: 16px;

  .page-title {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 0 0 4px;
    font-size: 22px;
    font-weight: 600;
  }

  .page-description {
    margin: 0;
    color: var(--el-text-color-secondary);
    font-size: 14px;
  }
}

.filter-card {
  margin-bottom: 16px;

  .offset-tip {
    margin-left: 8px;
    color: var(--el-text-color-secondary);
    font-size: 12px;
  }
}

.table-card {
  .pagination {
    display: flex;
    justify-content: flex-end;
    margin-top: 16px;
  }
}

.stock-cell {
  display: flex;
  flex-direction: column;

  .stock-name {
    font-weight: 600;
  }

  .stock-code {
    color: var(--el-text-color-secondary);
    font-size: 12px;
  }
}

.price-cell {
  display: flex;
  flex-direction: column;

  .price-date {
    color: var(--el-text-color-secondary);
    font-size: 12px;
  }
}

.pct-up {
  color: #f56c6c;
  font-weight: 600;
}

.pct-down {
  color: #67c23a;
  font-weight: 600;
}

.accuracy-summary {
  margin-bottom: 12px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.accuracy-block {
  margin-bottom: 14px;
  padding: 12px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
}

.accuracy-block-title {
  margin-bottom: 8px;
  font-weight: 600;
  font-size: 14px;
}

.accuracy-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 4px 0;
  font-size: 14px;

  strong {
    font-size: 18px;
  }
}

.backtest-summary {
  margin-bottom: 12px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.backtest-stat-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-bottom: 14px;
}

.backtest-stat {
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  background: var(--el-fill-color-blank);

  span {
    display: block;
    margin-bottom: 4px;
    color: var(--el-text-color-secondary);
    font-size: 12px;
  }

  strong {
    font-size: 16px;
    font-weight: 600;
  }
}

.backtest-block {
  margin-top: 14px;
}

.backtest-block-title {
  margin-bottom: 8px;
  font-weight: 600;
  font-size: 14px;
}

.muted {
  color: var(--el-text-color-secondary);
}
</style>
