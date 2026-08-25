import os
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
import pennylane as qml
from pennylane import numpy as np_qml
import pandas as pd
from sklearn.preprocessing import StandardScaler
import warnings
# 新增：解决PyTorch安全加载问题
from torch.serialization import add_safe_globals

warnings.filterwarnings('ignore')

# ==================== 新增：PyTorch安全白名单配置（解决加载报错） ====================
try:
    # 把PennyLane的类加入安全白名单，解决加载拦截问题
    add_safe_globals([
        qml.devices.default_qubit.DefaultQubit,
        qml.QNode
    ])
except Exception as e:
    print(f"⚠ 安全白名单配置提示: {e}")


# ==================== 配置类（适配你的数据集） ====================
class QuantumConfig:
    """量子模型配置类（兼容所有旧版PennyLane）"""

    def __init__(self):
        # 量子电路参数（最基础写法，无任何高级API）
        self.n_qubits = 8  # 量子比特数 = 输入特征维度（固定8）
        self.n_layers = 3  # 简化量子层，降低训练复杂度
        self.dev = qml.device("default.qubit", wires=self.n_qubits)  # 量子设备

        # 训练参数
        self.epochs = 15  # 减少训练轮数，快速验证
        self.batch_size = 8  # 批量大小
        self.lr = 5e-3
        self.random_state = 42

        # 路径配置
        module_dir = os.path.dirname(os.path.abspath(__file__))
        self.dataset_file = os.path.join(module_dir, "datasetnew.xlsx")
        self.pretrained_model_path = os.path.join(module_dir, "best_qnn_model.pth")

        # 适配你的数据集：输出维度=标签列数（你的数据集是2个指标）
        self.property_names = ["抗压强度", "弹性模量"]
        self.input_dim = self.n_qubits
        self.output_dim = len(self.property_names)  # 自动匹配输出维度


# ==================== 数据集类（适配你的Excel） ====================
class RockMaterialDataset:
    """岩石材料数据集类"""

    def __init__(self, config: QuantumConfig):
        self.config = config
        self.scaler_X = StandardScaler()
        self.scaler_y = StandardScaler()

        # 加载并预处理数据
        self.X_train, self.X_test, self.y_train, self.y_test = self._load_data()
        self.input_dim = self.X_train.shape[1]
        self.output_dim = self.y_train.shape[1]

        print(f"✅ 数据集加载完成")
        print(f"   训练集特征维度: {self.X_train.shape}")
        print(f"   训练集标签维度: {self.y_train.shape}")
        print(f"   测试集特征维度: {self.X_test.shape}")
        print(f"   测试集标签维度: {self.y_test.shape}")

    def _load_data(self):
        """从项目统一数据集构造 QNN 的配方输入和性质输出。"""
        dataset_path = self.config.dataset_file
        if not os.path.exists(dataset_path):
            raise FileNotFoundError(f"统一数据集不存在: {dataset_path}")

        print(f"📂 读取统一数据集: {dataset_path}")
        formula_df = pd.read_excel(dataset_path, sheet_name='Sheet1')
        property_df = pd.read_excel(dataset_path, sheet_name='Sheet2')
        merged = pd.merge(formula_df, property_df, on='label', how='inner')

        output_columns = ['抗压强度(MPa)', '弹性模量(MPa)']
        missing_outputs = [name for name in output_columns if name not in merged.columns]
        if missing_outputs:
            raise ValueError(f"统一数据集缺少性质列: {missing_outputs}")

        material_columns = [name for name in formula_df.columns if name != 'label']
        ranked_materials = sorted(
            material_columns,
            key=lambda name: (
                int(formula_df[name].fillna(0).ne(0).sum()),
                float(formula_df[name].fillna(0).var()),
            ),
            reverse=True,
        )
        self.feature_names = ranked_materials[:self.config.n_qubits]

        valid_rows = merged[output_columns].notna().all(axis=1)
        usable = merged.loc[valid_rows].reset_index(drop=True)
        if len(usable) < 10:
            raise ValueError(f"统一数据集有效样本不足: {len(usable)}")

        X = usable[self.feature_names].fillna(0).to_numpy(dtype=float)
        y = usable[output_columns].to_numpy(dtype=float)

        rng = np.random.RandomState(self.config.random_state)
        indices = rng.permutation(len(usable))
        test_size = max(1, int(round(len(indices) * 0.2)))
        test_indices = indices[:test_size]
        train_indices = indices[test_size:]

        X_train = self.scaler_X.fit_transform(X[train_indices])
        X_test = self.scaler_X.transform(X[test_indices])
        y_train = self.scaler_y.fit_transform(y[train_indices])
        y_test = self.scaler_y.transform(y[test_indices])

        print(f"✅ QNN 使用材料特征: {', '.join(self.feature_names)}")
        print(f"✅ 统一数据集有效样本: {len(usable)}（训练 {len(train_indices)} / 测试 {len(test_indices)}）")
        return X_train, X_test, y_train, y_test

    def inverse_transform_y(self, y_scaled):
        """反标准化标签到原始尺度"""
        return self.scaler_y.inverse_transform(y_scaled)


# ==================== 量子神经网络模型（兼容所有旧版PennyLane） ====================
class QNNModel(nn.Module):
    """量子神经网络模型（最基础原生写法，无任何高级API，兼容所有版本）"""

    def __init__(self, config: QuantumConfig):
        super(QNNModel, self).__init__()
        self.config = config
        self.n_qubits = config.n_qubits
        self.input_dim = config.input_dim
        self.output_dim = config.output_dim

        # 量子电路权重（用nn.Parameter管理，兼容PyTorch训练）
        self.weights = nn.Parameter(
            torch.randn(self.config.n_layers, self.n_qubits, 3, dtype=torch.float64)
        )

        # 经典输出层，维度匹配
        self.fc = nn.Linear(self.output_dim, self.output_dim, dtype=torch.float64)

        # 定义单样本量子电路（兼容所有旧版PennyLane）
        @qml.qnode(self.config.dev, interface="torch")
        def quantum_circuit(inputs, weights):
            # 单样本特征编码：inputs.shape = (n_qubits,)
            for i in range(self.n_qubits):
                qml.RY(inputs[i] * np_qml.pi, wires=i)

            # 量子层
            for layer in range(self.config.n_layers):
                # 单比特旋转门
                for i in range(self.n_qubits):
                    qml.Rot(weights[layer, i, 0], weights[layer, i, 1], weights[layer, i, 2], wires=i)
                # 相邻比特纠缠
                for i in range(self.n_qubits - 1):
                    qml.CNOT(wires=[i, i + 1])

            # 测量输出：返回前output_dim个比特的期望值
            return [qml.expval(qml.PauliZ(i)) for i in range(self.output_dim)]

        self.quantum_circuit = quantum_circuit

    def forward(self, x):
        """前向传播（兼容batch输入，循环处理每个样本，兼容所有版本）"""
        # x.shape = (batch_size, input_dim)
        batch_size = x.shape[0]
        outputs = []

        # 循环处理batch中的每个样本（兼容无批量API的旧版本）
        for i in range(batch_size):
            single_input = x[i]  # 取单个样本
            q_out = self.quantum_circuit(single_input, self.weights)  # 量子电路计算
            outputs.append(torch.stack(q_out))  # 保存结果

        # 拼接成batch输出
        batch_out = torch.stack(outputs)  # shape=(batch_size, output_dim)
        final_out = self.fc(batch_out)  # 经典层输出
        return final_out


# ==================== 核心预测器类 ====================
class QNNPredictor:
    """量子模型预测器（对外统一接口）"""

    def __init__(self, config: QuantumConfig = None):
        self.config = config or QuantumConfig()
        self.dataset = RockMaterialDataset(self.config)
        self.model = QNNModel(self.config)
        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=self.config.lr)
        self.criterion = nn.MSELoss()

        # 模型状态
        self.is_trained = False
        self.best_loss = float('inf')

    def train(self, verbose: bool = True):
        """训练模型"""
        train_dataset = TensorDataset(
            torch.tensor(self.dataset.X_train, dtype=torch.float64),
            torch.tensor(self.dataset.y_train, dtype=torch.float64)
        )
        # drop_last=True 避免最后一个batch维度不匹配
        train_loader = DataLoader(
            train_dataset,
            batch_size=self.config.batch_size,
            shuffle=True,
            drop_last=True
        )

        # 训练循环
        self.model.train()
        for epoch in range(self.config.epochs):
            total_loss = 0.0
            for batch_idx, (batch_X, batch_y) in enumerate(train_loader):
                self.optimizer.zero_grad()
                outputs = self.model(batch_X)
                loss = self.criterion(outputs, batch_y)
                loss.backward()
                self.optimizer.step()
                total_loss += loss.item()

            # 验证并保存最优模型
            avg_loss = total_loss / len(train_loader)
            if avg_loss < self.best_loss:
                self.best_loss = avg_loss
                self.save_model()

            if verbose and (epoch + 1) % 1 == 0:
                test_loss = self.evaluate()
                print(f"Epoch [{epoch + 1}/{self.config.epochs}], "
                      f"Train Loss: {avg_loss:.6f}, "
                      f"Test Loss: {test_loss:.6f}")

        self.is_trained = True
        print(f"✅ 量子模型训练完成，最优测试损失: {self.best_loss:.6f}")

    def evaluate(self, X=None, y=None) -> float:
        """评估模型性能"""
        self.model.eval()
        if X is None or y is None:
            X = torch.tensor(self.dataset.X_test, dtype=torch.float64)
            y = torch.tensor(self.dataset.y_test, dtype=torch.float64)

        with torch.no_grad():
            outputs = self.model(X)
            loss = self.criterion(outputs, y).item()
        return loss

    def save_model(self):
        """保存最优模型（核心修复：只保存可序列化的内容，避免加载报错）"""
        # 只保存权重、优化器状态和基础参数，不保存不可序列化的量子设备对象
        torch.save({
            'model_state_dict': self.model.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'best_loss': self.best_loss,
            'n_qubits': self.config.n_qubits,
            'n_layers': self.config.n_layers,
            'output_dim': self.config.output_dim,
            'property_names': self.config.property_names
        }, self.config.pretrained_model_path)
        print(f"💾 模型已保存至: {self.config.pretrained_model_path}")

    def load_pretrained_model(self) -> bool:
        """加载预训练模型（核心修复：解决PyTorch 2.6+加载报错）"""
        try:
            if not os.path.exists(self.config.pretrained_model_path):
                print(f"⚠ 预训练模型文件不存在: {self.config.pretrained_model_path}")
                return False

            # 修复1：设置weights_only=False，兼容自己生成的模型文件
            # 修复2：添加安全加载上下文
            checkpoint = torch.load(
                self.config.pretrained_model_path,
                weights_only=True,
                map_location='cpu'
            )

            # 加载权重和优化器
            self.model.load_state_dict(checkpoint['model_state_dict'])
            self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
            self.best_loss = checkpoint['best_loss']
            self.is_trained = True

            print(f"✅ 预训练模型加载成功，最优损失: {self.best_loss:.6f}")
            return True
        except Exception as e:
            print(f"❌ 加载预训练模型失败: {str(e)}")
            return False

    def predict_raw(self, input_data: np.ndarray) -> np.ndarray:
        """原始预测（标准化输出）"""
        if not self.is_trained:
            print("⚠ 模型未训练，先执行train()或load_pretrained_model()")
            return np.array([])

        self.model.eval()
        # 输入维度校验
        if len(input_data.shape) == 1:
            input_data = input_data.reshape(1, -1)
        if input_data.shape[1] != self.config.n_qubits:
            raise ValueError(f"输入特征维度必须为{self.config.n_qubits}，当前为{input_data.shape[1]}")

        input_tensor = torch.tensor(input_data, dtype=torch.float64)
        with torch.no_grad():
            output_scaled = self.model(input_tensor).numpy()
        return output_scaled

    def predict_unified(self, input_data: list | np.ndarray) -> dict:
        """
        统一预测接口（和大模型对齐）
        Args:
            input_data: 输入数据（列表/数组，8个特征）
        Returns:
            dict: 标准化输出结果
        """
        try:
            # 输入格式标准化
            if isinstance(input_data, list):
                input_data = np.array(input_data, dtype=np.float64)
            if len(input_data.shape) == 1:
                input_data = input_data.reshape(1, -1)

            # 输入特征标准化
            input_scaled = self.dataset.scaler_X.transform(input_data)

            # 模型预测
            output_scaled = self.predict_raw(input_scaled)
            if len(output_scaled) == 0:
                return {"error": "模型未训练或预测失败"}

            # 反标准化到原始尺度
            output_original = self.dataset.inverse_transform_y(output_scaled)

            # 构建统一返回格式
            result = {
                "input_raw": input_data.tolist(),
                "input_scaled": input_scaled.tolist(),
                "output_scaled": output_scaled.tolist(),
                "output_original": output_original.tolist(),
                "predictions": dict(zip(
                    self.config.property_names,
                    output_original[0] if len(output_original) > 0 else []
                )),
                "model_type": "quantum_model",
                "is_trained": self.is_trained
            }
            return result

        except Exception as e:
            print(f"❌ 统一预测接口执行失败: {str(e)}")
            return {"error": str(e)}


# ==================== 对外暴露的快速初始化函数 ====================
def init_quantum_model(custom_config: QuantumConfig = None, auto_load_pretrained: bool = True) -> QNNPredictor:
    """
    快速初始化量子模型
    Args:
        custom_config: 自定义配置
        auto_load_pretrained: 是否自动加载预训练模型
    Returns:
        QNNPredictor: 初始化完成的预测器实例
    """
    config = custom_config or QuantumConfig()
    predictor = QNNPredictor(config)

    if auto_load_pretrained:
        predictor.load_pretrained_model()

    return predictor


# ==================== 测试代码 ====================
if __name__ == "__main__":
    # 快速测试
    q_predictor = init_quantum_model(auto_load_pretrained=False)
    q_predictor.train(verbose=True)

    # 测试预测
    sample_input = [0.1, 0.2, 0.3, 0.05, 0.35, 0.0, 0.0, 0.0]
    result = q_predictor.predict_unified(sample_input)

    print("\n===== 测试预测结果 =====")
    if "error" in result:
        print(f"错误: {result['error']}")
    else:
        print(f"预测结果: {result['predictions']}")
