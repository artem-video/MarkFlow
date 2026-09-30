"""Why does onnxruntime not use the GPU? Prints facts, writes nothing else."""
import os, sys, gc, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
def sh(c):
    try: return subprocess.run(c, shell=True, capture_output=True, text=True, timeout=60).stdout.strip()
    except Exception as e: return f"(failed: {e})"
print("python", sys.version.split()[0])
print("--- pip (onnx / nvidia / cuda) ---"); print(sh('python -m pip list 2>nul | findstr /i "onnx nvidia cuda"'))
print("--- nvidia-smi ---"); print(sh("nvidia-smi --query-gpu=name,driver_version,memory.used,memory.total --format=csv,noheader"))
import bench_asr as b
b.add_cuda_dlls()
import onnxruntime as ort
print("--- onnxruntime ---", ort.__version__, ort.get_device(), ort.get_available_providers())
try: ort.preload_dlls(); print("preload_dlls ok")
except Exception as e: print("preload_dlls failed:", e)
ort.set_default_logger_severity(2)
import onnx_asr
m = onnx_asr.load_model("gigaam-v3-rnnt", providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
for o in gc.get_objects():
    if isinstance(o, ort.InferenceSession): print("session providers:", o.get_providers())
