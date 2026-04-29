import subprocess
import sys
import os
import signal
import threading

ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(ROOT, "backend")
FRONTEND = os.path.join(ROOT, "frontend")


def stream(proc, prefix):
    for line in iter(proc.stdout.readline, b""):
        print(f"[{prefix}] {line.decode(errors='replace').rstrip()}")


def main():
    procs = []
    try:
        backend = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app", "--reload", "--port", "8001"],
            cwd=BACKEND,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        procs.append(backend)
        threading.Thread(target=stream, args=(backend, "BACK"), daemon=True).start()

        node_path = r"C:\Program Files\nodejs"
        env = os.environ.copy()
        env["PATH"] = node_path + os.pathsep + env.get("PATH", "")

        frontend = subprocess.Popen(
            [r"C:\Program Files\nodejs\npm.cmd", "run", "dev"],
            cwd=FRONTEND,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
        )
        procs.append(frontend)
        threading.Thread(target=stream, args=(frontend, "FRONT"), daemon=True).start()

        print("서버 시작됨. Ctrl+C 로 종료.")
        for p in procs:
            p.wait()

    except KeyboardInterrupt:
        print("\n종료 중...")
        for p in procs:
            p.terminate()


if __name__ == "__main__":
    main()
