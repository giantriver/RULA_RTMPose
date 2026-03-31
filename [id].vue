<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute, useRouter, useRuntimeConfig } from '#imports'
import { Chart, registerables } from 'chart.js'
import type { Point } from 'chart.js'
import RulaParamsForm from '~/components/RulaParamsForm.vue'
import RulaCounselor from '~/components/RulaCounselor.vue'

Chart.register(...registerables)

// ---- 路由 /analysis/:id ----
const route = useRoute()
const router = useRouter()
const analysisId = Number(route.params.id)

// ---- 後端 API（從 .env → nuxt.config.ts → runtimeConfig 取得）----
const { public: { apiBase } } = useRuntimeConfig()
const VIDEO_API = `${apiBase}/video`
// 之後把原本 `${API_BASE}/...` 全部改成 `${VIDEO_API}/...`

// ---- Helper to get auth headers with JWT token ----
const getAuthHeaders = () => {
  const token = useCookie<string | null>('hfe_token')
  const headers: Record<string, string> = {}
  if (token.value) {
    headers['Authorization'] = `Bearer ${token.value}`
  }
  return headers
}

// ---- 狀態 ----
const processing = ref(true)
const error = ref('')
const uploadProgress = ref(0)
const uploadStatus = ref('分析初始化...')
const results = ref<any | null>(null)

const analysisStartTime = ref<number | null>(null)
const analysisEndTime = ref<number | null>(null)
const elapsedTime = ref(0)
let timerInterval: ReturnType<typeof setInterval> | null = null

// ---- 影片與覆蓋層 ----
const originalVideoUrl = ref('')
const videoElement = ref<HTMLVideoElement | null>(null)
const canvasElement = ref<HTMLCanvasElement | null>(null)
const showPoseOverlay = ref(true)
const currentVideoTime = ref(0)
const videoDuration = ref(0)
const isPlaying = ref(false)

// ---- 採樣播放 ----
const currentFrameIndex = ref(0)
let sampledPlaybackInterval: ReturnType<typeof setInterval> | null = null

// ---- 圖表 ----
const pieChartRef = ref<HTMLCanvasElement | null>(null)
const barChartRef = ref<HTMLCanvasElement | null>(null)
const lineChartRef = ref<HTMLCanvasElement | null>(null)

let pieChart: Chart | null = null
let barChart: Chart | null = null
let lineChart: Chart<"line", (Point | null)[], unknown> | null = null


// ========= 型別輔助 =========
type PoseLandmark = { x: number; y: number; z?: number; visibility?: number }
type TrendPoint = { x: number; y: number | null; idx: number; hasScore: boolean }

type FrameRow = {
  frame?: number
  timestamp?: number
  best_score?: number | string | null
  pose_landmarks?: PoseLandmark[]
  pose_world_landmarks?: PoseLandmark[]
  pose_detected?: boolean
}

// ========= 輪詢狀態 =========
let pollTimer: ReturnType<typeof setTimeout> | null = null

// 開始計時
const startTimer = () => {
  if (analysisStartTime.value) return // 避免重複開始
  
  analysisStartTime.value = Date.now()
  elapsedTime.value = 0
  
  timerInterval = setInterval(() => {
    if (analysisStartTime.value) {
      elapsedTime.value = Date.now() - analysisStartTime.value
    }
  }, 100) // 每100ms更新一次
}

// 停止計時
const stopTimer = () => {
  if (timerInterval) {
    clearInterval(timerInterval)
    timerInterval = null
  }
  if (analysisStartTime.value && !analysisEndTime.value) {
    analysisEndTime.value = Date.now()
  }
}

// 格式化時間顯示
const formatElapsedTime = (ms: number): string => {
  const seconds = Math.floor(ms / 1000)
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  const remainingMs = Math.floor((ms % 1000) / 100)
  
  if (minutes > 0) {
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}.${remainingMs}`
  } else {
    return `${remainingSeconds}.${remainingMs}`
  }
}

// 獲取總分析時間
const getTotalAnalysisTime = (): string => {
  if (!analysisStartTime.value) return '未開始'
  const endTime = analysisEndTime.value || Date.now()
  const total = endTime - analysisStartTime.value
  return formatElapsedTime(total)
}
let pollRetryCount = 0

const startPolling = () => {
  stopPolling()
  startTimer() // 開始計時
  
  pollRetryCount = 0

  const run = async () => {
    try {
      const resp = await fetch(`${VIDEO_API}/status/${analysisId}`, {
        credentials: 'include',
        headers: getAuthHeaders()
      })
      if (!resp.ok) throw new Error('狀態查詢失敗')
      const data = await resp.json()

      pollRetryCount = 0
      error.value = ''

      const s: string | undefined = data?.data?.status
      const p = Number(data?.data?.progress ?? 0)
      uploadProgress.value = Math.max(10, Math.min(100, isFinite(p) ? p : 0))
      uploadStatus.value =
        s === 'completed' ? '分析完成' :
        s === 'failed' ? '分析失敗' :
        '分析中...'

      if (s === 'completed') {
        stopTimer() // 停止計時
        results.value = data.data ?? null
        processing.value = false
        uploadProgress.value = 100
        setupVideoTimeTracking()

        await nextTick()
        setTimeout(() => {
          createPieChart()
          createBarChart()
          createLineChart()
          if (showPoseOverlay.value) drawPoseOverlay()
        }, 80)
      } else if (s === 'failed' || s === 'error') {
        stopTimer() // 停止計時
        processing.value = false
        error.value = data?.data?.error_message || '分析失敗'
      } else {
        // processing / queued → 繼續輪詢
        pollTimer = setTimeout(run, 5000)
      }
    } catch (e: any) {
      stopTimer() // 停止計時
      pollRetryCount += 1
      const message = e?.data?.message || e?.message || String(e)

      if (pollRetryCount >= 3) {
        error.value = message
        uploadStatus.value = '狀態查詢失敗'
        processing.value = false
        stopPolling()
      } else {
        processing.value = true
        uploadStatus.value = `狀態查詢失敗，重試中 (${pollRetryCount}/3)`
        error.value = ''
        pollTimer = setTimeout(run, 3000)
      }
    }
  }

  pollTimer = setTimeout(run, 800)
}

const stopPolling = () => {
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
  stopTimer() // 確保停止計時
}

// ========= 快速重算（RULA 參數） =========
const showRescore = ref(false)
const rescoreSubmitting = ref(false)

// 比照 dashboard.vue 的預設值（不包含 frame_interval，因為快速重算不改採樣）
const rescoreForm = ref({
  wrist_twist: 1 as 1|2,
  legs: 1 as 1|2,
  muscle_use_a: 0 as 0|1,
  muscle_use_b: 0 as 0|1,
  force_load_a: 0 as 0|1|2|3,
  force_load_b: 0 as 0|1|2|3,
})

const loadOptions: { label: string; value: 0|1|2|3 }[] = [
  { label: '載重 < 4.4 磅（間歇）', value: 0 },
  { label: '載重 4.4–22 磅（間歇）', value: 1 },
  { label: '載重 4.4–22 磅（靜態或重複）', value: 2 },
  { label: '載重 > 22 磅 或 重複/衝擊', value: 3 },
]




// 從 /status 帶回的 params_json 預填（有就覆蓋，沒有就保留預設）
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

const doRescore = async () => {
  if (rescoreSubmitting.value) return
  try {
    rescoreSubmitting.value = true
    error.value = ''
    processing.value = true
    uploadStatus.value = '重新計分中...'
    uploadProgress.value = 10

    // 重算時也要計時
    startTimer()

    // 呼叫後端快速重算（不改 frame_interval）
    const resp = await fetch(`${VIDEO_API}/rescore/${analysisId}`, {
      method: 'POST',
      credentials: 'include',  // ✅ Send cookies
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeaders()  // ✅ Add JWT token
      },
      body: JSON.stringify(rescoreForm.value)
    })
    if (!resp.ok) {
      const t = await resp.text()
      throw new Error(t || '重算 API 呼叫失敗')
    }

    // 關掉彈窗並啟動既有輪詢
    showRescore.value = false
    startPolling()
  } catch (e: any) {
    stopTimer() // 發生錯誤時停止計時
    error.value = e?.message || String(e)
    processing.value = false
  } finally {
    rescoreSubmitting.value = false
  }
}

// ========= 影片與骨架 =========
const getSafeRulaScore = (frame: FrameRow | null | undefined): number | null => {
  const s = frame?.best_score as any
  if (s === null || s === undefined || s === 'NULL') return null
  const n = Number(s)
  return Number.isFinite(n) ? n : null
}

const getCurrentFrames = (): FrameRow[] => {
  return (results.value?.analysis_results as FrameRow[]) ?? []
}

const getCurrentFrameData = (): FrameRow | null => {
  const frames = getCurrentFrames()
  if (!frames.length) return null
  const idx = Math.min(currentFrameIndex.value, frames.length - 1)
  return frames[idx] ?? null
}

const getCurrentActualFrameNumber = (): number => {
  const f = getCurrentFrameData()
  return f?.frame ?? 0
}

// 連線表
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

const drawPoseOverlay = () => {
  const canvas = canvasElement.value
  const video = videoElement.value
  if (!canvas || !video) return

  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const rect = video.getBoundingClientRect()
  canvas.width = video.videoWidth || rect.width
  canvas.height = video.videoHeight || rect.height
  canvas.style.width = `${rect.width}px`
  canvas.style.height = `${rect.height}px`

  ctx.clearRect(0, 0, canvas.width, canvas.height)

  const currentFrame = getCurrentFrameData()
  if (!currentFrame) {
    ctx.fillStyle = 'rgba(255,255,255,0.9)'
    ctx.font = '16px Arial'
    ctx.fillText('無分析數據', 10, 30)
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

  const hasPose = Array.isArray(currentFrame.pose_landmarks) && currentFrame.pose_landmarks.length > 0
  if (!hasPose) {
    ctx.fillStyle = 'rgba(255,215,0,0.95)'
    ctx.font = '16px Arial'
    ctx.fillText('未檢測到姿勢（不繪製骨架）', 10, 56)
    return
  }
  drawPoseLandmarks(ctx, currentFrame.pose_landmarks as PoseLandmark[], canvas.width, canvas.height, false)
}

const setupCanvasOverlay = () => {
  const canvas = canvasElement.value
  const video = videoElement.value
  if (!canvas || !video) return

  canvas.style.position = 'absolute'
  canvas.style.top = '0'
  canvas.style.left = '0'
  canvas.style.pointerEvents = 'none'
  canvas.style.zIndex = '10'
  drawPoseOverlay()
}

const startSampledPlayback = () => {
  if (sampledPlaybackInterval || !getCurrentFrames().length) return
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
  }, 1000)
}

const stopSampledPlayback = () => {
  if (sampledPlaybackInterval) {
    clearInterval(sampledPlaybackInterval)
    sampledPlaybackInterval = null
  }
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
  currentFrameIndex.value = Math.min(maxIndex, currentFrameIndex.value + 1)
  seekToFrame(currentFrameIndex.value)
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
}

// 切換骨架
const onPoseOverlayToggle = () => {
  if (showPoseOverlay.value) {
    if (isPlaying.value) {
      startSampledPlayback()
    } else {
      drawPoseOverlay()
    }
    return
  }

  // 關閉覆蓋層：確實守衛 canvas & ctx
  stopSampledPlayback()

  const canvas = canvasElement.value
  if (!canvas) return

  const ctx = canvas.getContext('2d')
  if (!ctx) return

  ctx.clearRect(0, 0, canvas.width, canvas.height)
}

// ========= 統計與圖表 =========
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

    // 取當前時間 t0（若缺值則回退到前一幀或 0）
    const rawT0 = f?.timestamp
    const prevRaw = frames[i - 1]?.timestamp
    const nextRaw = frames[i + 1]?.timestamp

    const t0 = isFiniteNum(rawT0)
      ? rawT0
      : (isFiniteNum(prevRaw) ? prevRaw : 0)

    let dt = 0
    if (i < frames.length - 1) {
      // 中間幀：下一幀 - 當前幀；缺值時用 t0+1
      const t1 = isFiniteNum(nextRaw) ? nextRaw : (t0 + 1)
      dt = Math.max(0, t1 - t0)
    } else if (i > 0) {
      // 最後一幀：當前幀 - 前一幀；缺值時用 t0-1
      const tp = isFiniteNum(prevRaw) ? prevRaw : (t0 - 1)
      dt = Math.max(0, t0 - tp)
    } else {
      // 只有一幀：沒有時間差
      dt = 0
    }

    // 若時間戳非遞增，dt 可能為 0；保留 0 以避免負值污染
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
      labels.push(`分數 ${s}`)
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
  const labels = ['分數 1','分數 2','分數 3','分數 4','分數 5','分數 6','分數 7']
  const colors = ['#10B981','#10B981','#F59E0B','#F59E0B','#EF4444','#EF4444','#DC2626']
  const data: number[] = []
  for (let s = 1; s <= 7; s++) data.push(scoreDurations[s] || 0)

  if (barChart) barChart.destroy()
  barChart = new Chart(el, {
    type: 'bar',
    data: { labels, datasets: [{ label: '時間 (秒)', data, backgroundColor: colors, borderColor: colors, borderWidth: 1 }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: {
        y: { beginAtZero: true, title: { display: true, text: '時間 (秒)' } },
        x: { title: { display: true, text: 'RULA 分數' } }
      },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (c: any) => `時間: ${Number(c.parsed?.y ?? 0).toFixed(2)} 秒` } }
      }
    }
  })
}
const createLineChart = () => {
  const el = lineChartRef.value
  if (!el) return

  const frames = getCurrentFrames()

  // 組資料：保留無分數點（y = null），並標記 hasScore
  const points: TrendPoint[] = frames.map((f, idx) => {
    const score = getSafeRulaScore(f) // 可能為 null
    const time = (typeof f.timestamp === 'number') ? f.timestamp : null
    const x = Number(((time ?? idx)).toFixed(2)) // 沒時間就用幀號頂上
    return { x, y: score, idx, hasScore: score != null }
  })

  // ✅ SORT BY X (TIME) to prevent crossing lines
  points.sort((a, b) => a.x - b.x)

  // 若完全沒有任何點，就清空/不畫
  if (!points.length) {
    if (lineChart) { lineChart.destroy(); lineChart = null }
    return
  }

  // 關鍵：把 TrendPoint[] 轉型給 Chart 泛型允許的型別 (Point|null)[]
  const dataForChart = points as unknown as (Point | null)[]

  if (lineChart) lineChart.destroy()
  lineChart = new Chart<"line", (Point | null)[], unknown>(el, {
    type: 'line',
    data: {
      datasets: [
        {
          label: 'RULA 分數',
          data: dataForChart,     // ← 泛型一致
          borderWidth: 2,
          tension: 0.25,
          fill: false,
          spanGaps: true,
          parsing: false,
          pointRadius: (ctx) => {
            // raw 實際仍是 TrendPoint，我們轉回來用
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
              const t = (p && typeof p.x === 'number') ? p.x.toFixed(2) : ''
              return `時間 ${t}s`
            },
            label: (item: any) => {
              const p = (item?.raw ?? null) as TrendPoint | null
              return (p && p.hasScore) ? `RULA 分數: ${p.y}` : '無分數'
            }
          }
        }
      },
      scales: {
        x: {
          type: 'linear',
          title: { display: true, text: '時間 (秒)' },
          ticks: { callback: (v: any) => Number(v).toFixed(1) }
        },
        y: {
          title: { display: true, text: 'RULA 分數' },
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
        // ds!.data 的靜態型別是 (Point|null)[]，但實際值仍是 TrendPoint[]
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
    const hasPose = !!(f.pose_landmarks?.length)
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

// ========= 下載 CSV =========
const downloadResults = async () => {
  try {
    const resp = await fetch(`${VIDEO_API}/download/${analysisId}`, {
      method: 'GET',
      credentials: 'include',  // ✅ Send cookies
      headers: {
        Accept: 'text/csv',
        ...getAuthHeaders()
      }
    })
    if (!resp.ok) {
      const raw = await resp.text()
      try {
        const parsed = JSON.parse(raw)
        throw new Error(parsed?.message || raw || '下載失敗')
      } catch {
        throw new Error(raw || '下載失敗')
      }
    }
    const blob = await resp.blob()
    const okType = ['text/csv','application/octet-stream','application/vnd.ms-excel','text/plain']
    if (!okType.includes(blob.type)) { error.value = `下載的檔案格式錯誤 (收到 ${blob.type})`; return }
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `rula_analysis_${analysisId}.csv`
    document.body.appendChild(a); a.click(); document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch (e: any) {
    error.value = `下載失敗: ${e?.message || e}`
  }
}

// ========= 返回鍵 =========
const goBack = () => {
  router.back()
}

// ========= 生命週期 =========
onMounted(() => {
  const url = sessionStorage.getItem('hfe_video_object_url') || ''
  if (url) originalVideoUrl.value = url
  startPolling()
})

onUnmounted(() => {
  stopPolling()
  stopSampledPlayback()
  stopTimer() // 確保清理計時器
  if (pieChart) pieChart.destroy()
  if (barChart) barChart.destroy()
  if (lineChart) lineChart.destroy()

  const url = sessionStorage.getItem('hfe_video_object_url')
  if (url) {
    URL.revokeObjectURL(url)
    sessionStorage.removeItem('hfe_video_object_url')
  }
})

// 監看：結果出現
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

watch([showPoseOverlay, results], () => {
  if (results.value) onPoseOverlayToggle()
})

// 安全取得：時間字串 / 分數字串
const getCurrentTimestampText = () => {
  const t = getCurrentFrameData()?.timestamp
  const v = typeof t === 'number' ? t : currentVideoTime.value
  return v.toFixed(2)
}

const getCurrentBestScoreText = () => {
  const s = getSafeRulaScore(getCurrentFrameData())
  return s == null ? 'NULL' : String(s)
}
</script>

<template>
  <div class="min-h-dvh p-6">
    <!-- 頁首 -->
    <div class="flex justify-between items-center mb-6">
      <h1 class="text-2xl font-bold">RULA 影片分析</h1>
      <div class="flex gap-2">
        <Button
          label="調整 RULA 參數（快速重算）"
          icon="pi pi-sliders-h"
          :disabled="processing"
          @click="openRescore"
        />
        <Button label="回上一頁" icon="pi pi-arrow-left" severity="secondary" @click="goBack" />
        <Button label="回首頁" icon="pi pi-home" severity="secondary" @click="$router.push('/')" />
      </div>
    </div>

    <!-- 錯誤 -->
    <Message v-if="error" severity="error" class="mb-4">{{ error }}</Message>

    <!-- 進度 -->
    <Card v-if="processing" class="mb-6">
      <template #content>
        <div class="text-center">
          <ProgressBar :value="Number(uploadProgress.toFixed(1))" class="mb-2" />
          <p class="text-lg font-medium">{{ uploadStatus }}</p>
          <div class="flex justify-center items-center gap-4 mt-2">
            <p class="text-sm text-gray-600">系統正在分析，請稍候...</p>
            <div class="flex items-center gap-1 text-sm text-blue-600">
              <i class="pi pi-clock"></i>
              <span class="font-mono">{{ formatElapsedTime(elapsedTime) }}</span>
            </div>
          </div>
          
        </div>
      </template>
    </Card>

    <!-- 內容 -->
    <div v-if="!processing" class="space-y-4">
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <!-- 視訊與覆蓋 -->
        <div class="lg:col-span-2">
          <Card>
            <template #title>
              <div class="flex justify-between items-center">
                <span>影片與骨架</span>
                <Button label="下載結果" icon="pi pi-download" size="small" @click="downloadResults" />
              </div>
            </template>
            <template #content>
              <div class="relative">
                <video ref="videoElement" :src="originalVideoUrl" :controls="false" class="w-full border rounded" />
                <canvas
                  ref="canvasElement"
                  class="absolute top-0 left-0 pointer-events-none rounded"
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
                  <label for="poseOverlay" class="text-sm font-medium cursor-pointer">顯示姿勢骨架</label>
                </div>
                <small class="text-gray-500">若無影片來源也可瀏覽下方圖表與統計</small>
              </div>

              <!-- 採樣播放控制 -->
              <div v-if="results" class="mt-4 p-3 bg-gray-50 rounded">
                <h5 class="font-semibold mb-3 text-sm">採樣播放控制</h5>
                <div class="flex items-center gap-2 mb-3">
                  <Button label="上一幀" icon="pi pi-step-backward" size="small" severity="secondary" @click="previousFrame" />
                  <Button label="下一幀" icon="pi pi-step-forward" size="small" severity="secondary" @click="nextFrame" />
                  <span class="text-sm text-gray-600 ml-2">
                    幀 {{ currentFrameIndex + 1 }} / {{ results?.analysis_results?.length || 0 }}
                  </span>
                </div>
                <div class="flex items-center gap-2">
                  <Button label="開始採樣播放" icon="pi pi-play" size="small" severity="success" @click="startSampledPlayback" />
                  <Button label="停止播放" icon="pi pi-stop" size="small" severity="danger" @click="stopSampledPlayback" />
                </div>
              </div>
            </template>
          </Card>

          <!-- AI Counselor Section（放左側下方，正常佈局） -->
          <div class="mt-4">
            <RulaCounselor
              :analysis-id="analysisId"
              :auth-headers="getAuthHeaders()"
              :disabled="false"
              @loading="(isLoading) => {}"
              @loaded="(data) => {}"
              @error="(err) => console.error('Counselor error:', err)"
            />
          </div>
        </div>

        <!-- 統計與圖表 -->
        <div class="space-y-4">
          <Card>
            <template #title>分析總覽</template>
            <template #content>
              <div class="grid grid-cols-2 gap-3">
                <div class="bg-blue-50 p-3 rounded">
                  <div class="text-xs font-semibold text-blue-800">總幀數</div>
                  <div class="text-lg font-bold text-blue-600">{{ getFrameStatistics().totalFrames }}</div>
                </div>
                <div class="bg-green-50 p-3 rounded">
                  <div class="text-xs font-semibold text-green-800">有效幀數</div>
                  <div class="text-lg font-bold text-green-600">{{ getFrameStatistics().validFrames }}</div>
                </div>
                <div class="bg-red-50 p-3 rounded">
                  <div class="text-xs font-semibold text-red-800">無效幀數</div>
                  <div class="text-lg font-bold text-red-600">{{ getFrameStatistics().invalidFrames }}</div>
                </div>
                <div class="bg-purple-50 p-3 rounded">
                  <div class="text-xs font-semibold text-purple-800">影片長度</div>
                  <div class="text-lg font-bold text-purple-600">{{ getFrameStatistics().duration.toFixed(1) }}s</div>
                </div>
              </div>
              <div class="mt-3 grid grid-cols-2 gap-3">
                <div class="bg-yellow-50 p-3 rounded">
                  <div class="text-xs font-semibold text-yellow-800">平均分數</div>
                  <div class="text-lg font-bold text-yellow-600">
                    {{ results?.statistics?.average_score?.toFixed(1) || results?.results?.avg_rula_score?.toFixed(1) || '0.0' }}
                  </div>
                </div>
                <div class="bg-indigo-50 p-3 rounded">
                  <div class="text-xs font-semibold text-indigo-800">
                    最高分數
                  </div>
                  <div class="text-lg font-bold text-indigo-600">
                    {{ getMaxRulaScoreText() }}
                  </div>
                </div>
              </div>
            </template>
          </Card>

          <Card>
            <template #title>當前幀資訊</template>
            <template #content>
              <div v-if="results && results.analysis_results?.length" class="text-sm space-y-2">
                <div class="flex justify-between">
                  <strong>幀索引 (Frame):</strong>
                  <span class="font-mono">{{ getCurrentActualFrameNumber() }}</span>
                </div>

                <div class="flex justify-between">
                  <strong>時間戳 (Time):</strong>
                  <span class="font-mono">{{ getCurrentTimestampText() }}s</span>
                </div>

                <div class="flex justify-between items-center">
                  <strong>RULA 分數:</strong>
                  <div class="flex items-center gap-2">
                    <Badge
                      v-if="getSafeRulaScore(getCurrentFrameData()) !== null"
                      :value="Math.round(getSafeRulaScore(getCurrentFrameData())!)"
                      :severity="getSafeRulaScore(getCurrentFrameData())! <= 2 ? 'success'
                              : getSafeRulaScore(getCurrentFrameData())! <= 4 ? 'warning' : 'danger'"
                    />
                    <span v-else class="text-gray-500 italic">NULL</span>
                    <small class="text-gray-500 font-mono">({{ getCurrentBestScoreText() }})</small>
                  </div>
                </div>
              </div>
              <div v-else class="text-gray-500">此時間點無數據</div>
            </template>
          </Card>

          <Card>
            <template #title>圖表分析</template>
            <template #content>
              <div class="mb-6">
                <h5 class="text-sm font-medium mb-2 text-gray-700">RULA 分數趨勢</h5>
                <div class="bg-white p-3 rounded border" style="height: 260px;">
                  <canvas ref="lineChartRef"></canvas>
                </div>
              </div>
              <div class="mb-6">
                <h5 class="text-sm font-medium mb-2 text-gray-700">分數占比分佈</h5>
                <div class="bg-white p-3 rounded border" style="height: 250px;">
                  <canvas ref="pieChartRef"></canvas>
                </div>
              </div>
              <div>
                <h5 class="text-sm font-medium mb-2 text-gray-700">各分數時間分佈</h5>
                <div class="bg-white p-3 rounded border" style="height: 250px;">
                  <canvas ref="barChartRef"></canvas>
                </div>
              </div>
              <div class="mt-2 text-xs text-gray-600 bg-gray-100 p-2 rounded">
                <div class="flex items-center mb-1"><div class="w-3 h-3 bg-green-500 rounded mr-2"></div><span>分數 1-2: acceptable posture</span></div>
                <div class="flex items-center mb-1"><div class="w-3 h-3 bg-yellow-500 rounded mr-2"></div><span>分數 3-4: further investigation, change may be needed</span></div>
                <div class="flex items-center mb-1"><div class="w-3 h-3 bg-red-500 rounded mr-2"></div><span>分數 5-6: further investigation, change soon</span></div>
                <div class="flex items-center"><div class="w-3 h-3 bg-red-600 rounded mr-2"></div><span>分數 7: investigate and implement change</span></div>
              </div>
            </template>
          </Card>
        </div>
      </div>
    </div>

    <!-- 調整 RULA 參數（快速重算）Dialog -->
    <Dialog v-model:visible="showRescore" modal header="調整 RULA 參數（不重跑 MediaPipe）" :style="{ width: '520px' }">
      <RulaParamsForm
        v-model="rescoreForm"
        :load-options="loadOptions"
        :submitting="rescoreSubmitting"
        id-prefix="rescore"
      />

      <template #footer>
        <Button label="取消" severity="secondary" :disabled="rescoreSubmitting" @click="showRescore=false" />
        <Button label="送出重算" icon="pi pi-check" :loading="rescoreSubmitting" @click="doRescore" />
      </template>
    </Dialog>

  </div>
</template>

<style scoped>
/* 依需要微調 Dialog 內 select 的外觀（若你已用 PrimeVue Theme 可省略） */
.p-inputtext {
  border: 1px solid #d1d5db;
  padding: 0.5rem 0.6rem;
  border-radius: 6px;
}
</style>