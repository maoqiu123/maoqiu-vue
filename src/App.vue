<template>
  <div id="app" class="workbench-bg">
    <div v-if="activeView === 'data-screen'" class="data-screen-light animate-fade-in">
      <header class="screen-header-light">
        <div class="header-left">
          <button class="back-link" @click="activeView = 'main'">
            <i class="fa fa-chevron-left"></i> 返回工作台
          </button>
        </div>
        <h1 class="header-title-light">相似材料配方数据集全景监控看板</h1>
        <div class="header-right">
          <span class="status-tag"><span class="dot-green"></span> 数据库实时同步: {{ recipeListData.length }} 条</span>
        </div>
      </header>

      <main class="screen-content">
        <div class="stats-grid-2">
          <div v-for="stat in stats" :key="stat.label"
               :class="['stat-item-card', { 'stat-clickable': stat.clickable }]"
               @click="stat.clickable ? (showMaterialsModal = true) : null">
            <div :class="['stat-icon-box', stat.colorClass]"><i :class="stat.icon"></i></div>
            <div class="stat-texts">
              <span class="stat-label">{{ stat.label }}</span>
              <span class="stat-value">{{ stat.value }} <small>{{ stat.unit }}</small></span>
              <div v-if="stat.clickable" class="click-hint"><i class="fa fa-th-large"></i> 点击查看图谱</div>
            </div>
          </div>
        </div>

        <div class="screen-main-grid">
          <div class="card-white chart-container-card full-width">
            <div class="card-header-bold flex justify-between items-center">
              <span>全样本物理力学性质分布趋势 (支持鼠标滚轮缩放)</span>
              <select v-model="currentTrendMetric" @change="initLightDashboard" class="trend-select">
                <option value="density">密度 (g/cm³)</option>
                <option value="tensile">抗拉强度 (MPa)</option>
                <option value="strength">抗压强度 (MPa)</option>
                <option value="elastic">弹性模量 (MPa)</option>
                <option value="poisson">泊松比</option>
              </select>
            </div>
            <div ref="distributionChart" class="canvas-box"></div>
          </div>

          <div class="table-column card-white full-width">
            <div class="card-header-bold flex justify-between items-center">
              <span>数据集配方清单明细</span>
              <button class="text-blue-600 text-xs font-semibold hover:underline">
                导出全量数据 <i class="fa fa-download ml-1"></i>
              </button>
            </div>
            <div class="table-wrapper">
              <table class="modern-table">
                <thead>
                  <tr>
                    <th>编号</th>
                    <th>配方组成</th>
                    <th>密度 (g/cm³)</th>
                    <th>抗拉强度 (MPa)</th>
                    <th>抗压强度 (MPa)</th>
                    <th>弹性模量 (MPa)</th>
                    <th>泊松比</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="item in recipeListData" :key="item.id">
                    <td>#{{ item.id }}</td>
                    <td class="composition-summary">{{ formatComposition(item.components) }}</td>
                    <td>{{ item.density || '-' }}</td>
                    <td>{{ item.tensile || '-' }}</td>
                    <td class="font-bold text-blue-600">{{ item.strength || '-' }}</td>
                    <td>{{ item.elastic || '-' }}</td>
                    <td>{{ item.poisson || '-' }}</td>
                    <td><button class="action-link" @click="showRecipeDetails(item)">配方明细</button></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </main>

      <div v-if="showMaterialsModal" class="modal-overlay-light" @click.self="showMaterialsModal = false">
        <div class="detail-modal-light animate-fade-in" style="width: 700px;">
          <div class="modal-header-light">
            <h3>数据集包含的具体材料种类图谱</h3>
            <button class="close-btn-light" @click="showMaterialsModal = false">×</button>
          </div>
          <div class="modal-body-light" style="background: #f8fafc;">
            <div class="material-grid">
              <div v-for="mat in uniqueMaterials" :key="mat" class="material-card" @click="openImagePreview(mat)">
                <div class="img-wrapper">
                  <img :src="getMaterialImage(mat)" :alt="mat" />
                  <div class="img-overlay"><i class="fa fa-search-plus"></i></div>
                </div>
                <span class="material-name">{{ mat }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="showImagePreview" class="modal-overlay-light preview-overlay animate-fade-in" @click.self="showImagePreview = false">
        <div class="preview-container">
          <button class="close-preview-btn" @click="showImagePreview = false"><i class="fa fa-times-circle"></i></button>
          <img :src="previewImageUrl" class="preview-img" />
          <h3 class="preview-title">{{ previewImageTitle }}</h3>
        </div>
      </div>

      <div v-if="showRecipeModal && currentRecipeDetail" class="modal-overlay-light" @click.self="showRecipeModal = false">
        <div class="detail-modal-light animate-fade-in" style="width: 800px;">
          <div class="modal-header-light">
            <h3>配方样本 #{{ currentRecipeDetail.id }} 详细参数</h3>
            <button class="close-btn-light" @click="showRecipeModal = false">×</button>
          </div>
          <div class="modal-body-light recipe-modal-body">
            <div class="recipe-props-side">
              <h4 class="sub-title"><i class="fa fa-sliders text-blue-500 mr-2"></i>物理力学性质</h4>
              <ul class="prop-list">
                <li><span>密度:</span> <b>{{ currentRecipeDetail.density || '-' }} <small>g/cm³</small></b></li>
                <li><span>抗拉强度:</span> <b>{{ currentRecipeDetail.tensile || '-' }} <small>MPa</small></b></li>
                <li><span>抗压强度:</span> <b class="text-blue-600">{{ currentRecipeDetail.strength || '-' }} <small>MPa</small></b></li>
                <li><span>弹性模量:</span> <b>{{ currentRecipeDetail.elastic || '-' }} <small>MPa</small></b></li>
                <li><span>泊松比:</span> <b>{{ currentRecipeDetail.poisson || '-' }}</b></li>
              </ul>
            </div>
            <div class="recipe-chart-side">
              <h4 class="sub-title"><i class="fa fa-bar-chart text-blue-500 mr-2"></i>真实组分质量配比 (%)</h4>
              <div v-if="currentComposition.length" class="composition-detail-list">
                <div v-for="item in currentComposition" :key="item.name" class="composition-detail-row">
                  <div class="composition-detail-head">
                    <span class="composition-material">{{ item.name }}</span>
                    <b>{{ formatPercent(item.value) }}</b>
                  </div>
                  <div class="composition-progress">
                    <span :style="{ width: Math.min(item.value * 100, 100) + '%' }"></span>
                  </div>
                </div>
              </div>
              <div v-else class="composition-empty">该样本暂无配方组成数据</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="system-layout animate-fade-in">
      <header class="system-header">
        <div class="header-container">
          <div class="brand">
            <span class="breadcrumb">控制面板 / 当前模块</span>
            <h1 class="workbench-title">相似材料配方逆向设计工作台</h1>
          </div>
          <div class="header-meta">
            <a href="/discovery-loop.html" class="loop-entry-btn">
              <i class="fa fa-refresh mr-2"></i> 可信反馈闭环
            </a>
            <button @click="activeView = 'data-screen'" class="dashboard-entry-btn">
              <i class="fa fa-bar-chart mr-2"></i> 数据看板
            </button>
            <span class="engine-status"><span class="dot-green"></span> 推理引擎在线</span>
            <span class="date-display">{{ currentDate }}</span>
          </div>
        </div>
      </header>

      <main class="workbench-content">
        <div class="workbench-grid">
          <div class="input-panel">
            <section class="card-white workbench-card">
              <h2 class="card-title"><i class="fa fa-commenting-o"></i> 语义目标解析 (Target Parsing)</h2>
              <textarea
                v-model="naturalLanguageInput"
                placeholder="在此输入目标岩石的物理及力学性质描述示例：抗压强度0.482, 抗拉强度0.055, 泊松比0.12,弹性模量54.517。"
                class="modern-textarea"
              ></textarea>
              <button @click="extractParameters" class="btn-dark-action">
                <i class="fa fa-magic mr-2"></i> 提取并映射至力学参数
              </button>
            </section>

            <section class="card-white workbench-card">
              <h2 class="card-title"><i class="fa fa-sliders"></i> 力学性质与约束设定 (Constraints)</h2>
              <div class="params-form">
                <div v-for="(label, key) in constraintFields" :key="key" class="form-item">
                  <label>{{ label }} <span class="req">*</span></label>
                  <div class="input-container">
                    <input type="number" v-model="rockForm[key]" placeholder="0.000">
                    <span class="unit-label">{{ getUnit(key) }}</span>
                  </div>
                </div>
              </div>
              <div class="algo-toggle">
                <button @click="modelType = 'llm'" :class="{active: modelType === 'llm'}">大模型算法</button>
                <button @click="modelType = 'quantum'" :class="{active: modelType === 'quantum'}">量子计算</button>
              </div>
              <button @click="generateFormula" :disabled="!allValid || isGenerating" class="btn-primary-launch">
                <i :class="['fa', isGenerating ? 'fa-spinner fa-spin' : 'fa-paper-plane', 'mr-2']"></i>
                {{ isGenerating ? '模型正在生成配方...' : '启动神经符号推理与逆向设计' }}
              </button>
            </section>
          </div>

          <div class="result-panel">
            <div v-if="generationError" class="card-white generation-error animate-fade-in">
              <i class="fa fa-exclamation-triangle"></i>
              <div>
                <h3>当前模型无法生成推荐配方</h3>
                <p>{{ generationError }}</p>
              </div>
            </div>

            <div v-else-if="showResults" class="results-active animate-fade-in">
              <section class="card-white workbench-card result-main">
                <div class="result-header">
                  <div class="header-info">
                    <h2 class="card-title">最优推荐配方 (Candidate Top-1)</h2>
                    <p class="card-sub">{{ resultModelLabel }}，与目标参数的综合相似度为 {{ resultSimilarityText }}</p>
                    <p v-if="resultReason" class="result-reason">{{ resultReason }}</p>
                  </div>
                  <button class="btn-export"><i class="fa fa-file-excel-o mr-1"></i> 导出配方参数</button>
                </div>

                <div class="result-charts">
                  <div class="segmented-bar-item animate-fade-in">
                    <h3 class="chart-inner-title">相似材料组分质量配比 (%)</h3>

                    <div class="segmented-bar-wrapper" ref="segmentedBarRef">
                      <div class="segmented-bar-container">
                        <div
                          v-for="(label, index) in genLabels"
                          :key="label"
                          class="bar-segment"
                          :style="{
                            width: genData[index] + '%',
                            background: getComponentColor(label, index)
                          }"
                        >
                          <div class="static-label-wrapper">
                            <div class="static-label-box">
                              <img :src="getMaterialImage(label)" class="static-mat-img" />
                              <div class="static-text-info">
                                <span class="label-text">{{ label }}</span>
                                <span class="label-percent">{{ genData[index] }}%</span>
                              </div>
                            </div>
                            <div class="label-line"></div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div class="chart-item border-l">
                    <h3 class="chart-inner-title">多维度物理性质拟合验证</h3>
                    <div class="chart-canvas-wrapper">
                      <canvas ref="comparisonChartRef"></canvas>
                    </div>
                  </div>
                </div>
              </section>

              <section class="card-white workbench-card">
                <h2 class="card-title"><i class="fa fa-gears"></i> 制备工艺流程与约束图谱</h2>
                <div class="process-list">
                  <div v-for="(step, i) in processSteps" :key="i" class="process-row">
                    <span class="step-num">步骤 {{ i+1 }}:</span>
                    <span class="step-title">{{ step.title }}</span>
                    <span class="step-desc">- {{ step.description }}</span>
                  </div>
                </div>
              </section>
            </div>

            <div v-else class="empty-state">
              <div class="empty-icon"><i class="fa fa-pie-chart"></i></div>
              <p>请在左侧设定参数生成设计方案</p>
            </div>
          </div>
        </div>
      </main>
    </div>

    <div :class="['toast-msg', { show: showToast }]">
      <i class="fa fa-check-circle mr-2"></i> {{ toastMessage }}
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import axios from 'axios'
import * as echarts from 'echarts'

export default {
  name: 'App',
  setup() {
    const activeView = ref('main')
    const currentDate = ref('')
    const naturalLanguageInput = ref('示例描述：抗压强度0.482, 抗拉强度0.055, 泊松比0.12,弹性模量54.517。')
    const rockForm = ref({ compressive: 0, tensile: 0, poisson: 0, elastic: 0, density: 0, hardness: 0 })
    const modelType = ref('llm')
    const showResults = ref(false)
    const showToast = ref(false)
    const toastMessage = ref('')

    const recipeListData = ref([])
    const currentRecipeDetail = ref(null)

    const showMaterialsModal = ref(false)
    const showRecipeModal = ref(false)
    const showImagePreview = ref(false)
    const previewImageUrl = ref('')
    const previewImageTitle = ref('')

    const segmentedBarRef = ref(null);
    const currentTrendMetric = ref('tensile')

    let radarChartObj = null

    // 后端模型返回的推荐配方
    const genLabels = ref([])
    const genData = ref([])
    const predictedProperties = ref({})
    const resultSimilarity = ref(null)
    const resultModelLabel = ref('')
    const resultReason = ref('')
    const isGenerating = ref(false)
    const generationError = ref('')

    const componentColors = {
      '石英砂': '#94a3b8',
      '水泥': '#cbd5e1',
      '细砂': '#a16207',
      '水': '#3b82f6',
      '减水剂': '#10b981',
    }

    const fallbackComponentColors = ['#64748b', '#2563eb', '#7c3aed', '#db2777', '#ea580c', '#16a34a', '#0891b2', '#ca8a04']
    const getComponentColor = (label, index) => componentColors[label] || fallbackComponentColors[index % fallbackComponentColors.length]

    const resultSimilarityText = computed(() => {
      if (resultSimilarity.value === null) return '未计算'
      return `${(Number(resultSimilarity.value) * 100).toFixed(1)}%`
    })

    const uniqueMaterials = computed(() => {
      const mats = new Set()
      recipeListData.value.forEach(item => {
        if (item.components) Object.keys(item.components).forEach(k => mats.add(k))
      })
      Object.keys(componentColors).forEach(k => mats.add(k))
      return Array.from(mats)
    })

    const sortedCompositionEntries = (components = {}) => Object.entries(components)
      .filter(([, value]) => Number(value) > 0)
      .sort((a, b) => Number(b[1]) - Number(a[1]))

    const formatPercent = (value) => {
      const percent = Number(value) * 100
      return `${percent.toFixed(2).replace(/\.?0+$/, '')}%`
    }

    const formatComposition = (components) => {
      const entries = sortedCompositionEntries(components)
      if (!entries.length) return '-'
      const visible = entries.slice(0, 4).map(([name, value]) => `${name} ${formatPercent(value)}`)
      return entries.length > 4 ? `${visible.join('、')} 等${entries.length}种` : visible.join('、')
    }

    const currentComposition = computed(() =>
      sortedCompositionEntries(currentRecipeDetail.value?.components).map(([name, value]) => ({
        name,
        value: Number(value)
      }))
    )

    const stats = computed(() => [
      { label: '材料种类总计', value: uniqueMaterials.value.length, unit: '类', icon: 'fa fa-cubes', colorClass: 'text-blue-500 bg-blue-50', clickable: true },
      { label: '配方样本总数', value: recipeListData.value.length, unit: '组', icon: 'fa fa-database', colorClass: 'text-indigo-500 bg-indigo-50', clickable: false }
    ])

    const constraintFields = { compressive:'抗压强度', tensile:'抗拉强度', poisson:'泊松比', elastic:'弹性模量', density:'密度', hardness:'硬度' }
    const getUnit = (k) => ({ compressive:'MPa', tensile:'MPa', poisson:'', elastic:'GPa', density:'g/cm³', hardness:'HRC' }[k])

    const processSteps = [
      { title: '原材料预处理', description: '精确称取基质材料与胶结剂，过2mm标准筛保证骨料料均度。' },
      { title: '混合与水化控制', description: '干拌2分钟，分批次注入溶剂（含减水剂），控制水化热响应。' },
      { title: '成型与养护环境', description: '模具内真空脱泡处理，置于标准养护箱（20±2℃，湿度≥95%）养护28天。' }
    ]

    const distributionChart = ref(null)
    const comparisonChartRef = ref(null)

    const allValid = computed(() => rockForm.value.compressive > 0)

    const showToastMessage = (msg) => {
      toastMessage.value = msg; showToast.value = true;
      setTimeout(() => showToast.value = false, 3000)
    }

    // 材料图片映射与处理逻辑
    const materialImageMap = {
      '标准砂': new URL('./assets/images/sink.jpeg', import.meta.url).href,
      '水泥': new URL('./assets/images/shuini.jpeg', import.meta.url).href,
      '硅油': new URL('./assets/images/guiyou.jpg', import.meta.url).href,
      '水': new URL('./assets/images/water.jpeg', import.meta.url).href,
      '石膏': new URL('./assets/images/shigao.jpeg', import.meta.url).href,
      '石英砂': new URL('./assets/images/shiyingsha.jpeg', import.meta.url).href,
      '云母粉': new URL('./assets/images/yunmufen.jpeg', import.meta.url).href,
      '粉煤灰': new URL('./assets/images/fenmeihui.jpeg', import.meta.url).href,
      '外加剂': new URL('./assets/images/waijiaji.jpeg', import.meta.url).href,
      '液体石蜡': new URL('./assets/images/yetishila.jpeg', import.meta.url).href,
      '重晶石粉': new URL('./assets/images/chongjingshifen.jpeg', import.meta.url).href,
      '铁矿粉': new URL('./assets/images/tiekuangfen.jpg', import.meta.url).href,
      '伊利石': new URL('./assets/images/yilishi.jpeg', import.meta.url).href,
      '绿泥石': new URL('./assets/images/lvnishi.jpg', import.meta.url).href,
      '松香': new URL('./assets/images/songxiang.jpeg', import.meta.url).href,
      '硅藻土': new URL('./assets/images/guizaotu.jpeg', import.meta.url).href,
      '红粘土': new URL('./assets/images/hongniantu.jpeg', import.meta.url).href,
      '石灰石粉': new URL('./assets/images/shihuishifen.jpeg', import.meta.url).href,
      '河砂': new URL('./assets/images/hesha.png', import.meta.url).href,
      '蒙脱石': new URL('./assets/images/mengtuoshi.jpeg', import.meta.url).href,
      '膨润土': new URL('./assets/images/pengruntu.jpeg', import.meta.url).href,
      '凡士林': new URL('./assets/images/fanshilin.jpeg', import.meta.url).href,
      '减水剂': new URL('./assets/images/jianshuiji.jpeg', import.meta.url).href,
      '缓凝剂': new URL('./assets/images/huanningji.jpeg', import.meta.url).href,
      '铁精粉': new URL('./assets/images/tiejingfen.jpeg', import.meta.url).href,
      '滑石粉': new URL('./assets/images/huashifen.jpg', import.meta.url).href,
      '液压油': new URL('./assets/images/yeyayou.jpeg', import.meta.url).href,
      '粉细砂': new URL('./assets/images/fenxisha.jpeg', import.meta.url).href,
      '黏土': new URL('./assets/images/niantu.webp', import.meta.url).href,
      '铁粉': new URL('./assets/images/tiefen.jpeg', import.meta.url).href,
      '超塑化剂': new URL('./assets/images/chaosuhuaji.jpeg', import.meta.url).href,
      '碳酸钠': new URL('./assets/images/tansuanna.jpeg', import.meta.url).href,
      '甘油': new URL('./assets/images/ganyou.jpeg', import.meta.url).href,
      '黄砂': new URL('./assets/images/huangsha.jpeg', import.meta.url).href,
      '酒精': new URL('./assets/images/jiujing.jpeg', import.meta.url).href,
      '钠谷氨酸': new URL('./assets/images/na.jpeg', import.meta.url).href,
      '乳胶粉': new URL('./assets/images/rujiao.jpeg', import.meta.url).href,
      '砂子': new URL('./assets/images/sha.jpeg', import.meta.url).href,
      '羧甲基纤维素钠': new URL('./assets/images/suo.jpeg', import.meta.url).href,
      '细砂': new URL('./assets/images/sha.jpeg', import.meta.url).href
    }

    const getMaterialImage = (mat) => {
      if (materialImageMap[mat]) return materialImageMap[mat]
      return `https://ui-avatars.com/api/?name=${encodeURIComponent(mat)}&background=e2e8f0&color=3b82f6&size=200&font-size=0.3&bold=true`
    }

    const openImagePreview = (mat) => {
      previewImageUrl.value = getMaterialImage(mat)
      previewImageTitle.value = mat
      showImagePreview.value = true
    }

    const fetchDataset = async () => {
      try {
        const res = await axios.get('http://127.0.0.1:5000/api/dataset')
        recipeListData.value = res.data
        if (activeView.value === 'data-screen') initLightDashboard()
      } catch (err) {
        showToastMessage('⚠ 无法连接至本地后端 (127.0.0.1:5000)')
      }
    }

    const initLightDashboard = () => {
      nextTick(() => {
        const data = recipeListData.value
        if (!data.length || !distributionChart.value) return

        const chart = echarts.getInstanceByDom(distributionChart.value) || echarts.init(distributionChart.value)

        const metric = currentTrendMetric.value
        const metricConfig = {
          'density': { name: '密度 (g/cm³)', color: '#10b981', area: 'rgba(16, 185, 129, 0.1)' },
          'tensile': { name: '抗拉强度 (MPa)', color: '#f59e0b', area: 'rgba(245, 158, 11, 0.1)' },
          'strength': { name: '抗压强度 (MPa)', color: '#3b82f6', area: 'rgba(59, 130, 246, 0.1)' },
          'elastic': { name: '弹性模量 (MPa)', color: '#8b5cf6', area: 'rgba(139, 92, 246, 0.1)' },
          'poisson': { name: '泊松比', color: '#ec4899', area: 'rgba(236, 72, 153, 0.1)' }
        }
        const config = metricConfig[metric]

        chart.setOption({
          grid: { top: 30, bottom: 60, left: 50, right: 20 },
          tooltip: {
            trigger: 'axis',
            formatter: function(params) {
              const p = params[0];
              if (p.value === null || p.value === undefined) {
                return `${p.name}<br/><span style="color:${config.color}">●</span> ${p.seriesName}: <b>未测试</b>`;
              }
              return `${p.name}<br/><span style="color:${config.color}">●</span> ${p.seriesName}: <b>${p.value}</b>`;
            }
          },
          dataZoom: [
            { type: 'slider', xAxisIndex: 0, height: 20, bottom: 10, start: 0, end: 100 },
            { type: 'inside', xAxisIndex: 0 },
            { type: 'inside', yAxisIndex: 0 }
          ],
          xAxis: { type: 'category', data: data.map(i => '#' + i.id), axisLine: { lineStyle: { color: '#e2e8f0' } } },
          yAxis: { type: 'value', name: config.name, scale: true, splitLine: { lineStyle: { type: 'dashed', color: '#f1f5f9' } } },
          series: [{
            name: config.name,
            type: 'line',
            smooth: true,
            data: data.map(i => (i[metric] === 0 || !i[metric]) ? null : i[metric]),
            connectNulls: true,
            showSymbol: true,
            symbolSize: 6,
            symbol: 'emptyCircle',
            color: config.color,
            areaStyle: { color: config.area }
          }]
        }, true)
      })
    }

    const showRecipeDetails = (item) => {
      currentRecipeDetail.value = item
      showRecipeModal.value = true
    }

    const initResultCharts = () => {
      if (comparisonChartRef.value) {
        if (radarChartObj) radarChartObj.destroy()

        const targetData = [
          parseFloat(rockForm.value.compressive) || 0,
          parseFloat(rockForm.value.tensile) || 0,
          parseFloat(rockForm.value.elastic) || 0,
          parseFloat(rockForm.value.poisson) || 0,
          parseFloat(rockForm.value.density) || 0,
          parseFloat(rockForm.value.hardness) || 0
        ]

        const predictedKeys = ['compressive', 'tensile', 'elastic', 'poisson', 'density', 'hardness']
        const predictedData = predictedKeys.map(key => {
          const value = predictedProperties.value[key]
          return value === null || value === undefined ? 0 : Number(value)
        })

        const maxValues = targetData.map((t, i) => Math.max(t, predictedData[i], 1) * 1.2)
        const normTarget = targetData.map((v, i) => (v / maxValues[i]) * 100)
        const normPredicted = predictedData.map((v, i) => (v / maxValues[i]) * 100)

        radarChartObj = new window.Chart(comparisonChartRef.value, {
          type: 'radar',
          data: {
            labels: ['抗压(MPa)', '抗拉(MPa)', '弹性', '泊松比', '密度', '硬度'],
            datasets: [
              { label: '目标设定', data: normTarget, borderColor: '#cbd5e1', backgroundColor: 'rgba(203, 213, 225, 0.2)', pointBackgroundColor: '#94a3b8' },
              { label: '模型预测', data: normPredicted, borderColor: '#3b82f6', backgroundColor: 'rgba(59, 130, 246, 0.3)', pointBackgroundColor: '#2563eb' }
            ]
          },
          options: {
            scales: { r: { min: 0, max: 100, ticks: { display: false }, grid: { color: '#f1f5f9' }, angleLines: { color: '#e2e8f0' } } },
            plugins: {
              legend: { position: 'bottom', labels: { boxWidth: 10 } },
              tooltip: {
                callbacks: {
                  label: function(context) {
                    const datasetLabel = context.dataset.label || '';
                    const realValue = context.datasetIndex === 0 ? targetData[context.dataIndex] : predictedData[context.dataIndex];
                    return `${datasetLabel}: ${realValue.toFixed(2)}`;
                  }
                }
              }
            }
          }
        })
      }
    }

    const extractParameters = async () => {
      const text = naturalLanguageInput.value.trim()
      if (!text) {
        showToastMessage('⚠ 请先在文本框中输入岩石的自然语言描述')
        return
      }
      showToastMessage('正在智能解析语义，请稍候...')
      try {
        const res = await axios.post('http://127.0.0.1:5000/extract-parameters', { text: text, model_type: modelType.value })
        if (res.data.success) {
          const params = res.data.data
          const nextForm = { ...rockForm.value }
          Object.keys(nextForm).forEach((key) => {
            const value = params[key]
            if (value !== null && value !== undefined && value !== '') {
              nextForm[key] = Number(value)
            }
          })
          // Replacing the ref value reliably refreshes Vue 2.7 dynamic v-model fields.
          rockForm.value = nextForm
          showToastMessage(`✅ 参数提取成功 (底层使用: ${res.data.method})`)
        } else {
          showToastMessage(`⚠ 解析失败: ${res.data.error}`)
        }
      } catch (err) {
        showToastMessage('⚠ 请求后端提取接口失败，请检查 Python 服务是否运行')
      }
    }

    const generateFormula = async () => {
      showToastMessage('正在执行逆向设计推理...')
      currentRecipeDetail.value = null
      showResults.value = false
      generationError.value = ''
      isGenerating.value = true
      try {
        const input = [
          ['抗压强度', rockForm.value.compressive],
          ['抗拉强度', rockForm.value.tensile],
          ['泊松比', rockForm.value.poisson],
          ['弹性模量', rockForm.value.elastic],
          ['密度', rockForm.value.density],
          ['硬度', rockForm.value.hardness]
        ]
          .filter(([, value]) => Number(value) > 0)
          .map(([label, value]) => `${label}:${value}`)
          .join(' ')
        const res = await axios.post('http://127.0.0.1:5000/get', {
          input,
          model_type: modelType.value
        })
        if (!res.data.success) throw new Error(res.data.error || '模型没有返回有效配方')

        const formula = res.data.data || {}
        const entries = sortedCompositionEntries(formula.components)
        if (!entries.length) throw new Error('后端模型返回的配方中没有有效材料比例')

        genLabels.value = entries.map(([name]) => name)
        genData.value = entries.map(([, value]) => Number((Number(value) * 100).toFixed(2)))
        predictedProperties.value = formula.predicted || {}
        resultSimilarity.value = formula.similarity ?? null
        resultModelLabel.value = `本地大模型 ${res.data.model_name || ''} 返回真实数据集样本 #${formula.source_sample_id || '-'}`
        resultReason.value = formula.reason || ''
        showResults.value = true
        showToastMessage(`✅ 配方生成成功 (底层使用: ${res.data.method || res.data.model_type})`)
        await nextTick()
        initResultCharts()
      } catch (err) {
        const message = err.response?.data?.error || err.message || '配方生成失败'
        generationError.value = message
        showToastMessage(`⚠ ${message}`)
      } finally {
        isGenerating.value = false
      }
    }

    watch(activeView, (v) => v === 'data-screen' && initLightDashboard())

    onMounted(() => {
      const now = new Date()
      currentDate.value = `${now.getFullYear()}年${now.getMonth()+1}月${now.getDate()}日 ${['星期日','星期一','星期二','星期三','星期四','星期五','星期六'][now.getDay()]}`
      fetchDataset()
    })

    return {
      activeView, currentDate, naturalLanguageInput, rockForm, modelType, showResults, showToast, toastMessage,
      distributionChart, comparisonChartRef, recipeListData, currentTrendMetric,
      segmentedBarRef, genLabels, genData, componentColors, getComponentColor,
      stats, processSteps, constraintFields, allValid, getUnit, currentRecipeDetail, showMaterialsModal, showRecipeModal, uniqueMaterials,
      currentComposition, formatPercent, formatComposition,
      predictedProperties, resultSimilarityText, resultModelLabel, resultReason, isGenerating, generationError,
      showImagePreview, previewImageUrl, previewImageTitle, getMaterialImage, openImagePreview,
      extractParameters, generateFormula, showRecipeDetails, initLightDashboard
    }
  }
}
</script>

<style scoped>
/* ==================== 全局基础 ==================== */
.workbench-bg { background-color: #f8fafc; min-height: 100vh; color: #334155; font-family: 'Inter', -apple-system, sans-serif; }
.card-white { background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05); }
.animate-fade-in { animation: fadeIn 0.4s ease-out; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

/* ==================== 视图一：看板 ==================== */
.data-screen-light { padding: 0 30px 30px; }
.screen-header-light { height: 80px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #e2e8f0; margin-bottom: 25px; }
.back-link { color: #64748b; font-size: 14px; font-weight: 600; cursor: pointer; border: none; background: none; }
.header-title-light { font-size: 24px; font-weight: 800; color: #0f172a; }
.dot-green { display: inline-block; width: 8px; height: 8px; background: #22c55e; border-radius: 50%; margin-right: 6px; }

.stats-grid-2 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 24px; margin-bottom: 24px; }
.stat-item-card { background: #fff; padding: 22px; border-radius: 12px; display: flex; align-items: center; border: 1px solid #e2e8f0; position: relative; }
.stat-clickable { cursor: pointer; transition: all 0.2s; }
.stat-clickable:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.08); border-color: #3b82f6; }
.stat-icon-box { width: 48px; height: 48px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 20px; margin-right: 18px; }
.stat-label { font-size: 13px; color: #64748b; display: block; margin-bottom: 2px; }
.stat-value { font-size: 24px; font-weight: 800; color: #0f172a; }
.click-hint { position: absolute; right: 20px; top: 35px; font-size: 12px; color: #3b82f6; font-weight: 600; opacity: 0.8; }

.screen-main-grid { display: flex; flex-direction: column; gap: 24px; }
.chart-container-card { height: 400px; padding: 20px; display: flex; flex-direction: column; }
.canvas-box { flex: 1; width: 100%; }
.card-header-bold { font-size: 16px; font-weight: 700; color: #1e293b; margin-bottom: 10px; }

.trend-select { padding: 6px 12px; border-radius: 6px; border: 1px solid #cbd5e1; font-size: 13px; color: #334155; background-color: #f8fafc; outline: none; cursor: pointer; }
.action-link { color: #2563eb; font-weight: 600; font-size: 13px; cursor: pointer; border: none; background: none; }

/* 模态框通用样式 */
.modal-overlay-light { position: fixed; top:0; left:0; width:100%; height:100%; background: rgba(15, 23, 42, 0.5); z-index: 1000; display: flex; align-items: center; justify-content: center; backdrop-filter: blur(4px); }
.detail-modal-light { background: #fff; border-radius: 16px; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.1); padding: 0; overflow: hidden; }
.modal-header-light { padding: 20px 24px; background: #ffffff; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e2e8f0; }
.modal-header-light h3 { margin: 0; font-size: 16px; font-weight: 700; color: #1e293b; }
.modal-body-light { padding: 24px; max-height: 600px; overflow-y: auto; }
.close-btn-light { font-size: 24px; color: #94a3b8; cursor: pointer; border: none; background: none; line-height: 1; transition: 0.2s; }
.close-btn-light:hover { color: #ef4444; }

/* 材料图谱网格样式 */
.material-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: 16px; }
.material-card { background: #fff; border-radius: 12px; border: 1px solid #e2e8f0; padding: 12px; display: flex; flex-direction: column; align-items: center; cursor: pointer; transition: all 0.2s; }
.material-card:hover { transform: translateY(-4px); box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1); border-color: #3b82f6; }
.img-wrapper { position: relative; width: 80px; height: 80px; border-radius: 50%; overflow: hidden; margin-bottom: 12px; border: 2px solid #f1f5f9; }
.img-wrapper img { width: 100%; height: 100%; object-fit: cover; }
.img-overlay { position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(59, 130, 246, 0.6); display: flex; align-items: center; justify-content: center; opacity: 0; transition: 0.3s; color: white; font-size: 20px; }
.material-card:hover .img-overlay { opacity: 1; }
.material-name { font-size: 13px; font-weight: 600; color: #334155; text-align: center; }

/* 图片全屏放大预览样式 */
.preview-overlay { z-index: 1200; background: rgba(15, 23, 42, 0.9); backdrop-filter: blur(8px); }
.preview-container { position: relative; display: flex; flex-direction: column; align-items: center; }
.preview-img { max-width: 80vw; max-height: 75vh; border-radius: 12px; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5); object-fit: contain; }
.preview-title { color: #fff; margin-top: 20px; font-size: 22px; font-weight: 700; letter-spacing: 2px; }
.close-preview-btn { position: absolute; top: -30px; right: -50px; font-size: 40px; color: rgba(255,255,255,0.6); background: none; border: none; cursor: pointer; transition: 0.2s; }
.close-preview-btn:hover { color: #ef4444; transform: scale(1.1); }

/* 配方明细弹窗专用样式 */
.recipe-modal-body { display: flex; gap: 30px; }
.recipe-props-side { flex: 1; border-right: 1px dashed #e2e8f0; padding-right: 30px; }
.recipe-chart-side { flex: 1.5; display: flex; flex-direction: column; }
.sub-title { font-size: 14px; font-weight: 700; color: #1e293b; margin-bottom: 16px; border-bottom: 2px solid #f1f5f9; padding-bottom: 8px; }
.prop-list { list-style: none; padding: 0; margin: 0; }
.prop-list li { display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px dashed #f1f5f9; font-size: 14px; }
.prop-list li span { color: #64748b; font-weight: 500; }
.prop-list li b { color: #1e293b; font-family: 'Inter', monospace; }
.prop-list li small { color: #94a3b8; font-size: 11px; margin-left: 4px; }
.modal-canvas-wrapper { flex: 1; min-height: 300px; position: relative; }

/* ==================== 视图二：工作台 ==================== */
.system-header { background: #fff; border-bottom: 1px solid #e2e8f0; padding: 18px 40px; }
.header-container { max-width: 1440px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center; }
.header-meta { display: flex; align-items: center; }
.breadcrumb { font-size: 12px; color: #3b82f6; font-weight: 600; margin-bottom: 4px; display: block; }
.workbench-title { font-size: 22px; font-weight: 800; color: #0f172a; }

.dashboard-entry-btn { background: #f1f5f9; border: 1px solid #e2e8f0; padding: 6px 14px; border-radius: 8px; font-size: 13px; font-weight: 600; margin-right: 20px; cursor: pointer; }
.engine-status { background: #f0fdf4; color: #166534; padding: 5px 14px; border-radius: 20px; font-size: 12px; font-weight: 600; margin-right: 20px; }
.date-display { font-size: 13px; color: #64748b; font-weight: 500; }

.workbench-content { max-width: 1440px; margin: 24px auto; padding: 0 40px; }
.workbench-grid { display: grid; grid-template-columns: 400px 1fr; gap: 30px; }

.workbench-card { padding: 24px; margin-bottom: 24px; }
.card-title { font-size: 17px; font-weight: 700; color: #0f172a; margin-bottom: 20px; display: flex; align-items: center; }
.card-title i { margin-right: 12px; color: #3b82f6; }

.modern-textarea { width: 100%; height: 160px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; font-size: 14px; line-height: 1.6; margin-bottom: 16px; resize: none; }
.btn-dark-action { width: 100%; background: #1e293b; color: #fff; padding: 12px; border-radius: 8px; font-weight: 700; cursor: pointer; border: none; }

.params-form { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }
.form-item label { font-size: 12px; font-weight: 700; color: #64748b; margin-bottom: 6px; display: block; }
.req { color: #ef4444; }
.input-container { position: relative; }
.input-container input { width: 100%; padding: 10px 12px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 14px; background: #fff; }
.unit-label { position: absolute; right: 10px; top: 10px; font-size: 11px; color: #94a3b8; font-weight: 600; }

.algo-toggle { display: flex; gap: 10px; margin-bottom: 24px; }
.algo-toggle button { flex: 1; padding: 10px; font-size: 12px; font-weight: 700; border-radius: 8px; border: 1px solid #e2e8f0; background: #f8fafc; color: #64748b; cursor: pointer; }
.algo-toggle button.active { background: #3b82f6; color: #fff; border-color: #3b82f6; }

.btn-primary-launch { width: 100%; background: #2563eb; color: #fff; padding: 16px; border-radius: 10px; font-weight: 800; font-size: 16px; border: none; cursor: pointer; box-shadow: 0 4px 12px rgba(37, 99, 235, 0.2); }
.btn-primary-launch:disabled { opacity: 0.5; cursor: not-allowed; }

.result-main { border-top: 4px solid #3b82f6; }
.result-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 24px; }
.card-sub { font-size: 13px; color: #64748b; margin-top: -15px; }
.btn-export { border: 1px solid #22c55e; color: #166534; padding: 6px 14px; border-radius: 6px; font-size: 12px; font-weight: 700; background: #f0fdf4; cursor: pointer; }

.result-charts { display: grid; grid-template-columns: 1fr 1fr; gap: 30px; }
.chart-inner-title { font-size: 13px; font-weight: 700; text-align: center; margin-bottom: 20px; color: #475569; }
.chart-canvas-wrapper { height: 260px; }
.border-l { border-left: 1px solid #f1f5f9; padding-left: 30px; }

/* ✨✨ ✨✨ 新增：静态固化的图文混排条形图样式 ✨✨ ✨✨ */
.segmented-bar-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.segmented-bar-wrapper {
  width: 100%;
  position: relative;
  padding-top: 120px; /* ✨ 核心：为顶部固定的图片和小卡片留出充足的高度 ✨ */
  padding-bottom: 20px;
}

.segmented-bar-container {
  width: 100%;
  height: 24px;
  background: #cbd5e1;
  border-radius: 12px;
  display: flex;
  position: relative;
  box-shadow: inset 0 2px 4px rgba(0,0,0,0.05);
}

.bar-segment {
  height: 100%;
  position: relative;
  display: flex;
  justify-content: center;
  transition: all 0.2s cubic-bezier(0.18, 0.89, 0.32, 1.28);
}

.bar-segment:hover {
  transform: translateY(-3px) scaleY(1.1);
  z-index: 10;
  box-shadow: 0 5px 15px rgba(0,0,0,0.1);
  border-radius: 12px;
}

.bar-segment:first-child { border-top-left-radius: 12px; border-bottom-left-radius: 12px; }
.bar-segment:last-child { border-top-right-radius: 12px; border-bottom-right-radius: 12px; }

/* ✨ 顶部静态图文卡片和连接线系统 ✨ */
.static-label-wrapper {
  position: absolute;
  top: -105px; /* 将整个图文组合定位在条形图的上方 */
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  pointer-events: auto;
}

/* 包含图片和文字的白色小卡片 */
.static-label-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  background: #ffffff;
  padding: 6px;
  border-radius: 8px;
  box-shadow: 0 4px 10px rgba(0,0,0,0.08); /* 柔和的阴影，凸显卡片层级 */
  border: 1px solid #e2e8f0;
  margin-bottom: 6px; /* 和下方连接线的间距 */
  min-width: 50px;
}

.static-mat-img {
  width: 40px;
  height: 40px;
  border-radius: 4px;
  object-fit: cover;
  margin-bottom: 4px;
  border: 1px solid #f1f5f9;
}

.static-text-info {
  display: flex;
  flex-direction: column;
  align-items: center;
  line-height: 1.2;
}

.label-text {
  font-size: 11px;
  font-weight: 700;
  color: #64748b;
  white-space: nowrap;
}

.label-percent {
  font-size: 13px;
  font-weight: 900;
  color: #0f172a;
}

/* 连接小卡片和条形图的垂直细线 */
.label-line {
  width: 1px;
  height: 15px;
  background: #94a3b8;
  position: relative;
}

/* 线上接触条形图的小圆点 */
.label-line::after {
  content: '';
  position: absolute;
  bottom: -3px;
  left: -2px;
  width: 5px;
  height: 5px;
  background: #94a3b8;
  border-radius: 50%;
}

.process-list { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 24px; }
.process-row { margin-bottom: 12px; font-size: 14px; line-height: 1.5; }
.step-num { font-weight: 800; color: #0f172a; margin-right: 10px; }
.step-title { font-weight: 700; color: #334155; }
.step-desc { color: #64748b; }

.empty-state { text-align: center; padding: 150px 0; color: #cbd5e1; }
.empty-icon { font-size: 50px; margin-bottom: 20px; }

.toast-msg { position: fixed; top: -50px; left: 50%; transform: translateX(-50%); background: #0f172a; color: #fff; padding: 12px 30px; border-radius: 40px; font-size: 14px; font-weight: 600; box-shadow: 0 10px 20px rgba(0,0,0,0.2); transition: all 0.4s cubic-bezier(0.18, 0.89, 0.32, 1.28); z-index: 9999; }
.toast-msg.show { top: 40px; }

.loop-entry-btn { display: inline-flex; align-items: center; padding: 9px 14px; border: 1px solid #fed7aa; border-radius: 8px; color: #c2410c; background: #fff7ed; font-size: 13px; font-weight: 700; text-decoration: none; transition: all .2s; }
.loop-entry-btn:hover { color: #9a3412; border-color: #fb923c; background: #ffedd5; transform: translateY(-1px); }

.table-wrapper { overflow-x: auto; max-height: 400px; }
.modern-table { width: 100%; border-collapse: collapse; }
.modern-table th { text-align: left; padding: 14px 20px; font-size: 13px; color: #64748b; border-bottom: 2px solid #f1f5f9; position: sticky; top: 0; background: #fff; z-index: 5; }
.modern-table td { padding: 16px 20px; font-size: 14px; border-bottom: 1px solid #f1f5f9; }

.composition-summary {
  min-width: 260px;
  max-width: 380px;
  color: #475569;
  line-height: 1.55;
}

.composition-detail-list {
  max-height: 320px;
  overflow-y: auto;
  padding-right: 6px;
}

.composition-detail-row { margin-bottom: 14px; }
.composition-detail-row:last-child { margin-bottom: 0; }
.composition-detail-head { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 7px; color: #334155; }
.composition-material { font-weight: 600; }
.composition-detail-head b { color: #2563eb; font-variant-numeric: tabular-nums; }
.composition-progress { height: 8px; overflow: hidden; background: #e2e8f0; border-radius: 999px; }
.composition-progress span { display: block; height: 100%; background: linear-gradient(90deg, #60a5fa, #2563eb); border-radius: inherit; }
.composition-empty { padding: 28px 0; color: #94a3b8; text-align: center; }

.result-reason { max-width: 760px; margin-top: 6px; color: #64748b; font-size: 13px; line-height: 1.5; }
.generation-error { display: flex; align-items: flex-start; gap: 16px; padding: 28px; color: #991b1b; border-color: #fecaca; background: #fff7f7; }
.generation-error > i { margin-top: 3px; color: #dc2626; font-size: 24px; }
.generation-error h3 { margin: 0 0 8px; font-size: 17px; }
.generation-error p { margin: 0; color: #7f1d1d; line-height: 1.65; }
</style>
