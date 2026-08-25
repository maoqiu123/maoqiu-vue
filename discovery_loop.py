"""岩石相似材料可信反馈闭环平台的独立 API 与 Research State。"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Callable

from flask import Blueprint, jsonify, request


PROPERTY_KEYS = ('compressive', 'tensile', 'poisson', 'elastic', 'density', 'hardness')
SUPPORTED_PROPERTY_KEYS = ('compressive', 'tensile', 'poisson', 'elastic', 'density')
PROPERTY_LABELS = {
    'compressive': '抗压强度',
    'tensile': '抗拉强度',
    'poisson': '泊松比',
    'elastic': '弹性模量',
    'density': '密度',
    'hardness': '硬度',
}
ACCEPTANCE_RULES = {
    'compressive': ('relative', 0.10, '相对偏差≤10%'),
    'tensile': ('relative', 0.20, '相对偏差≤20%'),
    'poisson': ('absolute', 0.015, '绝对偏差≤0.015'),
    'elastic': ('relative', 0.15, '相对偏差≤15%'),
    'density': ('relative', 0.10, '相对偏差≤10%'),
}


def create_discovery_blueprint(
    candidate_provider: Callable[[dict, list[str], str, dict, dict | None], dict],
    baseline_provider: Callable[[dict], dict],
    execution_plan_provider: Callable[[str, str, dict, dict, dict, str, dict | None], dict],
    model_catalog_provider: Callable[[], list[dict]],
    model_upload_handler: Callable,
    database_path: str,
) -> Blueprint:
    """创建独立闭环平台蓝图，候选生成能力由主项目模型注入。"""
    blueprint = Blueprint('discovery_loop', __name__, url_prefix='/api/discovery')
    os.makedirs(os.path.dirname(database_path), exist_ok=True)

    def connect() -> sqlite3.Connection:
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def init_database() -> None:
        with connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS discovery_rounds (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    parent_id TEXT,
                    round_no INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    hypothesis TEXT,
                    targets TEXT NOT NULL,
                    candidate TEXT NOT NULL,
                    execution_plan TEXT NOT NULL,
                    feedback TEXT,
                    evidence TEXT,
                    decision TEXT,
                    candidate_model TEXT NOT NULL DEFAULT 'ollama:qwen3.5:9b',
                    execution_model TEXT NOT NULL DEFAULT 'ollama:qwen3.5:9b',
                    baseline TEXT
                )
                """
            )
            columns = {
                item['name'] for item in connection.execute('PRAGMA table_info(discovery_rounds)').fetchall()
            }
            if 'candidate_model' not in columns:
                connection.execute(
                    "ALTER TABLE discovery_rounds ADD COLUMN candidate_model TEXT NOT NULL DEFAULT 'ollama:qwen3.5:9b'"
                )
            if 'execution_model' not in columns:
                connection.execute(
                    "ALTER TABLE discovery_rounds ADD COLUMN execution_model TEXT NOT NULL DEFAULT 'ollama:qwen3.5:9b'"
                )
            if 'baseline' not in columns:
                connection.execute('ALTER TABLE discovery_rounds ADD COLUMN baseline TEXT')

    def decode_json(value: str | None, fallback):
        if not value:
            return fallback
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return fallback

    def plain_text(value, fallback: str = '') -> str:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith('{') and stripped.endswith('}'):
                try:
                    return plain_text(json.loads(stripped), fallback)
                except json.JSONDecodeError:
                    return stripped
            return stripped
        if isinstance(value, dict):
            for key in ('description', 'summary', 'text'):
                if value.get(key):
                    return str(value[key]).strip()
        return fallback

    def clean_execution_plan(plan: dict, round_no: int) -> dict:
        plan = plan if isinstance(plan, dict) else {}
        protocol = [str(item).strip() for item in plan.get('protocol', []) if isinstance(item, str) and item.strip()]
        evidence_items = [
            str(item).strip()
            for item in plan.get('required_evidence', [])
            if isinstance(item, str) and item.strip()
        ]
        baseline = plain_text(plan.get('baseline'))
        environment = plain_text(
            plan.get('environment'),
            '请填写并固定温度、湿度、养护时长、加载速率和仪器编号。',
        )
        acceptance = plain_text(
            plan.get('acceptance_criteria'),
            '各目标指标均值相对目标偏差≤10%，每项至少3个有效试件。',
        )
        return {
            **plan,
            'protocol': protocol,
            'baseline': baseline,
            'baseline_purpose': '先计算数据基线到目标的误差，再计算新候选实测值到目标的误差；候选误差更小才说明模型带来了改善。',
            'environment': environment,
            'acceptance_criteria': acceptance,
            'required_evidence': evidence_items,
        }
    def serialize_row(row: sqlite3.Row) -> dict:
        return {
            'id': row['id'],
            'project_id': row['project_id'],
            'parent_id': row['parent_id'],
            'round_no': row['round_no'],
            'created_at': row['created_at'],
            'updated_at': row['updated_at'],
            'status': row['status'],
            'objective': row['objective'],
            'hypothesis': row['hypothesis'] or '',
            'targets': decode_json(row['targets'], {}),
            'baseline': decode_json(row['baseline'], None),
            'candidate': decode_json(row['candidate'], {}),
            'execution_plan': clean_execution_plan(
                decode_json(row['execution_plan'], {}), int(row['round_no'])
            ),
            'feedback': decode_json(row['feedback'], None),
            'evidence': decode_json(row['evidence'], None),
            'decision': decode_json(row['decision'], None),
            'candidate_model': row['candidate_model'],
            'execution_model': row['execution_model'],
        }

    def fetch_round(round_id: str) -> sqlite3.Row | None:
        with connect() as connection:
            return connection.execute(
                'SELECT * FROM discovery_rounds WHERE id = ?', (round_id,)
            ).fetchone()

    def normalize_targets(raw_targets: dict) -> dict:
        targets = {}
        for key in PROPERTY_KEYS:
            if key not in SUPPORTED_PROPERTY_KEYS:
                targets[key] = None
                continue
            raw_value = raw_targets.get(key)
            if raw_value in (None, ''):
                targets[key] = None
                continue
            try:
                value = float(raw_value)
                targets[key] = value if value > 0 else None
            except (TypeError, ValueError):
                targets[key] = None
        return targets

    def insert_round(
        *,
        project_id: str,
        parent_id: str | None,
        round_no: int,
        objective: str,
        hypothesis: str,
        targets: dict,
        baseline: dict,
        candidate: dict,
        candidate_model: str,
        execution_model: str,
        previous_session: dict | None = None,
    ) -> dict:
        round_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        execution_plan = execution_plan_provider(
            objective,
            hypothesis,
            targets,
            baseline,
            candidate,
            execution_model,
            previous_session,
        )
        execution_plan['revision'] = 1
        execution_plan['updated_at'] = now
        with connect() as connection:
            connection.execute(
                """
                INSERT INTO discovery_rounds (
                    id, project_id, parent_id, round_no, created_at, updated_at,
                    status, objective, hypothesis, targets, baseline, candidate, execution_plan,
                    candidate_model, execution_model
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    round_id,
                    project_id,
                    parent_id,
                    round_no,
                    now,
                    now,
                    'candidate_ready',
                    objective,
                    hypothesis,
                    json.dumps(targets, ensure_ascii=False),
                    json.dumps(baseline, ensure_ascii=False),
                    json.dumps(candidate, ensure_ascii=False),
                    json.dumps(execution_plan, ensure_ascii=False),
                    candidate_model,
                    execution_model,
                ),
            )
        return serialize_row(fetch_round(round_id))

    def evaluate_feedback(targets: dict, baseline: dict, feedback: dict) -> tuple[dict, dict, str]:
        observations = feedback.get('observations') or {}
        checks = feedback.get('checks') or {}
        baseline_properties = (baseline or {}).get('properties') or {}
        comparisons = []
        fit_scores = []
        baseline_errors = []
        candidate_errors = []

        for key in PROPERTY_KEYS:
            target = targets.get(key)
            measured = observations.get(key)
            if target is None or measured in (None, ''):
                continue
            try:
                target_value = float(target)
                measured_value = float(measured)
            except (TypeError, ValueError):
                continue
            relative_error = abs(measured_value - target_value) / max(abs(target_value), 1e-9)
            rule_type, rule_limit, rule_text = ACCEPTANCE_RULES[key]
            absolute_error = abs(measured_value - target_value)
            within_tolerance = (
                absolute_error <= rule_limit
                if rule_type == 'absolute'
                else relative_error <= rule_limit
            )
            fit = max(0.0, 1.0 - min(relative_error, 1.0))
            fit_scores.append(fit)
            baseline_value = baseline_properties.get(key)
            baseline_error = None
            improvement_rate = None
            if baseline_value is not None:
                baseline_value = float(baseline_value)
                baseline_error = abs(baseline_value - target_value) / max(abs(target_value), 1e-9)
                baseline_errors.append(baseline_error)
                candidate_errors.append(relative_error)
                if baseline_error > 1e-9:
                    improvement_rate = (baseline_error - relative_error) / baseline_error
                else:
                    improvement_rate = 0.0 if relative_error <= 1e-9 else -1.0
            comparisons.append({
                'key': key,
                'label': PROPERTY_LABELS[key],
                'target': target_value,
                'baseline': baseline_value,
                'measured': measured_value,
                'baseline_relative_error': round(baseline_error, 6) if baseline_error is not None else None,
                'relative_error': round(relative_error, 6),
                'improvement_rate': round(improvement_rate, 6) if improvement_rate is not None else None,
                'acceptance_rule': rule_text,
                'within_tolerance': within_tolerance,
            })

        fit_score = sum(fit_scores) / len(fit_scores) if fit_scores else 0.0
        baseline_error_score = sum(baseline_errors) / len(baseline_errors) if baseline_errors else None
        candidate_error_score = sum(candidate_errors) / len(candidate_errors) if candidate_errors else None
        if baseline_error_score is None or candidate_error_score is None:
            improvement_rate = None
        elif baseline_error_score > 1e-9:
            improvement_rate = (baseline_error_score - candidate_error_score) / baseline_error_score
        else:
            improvement_rate = 0.0 if candidate_error_score <= 1e-9 else -1.0
        improvement_score = max(0.0, min(1.0, improvement_rate or 0.0))
        check_keys = (
            'execution_verified',
            'baseline_comparable',
            'reproducible',
            'provenance_complete',
        )
        sample_count = int(feedback.get('sample_count') or 0)
        check_results = {
            'execution_verified': bool(checks.get('execution_verified')),
            'baseline_comparable': bool(checks.get('baseline_comparable')),
            'reproducible': bool(checks.get('reproducible')) and sample_count >= 3,
            'provenance_complete': (
                bool(checks.get('provenance_complete'))
                and bool(feedback.get('run_id'))
                and bool(feedback.get('environment'))
            ),
        }
        passed_checks = sum(check_results.values())
        integrity_score = passed_checks / len(check_keys)
        evidence_score = round(
            (fit_score * 0.45 + improvement_score * 0.30 + integrity_score * 0.25) * 100,
            1,
        )

        if not comparisons:
            gate = 'insufficient'
            status = 'review_required'
            action = '补充至少一项与目标对应的实测数据后重新评估。'
        elif improvement_rate is None:
            gate = 'insufficient'
            status = 'review_required'
            action = '数据基线缺少对应性质，暂时无法判断候选是否优于基线。'
        elif improvement_rate <= 0:
            gate = 'iterate'
            status = 'iteration_ready'
            action = '候选没有超过数据基线：保留本轮结果，下一轮继续基于本轮候选配方调整。'
        elif (
            evidence_score >= 75
            and passed_checks == len(check_keys)
            and all(item['within_tolerance'] for item in comparisons)
        ):
            gate = 'pass'
            status = 'accepted'
            action = f'候选相对数据基线改善 {improvement_rate * 100:.1f}%：保留配方并扩大复测。'
        elif improvement_rate > 0:
            gate = 'iterate'
            status = 'iteration_ready'
            if any(not item['within_tolerance'] for item in comparisons):
                reason = '但仍有目标指标未达到对应验收阈值'
            elif passed_checks < len(check_keys):
                reason = '但实验记录完整性不足'
            else:
                reason = '但综合证据分尚未达到通过标准'
            action = f'候选相对数据基线改善 {improvement_rate * 100:.1f}%，{reason}，建议继续迭代。'
        else:
            gate = 'review'
            status = 'review_required'
            action = '证据不足或偏差较大：暂停自动循环，提交专家复核。'

        evidence = {
            'score': evidence_score,
            'fit_score': round(fit_score * 100, 1),
            'baseline_error': round(baseline_error_score * 100, 1) if baseline_error_score is not None else None,
            'candidate_error': round(candidate_error_score * 100, 1) if candidate_error_score is not None else None,
            'improvement_rate': round(improvement_rate * 100, 1) if improvement_rate is not None else None,
            'improvement_score': round(improvement_score * 100, 1),
            'integrity_score': round(integrity_score * 100, 1),
            'gate': gate,
            'comparisons': comparisons,
            'passed_checks': passed_checks,
            'total_checks': len(check_keys),
            'check_results': check_results,
            'sample_count': sample_count,
        }
        decision = {
            'action': action,
            'next_step': 'accept' if gate == 'pass' else ('iterate' if gate == 'iterate' else 'human_review'),
            'generated_at': datetime.now(timezone.utc).isoformat(),
        }
        return evidence, decision, status

    def normalize_execution_plan(raw_plan: dict, current_plan: dict) -> dict:
        def clean_list(value, fallback):
            if not isinstance(value, list):
                return fallback
            cleaned = [str(item).strip() for item in value if isinstance(item, str) and item.strip()]
            return cleaned or fallback

        revision = int(current_plan.get('revision') or 1) + 1
        return {
            **current_plan,
            'protocol': clean_list(raw_plan.get('protocol'), current_plan.get('protocol') or []),
            'baseline': plain_text(current_plan.get('baseline')),
            'environment': plain_text(raw_plan.get('environment'), plain_text(current_plan.get('environment'))),
            'acceptance_criteria': plain_text(
                raw_plan.get('acceptance_criteria'), plain_text(current_plan.get('acceptance_criteria'))
            ),
            'required_evidence': clean_list(
                raw_plan.get('required_evidence'), current_plan.get('required_evidence') or []
            ),
            'revision': revision,
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'edited_by': 'user',
        }

    @blueprint.get('/models')
    def list_models():
        try:
            return jsonify({'success': True, 'data': model_catalog_provider()})
        except Exception as exc:
            return jsonify({'success': False, 'error': f'读取模型列表失败: {exc}'}), 500

    @blueprint.post('/models/upload')
    def upload_model():
        try:
            entry = model_upload_handler(
                request.files.get('file'),
                str(request.form.get('model_kind', '')).strip(),
                str(request.form.get('display_name', '')).strip(),
            )
            code = 201 if entry.get('status') == 'ready' else 202
            return jsonify({'success': entry.get('status') == 'ready', 'data': entry}), code
        except ValueError as exc:
            return jsonify({'success': False, 'error': str(exc)}), 400
        except Exception as exc:
            return jsonify({'success': False, 'error': f'模型上传失败: {exc}'}), 500

    @blueprint.get('/sessions')
    def list_sessions():
        with connect() as connection:
            rows = connection.execute(
                'SELECT * FROM discovery_rounds ORDER BY created_at DESC'
            ).fetchall()
        return jsonify([serialize_row(row) for row in rows])

    @blueprint.post('/sessions')
    def create_session():
        payload = request.get_json(silent=True) or {}
        objective = str(payload.get('objective', '')).strip()
        hypothesis = str(payload.get('hypothesis', '')).strip()
        candidate_model = str(payload.get('candidate_model') or 'ollama:qwen3.5:9b').strip()
        execution_model = 'fixed:protocol'
        raw_targets = payload.get('targets') or {}
        if raw_targets.get('hardness') not in (None, ''):
            return jsonify({'success': False, 'error': '当前数据集没有硬度字段，不能将硬度设为研究目标'}), 400
        targets = normalize_targets(raw_targets)
        if not objective:
            return jsonify({'success': False, 'error': '请填写本轮研究目标'}), 400
        if not any(value is not None for value in targets.values()):
            return jsonify({'success': False, 'error': '请至少设置一项大于0的目标性质'}), 400

        try:
            baseline = baseline_provider(targets)
            candidate = candidate_provider(targets, [], candidate_model, baseline, None)
            session = insert_round(
                project_id=str(uuid.uuid4()),
                parent_id=None,
                round_no=1,
                objective=objective,
                hypothesis=hypothesis,
                targets=targets,
                baseline=baseline,
                candidate=candidate,
                candidate_model=candidate_model,
                execution_model=execution_model,
            )
            return jsonify({'success': True, 'data': session}), 201
        except ValueError as exc:
            return jsonify({'success': False, 'error': str(exc)}), 400
        except Exception as exc:
            return jsonify({'success': False, 'error': f'候选生成失败: {exc}'}), 500

    @blueprint.get('/sessions/<round_id>')
    def get_session(round_id: str):
        row = fetch_round(round_id)
        if row is None:
            return jsonify({'success': False, 'error': '未找到该研究轮次'}), 404
        return jsonify({'success': True, 'data': serialize_row(row)})

    @blueprint.put('/sessions/<round_id>/execution-plan')
    def update_execution_plan(round_id: str):
        row = fetch_round(round_id)
        if row is None:
            return jsonify({'success': False, 'error': '未找到该研究轮次'}), 404
        return jsonify({'success': False, 'error': '实验流程为系统固定流程，不支持逐轮修改'}), 409

    @blueprint.post('/sessions/<round_id>/feedback')
    def submit_feedback(round_id: str):
        row = fetch_round(round_id)
        if row is None:
            return jsonify({'success': False, 'error': '未找到该研究轮次'}), 404
        if row['feedback']:
            return jsonify({'success': False, 'error': '本轮实测记录已经提交，为保证可追溯性不能覆盖'}), 409
        payload = request.get_json(silent=True) or {}
        requested_checks = payload.get('checks') or {}
        try:
            sample_count = int(payload.get('sample_count') or 0)
        except (TypeError, ValueError):
            sample_count = 0
        feedback = {
            'observations': normalize_targets(payload.get('observations') or {}),
            'checks': requested_checks,
            'run_id': str(payload.get('run_id', '')).strip(),
            'environment': str(payload.get('environment', '')).strip(),
            'sample_count': sample_count,
            'notes': str(payload.get('notes', '')).strip(),
            'submitted_at': datetime.now(timezone.utc).isoformat(),
        }
        targets = decode_json(row['targets'], {})
        if not feedback['run_id']:
            return jsonify({'success': False, 'error': '请填写实验运行编号'}), 400
        if not feedback['environment']:
            return jsonify({'success': False, 'error': '请填写养护条件、仪器或实验环境信息'}), 400
        if sample_count < 1:
            return jsonify({'success': False, 'error': '有效试件数量必须大于0'}), 400
        if not any(
            targets.get(key) is not None and feedback['observations'].get(key) is not None
            for key in SUPPORTED_PROPERTY_KEYS
        ):
            return jsonify({'success': False, 'error': '请至少填写一项与研究目标对应的实测值'}), 400
        baseline = decode_json(row['baseline'], None) or baseline_provider(targets)
        evidence, decision, status = evaluate_feedback(targets, baseline, feedback)
        now = datetime.now(timezone.utc).isoformat()
        with connect() as connection:
            connection.execute(
                """
                UPDATE discovery_rounds
                SET updated_at = ?, status = ?, feedback = ?, evidence = ?, decision = ?
                WHERE id = ?
                """,
                (
                    now,
                    status,
                    json.dumps(feedback, ensure_ascii=False),
                    json.dumps(evidence, ensure_ascii=False),
                    json.dumps(decision, ensure_ascii=False),
                    round_id,
                ),
            )
        return jsonify({'success': True, 'data': serialize_row(fetch_round(round_id))})

    @blueprint.post('/sessions/<round_id>/next')
    def create_next_round(round_id: str):
        row = fetch_round(round_id)
        if row is None:
            return jsonify({'success': False, 'error': '未找到该研究轮次'}), 404
        if row['status'] not in {'iteration_ready', 'accepted'}:
            return jsonify({'success': False, 'error': '只有完成审核且允许迭代的轮次才能生成下一轮候选'}), 409

        with connect() as connection:
            project_rows = connection.execute(
                'SELECT candidate FROM discovery_rounds WHERE project_id = ?',
                (row['project_id'],),
            ).fetchall()
        excluded_ids = []
        for item in project_rows:
            stored_candidate = decode_json(item['candidate'], {})
            identity = stored_candidate.get('formula_fingerprint') or stored_candidate.get('source_sample_id')
            if identity is not None:
                excluded_ids.append(str(identity))
        try:
            payload = request.get_json(silent=True) or {}
            candidate_model = str(payload.get('candidate_model') or row['candidate_model']).strip()
            execution_model = 'fixed:protocol'
            targets = decode_json(row['targets'], {})
            baseline = decode_json(row['baseline'], None) or baseline_provider(targets)
            previous_session = serialize_row(row)
            candidate = candidate_provider(
                targets, excluded_ids, candidate_model, baseline, previous_session
            )
            next_round = insert_round(
                project_id=row['project_id'],
                parent_id=row['id'],
                round_no=int(row['round_no']) + 1,
                objective=row['objective'],
                hypothesis=row['hypothesis'] or '',
                targets=targets,
                baseline=baseline,
                candidate=candidate,
                candidate_model=candidate_model,
                execution_model=execution_model,
                previous_session=previous_session,
            )
            return jsonify({'success': True, 'data': next_round}), 201
        except ValueError as exc:
            return jsonify({'success': False, 'error': str(exc)}), 400
        except Exception as exc:
            return jsonify({'success': False, 'error': f'下一轮候选生成失败: {exc}'}), 500

    init_database()
    return blueprint
