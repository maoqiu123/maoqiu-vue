"""Discovery Loop 本地模型目录、发现与上传管理。"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename


KNOWN_OLLAMA_MODELS = (
    'qwen3.5:9b',
    'qwen3:8b',
    'deepseek-r1:1.5b',
    'deepseek-r1:7b',
)

DATASET_PROPERTY_KEYS = ['compressive', 'tensile', 'poisson', 'elastic', 'density']
QNN_PROPERTY_KEYS = ['compressive', 'elastic']


class LocalModelManager:
    """统一暴露 Ollama、内置 QNN 和用户上传模型。"""

    def __init__(self, models_dir: str, ollama_base_url: str):
        self.models_dir = Path(models_dir).resolve()
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.models_dir / 'registry.json'
        self.ollama_base_url = ollama_base_url.rstrip('/')

    def _load_registry(self) -> list[dict]:
        if not self.registry_path.exists():
            return []
        try:
            value = json.loads(self.registry_path.read_text(encoding='utf-8'))
            return value if isinstance(value, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def _save_registry(self, entries: list[dict]) -> None:
        temporary = self.registry_path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(self.registry_path)

    def _installed_ollama_models(self) -> set[str]:
        try:
            response = httpx.get(f'{self.ollama_base_url}/api/tags', timeout=3.0)
            response.raise_for_status()
            return {
                str(item.get('name') or item.get('model'))
                for item in response.json().get('models', [])
                if item.get('name') or item.get('model')
            }
        except Exception:
            return set()

    def list_models(self, quantum_ready: bool) -> list[dict]:
        installed = self._installed_ollama_models()
        names = list(KNOWN_OLLAMA_MODELS)
        names.extend(sorted(name for name in installed if name not in names))
        models = [
            {
                'id': f'ollama:{name}',
                'name': name,
                'provider': 'ollama',
                'kind': 'large_language_model',
                'status': 'ready' if name in installed else 'offline',
                'status_text': '可用' if name in installed else '未安装或 Ollama 未启动',
                'capabilities': ['candidate_selection'],
                'supported_properties': DATASET_PROPERTY_KEYS,
                'uploaded': False,
            }
            for name in names
        ]
        models.append({
            'id': 'quantum:default',
            'name': '量子模型（QNN）',
            'provider': 'quantum',
            'kind': 'quantum_neural_network',
            'status': 'ready' if quantum_ready else 'offline',
            'status_text': '可用（前向预测）' if quantum_ready else '模型未成功加载',
            'capabilities': ['candidate_selection'],
            'supported_properties': QNN_PROPERTY_KEYS,
            'uploaded': False,
        })

        registered = self._load_registry()
        by_id = {item['id']: item for item in models}
        for entry in registered:
            item = dict(entry)
            if item.get('provider') == 'ollama' and item.get('ollama_name'):
                model_id = f"ollama:{item['ollama_name']}"
                item['id'] = model_id
                item['status'] = 'ready' if item['ollama_name'] in installed else item.get('status', 'offline')
                item['status_text'] = '可用' if item['status'] == 'ready' else item.get('status_text', '注册失败')
            item.setdefault(
                'supported_properties',
                QNN_PROPERTY_KEYS if item.get('provider') == 'quantum_file' else DATASET_PROPERTY_KEYS,
            )
            by_id[item['id']] = item
        return list(by_id.values())

    def get_uploaded_model(self, model_id: str) -> dict | None:
        for entry in self._load_registry():
            if entry.get('id') == model_id:
                return entry
        return None

    @staticmethod
    def _ollama_model_name(display_name: str, filename: str) -> str:
        raw_name = display_name.strip() or Path(filename).stem
        safe_name = re.sub(r'[^a-zA-Z0-9._-]+', '-', raw_name).strip('-_.').lower()
        return f'uploaded-{safe_name or uuid.uuid4().hex[:8]}'

    def upload(self, uploaded_file: FileStorage, model_kind: str, display_name: str = '') -> dict:
        if not uploaded_file or not uploaded_file.filename:
            raise ValueError('请选择要上传的模型文件')
        original_name = uploaded_file.filename
        filename = secure_filename(original_name) or f'model-{uuid.uuid4().hex}'
        extension = Path(filename).suffix.lower()
        allowed = {
            'ollama_gguf': {'.gguf'},
            'quantum_checkpoint': {'.pth', '.pt'},
        }
        if model_kind not in allowed:
            raise ValueError('模型类型必须是 Ollama GGUF 或兼容 QNN 检查点')
        if extension not in allowed[model_kind]:
            expected = '、'.join(sorted(allowed[model_kind]))
            raise ValueError(f'该模型类型只接受 {expected} 文件')

        upload_id = uuid.uuid4().hex
        stored_name = f'{upload_id[:10]}-{filename}'
        stored_path = (self.models_dir / stored_name).resolve()
        if self.models_dir not in stored_path.parents:
            raise ValueError('模型文件名不安全')
        uploaded_file.save(stored_path)
        size = stored_path.stat().st_size
        now = datetime.now(timezone.utc).isoformat()

        if model_kind == 'quantum_checkpoint':
            try:
                import torch

                checkpoint = torch.load(stored_path, map_location='cpu', weights_only=True)
                if not isinstance(checkpoint, dict) or 'model_state_dict' not in checkpoint:
                    raise ValueError('缺少 model_state_dict，无法按当前 QNN 结构加载')
                state = checkpoint['model_state_dict']
                expected_shapes = {
                    'weights': (3, 8, 3),
                    'fc.weight': (2, 2),
                    'fc.bias': (2,),
                }
                mismatches = [
                    f'{key}: {tuple(state[key].shape) if key in state else "缺失"}，期望 {shape}'
                    for key, shape in expected_shapes.items()
                    if key not in state or tuple(state[key].shape) != shape
                ]
                if mismatches:
                    raise ValueError('权重形状不兼容（' + '；'.join(mismatches) + '）')
                status = 'ready'
                status_text = '可用（兼容 QNN 检查点）'
            except Exception as exc:
                status = 'incompatible'
                status_text = f'文件已保存，但与当前 QNN 结构不兼容: {exc}'
            entry = {
                'id': f'quantum-file:{upload_id}',
                'name': display_name.strip() or Path(original_name).stem,
                'provider': 'quantum_file',
                'kind': 'quantum_neural_network',
                'status': status,
                'status_text': status_text,
                'capabilities': ['candidate_selection'],
                'supported_properties': QNN_PROPERTY_KEYS,
                'uploaded': True,
                'filename': stored_name,
                'size': size,
                'created_at': now,
            }
        else:
            ollama_name = self._ollama_model_name(display_name, original_name)
            modelfile_path = self.models_dir / f'{upload_id[:10]}.Modelfile'
            modelfile_path.write_text(f'FROM {stored_path.as_posix()}\n', encoding='utf-8')
            command = shutil.which('ollama')
            if not command:
                status = 'registration_failed'
                status_text = '文件已保存，但系统找不到 ollama 命令，尚不能运行'
            else:
                try:
                    options = {
                        'args': [command, 'create', ollama_name, '-f', str(modelfile_path)],
                        'capture_output': True,
                        'text': True,
                        'timeout': 3600,
                        'check': False,
                    }
                    if os.name == 'nt':
                        options['creationflags'] = subprocess.CREATE_NO_WINDOW
                    completed = subprocess.run(**options)
                    status = 'ready' if completed.returncode == 0 else 'registration_failed'
                    detail = (completed.stderr or completed.stdout or '').strip()
                    status_text = '已注册到 Ollama，可用' if status == 'ready' else f'Ollama 注册失败: {detail[-500:]}'
                except Exception as exc:
                    status = 'registration_failed'
                    status_text = f'Ollama 注册失败: {exc}'
            entry = {
                'id': f'ollama:{ollama_name}' if status == 'ready' else f'upload:{upload_id}',
                'name': display_name.strip() or ollama_name,
                'ollama_name': ollama_name,
                'provider': 'ollama',
                'kind': 'large_language_model',
                'status': status,
                'status_text': status_text,
                'capabilities': ['candidate_selection'],
                'supported_properties': DATASET_PROPERTY_KEYS,
                'uploaded': True,
                'filename': stored_name,
                'size': size,
                'created_at': now,
            }

        entries = self._load_registry()
        entries.append(entry)
        self._save_registry(entries)
        return entry
