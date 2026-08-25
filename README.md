# 岩石相似材料配方设计与可信反馈闭环

本项目由两个相互关联的界面组成：

- 配方设计系统：根据目标力学性质生成和展示材料配方。
- 可信反馈闭环：检索数据基线、调用本地模型生成候选配方、记录实测结果，并根据目标误差决定接受或继续迭代。

前端使用 Vue 2 与 Vite，后端使用 Flask。大模型通过本机 Ollama 调用；量子模型（QNN）为可选能力。

## 项目结构

```text
├─ main.py                 Flask 服务入口
├─ discovery_loop.py       循环试验状态、反馈与审核逻辑
├─ model_manager.py        本地模型列表与模型上传管理
├─ quantum_predictor.py    QNN 推理实现
├─ datasetnew.xlsx         配方与性质统一数据集
├─ src/                    Vue 前端源码
├─ models/                 运行时上传模型目录（内容不纳入 Git）
└─ runtime/                Research State 数据库（运行时自动创建）
```

## 环境要求

- Conda 环境：`FormDesign`
- Node.js 与 npm
- Ollama（使用本地大模型时需要）

Python 依赖见 `requirements.txt`。项目不会从仓库提供或自动下载模型权重。

## 启动项目

### 1. 启动后端

```powershell
conda activate FormDesign
pip install -r requirements.txt
python main.py
```

后端默认监听 `http://127.0.0.1:5000`。

### 2. 启动前端

在另一个终端中运行：

```powershell
npm install
npm run dev
```

前端默认访问地址为 `http://127.0.0.1:5173`，循环试验页面为：

```text
http://127.0.0.1:5173/discovery-loop.html
```

## 本地模型

大模型由 Ollama 管理，不存放在本仓库。默认模型可通过环境变量调整：

```powershell
$env:MATAGENT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
$env:MATAGENT_OLLAMA_MODEL = "qwen3.5:9b"
```

若需要启用默认 QNN，请在项目根目录自行放置：

```text
best_qnn_model.pth
```

该文件属于模型权重，已被 `.gitignore` 排除。通过页面上传的新模型保存在 `models/`，同样不会提交到 Git。

## 本地运行数据

循环试验的 Research State 保存在 `runtime/discovery_loop.db`。该数据库、日志、缓存、构建结果和模型文件均为本机运行产物，不会进入仓库。

循环试验的详细逻辑见 [DISCOVERY_LOOP.md](DISCOVERY_LOOP.md)。
