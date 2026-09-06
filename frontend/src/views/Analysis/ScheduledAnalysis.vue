<template>
  <div class="scheduled-analysis">
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><Clock /></el-icon>
        定时分析
      </h1>
      <p class="page-description">按设定的周期自动执行批量分析，支持多任务组</p>
    </div>

    <el-card class="list-card" shadow="never">
      <div class="list-header">
        <el-button type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon>
          新建任务组
        </el-button>
        <el-button @click="loadGroups" :loading="loading">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
        <el-button @click="openEmailSettings">
          <el-icon><Message /></el-icon>
          邮件设置
        </el-button>
      </div>

      <el-table :data="groups" v-loading="loading" style="width: 100%">
        <el-table-column prop="name" label="任务组" min-width="140" />
        <el-table-column label="周期" min-width="170">
          <template #default="{ row }">
            <span>{{ formatWeekdays(row.weekdays) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="time" label="触发时间" width="90" />
        <el-table-column label="股票" min-width="160">
          <template #default="{ row }">
            <el-tag v-for="s in row.symbols" :key="s" size="small" style="margin: 2px">{{ s }}</el-tag>
            <span v-if="!row.symbols || row.symbols.length === 0" class="text-gray">-</span>
          </template>
        </el-table-column>
        <el-table-column label="深度/模型" min-width="200">
          <template #default="{ row }">
            <el-tag type="warning" size="small">{{ depthText(row.parameters?.research_depth) }}</el-tag>
            <span class="text-gray">{{ row.parameters?.deep_analysis_model || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? '启用' : '停用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="上次执行" width="160">
          <template #default="{ row }">
            {{ row.last_run_at ? formatTime(row.last_run_at) : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="250" fixed="right">
          <template #default="{ row }">
            <el-button type="text" size="small" @click="runNow(row)">立即执行</el-button>
            <el-button type="text" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button type="text" size="small" @click="toggle(row)">{{ row.enabled ? '停用' : '启用' }}</el-button>
            <el-button type="text" size="small" style="color: #f56c6c" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新建/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑任务组' : '新建任务组'" width="720px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="任务组名" required>
          <el-input v-model="form.name" placeholder="如：每日早盘分析" />
        </el-form-item>

        <el-form-item label="触发周期" required>
          <el-checkbox-group v-model="form.weekdays">
            <el-checkbox v-for="(w, i) in WEEKDAY_LABELS" :key="i" :label="i">{{ w }}</el-checkbox>
          </el-checkbox-group>
        </el-form-item>

        <el-form-item label="触发时间" required>
          <el-time-picker v-model="form.time" format="HH:mm" value-format="HH:mm" placeholder="选择时间" />
        </el-form-item>

        <el-form-item label="股票列表" required>
          <el-input v-model="form.symbolsText" type="textarea" :rows="4" placeholder="每行一个股票代码，如：&#10;600519&#10;000001&#10;AAPL" />
        </el-form-item>

        <el-form-item label="分析深度">
          <el-select v-model="form.depth" style="width: 100%">
            <el-option label="⚡ 1级 - 快速分析" value="1" />
            <el-option label="📈 2级 - 基础分析" value="2" />
            <el-option label="🎯 3级 - 标准分析（推荐）" value="3" />
            <el-option label="🔍 4级 - 深度分析" value="4" />
            <el-option label="🏆 5级 - 全面分析" value="5" />
          </el-select>
        </el-form-item>

        <el-form-item label="分析师团队">
          <el-checkbox-group v-model="form.analysts" class="analysts-group">
            <el-checkbox v-for="a in ANALYSTS" :key="a.id" :label="a.name">
              <span style="margin-right: 4px;">{{ a.name }}</span>
              <span style="font-size: 12px; color: #909399;">{{ a.description }}</span>
            </el-checkbox>
          </el-checkbox-group>
        </el-form-item>

        <el-form-item label="AI模型">
          <ModelConfig
            v-model:quick-analysis-model="modelSettings.quickAnalysisModel"
            v-model:deep-analysis-model="modelSettings.deepAnalysisModel"
            :available-models="availableModels"
            :analysis-depth="form.depth"
          />
        </el-form-item>

        <el-form-item label="分析选项">
          <div class="options-row">
            <div class="option-item">
              <el-switch v-model="form.includeSentiment" />
              <span class="option-name">情绪分析</span>
            </div>
            <div class="option-item">
              <el-switch v-model="form.includeRisk" />
              <span class="option-name">风险评估</span>
            </div>
            <div class="option-item">
              <el-select v-model="form.language" size="small" style="width: 120px">
                <el-option label="中文" value="zh-CN" />
                <el-option label="English" value="en-US" />
              </el-select>
            </div>
          </div>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <!-- 邮件推送设置对话框 -->
    <el-dialog v-model="emailDialogVisible" title="邮件推送设置" width="560px">
      <el-form :model="emailForm" label-width="110px">
        <el-form-item label="启用邮件推送">
          <el-switch v-model="emailForm.enabled" />
        </el-form-item>
        <el-form-item label="SMTP服务器">
          <el-input v-model="emailForm.smtp_host" placeholder="smtp.163.com" />
        </el-form-item>
        <el-form-item label="端口">
          <el-input-number v-model="emailForm.smtp_port" :min="1" :max="65535" controls-position="right" style="width: 160px" />
        </el-form-item>
        <el-form-item label="发件邮箱">
          <el-input v-model="emailForm.sender" placeholder="you@163.com" />
        </el-form-item>
        <el-form-item label="授权码">
          <el-input v-model="emailForm.auth_code" type="password" show-password placeholder="163 邮箱 SMTP 授权码" />
        </el-form-item>
        <el-form-item label="收件邮箱">
          <el-input v-model="emailForm.recipientsText" type="textarea" :rows="2" placeholder="多个邮箱用逗号或换行分隔" />
        </el-form-item>
        <el-form-item label="附带PDF">
          <el-switch v-model="emailForm.attach_pdf" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="emailDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingEmail" @click="saveEmailConfig">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Clock, Plus, Refresh, Message } from '@element-plus/icons-vue'
import { scheduledAnalysisApi, type ScheduledGroup, type EmailConfig } from '@/api/scheduledAnalysis'
import { ANALYSTS, DEFAULT_ANALYSTS, convertAnalystNamesToIds, convertAnalystIdsToNames } from '@/constants/analysts'
import { configApi } from '@/api/config'
import ModelConfig from '@/components/ModelConfig.vue'

const WEEKDAY_LABELS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

const loading = ref(false)
const saving = ref(false)
const groups = ref<ScheduledGroup[]>([])
const dialogVisible = ref(false)
const editingId = ref('')

const emailDialogVisible = ref(false)
const savingEmail = ref(false)
const emailForm = reactive({
  enabled: false,
  smtp_host: 'smtp.163.com',
  smtp_port: 465,
  sender: '',
  auth_code: '',
  recipientsText: '',
  attach_pdf: true
})

const modelSettings = ref({
  quickAnalysisModel: 'qwen-turbo',
  deepAnalysisModel: 'qwen-max'
})
const availableModels = ref<any[]>([])

const form = reactive({
  name: '',
  weekdays: [0, 1, 2, 3, 4] as number[],
  time: '09:30',
  symbolsText: '',
  depth: '3',
  analysts: [...DEFAULT_ANALYSTS] as string[],
  includeSentiment: true,
  includeRisk: true,
  language: 'zh-CN'
})

const formatWeekdays = (weekdays: number[] | undefined) => {
  if (!weekdays || weekdays.length === 0) return '-'
  return weekdays.map((i) => WEEKDAY_LABELS[i] || String(i)).join('、')
}

const depthText = (d: string | number | undefined) => {
  const map: Record<string, string> = { '1': '快速', '2': '基础', '3': '标准', '4': '深度', '5': '全面' }
  return map[String(d)] || '标准'
}

const formatTime = (t: string) => new Date(t).toLocaleString('zh-CN')

const parseSymbols = (text: string): string[] => {
  return text
    .split(/[\s,;，；]+/)
    .map((s) => s.trim())
    .filter(Boolean)
}

const initializeModelSettings = async () => {
  try {
    const sortModelsByNewest = (configs: any[]) => {
      const getTimestamp = (config: any) => {
        const t = config.created_at || config.updated_at
        const ts = t ? new Date(t).getTime() : 0
        return Number.isNaN(ts) ? 0 : ts
      }
      return [...configs].sort((a, b) => getTimestamp(b) - getTimestamp(a))
    }
    const defaultModels = await configApi.getDefaultModels()
    modelSettings.value.quickAnalysisModel = defaultModels.quick_analysis_model
    modelSettings.value.deepAnalysisModel = defaultModels.deep_analysis_model

    const llmConfigs = await configApi.getLLMConfigs()
    availableModels.value = sortModelsByNewest(llmConfigs.filter((c: any) => c.enabled))
  } catch (e) {
    console.error('加载模型配置失败:', e)
  }
}

const loadGroups = async () => {
  loading.value = true
  try {
    const res = await scheduledAnalysisApi.listGroups()
    groups.value = res.data || []
  } catch (e: any) {
    ElMessage.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

const resetForm = () => {
  form.name = ''
  form.weekdays = [0, 1, 2, 3, 4]
  form.time = '09:30'
  form.symbolsText = ''
  form.depth = '3'
  form.analysts = [...DEFAULT_ANALYSTS]
  form.includeSentiment = true
  form.includeRisk = true
  form.language = 'zh-CN'
  modelSettings.value.quickAnalysisModel = 'qwen-turbo'
  modelSettings.value.deepAnalysisModel = 'qwen-max'
}

const openCreate = () => {
  editingId.value = ''
  resetForm()
  dialogVisible.value = true
}

const openEdit = (row: ScheduledGroup) => {
  editingId.value = row.group_id
  form.name = row.name
  form.weekdays = row.weekdays || []
  form.time = row.time || '09:30'
  form.symbolsText = (row.symbols || []).join('\n')
  const p = row.parameters || {}
  form.depth = String(p.research_depth || '3')
  form.analysts = convertAnalystIdsToNames(p.selected_analysts || [])
  form.includeSentiment = p.include_sentiment !== undefined ? p.include_sentiment : true
  form.includeRisk = p.include_risk !== undefined ? p.include_risk : true
  form.language = p.language || 'zh-CN'
  modelSettings.value.quickAnalysisModel = p.quick_analysis_model || 'qwen-turbo'
  modelSettings.value.deepAnalysisModel = p.deep_analysis_model || 'qwen-max'
  dialogVisible.value = true
}

const save = async () => {
  if (!form.name.trim()) {
    ElMessage.warning('请输入任务组名')
    return
  }
  if (!form.weekdays || form.weekdays.length === 0) {
    ElMessage.warning('请选择触发周期')
    return
  }
  if (!form.time) {
    ElMessage.warning('请选择触发时间')
    return
  }
  const symbols = parseSymbols(form.symbolsText)
  if (symbols.length === 0) {
    ElMessage.warning('请输入股票代码')
    return
  }

  const payload = {
    name: form.name.trim(),
    weekdays: form.weekdays,
    time: form.time,
    symbols,
    parameters: {
      research_depth: form.depth,
      selected_analysts: convertAnalystNamesToIds(form.analysts),
      include_sentiment: form.includeSentiment,
      include_risk: form.includeRisk,
      language: form.language,
      quick_analysis_model: modelSettings.value.quickAnalysisModel,
      deep_analysis_model: modelSettings.value.deepAnalysisModel
    }
  }

  saving.value = true
  try {
    if (editingId.value) {
      await scheduledAnalysisApi.updateGroup(editingId.value, payload)
    } else {
      await scheduledAnalysisApi.createGroup(payload)
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    await loadGroups()
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

const runNow = async (row: ScheduledGroup) => {
  try {
    await ElMessageBox.confirm(`确定立即执行任务组「${row.name}」吗？`, '立即执行', {
      confirmButtonText: '执行',
      cancelButtonText: '取消',
      type: 'info'
    })
    await scheduledAnalysisApi.runGroup(row.group_id)
    ElMessage.success('已提交执行，可前往任务中心查看进度')
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e?.message || '执行失败')
  }
}

const toggle = async (row: ScheduledGroup) => {
  try {
    await scheduledAnalysisApi.toggleGroup(row.group_id)
    ElMessage.success(row.enabled ? '已停用' : '已启用')
    await loadGroups()
  } catch (e: any) {
    ElMessage.error(e?.message || '操作失败')
  }
}

const remove = async (row: ScheduledGroup) => {
  try {
    await ElMessageBox.confirm(`确定删除任务组「${row.name}」吗？此操作不可恢复！`, '确认删除', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'error'
    })
    await scheduledAnalysisApi.deleteGroup(row.group_id)
    ElMessage.success('已删除')
    await loadGroups()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e?.message || '删除失败')
  }
}

const openEmailSettings = async () => {
  try {
    const res = await scheduledAnalysisApi.getEmailConfig()
    const cfg: EmailConfig = res.data || ({} as EmailConfig)
    emailForm.enabled = !!cfg.enabled
    emailForm.smtp_host = cfg.smtp_host || 'smtp.163.com'
    emailForm.smtp_port = cfg.smtp_port || 465
    emailForm.sender = cfg.sender || ''
    emailForm.auth_code = cfg.auth_code || ''
    emailForm.recipientsText = (cfg.recipients || []).join(', ')
    emailForm.attach_pdf = cfg.attach_pdf !== undefined ? cfg.attach_pdf : true
    emailDialogVisible.value = true
  } catch (e: any) {
    ElMessage.error(e?.message || '加载邮件配置失败')
  }
}

const saveEmailConfig = async () => {
  const recipients = emailForm.recipientsText
    .split(/[\s,;，；]+/)
    .map((s) => s.trim())
    .filter(Boolean)

  savingEmail.value = true
  try {
    await scheduledAnalysisApi.updateEmailConfig({
      enabled: emailForm.enabled,
      smtp_host: emailForm.smtp_host.trim(),
      smtp_port: emailForm.smtp_port,
      sender: emailForm.sender.trim(),
      auth_code: emailForm.auth_code.trim(),
      recipients,
      attach_pdf: emailForm.attach_pdf
    })
    ElMessage.success('邮件配置已保存')
    emailDialogVisible.value = false
  } catch (e: any) {
    ElMessage.error(e?.message || '保存邮件配置失败')
  } finally {
    savingEmail.value = false
  }
}

onMounted(async () => {
  await initializeModelSettings()
  loadGroups()
})
</script>

<style lang="scss" scoped>
.scheduled-analysis {
  .page-header {
    margin-bottom: 20px;
    .page-title {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 24px;
      font-weight: 600;
      margin: 0 0 8px 0;
    }
    .page-description {
      color: var(--el-text-color-regular);
      margin: 0;
    }
  }

  .list-header {
    display: flex;
    gap: 8px;
    margin-bottom: 14px;
  }

  .text-gray {
    color: var(--el-text-color-placeholder);
  }

  .analysts-group {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .options-row {
    display: flex;
    align-items: center;
    gap: 20px;
    .option-item {
      display: flex;
      align-items: center;
      gap: 8px;
      .option-name {
        font-size: 13px;
        color: var(--el-text-color-regular);
      }
    }
  }
}
</style>