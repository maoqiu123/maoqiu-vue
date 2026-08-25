<template>
  <div class="loop-shell">
    <header class="topbar">
      <a href="/index.html" class="back-home">← 返回配方设计系统</a>
      <div class="brand-block">
        <span class="brand-mark">DL</span>
        <div>
          <strong>岩石材料研究闭环</strong>
          <span>候选、实验、反馈与决策</span>
        </div>
      </div>
      <div :class="['engine-pill', { offline: !backendOnline }]"><span></span>{{ backendOnline ? '本地服务已连接' : '本地服务未连接' }}</div>
    </header>

    <main class="page-wrap">
      <section class="compact-head">
        <div><span class="eyebrow">可信实验反馈</span><h1>岩石材料研究闭环</h1></div>
        <div class="head-summary">
          <span>研究轮次 <b>{{ history.length }}</b></span><span>已通过 <b>{{ trustedCount }}</b></span><span>平均证据 <b>{{ averageEvidence === '—' ? '—' : `${averageEvidence}%` }}</b></span><span>当前 <b>{{ session ? `R${session.round_no}` : '待启动' }}</b></span>
        </div>
        <div class="hero-actions">
          <button :class="['tab-button', { active: view === 'workspace' }]" @click="view = 'workspace'">当前闭环</button>
          <button :class="['tab-button', { active: view === 'history' }]" @click="openHistory">研究记录</button>
        </div>
      </section>

      <section v-if="view === 'workspace'" class="single-workspace">
        <nav class="stepper" aria-label="研究步骤">
          <button v-for="stage in stages" :key="stage.index" :class="['step-tab', stage.state]" :disabled="!stage.available" @click="goToStep(stage.index)">
            <span>{{ stage.index }}</span><div><b>{{ stage.name }}</b><small>{{ stage.desc }}</small></div>
          </button>
        </nav>

        <section class="workflow-card">
          <article v-if="activeStep === 1" class="step-pane">
            <div class="panel-heading"><div><span class="panel-kicker">第一步</span><h2>设定研究目标</h2><p>填写目标性质并选择负责生成候选配方的模型。</p></div><button v-if="session" class="text-button" @click="resetWorkspace">新建研究</button></div>
            <div class="goal-layout">
              <div class="goal-copy">
                <label class="field-label">本轮研究目标</label>
                <textarea v-model="form.objective" :disabled="!!session" placeholder="例如：寻找抗压强度接近 0.48 MPa、泊松比约 0.12 的相似材料配方"></textarea>
                <label class="field-label">研究假设 <small>选填</small></label>
                <input v-model="form.hypothesis" :disabled="!!session" placeholder="例如：调整细骨料比例可降低目标性质偏差">
              </div>
              <div class="model-config-grid">
                <label><span>候选配方模型</span><select v-model="form.candidate_model" :disabled="!!session || loadingModels"><option v-for="model in candidateModels" :key="model.id" :value="model.id" :disabled="model.status !== 'ready'">{{ model.name }} · {{ model.status_text }}</option></select><small>{{ modelSupportText }}</small></label>
                <details v-if="!session" class="model-upload"><summary>＋ 上传并接入新模型</summary><div class="upload-grid"><label><span>显示名称</span><input v-model="uploadForm.display_name" placeholder="例如：实验室 QNN v2"></label><label><span>模型类型</span><select v-model="uploadForm.model_kind"><option value="ollama_gguf">Ollama GGUF</option><option value="quantum_checkpoint">QNN 检查点（.pth/.pt）</option></select></label><label class="file-field"><span>模型文件</span><input type="file" :accept="uploadAccept" @change="selectUploadFile"></label><button class="secondary-button" :disabled="uploading || !uploadForm.file" @click.prevent="uploadModel">{{ uploading ? '正在接入…' : '上传模型' }}</button></div></details>
              </div>
            </div>
            <div class="section-label"><b>目标性质</b><span>系统从研究目标中调用本地大模型提取并回填，您可以在生成候选前修正</span></div>
            <div class="target-grid"><label v-for="field in propertyFields" :key="field.key"><span>{{ field.label }} <small>{{ field.unit }}</small></span><input v-model="form.targets[field.key]" :disabled="!!session" type="number" min="0" step="any" placeholder="未设定"></label></div>
            <p v-if="extractionSummary && !session" class="extraction-note">{{ extractionSummary }}</p>
            <p v-if="createHint && !session" class="form-hint">{{ createHint }}</p>
            <div class="pane-actions"><button v-if="!session" class="primary-button" :disabled="creating || extractingTargets || !canAdvanceFromGoal" @click="advanceFromGoal">{{ primaryActionText }}</button><button v-else class="primary-button" @click="activeStep = 2">查看本轮方案 →</button></div>
          </article>

          <article v-else-if="activeStep === 2 && session" class="step-pane">
            <div class="panel-heading"><div><span class="panel-kicker">第二步</span><h2>确认候选与固定流程</h2><p>基线、模型候选和实验要求集中在同一页确认。</p></div><span class="version-tag">R{{ session.round_no }} · {{ statusText }}</span></div>
            <div class="review-grid">
              <section class="review-block baseline-review"><div class="block-title"><div><small>数据基线</small><h3>{{ session.baseline ? `样本 #${session.baseline.source_sample_id}` : '该历史轮次未记录数据基线' }}</h3></div><b>{{ session.baseline ? `${formatPercent(session.baseline.target_error)} 目标误差` : '—' }}</b></div><p>基线仅按本轮目标性质计算距离，但下方展示该样本在数据集中的全部可用性质。</p><h4>基线配方</h4><div class="composition-list compact-composition"><div v-for="item in baselineEntries" :key="item.name" class="composition-row"><div><span>{{ item.name }}</span><b>{{ formatRatio(item.ratio) }}</b></div><div class="ratio-track"><i :style="{ width: `${item.ratio * 100}%` }"></i></div></div><span v-if="!baselineEntries.length" class="empty-inline">当前记录没有配方明细</span></div><h4>数据集性质</h4><div class="baseline-property-grid"><div v-for="item in baselineProperties" :key="item.key"><span>{{ item.label }}</span><b>{{ item.value }}</b><small>{{ item.target }}</small></div></div></section>
              <section class="review-block candidate-review"><div class="block-title"><div><small>新候选配方</small><h3>{{ candidateSourceText }}</h3></div><b>{{ session.candidate.model_name }}</b></div><p>{{ session.candidate.reason }}</p><h4>候选配方</h4><div class="composition-list"><div v-for="item in candidateEntries" :key="item.name" class="composition-row"><div><span>{{ item.name }}</span><b>{{ formatRatio(item.ratio) }}</b></div><div class="ratio-track"><i :style="{ width: `${item.ratio * 100}%` }"></i></div></div></div><template v-if="candidateAdjustments.length"><h4>相对起始配方的调整</h4><div class="adjustment-list"><div v-for="item in candidateAdjustments" :key="item.material" class="adjustment-chip"><span>{{ item.material }}</span><small>{{ formatRatio(item.before) }} → {{ formatRatio(item.after) }}</small><b :class="item.delta > 0 ? 'positive' : 'negative'">{{ signedRatio(item.delta) }}</b></div></div></template><h4>全部估算性质</h4><div class="baseline-property-grid candidate-property-grid"><div v-for="item in candidateProperties" :key="item.key"><span>{{ item.label }}</span><b>{{ item.value }}</b><small>{{ item.target }}</small></div></div><div class="candidate-meta"><span>{{ candidateMethodText }}</span><span>本轮目标估算误差 <b>{{ formatPercent(session.candidate.predicted_target_error) }}</b></span></div></section>
            </div>
            <section class="protocol-box"><div class="block-title"><div><small>所有轮次统一执行</small><h3>固定实验流程</h3></div><span class="version-tag">不可修改</span></div><ol class="protocol-list"><li v-for="(step, index) in session.execution_plan.protocol" :key="`${index}-${step}`"><span>{{ index + 1 }}</span><p>{{ step }}</p></li></ol><details class="protocol-details"><summary>查看固定条件、通过标准和留存材料</summary><div><b>固定条件</b><span>{{ session.execution_plan.environment }}</span><b>通过标准</b><span>{{ session.execution_plan.acceptance_criteria }}</span><b>留存材料</b><span>{{ (session.execution_plan.required_evidence || []).join('；') }}</span></div></details></section>
            <div class="pane-actions split"><button class="secondary-button" @click="activeStep = 1">← 查看目标</button><button class="primary-button" @click="activeStep = 3">确认，进入实测录入 →</button></div>
          </article>

          <article v-else-if="activeStep === 3 && session" class="step-pane">
            <div class="panel-heading"><div><span class="panel-kicker">第三步</span><h2>录入新配方实测结果</h2><p>仅填写真实实验记录，模型不会代填任何结果。</p></div><span :class="['status-tag', statusClass]">{{ statusText }}</span></div>
            <div v-if="feedbackLocked" class="record-lock">本轮实测记录已提交并进入研究档案，只能查看，不能覆盖。</div>
            <div class="feedback-layout">
              <div><div class="run-meta-grid three"><label><span>实验运行编号</span><input v-model="feedback.run_id" :disabled="feedbackLocked" placeholder="例如：RUN-001"></label><label><span>环境、养护与仪器</span><input v-model="feedback.environment" :disabled="feedbackLocked" placeholder="例如：25℃、90%RH、仪器编号"></label><label><span>每项目标有效试件数</span><input v-model.number="feedback.sample_count" :disabled="feedbackLocked" type="number" min="1" step="1" placeholder="至少 1 个"></label></div><div class="section-label"><b>实测性质</b><span>仅显示本轮设置的目标指标</span></div><div class="observation-grid"><label v-for="field in activePropertyFields" :key="field.key"><span>{{ field.label }} <small>{{ field.unit }}</small></span><input v-model="feedback.observations[field.key]" :disabled="feedbackLocked" type="number" min="0" step="any" placeholder="实测均值"><em>目标 {{ displayTarget(field.key) }}</em></label></div></div>
              <div><div class="check-section"><h3>实验记录核验</h3><label v-for="check in evidenceChecks" :key="check.key" class="check-row"><input v-model="feedback.checks[check.key]" :disabled="feedbackLocked" type="checkbox"><span><b>{{ check.label }}</b><small>{{ check.desc }}</small></span></label></div><label class="field-label">异常、失败与人工干预 <small>选填</small></label><textarea v-model="feedback.notes" :disabled="feedbackLocked" class="notes-area" placeholder="如有异常请如实记录，没有可留空。"></textarea></div>
            </div>
            <p v-if="!feedbackLocked && !canSubmitFeedback" class="form-hint">请填写运行编号、环境信息、有效试件数量，以及至少一项对应的实测值。</p>
            <div class="pane-actions split"><button class="secondary-button" @click="activeStep = 2">← 查看方案</button><button v-if="!feedbackLocked" class="primary-button" :disabled="submitting || !canSubmitFeedback" @click="evaluateEvidence">{{ submitting ? '正在审核…' : '提交实测结果并比较 →' }}</button><button v-else class="primary-button" @click="activeStep = 4">查看审核结果 →</button></div>
          </article>

          <article v-else-if="activeStep === 4 && session && session.evidence" class="step-pane result-pane">
            <div class="result-hero"><div :class="['score-ring', session.evidence.gate]"><b>{{ session.evidence.score }}</b><span>证据分</span></div><div><span class="panel-kicker">第四步 · 结果决策</span><h2>{{ gateTitle }}</h2><p>{{ session.decision.action }}</p></div><span :class="['status-tag', statusClass]">{{ statusText }}</span></div>
            <div class="score-breakdown four"><div><span>基线误差</span><b>{{ displayEvidencePercent(session.evidence.baseline_error) }}</b></div><div><span>新配方误差</span><b>{{ displayEvidencePercent(session.evidence.candidate_error) }}</b></div><div><span>相对改善</span><b :class="improvementClass">{{ signedPercent(session.evidence.improvement_rate) }}</b></div><div><span>记录完整性</span><b>{{ displayEvidencePercent(session.evidence.integrity_score) }}</b></div></div>
            <div v-if="session.evidence.comparisons.length" class="comparison-table"><div class="comparison-head"><span>指标</span><span>目标</span><span>数据基线</span><span>新配方实测</span><span>改善率</span><span>验收结果</span></div><div v-for="item in session.evidence.comparisons" :key="item.key" class="comparison-row"><span>{{ item.label }}</span><span>{{ item.target }}</span><span>{{ item.baseline }}</span><span>{{ item.measured }}</span><span>{{ signedRatio(item.improvement_rate) }}</span><b :class="item.within_tolerance ? 'positive' : 'negative'">{{ item.within_tolerance ? '达标' : '未达标' }}<small>{{ item.acceptance_rule }}</small></b></div></div>
            <div v-if="canStartNext" class="next-round-config"><label><span>下一轮候选模型</span><select v-model="form.candidate_model" :disabled="creating"><option v-for="model in candidateModels" :key="model.id" :value="model.id" :disabled="model.status !== 'ready'">{{ model.name }} · {{ model.status_text }}</option></select></label><small v-if="unsupportedTargets.length">所选模型不支持：{{ unsupportedTargets.map(item => item.label).join('、') }}</small></div>
            <div class="pane-actions split"><button class="secondary-button" @click="activeStep = 3">← 查看实测记录</button><button v-if="canStartNext" class="primary-button dark" :disabled="creating || !nextModelReady" @click="startNextRound">{{ creating ? '正在生成下一轮…' : '生成下一轮候选 →' }}</button><span v-else class="review-stop">该轮次需要人工复核，系统不会自动生成下一轮。</span></div>
          </article>
        </section>
      </section>

      <section v-else class="history-panel workflow-card">
        <div class="history-header">
          <div><span class="panel-kicker">研究记录</span><h2>历史研究轮次</h2><p>目标、候选、固定流程快照、实测结果和决策都会按轮次保存。</p></div>
          <button class="secondary-button" @click="fetchHistory">刷新状态</button>
        </div>
        <div v-if="history.length" class="history-list">
          <button v-for="item in history" :key="item.id" class="history-item" @click="loadSession(item)">
            <span class="history-round">R{{ item.round_no }}</span>
            <div><b>{{ item.objective }}</b><small>{{ item.baseline ? `基线 #${item.baseline.source_sample_id}` : '未记录基线' }} · {{ item.candidate.model_name || '未记录模型' }} · {{ formatTime(item.created_at) }}</small></div>
            <span :class="['history-status', statusClassFor(item.status)]">{{ statusLabelFor(item.status) }}</span>
            <strong>{{ item.evidence ? `${item.evidence.score}分` : '待反馈' }}</strong>
          </button>
        </div>
        <div v-else class="history-empty">尚无研究记录，启动第一轮后会在这里形成可恢复状态。</div>
      </section>
    </main>

    <div v-if="notice" :class="['notice', noticeType]">{{ notice }}</div>
  </div>
</template>

<script>
import axios from 'axios'

const API_ORIGIN = `${window.location.protocol}//${window.location.hostname}:5000`
const API_BASE = `${API_ORIGIN}/api/discovery`

const emptyTargets = () => ({ compressive: '', tensile: '', poisson: '', elastic: '', density: '', hardness: '' })
const emptyFeedback = () => ({
  observations: emptyTargets(),
  checks: { execution_verified: false, baseline_comparable: false, reproducible: false, provenance_complete: false },
  run_id: '', environment: '', sample_count: '', notes: ''
})

export default {
  name: 'DiscoveryLoop',
  data() {
    return {
      view: 'workspace',
      activeStep: 1,
      backendOnline: false,
      extractingTargets: false,
      lastExtractedObjective: '',
      extractionSummary: '',
      form: {
        objective: '',
        hypothesis: '',
        targets: emptyTargets(),
        candidate_model: 'ollama:qwen3.5:9b'
      },
      propertyFields: [
        { key: 'compressive', label: '抗压强度', unit: 'MPa' },
        { key: 'tensile', label: '抗拉强度', unit: 'MPa' },
        { key: 'poisson', label: '泊松比', unit: '' },
        { key: 'elastic', label: '弹性模量', unit: 'MPa' },
        { key: 'density', label: '密度', unit: 'g/cm³' }
      ],
      evidenceChecks: [
        { key: 'execution_verified', label: '实验按固定流程完成', desc: '称量、混合、养护和测试都有记录' },
        { key: 'baseline_comparable', label: '数据基线可以直接比较', desc: '基线与本轮数据的单位、试验方法和评价口径一致' },
        { key: 'reproducible', label: '结果经过重复试验', desc: '有效试件不少于 3 个时才计入完整性评分' },
        { key: 'provenance_complete', label: '原始记录完整', desc: '能查到样品、仪器、原始数据和人工调整' }
      ],
      session: null,
      feedback: emptyFeedback(),
      history: [],
      models: [],
      loadingModels: false,
      uploadForm: { display_name: '', model_kind: 'ollama_gguf', file: null },
      uploading: false,
      creating: false,
      submitting: false,
      notice: '',
      noticeType: 'success',
      noticeTimer: null
    }
  },
  computed: {
    hasTargets() { return this.propertyFields.some(field => Number(this.form.targets[field.key]) > 0) },
    selectedModel() { return this.models.find(model => model.id === this.form.candidate_model) || null },
    extractionModel() {
      if (this.selectedModel && this.selectedModel.provider === 'ollama' && this.selectedModel.status === 'ready') return this.selectedModel
      return this.models.find(model => model.provider === 'ollama' && model.status === 'ready') || null
    },
    targetsNeedExtraction() {
      const objective = String(this.form.objective || '').trim()
      return !this.hasTargets || (!!this.lastExtractedObjective && objective !== this.lastExtractedObjective)
    },
    nextModelReady() { return !!this.selectedModel && this.selectedModel.status === 'ready' && !this.unsupportedTargets.length },
    unsupportedTargets() {
      if (!this.selectedModel) return []
      const supported = new Set(this.selectedModel.supported_properties || [])
      return this.propertyFields.filter(field => Number(this.form.targets[field.key]) > 0 && !supported.has(field.key))
    },
    modelSupportText() {
      if (!this.selectedModel) return this.loadingModels ? '正在读取本地模型…' : '当前没有可用模型。'
      const labels = this.propertyFields
        .filter(field => (this.selectedModel.supported_properties || []).includes(field.key))
        .map(field => field.label)
      return `可用于：${labels.join('、') || '未声明支持指标'}。模型只生成候选配方。`
    },
    canCreateLoop() {
      const hasObjective = !!String(this.form.objective || '').trim()
      return hasObjective && this.hasTargets && this.nextModelReady
    },
    canAdvanceFromGoal() {
      const hasObjective = !!String(this.form.objective || '').trim()
      const modelReady = !!this.selectedModel && this.selectedModel.status === 'ready'
      return hasObjective && modelReady && (this.targetsNeedExtraction || this.canCreateLoop)
    },
    primaryActionText() {
      if (this.extractingTargets) return '本地大模型正在提取目标性质…'
      if (this.creating) return '正在生成候选配方…'
      return this.targetsNeedExtraction ? '从研究目标提取性质 →' : '生成候选配方并继续 →'
    },
    createHint() {
      if (!String(this.form.objective || '').trim()) return '请填写本轮研究目标。'
      if (this.targetsNeedExtraction) return '点击下方按钮，系统会调用本地大模型识别目标性质并自动回填。'
      if (this.unsupportedTargets.length) return `${this.selectedModel.name} 不支持：${this.unsupportedTargets.map(item => item.label).join('、')}。请更换模型或调整目标。`
      if (!this.selectedModel || this.selectedModel.status !== 'ready') return '请选择状态为“可用”的候选配方模型。'
      return ''
    },
    activePropertyFields() {
      const targets = this.session ? this.session.targets || {} : {}
      return this.propertyFields.filter(field => targets[field.key] !== null && targets[field.key] !== undefined)
    },
    baselineProperties() {
      const baseline = this.session && this.session.baseline ? this.session.baseline.properties || {} : {}
      const targets = this.session ? this.session.targets || {} : {}
      return this.propertyFields
        .map(field => ({
          key: field.key,
          label: field.label,
          value: baseline[field.key] !== null && baseline[field.key] !== undefined
            ? `${baseline[field.key]}${field.unit ? ` ${field.unit}` : ''}`
            : '暂无数据',
          target: targets[field.key] !== null && targets[field.key] !== undefined ? `本轮目标 ${targets[field.key]}` : '未设为本轮目标'
        }))
    },
    baselineEntries() {
      const components = this.session && this.session.baseline ? this.session.baseline.components || {} : {}
      return Object.entries(components)
        .map(([name, ratio]) => ({ name, ratio: Number(ratio) }))
        .filter(item => item.ratio > 0)
        .sort((a, b) => b.ratio - a.ratio)
    },
    candidateModels() { return this.models.filter(model => (model.capabilities || []).includes('candidate_selection')) },
    uploadAccept() { return this.uploadForm.model_kind === 'ollama_gguf' ? '.gguf' : '.pth,.pt' },
    candidateMethodText() {
      const method = this.session && this.session.candidate ? this.session.candidate.model_type : ''
      if (method === 'local-llm-formula-refinement') return '本地大模型调整起始配方'
      if (method === 'quantum-formula-refinement') return 'QNN 筛选起始配方的局部调整'
      if (method === 'local-llm-grounded-selection') return '数据集候选（历史记录）'
      if (method === 'quantum-forward-screening') return 'QNN 筛选（历史记录）'
      if (method === 'quantum-blend-generation' || method === 'local-llm-blend-generation') return '旧版组合候选（历史记录）'
      return '模型生成候选配方'
    },
    candidateSourceText() {
      const candidate = this.session && this.session.candidate ? this.session.candidate : {}
      if (candidate.based_on === 'previous-candidate') return `基于上一轮 R${candidate.based_on_round_no || '—'} 候选调整`
      if (candidate.based_on === 'dataset-baseline') return `基于数据基线 #${candidate.based_on_baseline_id || (this.session.baseline || {}).source_sample_id || '—'} 生成`
      const parents = candidate.parent_sample_ids || []
      return parents.length ? `旧版历史组合样本 ${parents.join(' + ')}` : `历史候选 #${candidate.source_sample_id || '—'}`
    },
    improvementClass() {
      const value = this.session && this.session.evidence ? Number(this.session.evidence.improvement_rate) : 0
      return value > 0 ? 'positive' : (value < 0 ? 'negative' : '')
    },
    candidateEntries() {
      const components = this.session && this.session.candidate ? this.session.candidate.components || {} : {}
      return Object.entries(components)
        .map(([name, ratio]) => ({ name, ratio: Number(ratio) }))
        .filter(item => item.ratio > 0)
        .sort((a, b) => b.ratio - a.ratio)
    },
    candidateAdjustments() {
      const adjustments = this.session && this.session.candidate ? this.session.candidate.adjustments || [] : []
      return adjustments
        .map(item => ({
          material: item.material,
          before: Number(item.before),
          after: Number(item.after),
          delta: Number(item.delta)
        }))
        .filter(item => item.material && Number.isFinite(item.delta) && Math.abs(item.delta) > 0.000001)
        .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))
    },
    candidateProperties() {
      const predicted = this.session && this.session.candidate ? this.session.candidate.predicted || {} : {}
      const targets = this.session ? this.session.targets || {} : {}
      return this.propertyFields
        .map(field => ({
          key: field.key,
          label: field.label,
          value: predicted[field.key] !== null && predicted[field.key] !== undefined
            ? `${predicted[field.key]}${field.unit ? ` ${field.unit}` : ''}`
            : '暂无数据',
          target: targets[field.key] !== null && targets[field.key] !== undefined ? `本轮目标 ${targets[field.key]}` : '未设为本轮目标'
        }))
    },
    trustedCount() { return this.history.filter(item => item.status === 'accepted').length },
    averageEvidence() {
      const scored = this.history.filter(item => item.evidence && Number.isFinite(Number(item.evidence.score)))
      if (!scored.length) return '—'
      return (scored.reduce((sum, item) => sum + Number(item.evidence.score), 0) / scored.length).toFixed(1)
    },
    statusText() { return this.statusLabelFor(this.session ? this.session.status : '') },
    statusClass() { return this.statusClassFor(this.session ? this.session.status : '') },
    feedbackLocked() { return !!(this.session && this.session.feedback) },
    canSubmitFeedback() {
      if (!this.session || this.feedbackLocked) return false
      const hasObservation = this.activePropertyFields.some(field => Number(this.feedback.observations[field.key]) > 0)
      return !!String(this.feedback.run_id || '').trim()
        && !!String(this.feedback.environment || '').trim()
        && Number(this.feedback.sample_count) >= 1
        && hasObservation
    },
    canStartNext() { return this.session && ['accepted', 'iteration_ready'].includes(this.session.status) },
    gateTitle() {
      const gate = this.session && this.session.evidence ? this.session.evidence.gate : ''
      return { pass: '证据审核通过', iterate: '建议继续迭代', review: '需要专家复核', insufficient: '证据不完整' }[gate] || '等待评估'
    },
    stages() {
      const maxAvailable = !this.session ? 1 : (this.session.evidence ? 4 : 3)
      return [
        { name: '目标设定', desc: '目标与模型' },
        { name: '方案确认', desc: '基线、配方与流程' },
        { name: '实测录入', desc: '真实实验数据' },
        { name: '结果决策', desc: '比较并迭代' }
      ].map((stage, index) => {
        const step = index + 1
        return { ...stage, index: step, available: step <= maxAvailable, state: step === this.activeStep ? 'active' : (step < this.activeStep ? 'done' : '') }
      })
    }
  },
  mounted() { this.fetchModels(); this.fetchHistory() },
  methods: {
    showNotice(message, type = 'success') {
      this.notice = message
      this.noticeType = type
      clearTimeout(this.noticeTimer)
      this.noticeTimer = setTimeout(() => { this.notice = '' }, 4200)
    },
    errorMessage(error) { return (error.response && error.response.data && error.response.data.error) || error.message || '请求失败' },
    async fetchModels() {
      this.loadingModels = true
      try {
        const response = await axios.get(`${API_BASE}/models`)
        this.backendOnline = true
        this.models = response.data.data || []
        const readyIds = new Set(this.models.filter(item => item.status === 'ready').map(item => item.id))
        const firstReady = this.models.find(item => item.status === 'ready')
        if (!readyIds.has(this.form.candidate_model) && firstReady) this.form.candidate_model = firstReady.id
      } catch (error) { this.backendOnline = false; this.showNotice(this.errorMessage(error), 'error') }
      finally { this.loadingModels = false }
    },
    selectUploadFile(event) { this.uploadForm.file = event.target.files && event.target.files[0] },
    async uploadModel() {
      if (!this.uploadForm.file) return
      this.uploading = true
      try {
        const body = new FormData()
        body.append('file', this.uploadForm.file)
        body.append('model_kind', this.uploadForm.model_kind)
        body.append('display_name', this.uploadForm.display_name)
        const response = await axios.post(`${API_BASE}/models/upload`, body)
        await this.fetchModels()
        const uploaded = response.data.data
        if (uploaded && uploaded.status === 'ready') {
          this.form.candidate_model = uploaded.id
          this.showNotice(`模型 ${uploaded.name} 已接入并选中`)
          this.uploadForm = { display_name: '', model_kind: this.uploadForm.model_kind, file: null }
        } else {
          this.showNotice((uploaded && uploaded.status_text) || '文件已保存，但模型尚不能运行', 'error')
        }
      } catch (error) { this.showNotice(this.errorMessage(error), 'error') }
      finally { this.uploading = false }
    },
    async fetchHistory() {
      try { this.history = (await axios.get(`${API_BASE}/sessions`)).data; this.backendOnline = true }
      catch (error) { this.backendOnline = false; this.showNotice(this.errorMessage(error), 'error') }
    },
    async advanceFromGoal() {
      if (this.targetsNeedExtraction) {
        await this.extractTargets()
        return
      }
      await this.createLoop()
    },
    async extractTargets() {
      const objective = String(this.form.objective || '').trim()
      if (!objective) {
        this.showNotice('请先填写本轮研究目标', 'error')
        return false
      }
      if (!this.extractionModel) {
        this.showNotice('没有可用于目标提取的本地大模型，请先启动 Ollama 并确认模型可用', 'error')
        return false
      }
      this.extractingTargets = true
      try {
        const modelName = this.extractionModel.ollama_name || this.extractionModel.id.replace(/^ollama:/, '')
        const response = await axios.post(`${API_ORIGIN}/extract-parameters`, {
          text: objective,
          model_type: 'llm',
          model_name: modelName,
          strict_llm: true
        })
        const extracted = response.data.data || {}
        const nextTargets = emptyTargets()
        let count = 0
        this.propertyFields.forEach(field => {
          const value = extracted[field.key]
          if (value !== null && value !== undefined && Number(value) > 0) {
            nextTargets[field.key] = Number(value)
            count += 1
          }
        })
        if (!count) throw new Error('大模型没有识别到数据集支持的数值性质，请在研究目标中写明性质名称和目标值')
        this.form.targets = nextTargets
        this.lastExtractedObjective = objective
        this.extractionSummary = `已由本地模型 ${response.data.model_name || modelName} 提取 ${count} 项目标性质，请核对数值。`
        this.showNotice('目标性质已自动回填，请核对后生成候选配方')
        return true
      } catch (error) {
        this.extractionSummary = ''
        this.showNotice(this.errorMessage(error), 'error')
        return false
      } finally {
        this.extractingTargets = false
      }
    },
    async createLoop() {
      if (!this.canCreateLoop) {
        this.showNotice(this.createHint || '请先完成研究目标设置', 'error')
        return
      }
      this.creating = true
      try {
        const response = await axios.post(`${API_BASE}/sessions`, this.form)
        this.session = response.data.data
        this.feedback = emptyFeedback()
        this.activeStep = 2
        await this.fetchHistory()
        this.showNotice('第一轮候选配方已生成，请按固定流程开展实验')
      } catch (error) { this.showNotice(this.errorMessage(error), 'error') }
      finally { this.creating = false }
    },
    async evaluateEvidence() {
      if (!this.session || this.feedbackLocked) return
      if (!this.canSubmitFeedback) {
        this.showNotice('请先完整填写实验标识、环境、试件数量和实测值', 'error')
        return
      }
      this.submitting = true
      try {
        const response = await axios.post(`${API_BASE}/sessions/${this.session.id}/feedback`, this.feedback)
        this.session = response.data.data
        this.activeStep = 4
        await this.fetchHistory()
        this.showNotice('实测结果已审核，决策状态已更新')
      } catch (error) { this.showNotice(this.errorMessage(error), 'error') }
      finally { this.submitting = false }
    },
    async startNextRound() {
      if (!this.session || !this.canStartNext || !this.nextModelReady) return
      this.creating = true
      try {
        const response = await axios.post(`${API_BASE}/sessions/${this.session.id}/next`, {
          candidate_model: this.form.candidate_model
        })
        this.session = response.data.data
        this.feedback = emptyFeedback()
        this.activeStep = 2
        await this.fetchHistory()
        this.showNotice(`第 ${this.session.round_no} 轮候选已生成，上一轮证据已保留`)
      } catch (error) { this.showNotice(this.errorMessage(error), 'error') }
      finally { this.creating = false }
    },
    loadSession(item) {
      this.session = item
      const storedModel = item.candidate_model || item.candidate.model_id || 'ollama:qwen3.5:9b'
      const storedReady = this.models.some(model => model.id === storedModel && model.status === 'ready')
      const fallbackModel = this.candidateModels.find(model => model.status === 'ready')
      this.form = {
        objective: item.objective,
        hypothesis: item.hypothesis,
        targets: { ...emptyTargets(), ...item.targets },
        candidate_model: storedReady ? storedModel : (fallbackModel ? fallbackModel.id : storedModel)
      }
      this.feedback = item.feedback ? {
        observations: { ...emptyTargets(), ...(item.feedback.observations || {}) },
        checks: { ...emptyFeedback().checks, ...(item.feedback.checks || {}) },
        run_id: item.feedback.run_id || '', environment: item.feedback.environment || '',
        sample_count: item.feedback.sample_count || '', notes: item.feedback.notes || ''
      } : emptyFeedback()
      this.lastExtractedObjective = item.objective
      this.extractionSummary = ''
      this.view = 'workspace'
      this.activeStep = item.evidence ? 4 : 2
    },
    resetWorkspace() {
      this.session = null
      this.feedback = emptyFeedback()
      this.activeStep = 1
      this.lastExtractedObjective = ''
      this.extractionSummary = ''
      this.form = {
        objective: '', hypothesis: '', targets: emptyTargets(),
        candidate_model: this.form.candidate_model || 'ollama:qwen3.5:9b'
      }
    },
    openHistory() { this.view = 'history'; this.fetchHistory() },
    goToStep(step) {
      const available = this.stages.find(item => item.index === step && item.available)
      if (available) this.activeStep = step
    },
    displayTarget(key) {
      const value = this.session && this.session.targets ? this.session.targets[key] : null
      return value === null || value === undefined ? '—' : value
    },
    formatRatio(value) { return `${(Number(value || 0) * 100).toFixed(2).replace(/\.?0+$/, '')}%` },
    formatPercent(value) { return `${(Number(value || 0) * 100).toFixed(2).replace(/\.?0+$/, '')}%` },
    displayEvidencePercent(value) { return value === null || value === undefined ? '—' : `${value}%` },
    signedPercent(value) {
      if (value === null || value === undefined) return '—'
      const number = Number(value)
      return `${number > 0 ? '+' : ''}${number.toFixed(1)}%`
    },
    signedRatio(value) {
      if (value === null || value === undefined) return '—'
      const number = Number(value) * 100
      return `${number > 0 ? '+' : ''}${number.toFixed(1)}%`
    },
    formatTime(value) { return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—' },
    statusLabelFor(status) {
      return { candidate_ready: '等待实验反馈', accepted: '审核通过', iteration_ready: '可进入下一轮', review_required: '等待专家复核' }[status] || '尚未启动'
    },
    statusClassFor(status) {
      return { candidate_ready: 'waiting', accepted: 'accepted', iteration_ready: 'iterate', review_required: 'review' }[status] || 'idle'
    }
  }
}
</script>

<style>
* { box-sizing: border-box; }
html, body { margin: 0; min-height: 100%; background: #f3f5f7; color: #172033; font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif; }
button, input, textarea, select { font: inherit; }
button { cursor: pointer; }
.loop-shell { min-height: 100vh; background: radial-gradient(circle at 80% 0, rgba(238, 120, 52, .08), transparent 28%), #f3f5f7; }
.topbar { height: 72px; padding: 0 4vw; display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; background: #111827; color: #fff; }
.back-home { color: #b8c2d3; text-decoration: none; font-size: 13px; font-weight: 650; }
.back-home:hover { color: #fff; }
.brand-block { display: flex; align-items: center; gap: 12px; }
.brand-mark { width: 38px; height: 38px; display: grid; place-items: center; border-radius: 11px; background: #ed7b2f; font-size: 13px; font-weight: 900; letter-spacing: .5px; }
.brand-block div { display: flex; flex-direction: column; gap: 2px; }
.brand-block strong { font-size: 15px; letter-spacing: .4px; }
.brand-block div span { font-size: 11px; color: #94a3b8; }
.engine-pill { justify-self: end; font-size: 12px; color: #cbd5e1; }
.engine-pill span { display: inline-block; width: 7px; height: 7px; margin-right: 7px; border-radius: 50%; background: #34d399; box-shadow: 0 0 0 4px rgba(52,211,153,.12); }
.engine-pill.offline span { background: #f87171; box-shadow: 0 0 0 4px rgba(248,113,113,.12); }
.page-wrap { width: min(1480px, 94vw); margin: 0 auto; padding: 38px 0 70px; }
.hero { display: flex; justify-content: space-between; align-items: flex-end; gap: 30px; margin-bottom: 28px; }
.eyebrow, .panel-kicker { display: block; margin-bottom: 9px; color: #d96925; font-size: 11px; font-weight: 850; letter-spacing: 1.5px; }
.hero h1 { margin: 0 0 10px; font-size: clamp(28px, 3vw, 44px); line-height: 1.15; letter-spacing: -1.4px; color: #111827; }
.hero p { max-width: 820px; margin: 0; color: #687386; line-height: 1.75; font-size: 15px; }
.hero-actions { display: flex; padding: 4px; border: 1px solid #dde2e8; border-radius: 12px; background: #fff; box-shadow: 0 4px 16px rgba(17,24,39,.04); }
.tab-button { padding: 10px 16px; border: 0; border-radius: 8px; background: transparent; color: #6b7280; font-size: 13px; font-weight: 700; white-space: nowrap; }
.tab-button.active { background: #111827; color: #fff; }
.metrics-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 16px; }
.metric-card { min-height: 124px; padding: 20px 22px; border: 1px solid #e0e4e9; border-radius: 16px; background: #fff; box-shadow: 0 5px 18px rgba(17,24,39,.035); }
.metric-card > span { color: #7b8495; font-size: 12px; font-weight: 650; }
.metric-card b { display: block; margin: 9px 0 4px; font-size: 30px; letter-spacing: -1px; }
.metric-card b em { margin-left: 2px; font-size: 14px; font-style: normal; }
.metric-card small { color: #9aa2af; font-size: 11px; }
.accent-card { color: #fff; border-color: #172033; background: #172033; }
.accent-card > span, .accent-card small { color: #aeb8c9; }
.pipeline-card { display: grid; grid-template-columns: repeat(7, 1fr); margin-bottom: 16px; padding: 15px 18px; border: 1px solid #e0e4e9; border-radius: 16px; background: #fff; }
.stage { position: relative; display: flex; align-items: center; gap: 10px; min-width: 0; opacity: .45; }
.stage.done, .stage.active { opacity: 1; }
.stage-index { flex: 0 0 30px; height: 30px; display: grid; place-items: center; border: 1px solid #d9dee5; border-radius: 50%; color: #7a8495; font-size: 11px; font-weight: 800; }
.stage.done .stage-index { color: #fff; border-color: #1f9d77; background: #1f9d77; }
.stage.active .stage-index { color: #fff; border-color: #ed7b2f; background: #ed7b2f; box-shadow: 0 0 0 5px rgba(237,123,47,.1); }
.stage div { display: flex; flex-direction: column; min-width: 0; }
.stage b { font-size: 12px; }
.stage small { margin-top: 2px; color: #8d96a4; font-size: 10px; white-space: nowrap; }
.stage > i { position: absolute; right: 12px; color: #c5cbd4; font-style: normal; }
.workspace-grid { display: grid; grid-template-columns: minmax(0, 1.08fr) minmax(0, .92fr); gap: 16px; align-items: start; }
.workspace-column { display: flex; flex-direction: column; gap: 16px; }
.panel, .history-panel { padding: 24px; border: 1px solid #e0e4e9; border-radius: 18px; background: #fff; box-shadow: 0 6px 20px rgba(17,24,39,.035); }
.panel-heading { display: flex; justify-content: space-between; align-items: flex-start; gap: 20px; margin-bottom: 20px; }
.panel-heading h2, .history-header h2 { margin: 0; color: #172033; font-size: 19px; letter-spacing: -.3px; }
.field-label { display: block; margin: 16px 0 7px; color: #4e596a; font-size: 12px; font-weight: 750; }
input, textarea, select { width: 100%; border: 1px solid #dce1e7; border-radius: 10px; background: #fafbfc; color: #172033; outline: none; transition: .2s; }
input { height: 42px; padding: 0 12px; }
select { height: 42px; padding: 0 10px; }
textarea { min-height: 82px; padding: 11px 12px; resize: vertical; line-height: 1.6; }
input:focus, textarea:focus, select:focus { border-color: #ed7b2f; background: #fff; box-shadow: 0 0 0 3px rgba(237,123,47,.08); }
input:disabled, textarea:disabled { color: #6d7685; background: #f1f3f5; }
.model-config-grid { display: grid; grid-template-columns: 1fr; gap: 12px; margin-top: 17px; padding: 15px; border-radius: 12px; background: #f7f8fa; }
.model-config-grid label > span, .upload-grid label > span { display: block; margin-bottom: 6px; color: #4f5b6d; font-size: 11px; font-weight: 800; }
.model-config-grid label > small { display: block; margin-top: 6px; line-height: 1.45; }
.model-upload { margin-top: 10px; border: 1px solid #e4e7eb; border-radius: 11px; background: #fff; }
.model-upload summary { padding: 12px 14px; color: #d96925; cursor: pointer; font-size: 11px; font-weight: 800; }
.upload-grid { display: grid; grid-template-columns: 1fr 1.2fr; gap: 11px; padding: 4px 14px 12px; }
.upload-grid .secondary-button { align-self: end; height: 42px; }
.model-upload > p { margin: 0; padding: 0 14px 13px; color: #8a93a1; font-size: 10px; }
.model-upload code { color: #d96925; }
.target-grid, .observation-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 11px; margin-top: 17px; }
.target-grid label > span, .observation-grid label > span, .run-meta-grid label > span { display: block; margin-bottom: 6px; color: #566173; font-size: 11px; font-weight: 750; }
label small { color: #9ba3af; font-weight: 500; }
.observation-grid em { display: block; margin-top: 5px; color: #9aa2af; font-size: 10px; font-style: normal; }
.primary-button, .secondary-button, .next-button { border: 0; border-radius: 10px; font-weight: 750; }
.primary-button { padding: 13px 18px; color: #fff; background: #ed7b2f; box-shadow: 0 8px 18px rgba(237,123,47,.2); }
.primary-button:hover { background: #d96925; }
.primary-button:disabled, .next-button:disabled { cursor: not-allowed; opacity: .55; }
.full { width: 100%; margin-top: 20px; }
.text-button { border: 0; background: transparent; color: #d96925; font-size: 12px; font-weight: 750; }
.sample-tag, .version-tag, .status-tag { padding: 6px 9px; border-radius: 7px; font-size: 10px; font-weight: 800; }
.sample-tag { color: #9a4b18; background: #fff1e7; }
.version-tag { color: #4d5b70; background: #eef1f5; }
.model-note { margin: -5px 0 18px; color: #687386; font-size: 12px; line-height: 1.65; }
.plain-explanation { margin: -5px 0 16px; color: #687386; font-size: 12px; line-height: 1.65; }
.baseline-panel { border-left: 3px solid #4b89d1; }
.baseline-property-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 9px; }
.baseline-property-grid div { padding: 11px 12px; border-radius: 9px; background: #f4f8fd; }
.baseline-property-grid span, .baseline-property-grid small { display: block; color: #8290a3; font-size: 10px; }
.baseline-property-grid b { display: block; margin: 4px 0; color: #265e9e; font-size: 14px; }
.baseline-footer { display: flex; justify-content: space-between; margin-top: 12px; padding-top: 11px; border-top: 1px solid #e7edf5; color: #657286; font-size: 11px; }
.baseline-footer b { color: #265e9e; }
.composition-list { display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px 18px; }
.composition-row > div:first-child { display: flex; justify-content: space-between; margin-bottom: 6px; font-size: 12px; }
.composition-row b { color: #d96925; }
.ratio-track { height: 6px; overflow: hidden; border-radius: 999px; background: #eceff3; }
.ratio-track i { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, #ed7b2f, #f1a26d); }
.candidate-meta { display: flex; gap: 22px; margin-top: 20px; padding-top: 14px; border-top: 1px solid #edf0f3; color: #8a93a1; font-size: 11px; }
.candidate-meta b { color: #465164; }
.protocol-list { display: flex; flex-direction: column; gap: 10px; margin: 0; padding: 0; list-style: none; }
.protocol-list li { display: flex; align-items: flex-start; gap: 10px; color: #566173; font-size: 12px; line-height: 1.65; }
.protocol-list li span { flex: 0 0 25px; height: 25px; display: grid; place-items: center; border-radius: 7px; color: #d96925; background: #fff2e9; font-size: 10px; font-weight: 850; }
.plan-heading-actions { display: flex; align-items: center; gap: 8px; }
.locked-note { color: #929aa7; font-size: 10px; }
.plan-model-note { display: flex; gap: 9px; align-items: flex-start; margin: -6px 0 16px; padding: 10px 12px; border-left: 3px solid #ed7b2f; background: #fff8f3; font-size: 10px; line-height: 1.55; }
.plan-model-note b { color: #b55419; white-space: nowrap; }.plan-model-note span { color: #7a8493; }
.baseline-explainer { display: flex; flex-direction: column; gap: 5px; margin: 16px 0 10px; padding: 12px 14px; border-radius: 10px; color: #4f5b6d; background: #edf5ff; font-size: 11px; line-height: 1.65; }
.baseline-explainer b { color: #265e9e; }
.plan-notes { display: grid; gap: 8px; margin-top: 18px; padding: 14px; border-radius: 10px; background: #f7f8fa; }
.plan-notes div { display: grid; grid-template-columns: 70px 1fr; gap: 8px; font-size: 11px; }
.plan-notes span { color: #8a93a1; }
.plan-notes b { color: #586376; font-weight: 650; }
.plan-notes small { grid-column: 2; color: #929aa7; line-height: 1.55; }
.evidence-details { grid-column: 1 / -1; padding-top: 7px; border-top: 1px solid #e3e7ec; color: #647084; font-size: 11px; }
.evidence-details summary { cursor: pointer; font-weight: 700; }.evidence-details ul { margin: 8px 0 0; padding-left: 18px; line-height: 1.7; }
.status-tag.waiting { color: #9a6510; background: #fff6dd; }
.status-tag.accepted { color: #157458; background: #e5f7f1; }
.status-tag.iterate { color: #265e9e; background: #e9f2ff; }
.status-tag.review { color: #a83d3d; background: #ffebeb; }
.empty-evidence { padding: 70px 25px; text-align: center; }
.empty-evidence > span { display: block; color: #ed7b2f; font-size: 42px; }
.empty-evidence h3 { margin: 14px 0 7px; font-size: 16px; }
.empty-evidence p { max-width: 370px; margin: auto; color: #8a93a1; font-size: 12px; line-height: 1.7; }
.run-meta-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 11px; margin-bottom: 14px; }
.check-section { margin-top: 22px; padding: 16px; border: 1px solid #e6e9ed; border-radius: 12px; background: #fafbfc; }
.check-section h3 { margin: 0 0 12px; font-size: 13px; }
.check-row { display: flex; gap: 10px; align-items: flex-start; margin-top: 10px; cursor: pointer; }
.check-row input { flex: 0 0 16px; width: 16px; height: 16px; margin-top: 2px; accent-color: #ed7b2f; }
.check-row span { display: flex; flex-direction: column; gap: 2px; }
.check-row b { color: #4e596a; font-size: 11px; }
.check-row small { color: #939ba8; font-size: 10px; }
.notes-area { min-height: 74px; }
.gate-panel { border-top: 3px solid #ed7b2f; }
.gate-score { display: flex; align-items: center; gap: 20px; }
.gate-score h2 { margin: 2px 0 7px; font-size: 20px; }
.gate-score p { margin: 0; color: #687386; font-size: 12px; line-height: 1.6; }
.score-ring { flex: 0 0 88px; height: 88px; display: flex; flex-direction: column; align-items: center; justify-content: center; border: 7px solid #e4e7eb; border-radius: 50%; }
.score-ring.pass { border-color: #2aae83; }.score-ring.iterate { border-color: #4b89d1; }.score-ring.review, .score-ring.insufficient { border-color: #e06767; }
.score-ring b { font-size: 23px; }.score-ring span { color: #8b94a2; font-size: 9px; }
.score-breakdown { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 20px 0; }
.score-breakdown.four { grid-template-columns: repeat(4, 1fr); }
.score-breakdown div { padding: 12px; border-radius: 9px; background: #f6f8fa; }
.score-breakdown span { display: block; color: #8b94a2; font-size: 10px; }.score-breakdown b { display: block; margin-top: 5px; font-size: 16px; }
.score-breakdown b.positive { color: #157458; }.score-breakdown b.negative { color: #a83d3d; }
.comparison-table { overflow: hidden; border: 1px solid #e4e7eb; border-radius: 10px; }
.comparison-head, .comparison-row { display: grid; grid-template-columns: 1.15fr repeat(5, 1fr); align-items: center; padding: 9px 12px; font-size: 10px; }
.comparison-head { color: #8c95a3; background: #f5f7f9; font-weight: 750; }.comparison-row { border-top: 1px solid #edf0f3; color: #566173; }.comparison-row b { color: #d96925; }
.comparison-row b small { display: block; margin-top: 2px; color: #929aa7; font-size: 8px; font-weight: 500; }
.next-button { width: 100%; margin-top: 16px; padding: 12px; color: #fff; background: #172033; }
.history-panel { min-height: 480px; }
.history-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 22px; }
.history-header h2 { font-size: 24px; }.history-header p { margin: 7px 0 0; color: #858e9c; font-size: 12px; }
.secondary-button { padding: 10px 14px; border: 1px solid #dce1e7; color: #566173; background: #fff; }
.history-list { display: flex; flex-direction: column; gap: 8px; }
.history-item { width: 100%; display: grid; grid-template-columns: 48px 1fr auto 60px; align-items: center; gap: 14px; padding: 15px; border: 1px solid #e5e8ec; border-radius: 12px; background: #fff; text-align: left; }
.history-item:hover { border-color: #ed7b2f; background: #fffaf7; }
.history-round { width: 42px; height: 34px; display: grid; place-items: center; border-radius: 8px; color: #d96925; background: #fff0e6; font-size: 11px; font-weight: 850; }
.history-item div { display: flex; flex-direction: column; min-width: 0; }.history-item div b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }.history-item div small { margin-top: 4px; color: #929aa7; font-size: 10px; }
.history-status { padding: 5px 8px; border-radius: 6px; font-size: 9px; font-weight: 800; }.history-status.accepted { color: #157458; background: #e5f7f1; }.history-status.iterate { color: #265e9e; background: #e9f2ff; }.history-status.review { color: #a83d3d; background: #ffebeb; }.history-status.waiting { color: #9a6510; background: #fff6dd; }
.history-item > strong { justify-self: end; font-size: 11px; }.history-empty { padding: 100px 20px; color: #9aa2af; text-align: center; font-size: 13px; }
.notice { position: fixed; z-index: 50; right: 24px; bottom: 24px; max-width: 440px; padding: 13px 17px; border-radius: 10px; color: #fff; background: #172033; box-shadow: 0 14px 35px rgba(17,24,39,.22); font-size: 12px; }.notice.error { background: #a93e3e; }
@media (max-width: 1050px) { .workspace-grid { grid-template-columns: 1fr; }.metrics-grid { grid-template-columns: repeat(2, 1fr); }.pipeline-card { grid-template-columns: repeat(4, 1fr); gap: 18px; }.stage > i { display: none; } }
@media (max-width: 680px) { .topbar { height: auto; grid-template-columns: 1fr auto; gap: 14px; padding: 14px 4vw; }.brand-block { order: -1; }.engine-pill { display: none; }.hero { align-items: flex-start; flex-direction: column; }.metrics-grid { grid-template-columns: 1fr 1fr; }.pipeline-card { grid-template-columns: repeat(2, 1fr); }.target-grid, .observation-grid { grid-template-columns: repeat(2, 1fr); }.composition-list, .run-meta-grid, .model-config-grid, .upload-grid, .baseline-property-grid { grid-template-columns: 1fr; }.score-breakdown.four { grid-template-columns: repeat(2, 1fr); }.comparison-table { overflow-x: auto; }.comparison-head, .comparison-row { min-width: 560px; }.history-item { grid-template-columns: 42px 1fr; }.history-status, .history-item > strong { justify-self: start; }.page-wrap { width: 92vw; }.panel { padding: 18px; }.panel-heading { flex-direction: column; }.plan-heading-actions { width: 100%; justify-content: space-between; } }

/* 单窗口分步工作台 */
html, body { height: 100%; overflow: hidden; }
.loop-shell { height: 100vh; overflow: hidden; }
.topbar { height: 64px; }
.page-wrap { width: min(1320px, 95vw); height: calc(100vh - 64px); padding: 18px 0 22px; display: flex; flex-direction: column; overflow: hidden; }
.compact-head { flex: 0 0 58px; display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 28px; margin-bottom: 12px; }
.compact-head .eyebrow { margin-bottom: 3px; }
.compact-head h1 { margin: 0; font-size: 24px; letter-spacing: -.6px; }
.head-summary { justify-self: center; display: flex; gap: 6px; padding: 5px; border: 1px solid #e0e4e9; border-radius: 12px; background: #fff; }
.head-summary span { min-width: 112px; padding: 7px 12px; border-right: 1px solid #edf0f3; color: #88919f; font-size: 10px; white-space: nowrap; }
.head-summary span:last-child { border-right: 0; }
.head-summary b { display: block; margin-top: 2px; color: #263247; font-size: 13px; }
.single-workspace { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.stepper { flex: 0 0 72px; display: grid; grid-template-columns: repeat(4, 1fr); margin-bottom: 12px; padding: 6px; gap: 6px; border: 1px solid #e0e4e9; border-radius: 15px; background: #fff; box-shadow: 0 4px 14px rgba(17,24,39,.03); }
.step-tab { position: relative; display: flex; align-items: center; gap: 11px; padding: 8px 14px; border: 0; border-radius: 10px; color: #9aa2af; background: transparent; text-align: left; }
.step-tab::after { content: ''; position: absolute; right: -5px; width: 4px; height: 1px; background: #d8dde4; }
.step-tab:last-child::after { display: none; }
.step-tab:disabled { cursor: not-allowed; opacity: .45; }
.step-tab > span { flex: 0 0 32px; height: 32px; display: grid; place-items: center; border: 1px solid #dfe3e8; border-radius: 9px; font-size: 11px; font-weight: 850; }
.step-tab div { display: flex; flex-direction: column; gap: 2px; }
.step-tab b { color: #536075; font-size: 12px; }
.step-tab small { font-size: 10px; }
.step-tab.done { opacity: 1; }
.step-tab.done > span { color: #147457; border-color: #d5eee6; background: #e9f7f2; }
.step-tab.active { color: #b65a20; background: #fff4ec; box-shadow: inset 0 0 0 1px #f4d7c4; }
.step-tab.active > span { color: #fff; border-color: #ed7b2f; background: #ed7b2f; }
.step-tab.active b { color: #a64e18; }
.workflow-card { flex: 1; min-height: 0; padding: 0; overflow: hidden; border: 1px solid #dfe3e8; border-radius: 18px; background: #fff; box-shadow: 0 8px 28px rgba(17,24,39,.055); }
.step-pane { height: 100%; padding: 22px 26px 18px; overflow-y: auto; display: flex; flex-direction: column; animation: pane-in .22s ease-out; }
@keyframes pane-in { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }
.step-pane .panel-heading { flex: 0 0 auto; margin-bottom: 15px; padding-bottom: 13px; border-bottom: 1px solid #edf0f3; }
.step-pane .panel-heading p { margin: 5px 0 0; color: #8a93a1; font-size: 11px; }
.goal-layout { display: grid; grid-template-columns: 1.12fr .88fr; gap: 22px; }
.goal-copy textarea { min-height: 74px; }
.step-pane .model-config-grid { height: 100%; margin: 0; align-content: start; }
.step-pane .model-upload { margin-top: 12px; }
.step-pane .upload-grid { grid-template-columns: 1fr 1fr; }
.section-label { display: flex; align-items: baseline; gap: 10px; margin: 17px 0 9px; }
.section-label b { font-size: 12px; }
.section-label span { color: #9aa2af; font-size: 10px; }
.step-pane .target-grid { margin-top: 0; grid-template-columns: repeat(5, 1fr); }
.pane-actions { flex: 0 0 auto; display: flex; justify-content: flex-end; margin-top: auto; padding-top: 16px; }
.pane-actions.split { justify-content: space-between; }
.pane-actions .primary-button, .pane-actions .secondary-button { min-width: 180px; }
.primary-button.dark { background: #172033; box-shadow: 0 8px 18px rgba(17,32,51,.16); }
.review-grid { display: grid; grid-template-columns: .86fr 1.14fr; gap: 14px; }
.review-block, .protocol-box { padding: 15px 17px; border: 1px solid #e5e8ec; border-radius: 13px; background: #fafbfc; }
.baseline-review { background: #f6faff; border-color: #dfeaf7; }
.candidate-review { background: #fffaf6; border-color: #f4e3d7; }
.block-title { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.block-title small { color: #9099a7; font-size: 9px; font-weight: 750; }
.block-title h3 { margin: 2px 0 0; font-size: 15px; }
.block-title > b { color: #d96925; font-size: 11px; }
.review-block > p { min-height: 32px; margin: 8px 0 11px; color: #768193; font-size: 10px; line-height: 1.55; }
.review-block h4 { margin: 9px 0 7px; color: #626e80; font-size: 10px; }
.review-block .baseline-property-grid { grid-template-columns: repeat(2, 1fr); }
.review-block .composition-list { grid-template-columns: repeat(2, 1fr); gap: 9px 14px; max-height: 118px; overflow-y: auto; padding-right: 4px; }
.review-block .compact-composition { max-height: 82px; }
.adjustment-list { display: flex; flex-wrap: wrap; gap: 6px; }
.adjustment-chip { display: grid; grid-template-columns: auto auto auto; align-items: center; gap: 7px; padding: 6px 8px; border: 1px solid #eadfd7; border-radius: 8px; background: #fff; font-size: 10px; }
.adjustment-chip span { color: #536075; font-weight: 750; }
.adjustment-chip small { color: #929aa7; }
.adjustment-chip b.positive { color: #157458; }
.adjustment-chip b.negative { color: #a83d3d; }
.empty-inline { color: #9aa2af; font-size: 10px; }
.review-block .candidate-meta { justify-content: space-between; margin-top: 11px; padding-top: 10px; }
.protocol-box { margin-top: 14px; background: #fff; }
.protocol-list { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; margin-top: 12px; }
.protocol-list li { min-width: 0; padding: 9px; border-radius: 9px; background: #f6f7f9; line-height: 1.45; }
.protocol-list li p { margin: 0; }
.protocol-details { margin-top: 10px; color: #657286; font-size: 10px; }
.protocol-details summary { cursor: pointer; color: #d96925; font-weight: 750; }
.protocol-details > div { display: grid; grid-template-columns: 64px 1fr; gap: 6px 10px; margin-top: 9px; padding: 10px; border-radius: 8px; background: #f7f8fa; line-height: 1.55; }
.feedback-layout { display: grid; grid-template-columns: 1.08fr .92fr; gap: 22px; min-height: 0; }
.feedback-layout .observation-grid { margin-top: 0; }
.feedback-layout .check-section { margin-top: 0; padding: 13px 15px; }
.feedback-layout .check-row { margin-top: 8px; }
.feedback-layout .notes-area { min-height: 66px; }
.run-meta-grid.three { grid-template-columns: .8fr 1.4fr .7fr; }
.form-hint { margin: 10px 0 0; color: #a85a28; font-size: 10px; text-align: right; }
.extraction-note { margin: 10px 0 0; padding: 9px 11px; border-radius: 8px; color: #27664f; background: #edf8f3; font-size: 10px; }
.record-lock { margin: -2px 0 14px; padding: 10px 13px; border: 1px solid #dbe7f5; border-radius: 9px; color: #41658f; background: #f2f7fd; font-size: 11px; }
.next-round-config { margin-top: 16px; padding: 12px 14px; border: 1px solid #e4e7eb; border-radius: 10px; background: #f8f9fb; }
.next-round-config label { display: grid; grid-template-columns: 130px minmax(260px, 440px); align-items: center; gap: 12px; }
.next-round-config label > span { color: #566173; font-size: 11px; font-weight: 750; }
.next-round-config > small { display: block; margin: 7px 0 0 142px; color: #a34f4f; font-size: 10px; }
.review-stop { align-self: center; color: #9a4a4a; font-size: 11px; }
.result-hero { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 18px; padding: 4px 0 16px; border-bottom: 1px solid #edf0f3; }
.result-hero h2 { margin: 2px 0 5px; font-size: 21px; }
.result-hero p { margin: 0; color: #687386; font-size: 11px; }
.result-pane .score-breakdown { margin: 16px 0; }
.history-panel.workflow-card { padding: 22px 26px; overflow-y: auto; }

@media (max-width: 980px) {
  html, body, .loop-shell { height: auto; min-height: 100%; overflow: auto; }
  .page-wrap { height: auto; min-height: calc(100vh - 64px); overflow: visible; }
  .compact-head { grid-template-columns: 1fr auto; height: auto; }.head-summary { grid-column: 1 / -1; grid-row: 2; justify-self: stretch; justify-content: center; }
  .workflow-card { min-height: 640px; }.step-pane { height: auto; min-height: 640px; overflow: visible; }
  .step-tab small { display: none; }.goal-layout, .review-grid, .feedback-layout { grid-template-columns: 1fr; }.step-pane .target-grid { grid-template-columns: repeat(3, 1fr); }.protocol-list { grid-template-columns: 1fr 1fr; }.run-meta-grid.three { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 620px) {
  .compact-head { grid-template-columns: 1fr; }.hero-actions { justify-self: stretch; }.hero-actions button { flex: 1; }.head-summary { display: grid; grid-template-columns: 1fr 1fr; }.head-summary span { min-width: 0; border: 0; }
  .stepper { height: 62px; }.step-tab { justify-content: center; padding: 6px; }.step-tab div { display: none; }.step-pane { padding: 17px; }.step-pane .target-grid, .observation-grid, .run-meta-grid, .run-meta-grid.three, .upload-grid { grid-template-columns: 1fr 1fr; }.protocol-list { grid-template-columns: 1fr; }.pane-actions.split { gap: 8px; }.pane-actions .primary-button, .pane-actions .secondary-button { min-width: 0; flex: 1; }.result-hero { grid-template-columns: auto 1fr; }.result-hero .status-tag { grid-column: 1 / -1; justify-self: start; }.next-round-config label { grid-template-columns: 1fr; }
}
</style>
