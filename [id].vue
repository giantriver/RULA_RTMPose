<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute, useRouter, useRuntimeConfig } from '#imports'
import { Chart, registerables } from 'chart.js'
import type { Point } from 'chart.js'
import RulaParamsForm from '~/components/RulaParamsForm.vue'
import RulaCounselor from '~/components/RulaCounselor.vue'

Chart.register(...registerables)

// ---- i18n ----
const { t, locale } = useLocale()

// ---- 路由 /analysis/:id ----
const route = useRoute()
const router = useRouter()
const analysisId = Number(route.params.id)

// ---- 頝舐 /analysis/:id ----
const { public: { apiBase } } = useRuntimeConfig()
const VIDEO_API = `${apiBase}/video`
// 之`${API_BASE}/...` 部 `${VIDEO_API}/...`

// ---- Helper to get auth headers with JWT token ----
const getAuthHeaders = () => {
  const token = useCookie<string | null>('hfe_token')
  const headers: Record<string, string> = {}
  if (token.value) {
    headers['Authorization'] = `Bearer ${token.value}`
  }
  return headers
}

// ---- 頝舐 /analysis/:id ----
const processing = ref(true)
const error = ref('')
const uploadProgress = ref(0)
const uploadStatus = ref('..')
const currentFrame = ref(0)
const totalFrames = ref(0)
const results = ref<any | null>(null)
const cancelSubmitting = ref(false)

type UploadVideoInfo = {
  surveyDate: string
  assessor: string
  organization: string
  taskName: string
}

const statusVideoInfo = ref<UploadVideoInfo>({
  surveyDate: '',
  assessor: '',
  organization: '',
  taskName: '',
})

const normalizeText = (value: unknown): string => {
  if (value === null || value === undefined) return ''
  const text = String(value).trim()
  return text === 'NULL' ? '' : text
}

const syncVideoInfoFromPayload = (payload: any) => {
  if (!payload || typeof payload !== 'object') return

  const surveyDate = normalizeText(payload?.survey_date)
  const assessor = normalizeText(payload?.assessor)
  const organization = normalizeText(payload?.organization)
  const taskName = normalizeText(payload?.task_name)

  statusVideoInfo.value = {
    surveyDate: surveyDate || statusVideoInfo.value.surveyDate,
    assessor: assessor || statusVideoInfo.value.assessor,
    organization: organization || statusVideoInfo.value.organization,
    taskName: taskName || statusVideoInfo.value.taskName,
  }
}

const formatSurveyDate = (value: string): string => {
  if (!value) return '-'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleDateString('zh-TW')
}

const displayVideoInfo = computed(() => {
  const source = (results.value as any) || {}

  const surveyDate = normalizeText(source?.survey_date) || statusVideoInfo.value.surveyDate
  const assessor = normalizeText(source?.assessor) || statusVideoInfo.value.assessor
  const organization = normalizeText(source?.organization) || statusVideoInfo.value.organization
  const taskName = normalizeText(source?.task_name) || statusVideoInfo.value.taskName

  return {
    surveyDate: formatSurveyDate(surveyDate),
    assessor: assessor || '-',
    organization: organization || '-',
    taskName: taskName || '-',
  }
})

const counselingData = ref<{ score_explanation?: string; recommendations?: string; risk_level?: string; max_score?: number } | null>(null)

const onCounselorLoaded = (data: any) => {
  if (data?.score_explanation || data?.recommendations) {
    counselingData.value = {
      score_explanation: data.score_explanation || '',
      recommendations: data.recommendations || '',
      risk_level: data.risk_level || '',
      max_score: data.max_score,
    }
  }
}

const onCounselorError = (err: any) => {
  console.error('Counselor error:', err)
}

const extractSummaryFromMarkdown = (src: string): string => {
  if (!src) return ''
  const normalized = src
    .replace(/\\r\\n/g, '\n').replace(/\\+n/g, '\n').replace(/\r\n/g, '\n')
  const lines = normalized.split('\n')
  let inFirst = false
  const body: string[] = []
  for (const line of lines) {
    const trimmed = line.trim()
    if (trimmed.startsWith('## ') || trimmed.startsWith('# ')) {
      if (inFirst) break
      inFirst = true
      continue
    }
    if (inFirst) body.push(line)
  }
  const text = inFirst ? body.join('\n').trim() : lines.slice(0, 8).join('\n').trim()
  return text
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/\*(.*?)\*/g, '$1')
    .replace(/^[-*+]\s+/gm, '??')
    .replace(/^#+\s+/gm, '')
    .replace(/`([^`]+)`/g, '$1')
    .trim()
}

// ---- 頝舐 /analysis/:id ----
const originalVideoUrl = ref('')
const videoElement = ref<HTMLVideoElement | null>(null)
const canvasElement = ref<HTMLCanvasElement | null>(null)
const showPoseOverlay = ref(true)
const currentVideoTime = ref(0)
const videoDuration = ref(0)
const isPlaying = ref(false)

// ---- 頝舐 /analysis/:id ----
const currentFrameIndex = ref(0)
const frameInput = ref('1')
let sampledPlaybackInterval: ReturnType<typeof setInterval> | null = null
const sampledSpeedOptions = [0.5, 1, 2] as const
const selectedSampledSpeed = ref<0.5 | 1 | 2>(1)

// ---- 頝舐 /analysis/:id ----
let videoResizeObserver: ResizeObserver | null = null

const setupVideoResizeObserver = () => {
  const video = videoElement.value
  if (!video || typeof ResizeObserver === 'undefined') return
  videoResizeObserver = new ResizeObserver(() => {
    if (showPoseOverlay.value) drawPoseOverlay()
  })
  videoResizeObserver.observe(video)
}

const teardownVideoResizeObserver = () => {
  videoResizeObserver?.disconnect()
  videoResizeObserver = null
}

// ---- 頝舐 /analysis/:id ----
const pieChartRef = ref<HTMLCanvasElement | null>(null)
const barChartRef = ref<HTMLCanvasElement | null>(null)
const lineChartRef = ref<HTMLCanvasElement | null>(null)
const isPrintMode = ref(false)

// 印專用表（matplotlib 
const printLineChartUrl = ref('')
const printPieChartUrl = ref('')
const printBarChartUrl = ref('')

let pieChart: Chart | null = null
let barChart: Chart | null = null
let lineChart: Chart<"line", (Point | null)[], unknown> | null = null

const getCurrentMarkerX = (): number | null => {
  const frame = getCurrentFrameData()
  if (!frame) return null

  const ts = frame?.timestamp
  if (typeof ts === 'number' && Number.isFinite(ts)) {
    return Number(ts.toFixed(2))
  }

  return currentFrameIndex.value
}

const currentFrameMarkerPlugin = {
  id: 'currentFrameMarker',
  afterDatasetsDraw(chart: Chart) {
    const markerXValue = getCurrentMarkerX()
    if (markerXValue === null) return

    const xScale = (chart.scales as any)?.x
    const chartArea = chart.chartArea
    if (!xScale || !chartArea) return

    const rawX = xScale.getPixelForValue(markerXValue)
    if (!Number.isFinite(rawX)) return

    const x = Math.min(Math.max(rawX, chartArea.left), chartArea.right)
    const ctx = chart.ctx

    ctx.save()
    ctx.strokeStyle = '#dc2626'
    ctx.lineWidth = 2
    ctx.setLineDash([5, 4])
    ctx.beginPath()
    ctx.moveTo(x, chartArea.top)
    ctx.lineTo(x, chartArea.bottom)
    ctx.stroke()
    ctx.setLineDash([])

    ctx.fillStyle = '#dc2626'
    ctx.font = '12px Arial'
    ctx.textBaseline = 'top'
    ctx.textAlign = 'left'
    const labelX = Math.min(x + 4, chartArea.right - 40)
    ctx.fillText('幀', labelX, chartArea.top + 4)
    ctx.restore()
  }
}


// ========= 別輔助 =========
type PoseLandmark = { x: number; y: number; z?: number; visibility?: number }
type TrendPoint = { x: number; y: number | null; idx: number; hasScore: boolean }
type NativeDrawData = [number, number, number?][]
type RiskImage = { rank: number; filename: string; frame: number; time_sec: number; rula_score: number }

type FrameRow = {
  frame?: number
  timestamp?: number
  best_score?: number | string | null
  pose_landmarks?: PoseLandmark[]
  pose_world_landmarks?: PoseLandmark[]
  image_landmarks?: NativeDrawData | null
  native_draw_data?: NativeDrawData | null
  pose_detected?: boolean
  left_upper_arm_angle?: number | string | null
  left_lower_arm_angle?: number | string | null
  left_wrist_angle?: number | string | null
  left_neck_angle?: number | string | null
  left_trunk_angle?: number | string | null
  right_upper_arm_angle?: number | string | null
  right_lower_arm_angle?: number | string | null
  right_wrist_angle?: number | string | null
  right_neck_angle?: number | string | null
  right_trunk_angle?: number | string | null
  posture_score_a?: number | string | null
  posture_score_b?: number | string | null
  table_c_score?: number | string | null
  left_posture_score_a?: number | string | null
  left_posture_score_b?: number | string | null
  left_table_c_score?: number | string | null
  right_posture_score_a?: number | string | null
  right_posture_score_b?: number | string | null
  right_table_c_score?: number | string | null
}

// ========= 輪詢=========
let pollTimer: ReturnType<typeof setTimeout> | null = null
let sse: EventSource | null = null
const usingSse = ref(false)
let sseWatchdogTimer: ReturnType<typeof setInterval> | null = null
let lastSseEventAt = 0

const getAnalysisTimeText = (): string => {
  const sec = Number((results.value as any)?.statistics?.analysis_time ?? (results.value as any)?.results?.analysis_time)
  if (Number.isFinite(sec) && sec >= 0) {
    return `${sec.toFixed(1)}s`
  }
  return '-'
}
let pollRetryCount = 0

const FIRST_POLL_DELAY_MS = 300
const RETRY_POLL_DELAY_MS = 1500
const SLOW_POLL_MS = 1800
const FAST_POLL_MS = 1000

const getNextPollDelay = (progress: number) => {
  // 完快更平維較但暢輪詢
  if (progress >= 90) return FAST_POLL_MS
  if (progress >= 30) return 1200
  return SLOW_POLL_MS
}

const stopSse = () => {
  if (sse) {
    sse.close()
    sse = null
  }
  if (sseWatchdogTimer) {
    clearInterval(sseWatchdogTimer)
    sseWatchdogTimer = null
  }
  usingSse.value = false
}

const startSseWatchdog = () => {
  if (sseWatchdogTimer) {
    clearInterval(sseWatchdogTimer)
    sseWatchdogTimer = null
  }
  sseWatchdogTimer = setInterval(() => {
    if (!usingSse.value || !processing.value) return
    const staleFor = Date.now() - lastSseEventAt
    if (staleFor > 7000) {
      stopSse()
      uploadStatus.value = t('analysisResult.analyzing')
      startPolling()
    }
  }, 2000)
}

const applyStatusUpdate = async (payload: any) => {
  syncVideoInfoFromPayload(payload)

  const s: string | undefined = payload?.status
  const p = Number(payload?.progress ?? 0)
  const cf = Number(payload?.current_frame ?? 0)
  const tf = Number(payload?.total_frames ?? 0)

  if (Number.isFinite(cf) && cf >= 0) currentFrame.value = Math.floor(cf)
  if (Number.isFinite(tf) && tf > 0) totalFrames.value = Math.floor(tf)

  uploadProgress.value = Math.max(10, Math.min(100, isFinite(p) ? p : 0))
  uploadStatus.value =
    s === 'completed' ? t('analysisResult.analysisCompleted') :
    s === 'cancelled' ? t('analysisResult.analysisCancelled') :
    s === 'failed' ? t('analysisResult.analysisFailed') :
    t('analysisResult.analyzing')

  if (s === 'completed') {
    const resp = await fetch(`${VIDEO_API}/status/${analysisId}`, {
      credentials: 'include',
      headers: getAuthHeaders()
    })
    if (resp.ok) {
      const data = await resp.json()
      results.value = data?.data ?? null
      syncVideoInfoFromPayload(data?.data)
    }

    processing.value = false
    uploadProgress.value = 100
    const finalTotal = Number((results.value as any)?.results?.total_frames ?? (results.value as any)?.statistics?.total_frames ?? totalFrames.value)
    if (Number.isFinite(finalTotal) && finalTotal > 0) totalFrames.value = Math.floor(finalTotal)
    if (totalFrames.value > 0) currentFrame.value = totalFrames.value
    setupVideoTimeTracking()

    await nextTick()
    setTimeout(() => {
      createPieChart()
      createBarChart()
      createLineChart()
      if (showPoseOverlay.value) drawPoseOverlay()
    }, 80)

    stopSse()
    stopPolling()
    return
  }

  if (s === 'failed' || s === 'error') {
    processing.value = false
    error.value = payload?.error_message || t('analysisResult.analysisFailed')
    stopSse()
    stopPolling()
    return
  }

  if (s === 'cancelled') {
    processing.value = false
    error.value = t('analysisResult.analysisCancelled')
    stopSse()
    stopPolling()
  }
}

const startSse = () => {
  stopSse()
  const token = useCookie<string | null>('hfe_token')
  if (!token.value) return false

  const url = `${VIDEO_API}/progress_stream/${analysisId}?token=${encodeURIComponent(token.value)}`
  sse = new EventSource(url)
  usingSse.value = true
  lastSseEventAt = Date.now()
  startSseWatchdog()

  sse.addEventListener('progress', async (evt: MessageEvent) => {
    try {
      const payload = JSON.parse(evt.data)
      lastSseEventAt = Date.now()
      pollRetryCount = 0
      error.value = ''
      await applyStatusUpdate(payload)
    } catch {
      // ignore malformed event
    }
  })

  sse.onerror = () => {
    stopSse()
    startPolling()
  }

  return true
}

const startProgressUpdates = () => {
  stopPolling()
  const started = startSse()
  if (!started) {
    startPolling()
  }
}

const fetchInitialVideoInfo = async () => {
  try {
    const resp = await fetch(`${VIDEO_API}/status/${analysisId}`, {
      credentials: 'include',
      headers: getAuthHeaders()
    })
    if (!resp.ok) return

    const data = await resp.json()
    syncVideoInfoFromPayload(data?.data)
  } catch {
    // ignore metadata preload failure; regular polling/SSE updates will continue
  }
}

const startPolling = () => {
  stopPolling()
  usingSse.value = false
  
  pollRetryCount = 0

  const run = async () => {
    try {
      const resp = await fetch(`${VIDEO_API}/status/${analysisId}`, {
        credentials: 'include',
        headers: getAuthHeaders()
      })
      if (!resp.ok) throw new Error(t('analysisResult.statusQueryFailed'))
      const data = await resp.json()

      pollRetryCount = 0
      error.value = ''

      await applyStatusUpdate(data?.data || {})
      const s: string | undefined = data?.data?.status
      if (!(s === 'completed' || s === 'cancelled' || s === 'failed' || s === 'error')) {
        // processing / queued 繼輪詢
        pollTimer = setTimeout(run, getNextPollDelay(uploadProgress.value))
      }
    } catch (e: any) {
      pollRetryCount += 1
      const message = e?.data?.message || e?.message || String(e)

      if (pollRetryCount >= 3) {
        error.value = message
        uploadStatus.value = t('analysisResult.statusQueryFailed')
        processing.value = false
        stopPolling()
      } else {
        processing.value = true
        uploadStatus.value = `${t('analysisResult.statusQueryRetrying')} (${pollRetryCount}/3)`
        error.value = ''
        pollTimer = setTimeout(run, RETRY_POLL_DELAY_MS)
      }
    }
  }

  pollTimer = setTimeout(run, FIRST_POLL_DELAY_MS)
}

const stopPolling = () => {
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
}

const cancelAnalysisAndBackToForm = async () => {
  if (cancelSubmitting.value) return
  if (!window.confirm(t('analysisResult.cancelConfirm'))) return

  cancelSubmitting.value = true
  uploadStatus.value = t('analysisResult.cancelling2')

  try {
    const resp = await fetch(`${VIDEO_API}/cancel/${analysisId}`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeaders()
      },
      body: JSON.stringify({ cleanup: true })
    })

    if (!resp.ok) {
      const raw = await resp.text()
      try {
        const parsed = JSON.parse(raw)
        throw new Error(parsed?.message || raw || t('analysisResult.cancelFailed'))
      } catch {
        throw new Error(raw || t('analysisResult.cancelFailed'))
      }
    }

    stopSse()
    stopPolling()
    processing.value = false
    await router.push('/dashboard?openUpload=1&fromCancel=1')
  } catch (e: any) {
    error.value = e?.message || t('analysisResult.cancelFailed')
  } finally {
    cancelSubmitting.value = false
  }
}

// ========= 快速算RULA 數=========
const showRescore = ref(false)
const rescoreSubmitting = ref(false)
const showFrameMetricsDialog = ref(false)

// 比照 dashboard.vue 設值不frame_interval，快算採
const rescoreForm = ref({
  wrist_twist: 1 as 1|2,
  legs: 1 as 1|2,
  muscle_use_a: 0 as 0|1,
  muscle_use_b: 0 as 0|1,
  force_load_a: 0 as 0|1|2|3,
  force_load_b: 0 as 0|1|2|3,
})

const loadOptions = computed<{ label: string; value: 0|1|2|3 }[]>(() => [
  { label: t('rulaParams.loadOptions.0'), value: 0 },
  { label: t('rulaParams.loadOptions.1'), value: 1 },
  { label: t('rulaParams.loadOptions.2'), value: 2 },
  { label: t('rulaParams.loadOptions.3'), value: 3 },
])




// /status 帶params_json 填（就沒就設
const prefillParamsFromStatus = () => {
  const p = (results.value as any)?.params_json
  if (p && typeof p === 'object') {
    rescoreForm.value.wrist_twist = (Number(p.wrist_twist) === 2 ? 2 : 1)
    rescoreForm.value.legs        = (Number(p.legs) === 2 ? 2 : 1)
    rescoreForm.value.muscle_use_a = Number(p.muscle_use_a) ? 1 : 0
    rescoreForm.value.muscle_use_b = Number(p.muscle_use_b) ? 1 : 0
    rescoreForm.value.force_load_a = [0,1,2,3].includes(Number(p.force_load_a)) ? Number(p.force_load_a) as 0|1|2|3 : 0
    rescoreForm.value.force_load_b = [0,1,2,3].includes(Number(p.force_load_b)) ? Number(p.force_load_b) as 0|1|2|3 : 0
  }
}

const openRescore = () => {
  prefillParamsFromStatus()
  showRescore.value = true
}

const openFrameMetricsDialog = () => {
  showFrameMetricsDialog.value = true
}

const doRescore = async () => {
  if (rescoreSubmitting.value) return
  try {
    rescoreSubmitting.value = true
    error.value = ''
    processing.value = true
    uploadStatus.value = t('analysisResult.rescoring')
    uploadProgress.value = 10

    // 叫後端快速算不改 frame_interval
    const resp = await fetch(`${VIDEO_API}/rescore/${analysisId}`, {
      method: 'POST',
      credentials: 'include',  // ??Send cookies
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeaders()  // ??Add JWT token
      },
      body: JSON.stringify(rescoreForm.value)
    })
    if (!resp.ok) {
      const respText = await resp.text()
      throw new Error(respText || t('analysisResult.rescoreApiFailed'))
    }

    // 彈並既輪
    showRescore.value = false
    startProgressUpdates()
  } catch (e: any) {
    error.value = e?.message || String(e)
    processing.value = false
  } finally {
    rescoreSubmitting.value = false
  }
}

// ========= 影骨=========
const getSafeRulaScore = (frame: FrameRow | null | undefined): number | null => {
  const s = frame?.best_score as any
  if (s === null || s === undefined || s === 'NULL') return null
  const n = Number(s)
  return Number.isFinite(n) ? n : null
}

const getCurrentFrames = (): FrameRow[] => {
  return (results.value?.analysis_results as FrameRow[]) ?? []
}

const getSamplingIntervalN = (): number => {
  const raw = Number((results.value as any)?.params_json?.frame_interval)
  if (Number.isFinite(raw) && raw >= 1) return Math.floor(raw)
  return 10
}

const getMedian = (values: number[]): number | null => {
  if (!values.length) return null
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  if (sorted.length % 2 === 0) {
    return (sorted[mid - 1]! + sorted[mid]!) / 2
  }
  return sorted[mid]!
}

const estimatedVideoFps = computed<number | null>(() => {
  const frames = getCurrentFrames()
  if (frames.length < 2) return null

  const deltas: number[] = []
  for (let i = 1; i < frames.length; i++) {
    const prevTs = Number(frames[i - 1]?.timestamp)
    const currTs = Number(frames[i]?.timestamp)
    if (!Number.isFinite(prevTs) || !Number.isFinite(currTs)) continue
    const dt = currTs - prevTs
    if (dt > 0) deltas.push(dt)
  }

  const medianDeltaSec = getMedian(deltas)
  if (!medianDeltaSec || medianDeltaSec <= 0) return null

  const n = getSamplingIntervalN()
  const fps = n / medianDeltaSec
  return Number.isFinite(fps) && fps > 0 ? fps : null
})

const sourceVideoFps = computed<number | null>(() => {
  const total = Number((results.value as any)?.results?.total_frames ?? (results.value as any)?.statistics?.total_frames)
  if (!Number.isFinite(total) || total <= 0) return null

  const mediaDuration = Number(videoElement.value?.duration)
  const trackedDuration = Number(videoDuration.value)
  const statsDuration = Number((results.value as any)?.statistics?.duration_sec)

  const duration =
    (Number.isFinite(mediaDuration) && mediaDuration > 0 ? mediaDuration : null) ??
    (Number.isFinite(trackedDuration) && trackedDuration > 0 ? trackedDuration : null) ??
    (Number.isFinite(statsDuration) && statsDuration > 0 ? statsDuration : null)

  if (!duration || duration <= 0) return null

  const fps = total / duration
  return Number.isFinite(fps) && fps > 0 ? fps : null
})

const effectiveVideoFps = computed<number | null>(() => {
  // Prefer source-media FPS (total_frames / duration) to distinguish 30fps vs 60fps videos.
  return sourceVideoFps.value ?? estimatedVideoFps.value
})

const sampledRealtimeStepMs = computed(() => {
  const n = getSamplingIntervalN()
  const fps = effectiveVideoFps.value

  if (fps && fps > 0) {
    return (n / fps) * 1000
  }

  const frames = getCurrentFrames()
  const deltas: number[] = []
  for (let i = 1; i < frames.length; i++) {
    const prevTs = Number(frames[i - 1]?.timestamp)
    const currTs = Number(frames[i]?.timestamp)
    if (!Number.isFinite(prevTs) || !Number.isFinite(currTs)) continue
    const dt = currTs - prevTs
    if (dt > 0) deltas.push(dt)
  }
  const medianDeltaSec = getMedian(deltas)
  if (medianDeltaSec && medianDeltaSec > 0) return medianDeltaSec * 1000

  return 1000
})

const sampledPlaybackTickMs = computed(() => {
  const speed = Number(selectedSampledSpeed.value)
  const baseMs = sampledRealtimeStepMs.value
  const safeSpeed = Number.isFinite(speed) && speed > 0 ? speed : 1
  return Math.max(16, Math.round(baseMs / safeSpeed))
})

const sampledRealtimeHintText = computed(() => {
  const n = getSamplingIntervalN()
  const baseMs = sampledRealtimeStepMs.value
  const fps = effectiveVideoFps.value
  const fpsText = fps ? fps.toFixed(2) : 'unknown'
  const fpsSource = sourceVideoFps.value ? 'source-media' : (estimatedVideoFps.value ? 'timestamp-estimated' : 'fallback')
  const half = (baseMs / 0.5 / 1000).toFixed(2)
  const one = (baseMs / 1 / 1000).toFixed(2)
  const two = (baseMs / 2 / 1000).toFixed(2)
  return t('analysisResult.frameIntervalHint').replace('{half}', half).replace('{one}', one).replace('{two}', two)
})

const getCurrentFrameData = (): FrameRow | null => {
  const frames = getCurrentFrames()
  if (!frames.length) return null
  const idx = Math.min(currentFrameIndex.value, frames.length - 1)
  return frames[idx] ?? null
}

const maxScoreFrameIndexes = computed<number[]>(() => {
  const frames = getCurrentFrames()
  if (!frames.length) return []

  let maxScore = Number.NEGATIVE_INFINITY
  const scored: Array<{ idx: number; score: number }> = []

  for (let i = 0; i < frames.length; i++) {
    const score = getSafeRulaScore(frames[i])
    if (score === null) continue
    scored.push({ idx: i, score })
    if (score > maxScore) maxScore = score
  }

  if (!scored.length || !Number.isFinite(maxScore)) return []

  const EPSILON = 1e-6
  return scored
    .filter((item) => Math.abs(item.score - maxScore) <= EPSILON)
    .map((item) => item.idx)
})

const maxScoreFrameIndicator = computed(() => {
  const indexes = maxScoreFrameIndexes.value
  const total = indexes.length
  if (!total) return { current: 0, total: 0 }

  const foundPos = indexes.findIndex((idx) => idx === currentFrameIndex.value)
  return {
    current: foundPos >= 0 ? foundPos + 1 : 0,
    total,
  }
})

const maxScoreCycleButtonLabel = computed(() => {
  const indicator = maxScoreFrameIndicator.value
  return `${t('analysisResult.maxScoreFrame')} ${indicator.current}/${indicator.total}`
})

const getCurrentActualFrameNumber = (): number => {
  const f = getCurrentFrameData()
  return f?.frame ?? 0
}

// 
const connections: ReadonlyArray<readonly [number, number]> = [
  // Face
  [0,1],[1,2],[2,3],[3,7],[0,4],[4,5],[5,6],[6,8],
  // Torso
  [9,10],[11,12],[11,13],[13,15],[15,17],[15,19],[15,21],
  [12,14],[14,16],[16,18],[16,20],[16,22],[11,23],[12,24],[23,24],
  // Left arm
  [11,13],[13,15],
  // Right arm
  [12,14],[14,16],
  // Left leg
  [23,25],[25,27],[27,29],[29,31],[27,31],
  // Right leg
  [24,26],[26,28],[28,30],[30,32],[28,32],
] as const

const drawPoseLandmarks = (
  ctx: CanvasRenderingContext2D,
  landmarks: PoseLandmark[],
  width: number,
  height: number,
  isLastFrame = false
) => {
  if (!landmarks?.length) return

  const strokeColor = isLastFrame ? '#FF00FF' : '#00FF00'
  const pointColor = isLastFrame ? '#8A2BE2' : '#FF0000'
  const lineWidth = isLastFrame ? 4 : 3

  ctx.strokeStyle = strokeColor
  ctx.lineWidth = lineWidth
  ctx.beginPath()

  for (const [start, end] of connections) {
    const A = landmarks[start]
    const B = landmarks[end]
    const visA = A?.visibility ?? 0
    const visB = B?.visibility ?? 0
    if (A && B && visA > 0.5 && visB > 0.5) {
      ctx.moveTo(A.x * width, A.y * height)
      ctx.lineTo(B.x * width, B.y * height)
    }
  }
  ctx.stroke()

  ctx.fillStyle = pointColor
  const keyPoints = new Set([11,12,13,14,15,16,23,24,25,26,27,28])

  landmarks.forEach((lm, i) => {
    const vis = lm?.visibility ?? 0
    if (vis > 0.5) {
      const x = lm.x * width
      const y = lm.y * height
      ctx.beginPath()
      ctx.arc(x, y, isLastFrame ? 5 : 4, 0, Math.PI * 2)
      ctx.fill()

      if (keyPoints.has(i)) {
        ctx.fillStyle = '#FFFFFF'
        ctx.font = isLastFrame ? '14px Arial' : '12px Arial'
        ctx.fillText(String(i), x + 5, y - 5)
        ctx.fillStyle = pointColor
      }
    }
  })
}

const drawNativePoseData = (
  ctx: CanvasRenderingContext2D,
  nativeData: NativeDrawData,
  width: number,
  height: number
) => {
  if (!Array.isArray(nativeData) || !nativeData.length) return

  const parsed = nativeData.map((lm) => ({
    x: Number(lm?.[0] ?? 0),
    y: Number(lm?.[1] ?? 0),
    visibility: Number(lm?.[2] ?? 1),
  }))
  drawPoseLandmarks(ctx, parsed, width, height, false)
}

const drawPoseOverlay = () => {
  const canvas = canvasElement.value
  const video = videoElement.value
  if (!canvas || !video) return

  const ctx = canvas.getContext('2d')
  if (!ctx) return

  // 部度用影尺寸（確保繪製精度，CSS w-full h-full 負責顯示縮放
  canvas.width = video.videoWidth || video.clientWidth
  canvas.height = video.videoHeight || video.clientHeight

  ctx.clearRect(0, 0, canvas.width, canvas.height)

  const currentFrame = getCurrentFrameData()
  if (!currentFrame) {
    ctx.fillStyle = 'rgba(255,255,255,0.9)'
    ctx.font = '16px Arial'
    ctx.fillText(t('analysisResult.noDataAtTime'), 10, 30)
    return
  }

  const rula = getSafeRulaScore(currentFrame)
  const scoreText = `RULA: ${rula === null ? 'NULL' : Math.round(rula)}`
  ctx.fillStyle = 'rgba(255,255,255,0.9)'
  ctx.font = 'bold 18px Arial'
  ctx.strokeStyle = 'rgba(0,0,0,0.8)'
  ctx.lineWidth = 2
  ctx.strokeText(scoreText, 10, 30)
  ctx.fillText(scoreText, 10, 30)

  const imageLandmarks = currentFrame.image_landmarks ?? currentFrame.native_draw_data
  const hasImageLandmarks = !!(imageLandmarks && typeof imageLandmarks === 'object')
  const hasLegacyPose = Array.isArray(currentFrame.pose_landmarks) && currentFrame.pose_landmarks.length > 0

  if (hasImageLandmarks) {
    drawNativePoseData(ctx, imageLandmarks as NativeDrawData, canvas.width, canvas.height)
    return
  }

  if (!hasLegacyPose) {
    ctx.fillStyle = 'rgba(255,215,0,0.95)'
    ctx.font = '16px Arial'
    ctx.fillText(t('analysisResult.noDataAtTime'), 10, 56)
    return
  }
  drawPoseLandmarks(ctx, currentFrame.pose_landmarks as PoseLandmark[], canvas.width, canvas.height, false)
}

const setupCanvasOverlay = () => {
  drawPoseOverlay()
}

const startSampledPlayback = () => {
  if (sampledPlaybackInterval || !getCurrentFrames().length) return
  // 已後幀，第一幀始播
  if (currentFrameIndex.value >= getCurrentFrames().length - 1) {
    currentFrameIndex.value = 0
    seekToFrame(0)
  }
  isPlaying.value = true
  sampledPlaybackInterval = setInterval(() => {
    const frames = getCurrentFrames()
    if (currentFrameIndex.value < frames.length - 1) {
      currentFrameIndex.value++
      const f = frames[currentFrameIndex.value]
      const ts = f?.timestamp
      if (typeof ts === 'number' && videoElement.value) {
        videoElement.value.currentTime = ts
        currentVideoTime.value = ts
      }
      if (showPoseOverlay.value) drawPoseOverlay()
    } else {
      stopSampledPlayback()
      isPlaying.value = false
    }
  }, sampledPlaybackTickMs.value)
}

const stopSampledPlayback = () => {
  if (sampledPlaybackInterval) {
    clearInterval(sampledPlaybackInterval)
    sampledPlaybackInterval = null
  }
  isPlaying.value = false
}

const seekToFrame = (idx: number) => {
  const frames = getCurrentFrames()
  if (idx < 0 || idx >= frames.length) return
  const f = frames[idx]
  const ts = f?.timestamp
  const v = videoElement.value
  if (v && typeof ts === 'number') {
    v.currentTime = ts
    nextTick(() => showPoseOverlay.value && drawPoseOverlay())
  }
}

const previousFrame = () => {
  if (!getCurrentFrames().length) return
  currentFrameIndex.value = Math.max(0, currentFrameIndex.value - 1)
  seekToFrame(currentFrameIndex.value)
}

const nextFrame = () => {
  const frames = getCurrentFrames()
  if (!frames.length) return
  const maxIndex = frames.length - 1
  currentFrameIndex.value = currentFrameIndex.value >= maxIndex ? 0 : currentFrameIndex.value + 1
  seekToFrame(currentFrameIndex.value)
}

const jumpToNextMaxScoreFrame = () => {
  const indexes = maxScoreFrameIndexes.value
  if (!indexes.length) return

  stopSampledPlayback()
  isPlaying.value = false

  const current = currentFrameIndex.value
  const next = (indexes.find((idx) => idx > current) ?? indexes[0])!
  currentFrameIndex.value = next
  seekToFrame(next)
}

const jumpToFrameFromInput = () => {
  const frames = getCurrentFrames()
  const total = frames.length
  if (!total) {
    frameInput.value = '1'
    return
  }

  const parsed = Number.parseInt((frameInput.value || '').trim(), 10)
  if (!Number.isFinite(parsed)) {
    frameInput.value = String(currentFrameIndex.value + 1)
    return
  }

  const oneBased = Math.max(1, Math.min(total, parsed))
  currentFrameIndex.value = oneBased - 1
  frameInput.value = String(oneBased)
  seekToFrame(currentFrameIndex.value)
}

const onFrameInputEnter = (event: KeyboardEvent) => {
  const target = event.target as HTMLInputElement | null
  if (target?.value != null) {
    frameInput.value = String(target.value)
  }
  jumpToFrameFromInput()
}

const setupVideoTimeTracking = () => {
  const v = videoElement.value
  if (!v) return

  v.addEventListener('timeupdate', () => {
    currentVideoTime.value = v.currentTime
    if (showPoseOverlay.value && !isPlaying.value) drawPoseOverlay()
  })

  v.addEventListener('loadedmetadata', () => {
    videoDuration.value = v.duration
    setupCanvasOverlay()
  })

  v.addEventListener('play', () => {
    isPlaying.value = true
    startSampledPlayback()
  })

  v.addEventListener('pause', () => {
    isPlaying.value = false
    stopSampledPlayback()
    if (showPoseOverlay.value) drawPoseOverlay()
  })

  v.addEventListener('ended', () => {
    isPlaying.value = false
    stopSampledPlayback()
  })

  setupVideoResizeObserver()
}

// 骨架
const onPoseOverlayToggle = () => {
  if (showPoseOverlay.value) {
    if (isPlaying.value) {
      startSampledPlayback()
    } else {
      drawPoseOverlay()
    }
    return
  }

  // 覆層確實守 canvas & ctx
  stopSampledPlayback()

  const canvas = canvasElement.value
  if (!canvas) return

  const ctx = canvas.getContext('2d')
  if (!ctx) return

  ctx.clearRect(0, 0, canvas.width, canvas.height)
}

// ========= 資輔助 (Risk Images) =========
const getRiskImages = (): RiskImage[] => {
  const rows = (results.value as any)?.risk_images
  return Array.isArray(rows) ? rows as RiskImage[] : []
}

const getRiskImageUrl = (filename: string): string => {
  const clean = String(filename || '').trim()
  return `${VIDEO_API}/risk_image/${analysisId}/${encodeURIComponent(clean)}`
}

const showRiskImagePreview = ref(false)
const previewRiskImage = ref<RiskImage | null>(null)
const previewRiskImageUrl = ref('')

const openRiskImagePreview = (img: RiskImage) => {
  previewRiskImage.value = img
  previewRiskImageUrl.value = getRiskImageUrl(img.filename)
  showRiskImagePreview.value = true
}

// ========= 統=========
const analyzeRulaScores = () => {
  const frames = getCurrentFrames()
  const scoreDistribution: Record<number, number> = { 1:0,2:0,3:0,4:0,5:0,6:0,7:0 }
  const scoreDurations: Record<number, number> = { 1:0,2:0,3:0,4:0,5:0,6:0,7:0 }

  let totalValidFrames = 0
  let totalValidTime = 0

  const isFiniteNum = (x: unknown): x is number =>
    typeof x === 'number' && Number.isFinite(x)

  for (let i = 0; i < frames.length; i++) {
    const f = frames[i]!
    const v = getSafeRulaScore(f)
    if (!v || v < 1 || v > 7) continue

    const s = Math.round(v) as 1|2|3|4|5|6|7
    scoreDistribution[s]!++ // eslint-disable-line @typescript-eslint/no-non-null-assertion
    totalValidFrames++

    // 當t0（若缺值退一幀0
    const rawT0 = f?.timestamp
    const prevRaw = frames[i - 1]?.timestamp
    const nextRaw = frames[i + 1]?.timestamp

    const t0 = isFiniteNum(rawT0)
      ? rawT0
      : (isFiniteNum(prevRaw) ? prevRaw : 0)

    let dt = 0
    if (i < frames.length - 1) {
      // 中幀：一幀 - 幀；缺t0+1
      const t1 = isFiniteNum(nextRaw) ? nextRaw : (t0 + 1)
      dt = Math.max(0, t1 - t0)
    } else if (i > 0) {
      // 後幀：當 - 幀；缺t0-1
      const tp = isFiniteNum(prevRaw) ? prevRaw : (t0 - 1)
      dt = Math.max(0, t0 - tp)
    } else {
      // 一幀：差
      dt = 0
    }

    // 戳增dt 能0；0 以避污
    scoreDurations[s]! += dt // eslint-disable-line @typescript-eslint/no-non-null-assertion
    totalValidTime += dt
  }

  return { scoreDistribution, scoreDurations, totalValidTime, totalValidFrames }
}

const createPieChart = () => {
  const el = pieChartRef.value
  if (!el) return
  const { scoreDistribution, totalValidFrames } = analyzeRulaScores()

  const labels: string[] = []
  const data: number[] = []
  const colors = ['#10B981','#10B981','#F59E0B','#F59E0B','#EF4444','#EF4444','#DC2626']
  const bg: string[] = []

  for (let s = 1; s <= 7; s++) {
    const c = scoreDistribution[s] || 0
    if (c > 0) {
      labels.push(`${t('analysisResult.chartScoreLabel')} ${s}`)
      data.push(totalValidFrames > 0 ? (c / totalValidFrames * 100) : 0)
      bg.push(colors[s - 1] || '#6B7280')
    }
  }

  if (pieChart) pieChart.destroy()
  pieChart = new Chart(el, {
    type: 'pie',
    data: { labels, datasets: [{ data, backgroundColor: bg, borderColor: '#fff', borderWidth: 2 }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom', labels: { padding: 15, usePointStyle: true } },
        tooltip: { callbacks: { label: (c: any) => `${c.label || ''}: ${c.parsed.toFixed(1)}%` } }
      }
    }
  })
}

const createBarChart = () => {
  const el = barChartRef.value
  if (!el) return
  const { scoreDurations } = analyzeRulaScores()
  const labels = Array.from({length: 7}, (_, i) => `${t('analysisResult.chartScoreLabel')} ${i + 1}`)
  const colors = ['#10B981','#10B981','#F59E0B','#F59E0B','#EF4444','#EF4444','#DC2626']
  const data: number[] = []
  for (let s = 1; s <= 7; s++) data.push(scoreDurations[s] || 0)

  if (barChart) barChart.destroy()
  barChart = new Chart(el, {
    type: 'bar',
    data: { labels, datasets: [{ label: t('analysisResult.chartDurationLabel'), data, backgroundColor: colors, borderColor: colors, borderWidth: 1 }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: {
        y: { beginAtZero: true, title: { display: true, text: t('analysisResult.chartDurationLabel') } },
        x: { title: { display: true, text: t('analysisResult.chartRulaScore') } }
      },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (c: any) => `${t('analysisResult.analysisTime')}: ${Number(c.parsed?.y ?? 0).toFixed(2)} s` } }
      }
    }
  })
}
const createLineChart = () => {
  const el = lineChartRef.value
  if (!el) return

  const frames = getCurrentFrames()

  // Build points array (y can be null) with hasScore flag
  const points: TrendPoint[] = frames.map((f, idx) => {
    const score = getSafeRulaScore(f) // can be null
    const time = (typeof f.timestamp === 'number') ? f.timestamp : null
    const x = Number((time ?? idx).toFixed(2)) // use index if no timestamp
    return { x, y: score, idx, hasScore: score != null }
  })

  // Sort by x (time) to prevent crossing lines
  points.sort((a, b) => a.x - b.x)

  // 任何，就清空/不畫
  if (!points.length) {
    if (lineChart) { lineChart.destroy(); lineChart = null }
    return
  }

  // Key: cast TrendPoint[] to Chart.js compatible (Point|null)[]
  const dataForChart = points as unknown as (Point | null)[]

  if (lineChart) lineChart.destroy()
  lineChart = new Chart<"line", (Point | null)[], unknown>(el, {
    type: 'line',
    plugins: isPrintMode.value ? [] : [currentFrameMarkerPlugin],
    data: {
      datasets: [
        {
          label: 'RULA 數',
          data: dataForChart,     // 泛一
          borderWidth: 2,
          tension: 0.25,
          fill: false,
          spanGaps: true,
          parsing: false,
          pointRadius: (ctx) => {
            // raw 實仍是 TrendPoint，
            const p = (ctx as any).raw as TrendPoint | null
            return p?.hasScore ? 3 : 6
          },
          pointStyle: (ctx) => {
            const p = (ctx as any).raw as TrendPoint | null
            return p?.hasScore ? 'circle' : 'cross'
          },
          pointBorderColor: (ctx) => {
            const p = (ctx as any).raw as TrendPoint | null
            return p?.hasScore ? '#2563eb' : '#dc2626'
          },
          pointBackgroundColor: (ctx) => {
            const p = (ctx as any).raw as TrendPoint | null
            return p?.hasScore ? '#2563eb' : '#ffffff'
          },
          borderColor: '#2563eb',
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: true, position: 'top' },
        tooltip: {
          callbacks: {
            title: (items: any[]) => {
              const p = (items?.[0]?.raw ?? null) as TrendPoint | null
              const t_val = (p && typeof p.x === 'number') ? p.x.toFixed(2) : ''
              return `${t('analysisResult.chartTimeLabel').replace('(s)', '').replace('(', '')} ${t_val}s`
            },
            label: (item: any) => {
              const p = (item?.raw ?? null) as TrendPoint | null
              return (p && p.hasScore) ? `${t('analysisResult.chartRulaScore')}: ${p.y}` : t('analysisResult.chartNoScore')
            }
          }
        }
      },
      scales: {
        x: {
          type: 'linear',
          title: { display: true, text: t('analysisResult.chartTimeLabel') },
          ticks: { callback: (v: any) => Number(v).toFixed(1) }
        },
        y: {
          title: { display: true, text: t('analysisResult.chartRulaScore') },
          suggestedMin: 0,
          suggestedMax: 7,
          ticks: { stepSize: 1 }
        }
      },
      onClick: (evt) => {
        const chart = lineChart
        if (!chart) return

        const nearest = chart.getElementsAtEventForMode(
          evt as unknown as Event,
          'nearest',
          { intersect: false },
          true
        )
        if (!nearest || nearest.length === 0) return

        const firstEl = nearest[0]
        if (!firstEl) return

        const ds = chart.data.datasets?.[firstEl.datasetIndex]
        // ds!.data 是 (Point|null)[]，實TrendPoint[]
        const raw: any = (ds?.data as any[])?.[firstEl.index]
        if (!raw || typeof raw !== 'object') return

        const p = raw as TrendPoint
        if (Number.isFinite(p.x) && videoElement.value) {
          videoElement.value.currentTime = p.x
        }
        if (Number.isInteger(p.idx)) {
          currentFrameIndex.value = p.idx
          nextTick(() => showPoseOverlay.value && drawPoseOverlay())
        }
      }
    }
  })
}



// ========= Print-specific chart URLs (matplotlib backend) =========
const buildChartUrl = (type: string) => {
  const token = useCookie<string | null>('hfe_token')
  const base = `${VIDEO_API}/chart/${analysisId}/${type}`
  return token.value ? `${base}?token=${encodeURIComponent(token.value)}` : base
}

const loadPrintChartUrls = () => {
  const ts = Date.now()
  printLineChartUrl.value = `${buildChartUrl('line')}&_t=${ts}`
  printPieChartUrl.value = `${buildChartUrl('pie')}&_t=${ts}`
  printBarChartUrl.value = `${buildChartUrl('bar')}&_t=${ts}`
}

const getFrameStatistics = () => {
  const stats = results.value?.statistics
  if (stats) {
    return {
      totalFrames: stats.total_frames ?? 0,
      validFrames: stats.valid_frames ?? stats.valid_scores ?? 0,
      invalidFrames: stats.invalid_frames ?? stats.invalid_scores ?? 0,
      duration: stats.duration_sec ?? 0,
    }
  }
  const frames = getCurrentFrames()
  const totalFrames = frames.length
  let validFrames = 0, invalidFrames = 0
  frames.forEach((f) => {
    const hasPose = !!(f.pose_landmarks?.length) || !!f.image_landmarks || !!f.native_draw_data
    const score = getSafeRulaScore(f)
    if (!hasPose || !score || score <= 0) invalidFrames++
    else validFrames++
  })
  const duration = frames.length ? Math.max(...frames.map(f => f.timestamp ?? 0)) : videoDuration.value
  return { totalFrames, validFrames, invalidFrames, duration }
}

const getMaxRulaScoreText = (): string => {
  const statsMax = Number((results.value as any)?.statistics?.max_score)
  if (Number.isFinite(statsMax) && statsMax > 0) return String(Math.round(statsMax))

  const frames = getCurrentFrames()
  let maxScore: number | null = null
  for (let i = 0; i < frames.length; i++) {
    const v = getSafeRulaScore(frames[i])
    if (v == null) continue
    maxScore = maxScore == null ? v : Math.max(maxScore, v)
  }
  return maxScore == null ? 'N/A' : String(Math.round(maxScore))
}

// ========= 下 CSV =========
const downloadResults = async () => {
  try {
    const resp = await fetch(`${VIDEO_API}/download/${analysisId}`, {
      method: 'GET',
      credentials: 'include',  // ??Send cookies
      headers: {
        Accept: 'text/csv',
        ...getAuthHeaders()
      }
    })
    if (!resp.ok) {
      const raw = await resp.text()
      try {
        const parsed = JSON.parse(raw)
        throw new Error(parsed?.message || raw || t('analysisResult.downloadFailed'))
      } catch {
        throw new Error(raw || t('analysisResult.downloadFailed'))
      }
    }
    const blob = await resp.blob()
    const okType = ['text/csv','application/octet-stream','application/vnd.ms-excel','text/plain']
    if (!okType.includes(blob.type)) { error.value = `${t('analysisResult.downloadFormatError')} (${blob.type})`; return }
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `rula_analysis_${analysisId}.csv`
    document.body.appendChild(a); a.click(); document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch (e: any) {
    error.value = `${t('analysisResult.downloadFailed')}: ${e?.message || e}`
  }
}

// ========= 返=========
const goBack = () => {
  router.back()
}

const previewPrint = async () => {
  loadPrintChartUrls()
  isPrintMode.value = true
  await nextTick()
  // 等載入完
  await new Promise(resolve => {
    let loadedCount = 0
    const checkLoaded = () => {
      loadedCount++
      if (loadedCount === 3) {
        setTimeout(resolve, 200) // 額等確渲完
      }
    }
    // 設置大待
    setTimeout(resolve, 3000)
    // 載入
    const imgs = document.querySelectorAll('.print-chart-img')
    if (imgs.length === 0) {
      setTimeout(resolve, 1500)
    } else {
      imgs.forEach(img => {
        if ((img as HTMLImageElement).complete) {
          checkLoaded()
        } else {
          img.addEventListener('load', checkLoaded)
          img.addEventListener('error', checkLoaded)
        }
      })
    }
  })
  window.print()
}

const handleAfterPrint = () => {
  isPrintMode.value = false
  if (lineChart) {
    lineChart.destroy()
    lineChart = null
    createLineChart()
  }
}

// ========= 命 =========
onMounted(() => {
  const url = sessionStorage.getItem('hfe_video_object_url') || ''
  if (url) originalVideoUrl.value = url
  fetchInitialVideoInfo()
  startProgressUpdates()
  window.addEventListener('afterprint', handleAfterPrint)
})

onUnmounted(() => {
  stopSse()
  stopPolling()
  stopSampledPlayback()
  teardownVideoResizeObserver()
  if (pieChart) pieChart.destroy()
  if (barChart) barChart.destroy()
  if (lineChart) lineChart.destroy()
  window.removeEventListener('afterprint', handleAfterPrint)

  const url = sessionStorage.getItem('hfe_video_object_url')
  if (url) {
    URL.revokeObjectURL(url)
    sessionStorage.removeItem('hfe_video_object_url')
  }
})

// ：言建
watch(locale, () => {
  if (!processing.value && results.value) {
    createPieChart()
    createBarChart()
    createLineChart()
  }
})

// ：出
watch(results, async (v) => {
  if (v?.analysis_results?.length) {
    await nextTick()
    setTimeout(() => {
      createPieChart()
      createBarChart()
      createLineChart()
      if (showPoseOverlay.value) drawPoseOverlay()
    }, 80)
  }
})
watch(results, () => prefillParamsFromStatus())

watch(results, () => {
  const total = getCurrentFrames().length
  if (!total) {
    currentFrameIndex.value = 0
    frameInput.value = '1'
    return
  }

  const safeIndex = Math.min(currentFrameIndex.value, total - 1)
  if (safeIndex !== currentFrameIndex.value) {
    currentFrameIndex.value = safeIndex
  }
  frameInput.value = String(safeIndex + 1)
})

watch(currentFrameIndex, (idx) => {
  frameInput.value = String(idx + 1)
  if (lineChart) lineChart.update()
})

watch(selectedSampledSpeed, () => {
  if (!sampledPlaybackInterval || !isPlaying.value) return
  stopSampledPlayback()
  startSampledPlayback()
})

watch([showPoseOverlay, results], () => {
  if (results.value) onPoseOverlayToggle()
})

// 安全：/ 數字串
const getCurrentTimestampText = () => {
  const t = getCurrentFrameData()?.timestamp
  const v = typeof t === 'number' ? t : currentVideoTime.value
  return v.toFixed(2)
}

const getFrameMetricText = (key: keyof FrameRow, digits = 1): string => {
  const frame = getCurrentFrameData()
  const raw = (frame as any)?.[key]
  if (raw === null || raw === undefined || raw === 'NULL' || raw === '') return 'NULL'
  const n = Number(raw)
  if (Number.isFinite(n)) return n.toFixed(digits)
  return String(raw)
}

const getFrameAngleText = (key: keyof FrameRow): string => {
  const text = getFrameMetricText(key, 1)
  return text === 'NULL' ? text : `${text}°`
}

const getFrameTableText = (key: keyof FrameRow): string => {
  return getFrameMetricText(key, 0)
}

const isNullMetric = (value: string): boolean => value === 'NULL'
</script>

<template>
  <div class="min-h-dvh p-6">
    <!-- ========= 專用印布（單湊========= -->
    <div v-show="isPrintMode" class="print-only-layout">
      <!-- 表標 -->
      <div class="text-center mb-2">
        <h1 class="text-lg font-bold">{{ t('analysisResult.printReportTitle') }}</h1>
      </div>

      <!-- 本資橫 -->
      <div class="flex items-center justify-between text-[9px] border-b pb-1 mb-2">
        <div><strong>{{ t('analysisResult.surveyDate') }}:</strong>{{ displayVideoInfo.surveyDate }}</div>
        <div><strong>{{ t('analysisResult.assessor') }}:</strong>{{ displayVideoInfo.assessor }}</div>
        <div><strong>{{ t('analysisResult.organization') }}:</strong>{{ displayVideoInfo.organization }}</div>
        <div><strong>{{ t('analysisResult.taskName') }}:</strong>{{ displayVideoInfo.taskName }}</div>
      </div>

      <!-- 主容：左兩-->
      <div class="grid grid-cols-[1fr_1.4fr] gap-2">
        <!-- 左側：統計表+ 風險影 -->
        <div class="space-y-2">
          <!-- 統表格 -->
          <div class="border rounded-sm overflow-hidden">
            <div class="bg-gray-100 px-2 py-0.5 text-[10px] font-semibold border-b">{{ t('analysisResult.printStatistics') }}</div>
            <table class="w-full text-[9px]">
              <tbody>
                <tr class="border-b">
                  <td class="px-2 py-0.5 bg-gray-50 font-medium w-24">{{ t('analysisResult.totalFrames') }}</td>
                  <td class="px-2 py-0.5">{{ getFrameStatistics().totalFrames }}</td>
                </tr>
                <tr class="border-b">
                  <td class="px-2 py-0.5 bg-gray-50 font-medium">{{ t('analysisResult.validFrames') }}</td>
                  <td class="px-2 py-0.5">{{ getFrameStatistics().validFrames }}</td>
                </tr>
                <tr class="border-b">
                  <td class="px-2 py-0.5 bg-gray-50 font-medium">{{ t('analysisResult.videoDuration') }}</td>
                  <td class="px-2 py-0.5">{{ getFrameStatistics().duration.toFixed(1) }}s</td>
                </tr>
                <tr class="border-b">
                  <td class="px-2 py-0.5 bg-gray-50 font-medium">{{ t('analysisResult.averageScore') }}</td>
                  <td class="px-2 py-0.5 font-semibold text-yellow-700">
                    {{ results?.statistics?.average_score?.toFixed(1) || results?.results?.avg_rula_score?.toFixed(1) || '0.0' }}
                  </td>
                </tr>
                <tr>
                  <td class="px-2 py-0.5 bg-gray-50 font-medium">{{ t('analysisResult.maxScore') }}</td>
                  <td class="px-2 py-0.5 font-bold text-red-600">{{ getMaxRulaScoreText() }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- 風險影（下 -->
          <div v-if="getRiskImages().length > 0" class="border rounded-sm overflow-hidden">
            <div class="bg-gray-100 px-2 py-0.5 text-[10px] font-semibold border-b">{{ t('analysisResult.topRiskImages') }}</div>
            <div class="flex flex-col gap-1.5 p-1.5">
              <div
                v-for="img in getRiskImages().slice(0, 2)"
                :key="img.filename"
                class="border rounded-sm overflow-hidden bg-white"
              >
                <img
                  :src="getRiskImageUrl(img.filename)"
                  :alt="`risk-${img.rank}`"
                  class="w-full aspect-[4/3] object-contain bg-gray-50"
                />
                <div class="px-1.5 py-0.5 text-[9px] bg-gray-50 border-t flex justify-between">
                  <span>RULA: {{ img.rula_score }}</span>
                  <span>{{ img.time_sec.toFixed(1) }}s</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 側 表縱-->
        <div class="space-y-1.5">
          <!-- 趨勢??-->
          <div class="border rounded-sm overflow-hidden">
            <div class="bg-gray-100 px-2 py-0.5 text-[10px] font-semibold border-b">{{ t('analysisResult.printChartTrend') }}</div>
            <div class="p-1">
              <img v-if="printLineChartUrl" :src="printLineChartUrl" class="print-chart-img w-full h-auto" alt="" crossorigin="anonymous" />
            </div>
          </div>

          <!-- -->
          <div class="border rounded-sm overflow-hidden">
            <div class="bg-gray-100 px-2 py-0.5 text-[10px] font-semibold border-b">{{ t('analysisResult.printChartPie') }}</div>
            <div class="p-1 flex justify-center">
              <img v-if="printPieChartUrl" :src="printPieChartUrl" class="print-chart-img h-auto" style="max-width: 60%;" alt="" crossorigin="anonymous" />
            </div>
          </div>

          <!--  -->
          <div class="border rounded-sm overflow-hidden">
            <div class="bg-gray-100 px-2 py-0.5 text-[10px] font-semibold border-b">{{ t('analysisResult.printChartBar') }}</div>
            <div class="p-1">
              <img v-if="printBarChartUrl" :src="printBarChartUrl" class="print-chart-img w-full h-auto" alt="" crossorigin="anonymous" />
            </div>
          </div>
        </div>
      </div>

      <!-- AI （ AI 容顯示 -->
      <div v-if="counselingData?.score_explanation || counselingData?.recommendations" class="mt-2 border rounded-sm overflow-hidden">
        <div class="bg-gray-100 px-2 py-0.5 text-[10px] font-semibold border-b">{{ t('analysisResult.aiSummary') }}</div>
        <div class="p-2 grid grid-cols-2 gap-3">
          <div v-if="counselingData?.score_explanation">
            <div class="text-[9px] font-semibold text-gray-700 mb-0.5">{{ t('analysisResult.scoreExplanationLabel') }}</div>
            <div class="text-[9px] text-gray-600 whitespace-pre-line leading-relaxed">{{ extractSummaryFromMarkdown(counselingData.score_explanation) }}</div>
          </div>
          <div v-if="counselingData?.recommendations">
            <div class="text-[9px] font-semibold text-gray-700 mb-0.5">{{ t('analysisResult.improvementSummary') }}</div>
            <div class="text-[9px] text-gray-600 whitespace-pre-line leading-relaxed">{{ extractSummaryFromMarkdown(counselingData.recommendations) }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- ========= 面容（螢幕顯示 ========= -->
    <div v-show="!isPrintMode" class="print:hidden">
    <!--  -->
    <div class="flex justify-between items-start mb-6">
      <div class="flex flex-col">
        <h1 class="text-2xl font-bold">{{ t('analysisResult.analysisTitle') }}</h1>
        <a
          href="https://ergo-plus.com/rula-assessment-tool-guide/"
          target="_blank"
          rel="noopener noreferrer"
          class="mt-1 inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700"
        >
          <i class="pi pi-question-circle" aria-hidden="true"></i>
          {{ t('analysisResult.whatIsRula') }}
        </a>
      </div>
      <div class="flex gap-2 print:hidden">
        <Button
          :label="t('analysisResult.rescoreBtn')"
          icon="pi pi-sliders-h"
          :disabled="processing"
          @click="openRescore"
        />
        <Button :label="t('analysisResult.downloadBtn')" icon="pi pi-download" severity="secondary" :disabled="processing" @click="downloadResults" />
        <Button :label="t('analysisResult.exportBtn')" icon="pi pi-print" severity="secondary" @click="previewPrint" />
        <Button :label="t('common.goBack')" icon="pi pi-arrow-left" severity="secondary" @click="goBack" />
        <Button :label="t('common.backHome')" icon="pi pi-home" severity="secondary" @click="$router.push('/')" />
      </div>
    </div>

    <div class="mb-4 rounded-md border border-slate-200 bg-slate-50/80 px-3 py-2 overflow-x-auto">
      <div class="flex min-w-max items-center gap-4 text-xs text-slate-700">
        <div class="flex items-center gap-1.5">
          <span class="text-slate-500">{{ t('analysisResult.surveyDate') }}</span>
          <span class="font-semibold text-slate-900">{{ displayVideoInfo.surveyDate }}</span>
        </div>
        <span class="text-slate-300">|</span>
        <div class="flex items-center gap-1.5">
          <span class="text-slate-500">{{ t('analysisResult.assessor') }}</span>
          <span class="font-semibold text-slate-900">{{ displayVideoInfo.assessor }}</span>
        </div>
        <span class="text-slate-300">|</span>
        <div class="flex items-center gap-1.5">
          <span class="text-slate-500">{{ t('analysisResult.organization') }}</span>
          <span class="font-semibold text-slate-900">{{ displayVideoInfo.organization }}</span>
        </div>
        <span class="text-slate-300">|</span>
        <div class="flex items-center gap-1.5">
          <span class="text-slate-500">{{ t('analysisResult.taskName') }}</span>
          <span class="font-semibold text-slate-900">{{ displayVideoInfo.taskName }}</span>
        </div>
      </div>
    </div>

    <!-- 誤 -->
    <Message v-if="error" severity="error" class="mb-4">{{ error }}</Message>

    <!-- 度 -->
    <Card v-if="processing" class="mb-6">
      <template #content>
        <div class="text-center">
          <ProgressBar :value="Number(uploadProgress.toFixed(1))" class="mb-2" />
          <p class="text-lg font-medium">{{ uploadStatus }}</p>
          <p v-if="totalFrames > 0" class="text-sm text-gray-700 mt-1">
            {{ t('analysisResult.frameProcessingStatus').replace('{current}', String(currentFrame)).replace('{total}', String(totalFrames)).replace('{pct}', String(Number(uploadProgress.toFixed(1)))) }}
          </p>
          <div class="flex justify-center items-center gap-4 mt-2">
            <p class="text-sm text-gray-600">{{ t('analysisResult.systemAnalyzing') }}</p>
          </div>
          <div class="mt-4">
            <Button
              :label="t('analysisResult.cancelAndBack')"
              icon="pi pi-times"
              severity="danger"
              :loading="cancelSubmitting"
              @click="cancelAnalysisAndBackToForm"
            />
            <p class="text-xs text-gray-500 mt-2">{{ t('analysisResult.cancelNote') }}</p>
          </div>
          
        </div>
      </template>
    </Card>

    <!-- 容 -->
    <div v-if="!processing" class="space-y-4">
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 print:block print:w-full">
        <!-- 視(印隱 -->
        <div class="lg:col-span-2 print:hidden">
          <Card>
            <template #title>
              <div class="flex justify-between items-center">
                <span>{{ t('analysisResult.videoAndSkeleton') }}</span>
              </div>
            </template>
            <template #content>
              <div class="relative">
                <video ref="videoElement" :src="originalVideoUrl" :controls="false" class="w-full border rounded" />
                <canvas
                  ref="canvasElement"
                  class="absolute top-0 left-0 w-full h-full z-10 pointer-events-none rounded"
                  :style="{ display: showPoseOverlay ? 'block' : 'none' }"
                />
              </div>

              <div class="mt-3 flex items-center gap-3" v-if="results">
                <div class="flex items-center">
                  <input
                    v-model="showPoseOverlay"
                    type="checkbox"
                    id="poseOverlay"
                    class="mr-2"
                    @change="onPoseOverlayToggle"
                  />
                  <label for="poseOverlay" class="text-sm font-medium cursor-pointer">{{ t('analysisResult.showPoseSkeleton') }}</label>
                </div>
                <Button
                  :label="t('analysisResult.viewFrameMetrics')"
                  icon="pi pi-table"
                  size="small"
                  severity="secondary"
                  :disabled="!(results?.analysis_results?.length)"
                  @click="openFrameMetricsDialog"
                />
                <small class="text-gray-500">{{ t('analysisResult.videoSourceHint') }}</small>
              </div>

              <!-- 樣放制 -->
              <div v-if="results" class="mt-4 p-3 bg-gray-50 rounded">
                <h5 class="font-semibold mb-3 text-sm">{{ t('analysisResult.sampledPlayback') }}</h5>
                <div class="flex items-center gap-2 mb-3">
                  <Button :label="t('analysisResult.prevFrame')" icon="pi pi-step-backward" size="small" severity="secondary" @click="previousFrame" />
                  <Button :label="t('analysisResult.nextFrame')" icon="pi pi-step-forward" size="small" severity="secondary" @click="nextFrame" />
                  <div class="ml-2 flex items-center gap-2 text-sm text-gray-600">
                    <span>{{ t('analysisResult.frameLabel') }}</span>
                    <input
                      v-model="frameInput"
                      type="number"
                      min="1"
                      :max="results?.analysis_results?.length || 1"
                      :disabled="!(results?.analysis_results?.length)"
                      class="w-20 rounded border border-gray-300 bg-white px-2 py-1 text-sm text-gray-700"
                      @keyup.enter.prevent="onFrameInputEnter"
                      @blur="jumpToFrameFromInput"
                      @change="jumpToFrameFromInput"
                    />
                    <span>/ {{ results?.analysis_results?.length || 0 }}</span>
                  </div>
                </div>
                <div class="flex items-center gap-2">
                  <Button :label="t('analysisResult.startPlayback')" icon="pi pi-play" size="small" severity="success" @click="startSampledPlayback" />
                  <Button :label="t('analysisResult.stopPlayback')" icon="pi pi-stop" size="small" severity="danger" @click="stopSampledPlayback" />
                  <div class="ml-2 flex items-center gap-2 text-sm text-gray-700">
                    <span>{{ t('analysisResult.playbackSpeed') }}</span>
                    <select
                      v-model.number="selectedSampledSpeed"
                      class="rounded border border-gray-300 bg-white px-2 py-1 text-sm"
                    >
                      <option v-for="speed in sampledSpeedOptions" :key="speed" :value="speed">
                        {{ speed }}x
                      </option>
                    </select>
                  </div>
                  <Button
                    :label="maxScoreCycleButtonLabel"
                    icon="pi pi-angle-double-right"
                    size="small"
                    severity="warning"
                    class="!bg-yellow-400 !border-yellow-500 !text-yellow-950 hover:!bg-yellow-300"
                    :disabled="maxScoreFrameIndicator.total === 0"
                    @click="jumpToNextMaxScoreFrame"
                  />
                </div>
                <div class="mt-2 text-xs text-gray-500">
                  {{ sampledRealtimeHintText }}
                </div>
              </div>
            </template>
          </Card>

          <!-- AI Counselor Section（放左側下方，正常局-->
          <div class="mt-4">
            <RulaCounselor
              :analysis-id="analysisId"
              :task-name="displayVideoInfo.taskName === '-' ? '' : displayVideoInfo.taskName"
              :auth-headers="getAuthHeaders()"
              :disabled="false"
              :auto-load="false"
              @loading="(isLoading) => {}"
              @loaded="onCounselorLoaded"
              @error="onCounselorError"
            />
          </div>
        </div>

        <!-- 統-->
        <div class="space-y-4 print:w-full print:block">
          <!-- 高風影顯示，訊塊為表部-->
          <Card v-if="getRiskImages().length > 0" class="hidden print:block mb-4 print:break-inside-avoid">
            <template #title>{{ t('analysisResult.topRiskImages') }}</template>
            <template #content>
              <div class="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(220px,1fr))]">
                <div
                  v-for="img in getRiskImages()"
                  :key="img.filename"
                  class="w-full max-w-[340px] rounded border bg-white overflow-hidden mx-auto print:border-gray-200"
                >
                  <img
                    :src="getRiskImageUrl(img.filename)"
                    :alt="`risk-${img.rank}`"
                    class="w-full aspect-[4/3] object-contain bg-gray-100"
                  />
                  <div class="p-2 text-xs text-gray-700 bg-gray-50">
                    <div>RULA: {{ img.rula_score }}</div>
                    <div>Frame: {{ img.frame }} / {{ img.time_sec.toFixed(2) }}s</div>
                  </div>
                </div>
              </div>
            </template>
          </Card>

          <Card class="print:break-inside-avoid print:mb-4">
            <template #title>{{ t('analysisResult.analysisOverview') }}</template>
            <template #content>
              <div class="grid grid-cols-2 gap-3">
                <div class="bg-blue-50 p-3 rounded">
                  <div class="text-xs font-semibold text-blue-800">{{ t('analysisResult.totalFrames') }}</div>
                  <div class="text-lg font-bold text-blue-600">{{ getFrameStatistics().totalFrames }}</div>
                </div>
                <div class="bg-green-50 p-3 rounded">
                  <div class="text-xs font-semibold text-green-800">{{ t('analysisResult.validFrames') }}</div>
                  <div class="text-lg font-bold text-green-600">{{ getFrameStatistics().validFrames }}</div>
                </div>
                <div class="bg-red-50 p-3 rounded">
                  <div class="text-xs font-semibold text-red-800">{{ t('analysisResult.invalidFrames') }}</div>
                  <div class="text-lg font-bold text-red-600">{{ getFrameStatistics().invalidFrames }}</div>
                </div>
                <div class="bg-purple-50 p-3 rounded">
                  <div class="text-xs font-semibold text-purple-800">{{ t('analysisResult.videoDuration') }}</div>
                  <div class="text-lg font-bold text-purple-600">{{ getFrameStatistics().duration.toFixed(1) }}s</div>
                </div>
              </div>
              <div class="mt-3 grid grid-cols-2 gap-3">
                <div class="bg-yellow-50 p-3 rounded">
                  <div class="text-xs font-semibold text-yellow-800">{{ t('analysisResult.averageScore') }}</div>
                  <div class="text-lg font-bold text-yellow-600">
                    {{ results?.statistics?.average_score?.toFixed(1) || results?.results?.avg_rula_score?.toFixed(1) || '0.0' }}
                  </div>
                </div>
                <div class="bg-indigo-50 p-3 rounded">
                  <div class="text-xs font-semibold text-indigo-800">
                    {{ t('analysisResult.maxScore') }}
                  </div>
                  <div class="text-lg font-bold text-indigo-600">
                    {{ getMaxRulaScoreText() }}
                  </div>
                </div>
              </div>
              <div class="mt-3 grid grid-cols-2 gap-3">
                <div class="bg-slate-50 p-3 rounded">
                  <div class="text-xs font-semibold text-slate-800">{{ t('analysisResult.analysisTime') }}</div>
                  <div class="text-lg font-bold text-slate-600">
                    {{ getAnalysisTimeText() }}
                  </div>
                </div>
              </div>
            </template>
          </Card>

          <Card class="print:hidden">
            <template #title>{{ t('analysisResult.currentFrameInfo') }}</template>
            <template #content>
              <div v-if="results && results.analysis_results?.length" class="text-sm space-y-2">
                <div class="flex justify-between">
                  <strong>{{ t('analysisResult.frameIndex') }}</strong>
                  <span class="font-mono">{{ getCurrentActualFrameNumber() }}</span>
                </div>

                <div class="flex justify-between">
                  <strong>{{ t('analysisResult.timestampLabel') }}</strong>
                  <span class="font-mono">{{ getCurrentTimestampText() }}s</span>
                </div>

                <div class="flex justify-between items-center">
                  <strong>{{ t('analysisResult.rulaScoreLabel') }}</strong>
                  <div class="flex items-center">
                    <span
                      v-if="getSafeRulaScore(getCurrentFrameData()) !== null"
                      class="inline-flex min-w-[3rem] items-center justify-center rounded-full px-3 py-1 text-2xl font-bold leading-none"
                      :class="getSafeRulaScore(getCurrentFrameData())! <= 2
                        ? 'bg-green-100 text-green-700'
                        : getSafeRulaScore(getCurrentFrameData())! <= 4
                          ? 'bg-amber-100 text-amber-700'
                          : 'bg-red-100 text-red-700'"
                    >
                      {{ Math.round(getSafeRulaScore(getCurrentFrameData())!) }}
                    </span>
                    <span v-else class="text-gray-500 italic text-lg font-semibold">NULL</span>
                  </div>
                </div>
              </div>
              <div v-else class="text-gray-500">{{ t('analysisResult.noDataAtTime') }}</div>
            </template>
          </Card>

          <Card class="print:break-inside-avoid">
            <template #title>{{ t('analysisResult.chartAnalysis') }}</template>
            <template #content>
              <div class="mb-6">
                <h5 class="text-sm font-medium mb-2 text-gray-700">{{ t('analysisResult.printChartTrend') }}</h5>
                <div class="bg-white p-3 rounded border" style="height: 260px;">
                  <canvas ref="lineChartRef"></canvas>
                </div>
              </div>
              <div class="mb-6">
                <h5 class="text-sm font-medium mb-2 text-gray-700">{{ t('analysisResult.printChartPie') }}</h5>
                <div class="bg-white p-3 rounded border" style="height: 250px;">
                  <canvas ref="pieChartRef"></canvas>
                </div>
              </div>
              <div>
                <h5 class="text-sm font-medium mb-2 text-gray-700">{{ t('analysisResult.printChartBar') }}</h5>
                <div class="bg-white p-3 rounded border" style="height: 250px;">
                  <canvas ref="barChartRef"></canvas>
                </div>
              </div>
              <div class="mt-2 text-xs text-gray-600 bg-gray-100 p-2 rounded">
                <div class="flex items-center mb-1"><div class="w-3 h-3 bg-green-500 rounded mr-2"></div><span>{{ t('analysisResult.risk12') }}</span></div>
                <div class="flex items-center mb-1"><div class="w-3 h-3 bg-yellow-500 rounded mr-2"></div><span>{{ t('analysisResult.risk34') }}</span></div>
                <div class="flex items-center mb-1"><div class="w-3 h-3 bg-red-500 rounded mr-2"></div><span>{{ t('analysisResult.risk56') }}</span></div>
                <div class="flex items-center"><div class="w-3 h-3 bg-red-600 rounded mr-2"></div><span>{{ t('analysisResult.risk7') }}</span></div>
              </div>
            </template>
          </Card>
        </div>
      </div>
    </div>

    <Dialog
      v-model:visible="showFrameMetricsDialog"
      modal
      :header="t('analysisResult.frameMetricsTitle')"
      :style="{ width: '760px' }"
    >
      <div v-if="getCurrentFrameData()" class="space-y-4">
        <div class="text-sm text-gray-600">
          {{ t('analysisResult.frameLabel') }} {{ getCurrentActualFrameNumber() }} / {{ t('analysisResult.timestampLabel').replace(':', '') }} {{ getCurrentTimestampText() }}s
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div class="border rounded p-3 bg-slate-50">
            <h6 class="font-semibold mb-2">{{ t('analysisResult.leftAngles') }}</h6>
            <div class="text-sm space-y-1">
              <div class="flex justify-between"><span>Upper Arm</span><span class="font-mono" :class="isNullMetric(getFrameAngleText('left_upper_arm_angle')) ? 'text-red-500' : ''">{{ getFrameAngleText('left_upper_arm_angle') }}</span></div>
              <div class="flex justify-between"><span>Lower Arm</span><span class="font-mono" :class="isNullMetric(getFrameAngleText('left_lower_arm_angle')) ? 'text-red-500' : ''">{{ getFrameAngleText('left_lower_arm_angle') }}</span></div>
              <div class="flex justify-between"><span>Wrist</span><span class="font-mono" :class="isNullMetric(getFrameAngleText('left_wrist_angle')) ? 'text-red-500' : ''">{{ getFrameAngleText('left_wrist_angle') }}</span></div>
              <div class="flex justify-between"><span>Neck</span><span class="font-mono" :class="isNullMetric(getFrameAngleText('left_neck_angle')) ? 'text-red-500' : ''">{{ getFrameAngleText('left_neck_angle') }}</span></div>
              <div class="flex justify-between"><span>Trunk</span><span class="font-mono" :class="isNullMetric(getFrameAngleText('left_trunk_angle')) ? 'text-red-500' : ''">{{ getFrameAngleText('left_trunk_angle') }}</span></div>
            </div>
          </div>

          <div class="border rounded p-3 bg-slate-50">
            <h6 class="font-semibold mb-2">{{ t('analysisResult.rightAngles') }}</h6>
            <div class="text-sm space-y-1">
              <div class="flex justify-between"><span>Upper Arm</span><span class="font-mono" :class="isNullMetric(getFrameAngleText('right_upper_arm_angle')) ? 'text-red-500' : ''">{{ getFrameAngleText('right_upper_arm_angle') }}</span></div>
              <div class="flex justify-between"><span>Lower Arm</span><span class="font-mono" :class="isNullMetric(getFrameAngleText('right_lower_arm_angle')) ? 'text-red-500' : ''">{{ getFrameAngleText('right_lower_arm_angle') }}</span></div>
              <div class="flex justify-between"><span>Wrist</span><span class="font-mono" :class="isNullMetric(getFrameAngleText('right_wrist_angle')) ? 'text-red-500' : ''">{{ getFrameAngleText('right_wrist_angle') }}</span></div>
              <div class="flex justify-between"><span>Neck</span><span class="font-mono" :class="isNullMetric(getFrameAngleText('right_neck_angle')) ? 'text-red-500' : ''">{{ getFrameAngleText('right_neck_angle') }}</span></div>
              <div class="flex justify-between"><span>Trunk</span><span class="font-mono" :class="isNullMetric(getFrameAngleText('right_trunk_angle')) ? 'text-red-500' : ''">{{ getFrameAngleText('right_trunk_angle') }}</span></div>
            </div>
          </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div class="border rounded p-3 bg-blue-50">
            <h6 class="font-semibold mb-2">{{ t('analysisResult.mainScores') }}</h6>
            <div class="text-sm space-y-1">
              <div class="flex justify-between"><span>Table A</span><span class="font-mono" :class="isNullMetric(getFrameTableText('posture_score_a')) ? 'text-red-500' : ''">{{ getFrameTableText('posture_score_a') }}</span></div>
              <div class="flex justify-between"><span>Table B</span><span class="font-mono" :class="isNullMetric(getFrameTableText('posture_score_b')) ? 'text-red-500' : ''">{{ getFrameTableText('posture_score_b') }}</span></div>
              <div class="flex justify-between"><span>Table C</span><span class="font-mono" :class="isNullMetric(getFrameTableText('table_c_score')) ? 'text-red-500' : ''">{{ getFrameTableText('table_c_score') }}</span></div>
            </div>
          </div>

          <div class="border rounded p-3 bg-emerald-50">
            <h6 class="font-semibold mb-2">{{ t('analysisResult.leftTable') }}</h6>
            <div class="text-sm space-y-1">
              <div class="flex justify-between"><span>Table A</span><span class="font-mono" :class="isNullMetric(getFrameTableText('left_posture_score_a')) ? 'text-red-500' : ''">{{ getFrameTableText('left_posture_score_a') }}</span></div>
              <div class="flex justify-between"><span>Table B</span><span class="font-mono" :class="isNullMetric(getFrameTableText('left_posture_score_b')) ? 'text-red-500' : ''">{{ getFrameTableText('left_posture_score_b') }}</span></div>
              <div class="flex justify-between"><span>Table C</span><span class="font-mono" :class="isNullMetric(getFrameTableText('left_table_c_score')) ? 'text-red-500' : ''">{{ getFrameTableText('left_table_c_score') }}</span></div>
            </div>
          </div>

          <div class="border rounded p-3 bg-amber-50">
            <h6 class="font-semibold mb-2">{{ t('analysisResult.rightTable') }}</h6>
            <div class="text-sm space-y-1">
              <div class="flex justify-between"><span>Table A</span><span class="font-mono" :class="isNullMetric(getFrameTableText('right_posture_score_a')) ? 'text-red-500' : ''">{{ getFrameTableText('right_posture_score_a') }}</span></div>
              <div class="flex justify-between"><span>Table B</span><span class="font-mono" :class="isNullMetric(getFrameTableText('right_posture_score_b')) ? 'text-red-500' : ''">{{ getFrameTableText('right_posture_score_b') }}</span></div>
              <div class="flex justify-between"><span>Table C</span><span class="font-mono" :class="isNullMetric(getFrameTableText('right_table_c_score')) ? 'text-red-500' : ''">{{ getFrameTableText('right_table_c_score') }}</span></div>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="text-gray-500">{{ t('analysisResult.noDataAtTime') }}</div>
    </Dialog>

    <!-- 調整 RULA 數（快算Dialog -->
    <Dialog v-model:visible="showRescore" modal :header="t('analysisResult.rescoreDialogTitle')" :style="{ width: '520px' }">
      <RulaParamsForm
        v-model="rescoreForm"
        :load-options="loadOptions"
        :submitting="rescoreSubmitting"
        id-prefix="rescore"
      />

      <template #footer>
        <Button :label="t('common.cancel')" severity="secondary" :disabled="rescoreSubmitting" @click="showRescore=false" />
        <Button :label="t('analysisResult.rescoreSubmit')" icon="pi pi-check" :loading="rescoreSubmitting" @click="doRescore" />
      </template>
    </Dialog>

    <!-- 高風影檢Dialog -->
    <Dialog
      v-model:visible="showRiskImagePreview"
      modal
      :header="`${t('analysisResult.riskImageDialogTitle')} (Frame: ${previewRiskImage?.frame})`"
      :style="{ width: '80vw', maxWidth: '1000px' }"
    >
      <img
        v-if="previewRiskImageUrl"
        :src="previewRiskImageUrl"
        class="w-full h-auto object-contain cursor-zoom-out"
        @click="showRiskImagePreview = false"
      />
    </Dialog>
    </div>
    <!-- ========= 結面容 ========= -->

  </div>
</template>

<style scoped>
/* 依要微Dialog select 觀（若你已PrimeVue Theme  */
.p-inputtext {
  border: 1px solid #d1d5db;
  padding: 0.5rem 0.6rem;
  border-radius: 6px;
}

/* 印專用 */
@media print {
  @page {
    size: A4;
    margin: 8mm;
  }

  body {
    print-color-adjust: exact;
    -webkit-print-color-adjust: exact;
  }

  .print-only-layout {
    width: 100%;
    max-height: 100%;
    overflow: hidden;
    page-break-after: avoid;
    page-break-inside: avoid;
  }

  /* 確表不太大 */
  canvas {
    max-width: 100% !important;
    height: auto !important;
  }
  
  /* 止跨 */
  .border {
    page-break-inside: avoid;
  }
}
</style>