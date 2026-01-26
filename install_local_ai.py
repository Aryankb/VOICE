"""
Installation script for local AI setup
Automates installation of Ollama and TTS dependencies
"""

import subprocess
import sys
import platform
import os
from pathlib import Path


def run_command(cmd, description, check=True):
    """Run a shell command and print status"""
    print(f"\n{'=' * 60}")
    print(f"{description}...")
    print(f"{'=' * 60}")
    print(f"Running: {cmd}")

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            check=check,
            capture_output=True,
            text=True
        )

        if result.stdout:
            print(result.stdout)

        if result.returncode == 0:
            print(f"✅ {description} - SUCCESS")
            return True
        else:
            if result.stderr:
                print(f"Error: {result.stderr}")
            print(f"❌ {description} - FAILED")
            return False

    except subprocess.CalledProcessError as e:
        print(f"❌ {description} - FAILED")
        print(f"Error: {e.stderr}")
        return False
    except Exception as e:
        print(f"❌ {description} - FAILED")
        print(f"Error: {str(e)}")
        return False


def check_ollama_installed():
    """Check if Ollama is installed"""
    try:
        result = subprocess.run(
            ["ollama", "--version"],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def install_ollama():
    """Install Ollama based on OS"""
    print("\n" + "=" * 60)
    print("Installing Ollama")
    print("=" * 60)

    system = platform.system()

    if system == "Windows":
        print("\n📥 Downloading Ollama for Windows...")
        print("\nPlease download and install Ollama manually:")
        print("1. Visit: https://ollama.ai/download/windows")
        print("2. Download and run OllamaSetup.exe")
        print("3. After installation, come back and press Enter")
        input("\nPress Enter when Ollama is installed...")

        if check_ollama_installed():
            print("✅ Ollama installed successfully")
            return True
        else:
            print("❌ Ollama not detected. Please install manually.")
            return False

    elif system == "Darwin":  # macOS
        print("\n📥 Installing Ollama for macOS...")
        return run_command(
            "brew install ollama",
            "Install Ollama via Homebrew",
            check=False
        )

    elif system == "Linux":
        print("\n📥 Installing Ollama for Linux...")
        return run_command(
            "curl -fsSL https://ollama.ai/install.sh | sh",
            "Install Ollama",
            check=False
        )

    else:
        print(f"❌ Unsupported OS: {system}")
        return False


def pull_ollama_model(model_name):
    """Pull Ollama model"""
    print(f"\n📥 Pulling model: {model_name}")
    print("This may take 10-15 minutes depending on your internet speed...")

    return run_command(
        f"ollama pull {model_name}",
        f"Pull {model_name}",
        check=False
    )


def install_python_dependencies():
    """Install Python dependencies"""
    print("\n" + "=" * 60)
    print("Installing Python Dependencies")
    print("=" * 60)

    # Try uv first, fallback to pip
    if run_command("uv --version", "Check uv", check=False):
        return run_command("uv sync", "Install dependencies with uv")
    else:
        print("\n⚠️ uv not found, using pip")
        return run_command(
            "pip install httpx coqui-tts",
            "Install httpx and coqui-tts"
        )


def create_env_file():
    """Create .env file from .env.example if it doesn't exist"""
    env_file = Path(".env")
    env_example = Path(".env.example")

    if env_file.exists():
        print("\n✅ .env file already exists")
        return True

    if not env_example.exists():
        print("\n⚠️ .env.example not found")
        return False

    print("\n📝 Creating .env file from .env.example...")
    env_file.write_text(env_example.read_text())
    print("✅ .env file created")
    print("\n⚠️ IMPORTANT: Update these values in .env:")
    print("  - PUBLIC_URL (after starting ngrok)")
    return True


def main():
    """Main installation process"""
    print("\n" + "=" * 60)
    print("LOCAL AI INSTALLATION SCRIPT")
    print("=" * 60)
    print("\nThis script will install:")
    print("  1. Ollama (local LLM runtime)")
    print("  2. Qwen 2.5 Coder 32B model")
    print("  3. Python dependencies (httpx, coqui-tts)")
    print("\nEstimated time: 15-20 minutes")
    print("Disk space needed: ~25GB")

    response = input("\n Continue? (y/n): ")
    if response.lower() != 'y':
        print("Installation cancelled.")
        return

    results = {}

    # Step 1: Check/Install Ollama
    if check_ollama_installed():
        print("\n✅ Ollama is already installed")
        results["ollama"] = True
    else:
        results["ollama"] = install_ollama()

    # Step 2: Pull model
    if results.get("ollama"):
        model_name = "qwen2.5-coder:32b-instruct-q4_K_M"
        results["model"] = pull_ollama_model(model_name)
    else:
        print("\n⏭️ Skipping model pull (Ollama not installed)")
        results["model"] = False

    # Step 3: Install Python dependencies
    results["python_deps"] = install_python_dependencies()

    # Step 4: Create .env file
    results["env_file"] = create_env_file()

    # Summary
    print("\n" + "=" * 60)
    print("INSTALLATION SUMMARY")
    print("=" * 60)
    print(f"  Ollama:       {'✅ INSTALLED' if results.get('ollama') else '❌ FAILED'}")
    print(f"  Model:        {'✅ PULLED' if results.get('model') else '❌ FAILED'}")
    print(f"  Python Deps:  {'✅ INSTALLED' if results.get('python_deps') else '❌ FAILED'}")
    print(f"  .env file:    {'✅ CREATED' if results.get('env_file') else '❌ FAILED'}")
    print("=" * 60)

    if all(results.values()):
        print("\n🎉 Installation complete!")
        print("\nNext steps:")
        print("  1. Test the setup: python test_local_setup.py")
        print("  2. Start ngrok: ngrok http 8000")
        print("  3. Update PUBLIC_URL in .env")
        print("  4. Start server: python app.py")
    else:
        print("\n⚠️ Installation incomplete. Please check errors above.")
        print("\nManual installation:")
        if not results.get("ollama"):
            print("  1. Install Ollama: https://ollama.ai")
        if not results.get("model"):
            print("  2. Pull model: ollama pull qwen2.5-coder:32b-instruct-q4_K_M")
        if not results.get("python_deps"):
            print("  3. Install deps: pip install httpx coqui-tts")


if __name__ == "__main__":
    main()
