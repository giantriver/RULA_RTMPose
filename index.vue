<template>
  <div class="analysis-page">
    <!-- 頁面標題與導航 -->
    <div class="page-header">
      <div class="header-content">
        <div class="title-section">
          <div class="title-icon">
            <i class="pi pi-list"></i>
          </div>
          <div>
            <h1>分析紀錄查詢</h1>
            <p>查看您最近的影片分析記錄</p>
          </div>
        </div>
        <div class="header-actions">
          <Button label="回到主頁" icon="pi pi-home" class="home-btn" @click="goHome" />
        </div>
      </div>
    </div>

    <div class="content-wrapper">

    <!-- 載入狀態 -->
    <div v-if="loading" class="loading-state">
      <ProgressSpinner />
      <span>載入分析記錄中...</span>
    </div>

    <!-- 無資料狀態 -->
    <div v-else-if="!loading && analyses.length === 0" class="empty-state">
      <i class="pi pi-file-o"></i>
      <h3>尚無分析記錄</h3>
      <p>您還沒有上傳任何影片進行分析</p>
    </div>

    <!-- 分析記錄表格 -->
    <div v-else class="table-card">
      <DataTable 
        :value="analyses" 
        :paginator="false"
        :rows="10"
        dataKey="id"
        :loading="loading"
        responsiveLayout="scroll"
        class="p-datatable-sm"
      >
        <!-- 調查日期 -->
        <Column field="survey_date" header="調查日期" :sortable="true" style="width: 140px; white-space: nowrap">
          <template #body="slotProps">
            <span class="text-sm">
              {{ slotProps.data.survey_date ? formatDate(slotProps.data.survey_date) : '-' }}
            </span>
          </template>
        </Column>

        <!-- 評估員 -->
        <Column field="assessor" header="評估員" :sortable="true" style="width: 120px">
          <template #body="slotProps">
            <span class="text-sm">{{ slotProps.data.assessor || '-' }}</span>
          </template>
        </Column>

        <!-- 單位 -->
        <Column field="organization" header="單位" :sortable="true" style="width: 150px">
          <template #body="slotProps">
            <span class="text-sm">{{ slotProps.data.organization || '-' }}</span>
          </template>
        </Column>

        <!-- 作業名稱 -->
        <Column field="task_name" header="作業名稱" :sortable="true" style="width: 200px">
          <template #body="slotProps">
            <span class="text-sm">{{ slotProps.data.task_name || '-' }}</span>
          </template>
        </Column>

        <!-- 檔案名稱 -->
        <Column field="original_filename" header="影片檔名" :sortable="true" style="width: 200px">
          <template #body="slotProps">
            <span class="text-sm text-blue-600 truncate block" :title="slotProps.data.original_filename">
              {{ slotProps.data.original_filename }}
            </span>
          </template>
        </Column>

        <!-- 上傳時間 -->
        <Column field="created_at" header="上傳時間" :sortable="true" style="width: 150px">
          <template #body="slotProps">
            <span class="text-sm text-gray-600">
              {{ formatDateTime(slotProps.data.created_at) }}
            </span>
          </template>
        </Column>

        <!-- 狀態 -->
        <Column field="status" header="狀態" style="width: 120px">
          <template #body="slotProps">
            <Tag :severity="statusSeverity(slotProps.data.status)" :value="statusLabel(slotProps.data.status)" />
          </template>
        </Column>

        <!-- 操作列 -->
        <Column header="操作" style="width: 120px">
          <template #body="slotProps">
            <div class="flex gap-1">
              <!-- 查看結果 -->
              <Button
                icon="pi pi-eye"
                size="small"
                severity="info"
                text
                rounded
                :disabled="slotProps.data.status !== 'completed'"
                @click="viewAnalysis(slotProps.data.id)"
                v-tooltip.top="'查看分析結果'"
              />
              <!-- 下載按鈕 -->
              <Button
                icon="pi pi-download"
                size="small"
                severity="success"
                text
                rounded
                :disabled="!slotProps.data.has_csv || downloading === slotProps.data.id"
                :loading="downloading === slotProps.data.id"
                @click="downloadCsv(slotProps.data.id)"
                v-tooltip.top="'下載 CSV 報告'"
              />
            </div>
          </template>
        </Column>
      </DataTable>
    </div>

    <!-- 錯誤訊息 -->
    <div v-if="error" class="error-message">
      <i class="pi pi-exclamation-triangle"></i>
      <span>{{ error }}</span>
    </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useToast } from 'primevue/usetoast'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const toast = useToast()
const user = useUserStore()

const loading = ref(false)
const downloading = ref(null)
const analyses = ref([])
const error = ref('')

// 載入分析記錄
const loadAnalyses = async () => {
  try {
    loading.value = true
    error.value = ''
    
    const response = await user.apiFetchWithRetry('video/list')
    
    if (response.status === 'success') {
      analyses.value = response.data || []
    } else {
      throw new Error(response.message || '載入失敗')
    }
  } catch (err) {
    console.error('Load analyses error:', err)
    error.value = err.message || '載入分析記錄失敗'
    
    if (err.message === 'Token refresh failed') {
      toast.add({
        severity: 'error',
        summary: '登入已過期',
        detail: '請重新登入',
        life: 3000
      })
      setTimeout(() => {
        navigateTo('/login')
      }, 1000)
    }
  } finally {
    loading.value = false
  }
}

// 下載 CSV 檔案
const downloadCsv = async (analysisId) => {
  try {
    downloading.value = analysisId
    
    // ✅ 修復：使用正確的方式獲取 API base URL
    const { public: { apiBase } } = useRuntimeConfig()
    const response = await fetch(`${apiBase}/video/download/${analysisId}`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${user.token}`
      }
    })

    if (!response.ok) {
      const errorText = await response.text()
      try {
        const errorData = JSON.parse(errorText)
        throw new Error(errorData.message || '下載失敗')
      } catch {
        throw new Error(`下載失敗 (${response.status}): ${response.statusText}`)
      }
    }

    // 獲取檔案名稱
    const contentDisposition = response.headers.get('content-disposition')
    let filename = `analysis_${analysisId}.csv`
    if (contentDisposition) {
      const filenameMatch = contentDisposition.match(/filename="?([^"]+)"?/)
      if (filenameMatch) {
        filename = filenameMatch[1]
      }
    }

    // 創建下載
    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    window.URL.revokeObjectURL(url)
    document.body.removeChild(a)

    toast.add({
      severity: 'success',
      summary: '下載成功',
      detail: `CSV 報告已下載`,
      life: 3000
    })
  } catch (err) {
    console.error('Download error:', err)
    toast.add({
      severity: 'error',
      summary: '下載失敗',
      detail: err.message || '無法下載 CSV 檔案',
      life: 4000
    })
  } finally {
    downloading.value = null
  }
}

// 導航方法
const goHome = () => {
  router.push('/dashboard')
}

const viewAnalysis = (id) => {
  router.push(`/analysis/history/${id}`)
}

// 狀態標籤與顏色
const statusLabel = (status) => {
  const map = {
    pending:    '等待中',
    processing: '分析中',
    completed:  '已完成',
    failed:     '失敗',
    error:      '錯誤',
  }
  return map[status] ?? status
}

const statusSeverity = (status) => {
  const map = {
    pending:    'secondary',
    processing: 'info',
    completed:  'success',
    failed:     'danger',
    error:      'danger',
  }
  return map[status] ?? 'secondary'
}

// 格式化日期
const formatDate = (dateString) => {
  if (!dateString) return '-'
  return new Date(dateString).toLocaleDateString('zh-TW')
}

const formatDateTime = (dateString) => {
  if (!dateString) return '-'
  return new Date(dateString).toLocaleString('zh-TW', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

// 頁面載入時取得資料
onMounted(() => {
  loadAnalyses()
})
</script>

<style scoped>
.analysis-page {
  min-height: 100vh;
  background-color: #fafafa;
  background-image: url('@/assets/HFE_Background.jpg');
  background-size: cover;
  background-position: center;
  background-attachment: fixed;
  padding: 2rem;
  position: relative;
}

/* 疊加半透明遮罩，統一新風格 */
.analysis-page::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, rgba(15, 23, 42, 0.85) 0%, rgba(6, 78, 59, 0.75) 100%);
  backdrop-filter: blur(5px);
  z-index: 0;
}

/* 確保內容在遮罩之上 */
.page-header, .content-wrapper, .error-message {
  position: relative;
  z-index: 10;
}

.page-header {
  margin-bottom: 2rem;
  animation: fadeInDown 0.6s ease-out;
}

@keyframes fadeInDown {
  from {
    opacity: 0;
    transform: translateY(-20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: rgba(255, 255, 255, 0.95);
  padding: 1.5rem;
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
}

.title-section {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.title-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  /* 換成祖母綠漸變色 */
  background: linear-gradient(135deg, #10b981, #059669);
  border-radius: 12px;
  color: white;
  font-size: 1.25rem;
  box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);
}

.title-section h1 {
  margin: 0;
}

.home-btn:hover {
  background: linear-gradient(135deg, #059669, #047857);
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(16, 185, 129, 0.3);
}

.home-btn {
  background: linear-gradient(135deg, #3b82f6, #2563eb);
  border: none;
  border-radius: 8px;
  transition: all 0.3s;
}

.home-btn:hover {
  background: linear-gradient(135deg, #2563eb, #1e40af);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4);
}

.content-wrapper {
  animation: fadeInUp 0.8s ease-out;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.loading-state {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 1rem;
  padding: 4rem;
  background: rgba(255, 255, 255, 0.95);
  border-radius: 16px;
  color: #64748b;
  font-size: 1rem;
}

.empty-state {
  text-align: center;
  padding: 4rem 2rem;
  background: rgba(255, 255, 255, 0.95);
  border-radius: 16px;
}

.empty-state i {
  font-size: 4rem;
  color: #cbd5e1;
  margin-bottom: 1rem;
}

.empty-state h3 {
  font-size: 1.125rem;
  font-weight: 600;
  color: #0f172a;
  margin: 0 0 0.5rem 0;
}

.empty-state p {
  font-size: 0.9375rem;
  color: #64748b;
  margin: 0;
}

.table-card {
  background: rgba(255, 255, 255, 0.95);
  border-radius: 16px;
  overflow: hidden;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.error-message {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-top: 1rem;
  padding: 1rem 1.25rem;
  background: rgba(254, 242, 242, 0.95);
  border-radius: 12px;
  border-left: 4px solid #ef4444;
  color: #991b1b;
}

.error-message i {
  font-size: 1.25rem;
}

:deep(.p-datatable) {
  border-radius: 16px;
}

:deep(.p-datatable .p-datatable-thead > tr > th) {
  background: #f8fafc;
  font-weight: 600;
  color: #0f172a;
  border: none;
  padding: 1rem;
  border-bottom: 2px solid #e2e8f0;
  white-space: nowrap;
}

:deep(.p-datatable .p-datatable-tbody > tr) {
  transition: all 0.2s;
}

:deep(.p-datatable .p-datatable-tbody > tr:hover) {
  background-color: #f8fafc;
  transform: scale(1.01);
}

:deep(.p-datatable .p-datatable-tbody > tr > td) {
  padding: 0.875rem 1rem;
  border-bottom: 1px solid #f1f5f9;
}

:deep(.p-button.p-button-text) {
  padding: 0.375rem;
}

:deep(.p-button-success) {
  color: #10b981;
}

:deep(.p-button-success:hover) {
  color: #059669;
  background: rgba(16, 185, 129, 0.1);
}

@media (max-width: 768px) {
  .analysis-page {
    padding: 1rem;
  }

  .header-content {
    flex-direction: column;
    gap: 1rem;
    align-items: flex-start;
  }

  .title-section h1 {
    font-size: 1.25rem;
  }
}
</style>