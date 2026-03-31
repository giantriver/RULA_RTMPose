import rtmlib
import cv2
import onnxruntime as ort
import importlib.metadata

# 1. 檢查版本 (改用 importlib)
try:
    version = importlib.metadata.version('rtmlib')
    print(f"✅ rtmlib version: {version}")
except importlib.metadata.PackageNotFoundError:
    print("❌ rtmlib is not installed.")

# 2. 檢查 ONNX Runtime 的硬體加速
providers = ort.get_available_providers()
print(f"🔍 Available Providers: {providers}")

if 'CUDAExecutionProvider' in providers:
    print("🚀 Great! CUDA (GPU) is available for RTMPose.")
else:
    print("⚠️ Warning: CUDA not found. Running on CPU (might be slow).")

# 3. 測試初始化模型 (這會觸發模型下載，請確保有網路)
from rtmlib import Body
try:
    print("⏳ Initializing RTMPose model (this may take a moment)...")
    # 第一次執行會下載模型到 ~/.cache/rtmlib/
    model = Body(mode='lightweight', backend='onnxruntime', device='cpu')
    print("✅ Model initialized successfully!")
except Exception as e:
    print(f"❌ Error during model initialization: {e}")