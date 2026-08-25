from flask import Flask, request, jsonify
from flask_cors import CORS
from discovery_loop import create_discovery_blueprint
from model_manager import LocalModelManager
import httpx
import hashlib
import json
import re
import logging
import os
import numpy as np
import pandas as pd  # 新增：用于处理数据集

# ==================== 新增：导入量子模型 ====================
try:
    from quantum_predictor import init_quantum_model, QuantumConfig

    QUANTUM_AVAILABLE = True
    logging.info("✓ 量子模型模块导入成功")
except ImportError as e:
    QUANTUM_AVAILABLE = False
    logging.warning(f"⚠ 量子模型模块导入失败: {e}")

# ==================== 基础配置 ====================
# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("rock_api")

# 数据集文件路径配置 (统一使用 Excel 绝对路径)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_EXCEL = os.path.join(BASE_DIR, 'datasetnew.xlsx')
MODELS_DIR = os.path.join(BASE_DIR, 'models')

# ==================== Flask 应用初始化 ====================
app = Flask(__name__)
CORS(app)  # 允许跨域请求

# ==================== 本地 Ollama 大模型配置 ====================
OLLAMA_BASE_URL = os.getenv(
    "MATAGENT_OLLAMA_BASE_URL", "http://127.0.0.1:11434"
).rstrip("/")
OLLAMA_MODEL = os.getenv("MATAGENT_OLLAMA_MODEL", "qwen3.5:9b")
OLLAMA_TIMEOUT = float(os.getenv("MATAGENT_OLLAMA_TIMEOUT", "120"))
LLM_AVAILABLE = True
model_manager = LocalModelManager(MODELS_DIR, OLLAMA_BASE_URL)
logger.info("✓ 本地大模型已配置: %s (%s)", OLLAMA_MODEL, OLLAMA_BASE_URL)

# ==================== 初始化量子模型 ====================
quantum_model = None
if QUANTUM_AVAILABLE:
    try:
        # 自定义量子模型配置
        quantum_config = QuantumConfig()
        quantum_config.dataset_file = FILE_EXCEL
        quantum_config.pretrained_model_path = os.path.join(BASE_DIR, "best_qnn_model.pth")
        quantum_model = init_quantum_model(quantum_config)
        logger.info("✓ 量子模型初始化成功")
    except Exception as e:
        logger.warning(f"⚠ 量子模型初始化失败: {e}")

# ==================== 系统提示词（大模型）====================
SYSTEM_PROMPT = """你是一个专业的岩石力学参数提取助手。你的任务是从用户提供的自然语言描述中，准确提取岩石的力学性质参数。

**提取规则：**
1. 只提取明确提到的参数，未提及的参数设为null
   - 参数名称后只要出现数值就必须提取，不得因为没有单位、数值较小或看起来不合理而设为null
   - 例如“抗压强度0.482”必须提取compressive为0.482，“弹性模量54.517”必须提取elastic为54.517
   - 你只负责忠实提取原文数值，不负责判断数据是否合理
2. 数值保留原始精度，不要四舍五入
3. 识别同义词：抗压强度=单轴抗压强度=压缩强度=UCS
4. 识别范围值：如"10-15MPa"取中间值12.5
5. 识别约数：如"约150MPa"、"150MPa左右"提取为150
6. 单位统一转换：
   - 抗压强度：统一为MPa
   - 抗拉强度：统一为MPa
   - 弹性模量：统一为MPa（若原文为GPa，乘以1000）
   - 泊松比：无单位（0-0.5）
   - 密度：统一为g/cm³
   - 硬度：统一为HRC

**必须严格按照以下JSON格式输出，不要添加任何额外文字：**
```json
{
  "compressive": 数值或null,
  "tensile": 数值或null,
  "poisson": 数值或null,
  "elastic": 数值或null,
  "density": 数值或null,
  "hardness": 数值或null
}
```"""

FORMULA_SELECTION_PROMPT = """你是岩石相似材料配方筛选专家。
用户会提供目标力学性质和若干条来自真实实验数据集的候选配方。
你只能从候选配方中选择最接近目标的一条，不能创造候选编号、材料或配比。
返回JSON中的candidate_id必须是候选列表内的编号。reason用一句中文说明选择依据。"""

# ==================== 路由0: 获取真实数据集 ====================
@app.route('/api/dataset', methods=['GET'])
def get_dataset():
    """读取并合并真实数据集，供前端全景监控看板使用"""
    try:
        if not os.path.exists(FILE_EXCEL):
            logger.error("数据集文件未找到，请检查当前目录下是否存在对应的Excel文件。")
            return jsonify({"error": "Dataset files not found on server"}), 404

        # 1. 读取数据
        df1 = pd.read_excel(FILE_EXCEL, sheet_name='Sheet1')
        df2 = pd.read_excel(FILE_EXCEL, sheet_name='Sheet2')

        # 2. 合并数据 (基于 label 列)
        merged = pd.merge(df1, df2, on='label', how='inner')
        merged = merged.fillna(0) # 将 NaN 替换为 0

        # 3. 构造 JSON
        result = []
        for _, row in merged.iterrows():
            # 自动提取 Sheet1 中所有比例 > 0 的材料组分
            components = {
                col: round(float(row[col]), 4)
                for col in df1.columns if col != 'label' and float(row[col]) > 0
            }

            result.append({
                "id": str(int(row['label'])),
                # 性能指标 (对应 Sheet2)
                "strength": round(float(row.get('抗压强度(MPa)', 0)), 3),
                "tensile": round(float(row.get('抗拉强度(MPa)', 0)), 3),
                "elastic": round(float(row.get('弹性模量(MPa)', 0)), 3),
                "poisson": round(float(row.get('泊松比', 0)), 3),
                "density": round(float(row.get('密度g/cm³', 0)), 3),
                # 组分数据 (对应 Sheet1)
                "components": components,
                # 从数据集中提取或者提供默认标记
                "method": "3D打印" if float(row.get('抗压强度(MPa)', 0)) > 5 else "实验浇筑"
            })

        logger.info(f"[数据集加载] 成功加载 {len(result)} 条合并后的配方数据")
        return jsonify(result)
    except Exception as e:
        logger.error(f"[数据集加载失败] {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ==================== 路由1: 配方生成（支持模型选择）====================
@app.route("/get", methods=['POST'])
def get_formula():
    """配方生成接口"""
    try:
        data = request.get_json()
        input_text = data.get('input', '').strip()
        model_type = data.get('model_type', 'default').lower()

        if not input_text:
            return jsonify({'success': False, 'error': '请提供input参数'}), 400

        logger.info(f"[配方生成] 输入: {input_text[:100]}... | 模型类型: {model_type}")

        targets = extract_with_regex(input_text)
        if not any(value is not None for value in targets.values()):
            return jsonify({'success': False, 'error': '输入中未识别到可用于配方设计的目标参数'}), 400

        if model_type == 'quantum':
            reason = (
                '当前QNN是正向性能预测模型：输入为8维材料配比，输出仅包含抗压强度和弹性模量；'
                '它没有“目标性能→材料名称及配比”的逆向输出层，因此不能生成Candidate Top-1配方。'
            )
            logger.warning("[配方生成] 量子模型不支持逆向配方生成")
            return jsonify({
                'success': False,
                'error': reason,
                'model_type': 'quantum',
                'capabilities': {
                    'input': '8维材料配比',
                    'output': ['抗压强度', '弹性模量'],
                    'inverse_formula_generation': False,
                },
            }), 422

        if model_type not in {'llm', 'default'}:
            return jsonify({'success': False, 'error': f'不支持的模型类型: {model_type}'}), 400

        candidates = build_formula_candidates(targets, limit=6)
        if not candidates:
            return jsonify({'success': False, 'error': '真实数据集中没有可用的候选配方'}), 500

        selected_id, reason = select_formula_with_local_llm(targets, candidates)
        selected = next(item for item in candidates if item['id'] == selected_id)

        logger.info("[配方生成] 本地大模型选择数据集配方 #%s", selected_id)
        return jsonify({
            'success': True,
            'model_type': 'llm',
            'method': 'local-llm-grounded-selection',
            'model_name': OLLAMA_MODEL,
            'data': {
                'components': selected['components'],
                'predicted': selected['predicted'],
                'similarity': selected['similarity'],
                'source_sample_id': selected['id'],
                'reason': reason or '本地大模型从真实数据集近邻候选中选出该配方。',
            },
        })

    except Exception as e:
        logger.error(f"[配方生成错误] {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== 路由2: 语义提取（新增量子模型选项）====================
@app.route('/extract-parameters', methods=['POST'])
def extract_parameters():
    """语义提取接口"""
    try:
        data = request.get_json()
        text = data.get('text', '').strip()
        model_type = data.get('model_type', 'llm').lower()
        requested_model = str(data.get('model_name') or OLLAMA_MODEL).strip()
        strict_llm = bool(data.get('strict_llm', False))

        if not text:
            return jsonify({'success': False, 'error': '请提供text参数'}), 400

        logger.info(f"\n[语义提取] 文本预览: {text[:100]}... | 模型类型: {model_type}")

        result = None
        method = 'none'

        if model_type == 'quantum' and QUANTUM_AVAILABLE and quantum_model:
            logger.info("[语义提取] 尝试使用量子模型...")
            try:
                regex_result = extract_with_regex(text)
                quantum_input = convert_params_to_quantum_input(regex_result)
                quantum_result = quantum_model.predict_unified(quantum_input)

                if "error" not in quantum_result:
                    result = quantum_result['predictions']
                    method = 'quantum'
                    logger.info("[语义提取] 量子模型提取成功")
            except Exception as e:
                logger.error(f"量子模型提取失败: {e}")

        elif model_type == 'llm' and LLM_AVAILABLE:
            logger.info("[语义提取] 尝试使用大模型...")
            llm_result = extract_with_llm(text, requested_model)
            regex_result = extract_with_regex(text)
            if llm_result:
                result = {
                    key: llm_result.get(key)
                    if llm_result.get(key) is not None
                    else regex_result.get(key)
                    for key in PARAMETER_KEYS
                }
                llm_count = sum(llm_result.get(key) is not None for key in PARAMETER_KEYS)
                regex_fill_count = sum(
                    llm_result.get(key) is None and regex_result.get(key) is not None
                    for key in PARAMETER_KEYS
                )
                if llm_count:
                    method = 'local-llm+regex' if regex_fill_count else 'local-llm'
                    logger.info(
                        "[语义提取] 大模型提取成功，LLM命中 %s 项，正则补齐 %s 项",
                        llm_count,
                        regex_fill_count,
                    )
                elif any(value is not None for value in regex_result.values()):
                    result = regex_result
                    method = 'regex'
                    logger.warning("[语义提取] 大模型未返回有效数值，已回退正则提取")
                else:
                    result = None
                    if strict_llm:
                        return jsonify({
                            'success': False,
                            'error': '本地大模型没有从研究目标中识别到明确的数值性质，请补充目标数值后重试',
                        }), 422
            elif strict_llm:
                return jsonify({
                    'success': False,
                    'error': f'本地大模型 {requested_model} 调用失败，请确认 Ollama 已启动且模型可用',
                }), 503

        if result is None:
            logger.info("[语义提取] 使用正则表达式提取...")
            result = extract_with_regex(text)
            method = 'regex'

        logger.info(f"[语义提取] 提取结果: {result} | 方法: {method}")
        return jsonify({
            'success': True,
            'data': result,
            'method': method,
            'model_name': requested_model if method.startswith('local-llm') else None,
        })

    except Exception as e:
        logger.error(f"[语义提取错误] {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== 路由3: 健康检查（新增量子模型状态）====================
@app.route('/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    # 统一修改为 FILE_EXCEL
    dataset_ok = os.path.exists(FILE_EXCEL)
    local_llm_ok = is_local_llm_available()
    return jsonify({
        'status': 'healthy',
        'services': {
            'formula_generation': 'available',
            'semantic_extraction': 'available',
            'llm': 'available' if local_llm_ok else 'unavailable',
            'quantum': 'available' if QUANTUM_AVAILABLE and quantum_model else 'unavailable',
            'regex': 'available',
            'dataset': 'available' if dataset_ok else 'unavailable'
        },
        'version': '1.0.2'
    })


# ==================== 路由4: API信息 ====================
@app.route('/', methods=['GET'])
def index():
    """API信息"""
    return jsonify({
        'name': '岩石相似材料配方设计系统 API',
        'version': '1.0.2',
        'endpoints': {
            'GET /api/dataset': {'description': '获取真实合并后的材料数据集 (看板与明细用)'},
            'POST /get': {'description': '生成配方设计（支持模型选择）'},
            'POST /extract-parameters': {'description': '从自然语言提取岩石参数'},
            'GET /health': {'description': '健康检查（包含量子模型与数据集状态）'}
        },
        'model_support': {
            'llm': f'本地 Ollama 大模型（{OLLAMA_MODEL}）',
            'quantum': '量子神经网络模型（QNN）',
            'regex': '正则表达式（兜底方案）'
        }
    })


# ==================== 辅助函数：本地 Ollama 大模型 ====================
def is_local_llm_available() -> bool:
    """检查 Ollama 服务是否在线且目标模型已经安装。"""
    try:
        response = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2.0)
        response.raise_for_status()
        models = response.json().get("models", [])
        return any(
            item.get("name") == OLLAMA_MODEL or item.get("model") == OLLAMA_MODEL
            for item in models
        )
    except Exception:
        return False


def extract_with_llm(text: str, model_name: str = OLLAMA_MODEL) -> dict:
    try:
        user_prompt = f"请忠实提取以下岩石描述中参数名后面的数值，不要校验数值合理性，也不要因为省略单位而忽略：\n\n{text}"
        response = httpx.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": model_name,
                "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "format": "json",
                "think": False,
                "options": {"temperature": 0},
            },
            timeout=OLLAMA_TIMEOUT,
        )
        response.raise_for_status()
        content = response.json().get("message", {}).get("content", "").strip()
        if not content:
            raise ValueError("本地模型返回了空内容")
        return parse_json_response(content)
    except Exception as e:
        logger.error(f"[本地LLM错误] {str(e)}")
        return None


# ==================== 辅助函数：JSON解析 ====================
def parse_json_response(text: str) -> dict:
    try:
        json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_match = re.search(r'\{[\s\S]*\}', text)
            json_str = json_match.group(0) if json_match else text

        data = json.loads(json_str)
        result = {}
        for key in ['compressive', 'tensile', 'poisson', 'elastic', 'density', 'hardness']:
            value = data.get(key)
            if value is not None and str(value).lower() not in ['null', 'none']:
                try:
                    result[key] = float(value)
                except:
                    result[key] = None
            else:
                result[key] = None
        return result
    except Exception as e:
        logger.error(f"[JSON解析错误] {str(e)}")
        return None


def parse_model_json_object(text: str) -> dict:
    """兼容部分本地推理模型附带的 think 标签或 Markdown 代码块。"""
    cleaned = re.sub(r'<think>[\s\S]*?</think>', '', text, flags=re.IGNORECASE).strip()
    fenced = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', cleaned, re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1).strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        object_match = re.search(r'\{[\s\S]*\}', cleaned)
        if not object_match:
            raise ValueError('模型响应中没有可解析的 JSON 对象')
        value = json.loads(object_match.group(0))
    if not isinstance(value, dict):
        raise ValueError('模型响应必须是 JSON 对象')
    return value


# ==================== 辅助函数：正则表达式提取 ====================
PARAMETER_KEYS = ('compressive', 'tensile', 'poisson', 'elastic', 'density', 'hardness')


def extract_with_regex(text: str) -> dict:
    result = {key: None for key in PARAMETER_KEYS}
    patterns = {
        'compressive': [r'(?:单轴抗压强度|抗压强度|压缩强度|UCS)\s*(?:约为?|为|是|达到|[:：=])?\s*(\d+(?:\.\d+)?)'],
        'tensile': [r'(?:抗拉强度|拉伸强度)\s*(?:约为?|为|是|达到|[:：=])?\s*(\d+(?:\.\d+)?)'],
        'poisson': [r'(?:泊松比|Poisson(?:\s*ratio)?)\s*(?:约为?|为|是|达到|[:：=])?\s*(\d+(?:\.\d+)?)'],
        'elastic': [r'(?:弹性模量|杨氏模量|Young[\'’]?s modulus)\s*(?:约为?|为|是|达到|[:：=])?\s*(\d+(?:\.\d+)?)'],
        'density': [r'(?:密度|体积密度)\s*(?:约为?|为|是|达到|[:：=])?\s*(\d+(?:\.\d+)?)'],
        'hardness': [r'(?:洛氏硬度|硬度)\s*(?:约为?|为|是|达到|[:：=])?\s*(\d+(?:\.\d+)?)']
    }
    for key, pattern_list in patterns.items():
        for pattern in pattern_list:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    result[key] = float(match.group(1))
                    break
                except:
                    pass
    return result


# ==================== 辅助函数：真实数据集候选与本地大模型选择 ====================
PROPERTY_COLUMN_MAP = {
    'compressive': '抗压强度(MPa)',
    'tensile': '抗拉强度(MPa)',
    'elastic': '弹性模量(MPa)',
    'poisson': '泊松比',
    'density': '密度g/cm³',
}


def build_formula_candidates(targets: dict, limit: int = 6) -> list:
    """按目标性质从真实数据集中筛出少量近邻，供本地大模型做最终选择。"""
    formula_df = pd.read_excel(FILE_EXCEL, sheet_name='Sheet1')
    property_df = pd.read_excel(FILE_EXCEL, sheet_name='Sheet2')
    merged = pd.merge(formula_df, property_df, on='label', how='inner')

    active_keys = [
        key for key, column in PROPERTY_COLUMN_MAP.items()
        if targets.get(key) is not None and float(targets[key]) > 0 and column in merged.columns
    ]
    if not active_keys:
        return []

    active_columns = [PROPERTY_COLUMN_MAP[key] for key in active_keys]
    merged = merged.copy()
    for column in active_columns:
        merged[column] = pd.to_numeric(merged[column], errors='coerce')
    complete_rows = np.ones(len(merged), dtype=bool)
    for column in active_columns:
        complete_rows &= merged[column].notna().to_numpy() & (merged[column].to_numpy(dtype=float) > 0)
    merged = merged.loc[complete_rows].copy()
    if merged.empty:
        return []

    squared_distance = np.zeros(len(merged), dtype=float)
    for key in active_keys:
        column = PROPERTY_COLUMN_MAP[key]
        values = merged[column]
        span = float(values.max() - values.min()) or 1.0
        squared_distance += ((values.to_numpy(dtype=float) - float(targets[key])) / span) ** 2

    merged['_distance'] = np.sqrt(squared_distance / len(active_keys))
    nearest = merged.nsmallest(min(limit, len(merged)), '_distance')
    material_columns = [column for column in formula_df.columns if column != 'label']

    candidates = []
    for _, row in nearest.iterrows():
        components = {
            column: round(float(row[column]), 6)
            for column in material_columns
            if pd.notna(row[column]) and float(row[column]) > 0
        }
        total = sum(components.values())
        if total <= 0:
            continue
        components = {name: round(value / total, 6) for name, value in components.items()}
        predicted = {
            key: round(float(row[column]), 6) if pd.notna(row[column]) else None
            for key, column in PROPERTY_COLUMN_MAP.items()
        }
        predicted['hardness'] = None
        distance = float(row['_distance'])
        candidates.append({
            'id': str(int(row['label'])),
            'components': components,
            'predicted': predicted,
            'similarity': round(1.0 / (1.0 + distance), 6),
        })
    return candidates


def select_formula_with_local_llm(
    targets: dict,
    candidates: list,
    model_name: str = OLLAMA_MODEL,
) -> tuple[str, str]:
    """让本地Ollama模型在经过数值近邻筛选的真实配方中确定Top-1。"""
    candidate_ids = [item['id'] for item in candidates]
    response_schema = {
        'type': 'object',
        'properties': {
            'candidate_id': {'type': 'string', 'enum': candidate_ids},
            'reason': {'type': 'string'},
        },
        'required': ['candidate_id', 'reason'],
    }
    response = httpx.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json={
            'model': model_name,
            'messages': [
                {'role': 'system', 'content': FORMULA_SELECTION_PROMPT},
                {'role': 'user', 'content': json.dumps({
                    'target': targets,
                    'candidates': candidates,
                }, ensure_ascii=False)},
            ],
            'stream': False,
            'format': response_schema,
            'think': False,
            'options': {'temperature': 0},
        },
        timeout=OLLAMA_TIMEOUT,
    )
    response.raise_for_status()
    content = response.json().get('message', {}).get('content', '').strip()
    if not content:
        raise ValueError('本地大模型没有返回配方选择结果')
    selection = parse_model_json_object(content)
    selected_id = str(selection.get('candidate_id', ''))
    if selected_id not in candidate_ids:
        raise ValueError(f'本地大模型返回了无效候选编号: {selected_id}')
    return selected_id, str(selection.get('reason', '')).strip()


# ==================== 新增：输入解析辅助函数（适配量子模型）====================
def parse_input_to_quantum_features(input_text: str) -> list:
    compressive = re.search(r'抗压强度:(\d+\.?\d*)', input_text)
    tensile = re.search(r'抗拉强度:(\d+\.?\d*)', input_text)
    poisson = re.search(r'泊松比:(\d+\.?\d*)', input_text)
    elastic = re.search(r'弹性模量:(\d+\.?\d*)', input_text)

    features = [
        float(compressive.group(1)) if compressive else 0.0,
        float(tensile.group(1)) if tensile else 0.0,
        float(poisson.group(1)) if poisson else 0.0,
        float(elastic.group(1)) if elastic else 0.0,
        0.0, 0.0, 0.0, 0.0
    ]
    return features


def convert_params_to_quantum_input(params: dict) -> list:
    return [
        params.get('compressive', 0.0),
        params.get('tensile', 0.0),
        params.get('poisson', 0.0),
        params.get('elastic', 0.0),
        params.get('density', 0.0),
        params.get('hardness', 0.0),
        0.0, 0.0
    ]


_uploaded_quantum_models = {}


def discovery_model_catalog() -> list[dict]:
    return model_manager.list_models(bool(QUANTUM_AVAILABLE and quantum_model and quantum_model.is_trained))


def require_ready_discovery_model(model_id: str) -> dict:
    model = next((item for item in discovery_model_catalog() if item['id'] == model_id), None)
    if model is None:
        raise ValueError(f'未知模型: {model_id}')
    if model.get('status') != 'ready':
        raise ValueError(f"模型 {model.get('name', model_id)} 当前不可用：{model.get('status_text', '未就绪')}")
    return model


def get_quantum_predictor(model_id: str):
    if model_id == 'quantum:default':
        if not quantum_model or not quantum_model.is_trained:
            raise ValueError('内置量子模型没有成功加载')
        return quantum_model
    if model_id in _uploaded_quantum_models:
        return _uploaded_quantum_models[model_id]
    entry = model_manager.get_uploaded_model(model_id)
    if not entry or entry.get('provider') != 'quantum_file':
        raise ValueError('找不到对应的 QNN 检查点')
    checkpoint_path = os.path.join(MODELS_DIR, entry['filename'])
    config = QuantumConfig()
    config.dataset_file = FILE_EXCEL
    config.pretrained_model_path = checkpoint_path
    predictor = init_quantum_model(config)
    if not predictor.is_trained:
        raise ValueError('上传的 QNN 检查点无法按当前网络结构加载')
    _uploaded_quantum_models[model_id] = predictor
    return predictor


def calculate_target_error(values: dict, targets: dict, keys: tuple[str, ...] = PARAMETER_KEYS) -> float | None:
    errors = []
    for key in keys:
        target = targets.get(key)
        value = values.get(key)
        if target is None or value is None:
            continue
        errors.append(abs(float(value) - float(target)) / max(abs(float(target)), 1e-9))
    return sum(errors) / len(errors) if errors else None


def generate_discovery_baseline(targets: dict) -> dict:
    """按闭环最终评价口径，取目标相对误差最低的已知配方作为数据基线。"""
    matches = build_formula_candidates(targets, limit=1_000_000)
    if not matches:
        raise ValueError('数据集中没有同时包含全部目标性质的样本，无法建立可比较的基线')
    nearest = min(
        matches,
        key=lambda item: (
            float(error) if (error := calculate_target_error(item['predicted'], targets)) is not None
            else float('inf')
        ),
    )
    error = calculate_target_error(nearest['predicted'], targets)
    return {
        'source_sample_id': nearest['id'],
        'components': nearest['components'],
        'properties': nearest['predicted'],
        'target_error': round(float(error or 0.0), 6),
        'similarity': nearest['similarity'],
        'method': 'nearest-dataset-sample',
        'description': '数据集中与目标性质综合距离最近的已知配方。',
    }


def normalize_formula_components(raw_components: dict, allowed_materials: set[str]) -> dict:
    if not isinstance(raw_components, dict):
        raise ValueError('模型没有返回有效的配方组成')
    cleaned = {}
    for name, value in raw_components.items():
        if name not in allowed_materials:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            cleaned[name] = number
    total = sum(cleaned.values())
    if total <= 0:
        raise ValueError('模型返回的配方比例无效')
    normalized = {
        name: round(value / total, 6)
        for name, value in cleaned.items()
        if value / total > 1e-8
    }
    if normalized:
        largest = max(normalized, key=normalized.get)
        normalized[largest] = round(normalized[largest] + (1.0 - sum(normalized.values())), 6)
    return normalized


def formula_fingerprint(components: dict) -> str:
    canonical = '|'.join(f'{name}:{float(value):.6f}' for name, value in sorted(components.items()))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]


def formula_adjustments(anchor: dict, candidate: dict) -> list[dict]:
    changes = []
    for name in sorted(set(anchor) | set(candidate)):
        before = float(anchor.get(name, 0.0))
        after = float(candidate.get(name, 0.0))
        delta = after - before
        if abs(delta) >= 0.0001:
            changes.append({
                'material': name,
                'before': round(before, 6),
                'after': round(after, 6),
                'delta': round(delta, 6),
            })
    return sorted(changes, key=lambda item: abs(item['delta']), reverse=True)


def estimate_formula_properties(components: dict, references: list[dict], neighbor_count: int = 5) -> dict:
    """按配方距离对真实近邻性质加权，仅作为实验前估算。"""
    material_names = set(components)
    for reference in references:
        material_names.update(reference.get('components', {}))
    distances = []
    for reference in references:
        distance = np.sqrt(sum(
            (float(components.get(name, 0.0)) - float(reference['components'].get(name, 0.0))) ** 2
            for name in material_names
        ))
        distances.append((float(distance), reference))
    nearest = sorted(distances, key=lambda item: item[0])[:max(1, neighbor_count)]
    predicted = {}
    for key in PARAMETER_KEYS:
        weighted_values = []
        for distance, reference in nearest:
            value = reference.get('predicted', {}).get(key)
            if value is not None:
                weighted_values.append((1.0 / max(distance, 1e-6), float(value)))
        if weighted_values:
            weight_total = sum(weight for weight, _ in weighted_values)
            predicted[key] = round(
                sum(weight * value for weight, value in weighted_values) / weight_total, 6
            )
        else:
            predicted[key] = None
    return predicted


FORMULA_REFINEMENT_PROMPT = """你是岩石相似材料配方优化助手。你必须基于给定的起始配方进行小幅调整，不能把两条数据样本直接混合作为结果。
第一轮的起始配方是数据基线；后续轮次的起始配方是上一轮模型候选。若提供了上一轮实测结果，必须根据实测值与目标值的偏差决定调整方向。
要求：
1. components只能使用allowed_materials中的材料，所有比例非负且总和为1。
2. 每种材料相对起始配方的绝对变化不超过0.10，优先小幅、可解释调整。
3. 至少调整一种材料，不得原样返回起始配方。
4. reference_samples只用于判断合理范围，不能直接复制或混合成候选。
5. 只围绕target_properties中实际给出的目标解释调整，不得声称优化未设置的性质。
6. 返回JSON对象：components、reason。reason用一句中文说明相对起始配方的调整依据。"""


def refine_formula_with_local_llm(
    targets: dict,
    anchor: dict,
    anchor_properties: dict,
    references: list[dict],
    model_name: str,
    previous_session: dict | None,
) -> tuple[dict, str]:
    active_keys = [key for key, value in targets.items() if value is not None]
    allowed_materials = sorted(
        set(anchor) | {
            name for reference in references[:10] for name in reference.get('components', {})
        }
    )
    feedback = (previous_session or {}).get('feedback') or {}
    measured = feedback.get('observations') or {}
    reference_context = [
        {
            'id': reference.get('id'),
            'components': reference.get('components') or {},
            'properties': {
                key: (reference.get('predicted') or {}).get(key)
                for key in active_keys
            },
        }
        for reference in references[:10]
    ]
    response = httpx.post(
        f'{OLLAMA_BASE_URL}/api/chat',
        json={
            'model': model_name,
            'messages': [
                {'role': 'system', 'content': FORMULA_REFINEMENT_PROMPT},
                {'role': 'user', 'content': json.dumps({
                    'target_properties': targets,
                    'starting_components': anchor,
                    'starting_properties': {key: anchor_properties.get(key) for key in active_keys},
                    'previous_measured_properties': {key: measured.get(key) for key in active_keys},
                    'previous_decision': (previous_session or {}).get('decision'),
                    'allowed_materials': allowed_materials,
                    'reference_samples': reference_context,
                }, ensure_ascii=False)},
            ],
            'stream': False,
            'format': 'json',
            'think': False,
            'options': {'temperature': 0},
        },
        timeout=OLLAMA_TIMEOUT,
    )
    response.raise_for_status()
    content = response.json().get('message', {}).get('content', '').strip()
    result = parse_model_json_object(content)
    proposed = normalize_formula_components(result.get('components'), set(allowed_materials))

    material_names = set(anchor) | set(proposed)
    largest_requested_change = max(
        abs(float(proposed.get(name, 0.0)) - float(anchor.get(name, 0.0)))
        for name in material_names
    )
    scale = min(1.0, 0.10 / largest_requested_change) if largest_requested_change > 0 else 1.0
    bounded = {
        name: float(anchor.get(name, 0.0))
        + scale * (float(proposed.get(name, 0.0)) - float(anchor.get(name, 0.0)))
        for name in material_names
    }
    candidate = normalize_formula_components(bounded, set(allowed_materials))
    if not formula_adjustments(anchor, candidate):
        raise ValueError('本地大模型没有对上一阶段配方作出有效调整，请补充更明确的目标后重试')
    return candidate, str(result.get('reason', '')).strip()


def local_formula_variants(anchor: dict, references: list[dict]) -> list[dict]:
    """在上一阶段配方附近转移少量质量分数，不组合整条数据配方。"""
    material_names = set(anchor)
    for reference in references[:6]:
        material_names.update(reference.get('components', {}))
    donors = [name for name, value in anchor.items() if float(value) >= 0.02]
    variants = []
    for donor in donors:
        for receiver in sorted(material_names - {donor}):
            for step in (0.01, 0.02, 0.05):
                transfer = min(step, float(anchor.get(donor, 0.0)) * 0.5)
                if transfer <= 0:
                    continue
                changed = dict(anchor)
                changed[donor] = float(changed.get(donor, 0.0)) - transfer
                changed[receiver] = float(changed.get(receiver, 0.0)) + transfer
                changed = normalize_formula_components(changed, material_names)
                variants.append(changed)
    return variants


def refine_formula_with_quantum_model(
    targets: dict,
    anchor: dict,
    references: list[dict],
    model_id: str,
    previous_session: dict | None,
    excluded_fingerprints: set[str],
) -> tuple[dict, dict, str]:
    unsupported_keys = [
        key for key, value in targets.items()
        if value is not None and key not in {'compressive', 'elastic'}
    ]
    if unsupported_keys:
        unsupported_labels = {
            'tensile': '抗拉强度', 'poisson': '泊松比', 'density': '密度', 'hardness': '硬度'
        }
        names = '、'.join(unsupported_labels.get(key, key) for key in unsupported_keys)
        raise ValueError(f'量子模型目前不能针对{names}优化，请改用本地大模型或调整目标性质')
    active_keys = [key for key in ('compressive', 'elastic') if targets.get(key) is not None]
    if not active_keys:
        raise ValueError('量子模型目前只输出抗压强度和弹性模量，请至少设置其中一项目标')

    variants = [
        item for item in local_formula_variants(anchor, references)
        if formula_fingerprint(item) not in excluded_fingerprints
    ]
    if not variants:
        raise ValueError('上一阶段配方附近没有尚未探索的局部调整候选')
    predictor = get_quantum_predictor(model_id)
    feature_names = predictor.dataset.feature_names
    all_formulas = [anchor, *variants]
    model_inputs = np.asarray([
        [float(components.get(name, 0.0)) for name in feature_names]
        for components in all_formulas
    ], dtype=float)
    prediction = predictor.predict_unified(model_inputs)
    if prediction.get('error'):
        raise ValueError(f"量子模型预测失败: {prediction['error']}")
    outputs = prediction.get('output_original') or []
    if len(outputs) != len(all_formulas):
        raise ValueError('量子模型返回的候选数量不完整')

    previous_observations = ((previous_session or {}).get('feedback') or {}).get('observations') or {}
    anchor_output = outputs[0]
    correction = {}
    for index, key in enumerate(('compressive', 'elastic')):
        measured = previous_observations.get(key)
        correction[key] = float(measured) - float(anchor_output[index]) if measured is not None else 0.0

    scored = []
    for components, output in zip(variants, outputs[1:]):
        values = {
            'compressive': float(output[0]) + correction['compressive'],
            'elastic': float(output[1]) + correction['elastic'],
        }
        error = calculate_target_error(values, targets, tuple(active_keys))
        scored.append((float(error), components, values))
    error, selected, qnn_values = min(scored, key=lambda item: item[0])
    return (
        selected,
        qnn_values,
        f'QNN 在上一阶段配方附近评估 {len(variants)} 个小幅调整，并选择目标误差最低的候选（{error * 100:.2f}%）。',
    )


def generate_discovery_candidate(
    targets: dict,
    excluded_ids: list[str] | None = None,
    model_id: str = 'ollama:qwen3.5:9b',
    baseline: dict | None = None,
    previous_session: dict | None = None,
) -> dict:
    """第一轮基于数据基线，后续轮次严格基于上一轮候选配方继续调整。"""
    model_info = require_ready_discovery_model(model_id)
    excluded = {str(item) for item in (excluded_ids or [])}
    references = build_formula_candidates(targets, limit=80)
    if len(references) < 2:
        raise ValueError('数据集中至少需要两条同时包含全部目标性质的参考配方')

    if previous_session:
        previous_candidate = previous_session.get('candidate') or {}
        anchor = previous_candidate.get('components') or {}
        if not anchor:
            raise ValueError('上一轮候选缺少配方组成，无法继续迭代')
        previous_observations = (previous_session.get('feedback') or {}).get('observations') or {}
        anchor_properties = {
            key: previous_observations.get(key)
            if previous_observations.get(key) is not None
            else (previous_candidate.get('predicted') or {}).get(key)
            for key in PARAMETER_KEYS
        }
        source = {
            'based_on': 'previous-candidate',
            'based_on_round_id': previous_session.get('id'),
            'based_on_round_no': previous_session.get('round_no'),
        }
    else:
        anchor = (baseline or {}).get('components') or {}
        anchor_properties = (baseline or {}).get('properties') or {}
        if not anchor:
            raise ValueError('数据基线缺少配方组成，无法生成第一轮候选')
        source = {
            'based_on': 'dataset-baseline',
            'based_on_baseline_id': (baseline or {}).get('source_sample_id'),
        }

    if model_info['provider'] in {'quantum', 'quantum_file'}:
        components, qnn_values, reason = refine_formula_with_quantum_model(
            targets, anchor, references, model_id, previous_session, excluded
        )
        predicted = {**estimate_formula_properties(components, references), **qnn_values}
        model_type = 'quantum-formula-refinement'
    else:
        ollama_name = model_info.get('ollama_name') or model_id.removeprefix('ollama:')
        components, reason = refine_formula_with_local_llm(
            targets, anchor, anchor_properties, references, ollama_name, previous_session
        )
        predicted = estimate_formula_properties(components, references)
        model_type = 'local-llm-formula-refinement'

    fingerprint = formula_fingerprint(components)
    if fingerprint in excluded:
        raise ValueError('模型生成了已经探索过的配方，请调整目标或更换模型后重试')
    predicted_error = calculate_target_error(predicted, targets)
    return {
        'components': components,
        'predicted': predicted,
        'similarity': round(1.0 / (1.0 + float(predicted_error or 0.0)), 6),
        'source_sample_id': f'generated-{fingerprint}',
        'formula_fingerprint': fingerprint,
        'adjustments': formula_adjustments(anchor, components),
        'predicted_target_error': round(float(predicted_error or 0.0), 6),
        'reason': reason or '所选模型基于上一阶段配方和目标偏差生成了调整后的候选。',
        'model_type': model_type,
        'model_id': model_id,
        'model_name': model_info['name'],
        **source,
    }


def build_concrete_protocol(candidate: dict, baseline_data: dict, targets: dict, previous_session: dict | None) -> dict:
    batch_mass = 1000.0
    weighing = '；'.join(
        f'{name} {ratio * batch_mass:.1f} g'
        for name, ratio in candidate.get('components', {}).items()
        if float(ratio) > 0
    )
    target_labels = {
        'compressive': '抗压强度', 'tensile': '抗拉强度', 'poisson': '泊松比',
        'elastic': '弹性模量', 'density': '密度',
    }
    target_text = '；'.join(
        f'{target_labels.get(key, key)}={value}'
        for key, value in targets.items()
        if value is not None and key in target_labels
    )
    acceptance_rules = {
        'compressive': '抗压强度相对偏差≤10%',
        'tensile': '抗拉强度相对偏差≤20%',
        'poisson': '泊松比绝对偏差≤0.015',
        'elastic': '弹性模量相对偏差≤15%',
        'density': '密度相对偏差≤10%',
    }
    acceptance_text = '；'.join(
        acceptance_rules[key]
        for key, value in targets.items()
        if value is not None and key in acceptance_rules
    )
    baseline_properties = '；'.join(
        f'{key}={value}'
        for key, value in (baseline_data.get('properties') or {}).items()
        if value is not None and targets.get(key) is not None
    )
    baseline = (
        f"数据基线为样本 #{baseline_data.get('source_sample_id', '-')}（{baseline_properties}）。"
        '它是数据集中最接近目标的已知配方，用于判断新候选是否进一步缩小目标误差。'
    )
    return {
        'protocol': [
            f'按干料总质量 {batch_mass:.0f} g 称量：{weighing}；记录实际重量和原料批号。',
            '固定混合顺序、混合时间和成型方法；制作至少 3 个带编号的平行试件。',
            '填写实际养护温度、湿度和时长；候选与对照配方必须同批制备和养护。',
            '记录仪器编号、校准状态和加载速率；保存每个试件的原始测量值。',
            '计算均值、离散性和目标偏差；单独记录异常值、失败和人工调整。',
        ],
        'baseline': baseline,
        'baseline_purpose': '先计算数据基线到目标的误差，再计算新候选实测值到目标的误差；后者更小时才算取得改善。',
        'environment': '填写并固定：温度、湿度、养护时长、试件尺寸、加载速率和仪器编号。',
        'acceptance_criteria': f'目标（{target_text}）；{acceptance_text}；每项目标至少 3 个有效试件。',
        'required_evidence': [
            '配方版本、原料批号、理论/实际称量表',
            '基线或平行样的同条件原始数据',
            '每个试件的编号、尺寸、养护和仪器原始记录',
            '均值、离散性、异常值处理及人工干预说明',
        ],
    }


def generate_discovery_execution_plan(
    objective: str,
    hypothesis: str,
    targets: dict,
    baseline_data: dict,
    candidate: dict,
    model_id: str,
    previous_session: dict | None,
) -> dict:
    draft = build_concrete_protocol(candidate, baseline_data, targets, previous_session)
    return {
        **draft,
        'generation_method': 'fixed-protocol',
        'model_id': None,
        'model_name': '系统固定流程',
        'model_note': '该流程不调用模型，所有研究轮次使用相同步骤。',
    }


app.register_blueprint(create_discovery_blueprint(
    generate_discovery_candidate,
    generate_discovery_baseline,
    generate_discovery_execution_plan,
    discovery_model_catalog,
    model_manager.upload,
    os.path.join(BASE_DIR, 'runtime', 'discovery_loop.db'),
))


# ==================== 启动服务 ====================
if __name__ == '__main__':
    print("=" * 70)
    print("🚀 岩石相似材料配方设计系统 API 服务启动中... (v1.0.2)")
    print("=" * 70)
    print("📡 可用接口:")
    print("   - GET  /api/dataset         : 拉取全景数据集")
    print("   - POST /get                 : 生成配方设计（支持llm/quantum/default）")
    print("   - POST /extract-parameters  : 提取岩石参数（支持llm/regex/quantum）")
    print("   - GET  /health              : 健康检查")
    print("=" * 70)
    print("🔧 状态检查:")
    print(f"   - 本地大模型: {OLLAMA_MODEL} ({OLLAMA_BASE_URL})")
    print(f"   - 量子模型: {'可用 (QNN)' if QUANTUM_AVAILABLE and quantum_model else '❌ 不可用'}")
    # 统一修改为 FILE_EXCEL
    print(f"   - 数据集关联: {'可用' if os.path.exists(FILE_EXCEL) else '❌ 找不到Excel文件'}")
    print("=" * 70)
    print("📍 服务地址: http://0.0.0.0:5000")
    print("=" * 70)

    debug_mode = os.getenv('FLASK_DEBUG', '0').lower() in {'1', 'true', 'yes'}
    app.run(host='0.0.0.0', port=5000, debug=debug_mode)
