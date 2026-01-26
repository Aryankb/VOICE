import sys
print("Python executable:", sys.executable)
print("Python version:", sys.version)

try:
    import torch
    print("Number of GPU: ", torch.cuda.device_count())
    print("GPU Name: ", torch.cuda.get_device_name())
    
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print('Using device:', device)
except ModuleNotFoundError:
    print("ERROR: torch not found in this Python environment")
    print("Try: uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu130")