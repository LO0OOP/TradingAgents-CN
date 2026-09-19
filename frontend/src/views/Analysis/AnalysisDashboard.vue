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
            错误 {{ accuracyData.spot.wrong }} / 无行情 {{ accuracyData.spot.no_price }}
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
            错误 {{ accuracyData.t_plus_x.wrong }} / 待更新 {{ accuracyData.t_plus_x.pending }} /
            无行情 {{ accuracyData.t_plus_x.no_price }}
          </div>
        </div>

        <div v-if="accuracyData.by_action && Object.keys(accuracyData.by_action).length" class="accuracy-block">
          <div class="accuracy-block-title">按结论方向</div>
          <div v-for="(item, key) in accuracyData.by_action" :key="key" class="accuracy-row">
            <span>{{ key }}</span>
            <span class="muted">
              共 {{ item.total }} 条，现价正确 {{ item.spot_correct }}/{{ item.spot_evaluated }}，
              T+{{ accuracyData.offset }} 正确 {{ item.t_plus_correct }}/{{ item.t_plus_evaluated }}
            </span>
          </div>
        </div>
      </template>
      <el-empty v-else description="暂无数据" />
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
  type AnalysisDashboardRecord,
  type AnalysisDashboardAccuracyResponse,
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

.muted {
  color: var(--el-text-color-secondary);
}
</style>
