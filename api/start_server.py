import subprocess
import sys
import os

os.chdir("D:/Knowledge_Map/api")

proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8000"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1
)

print(f"Started uvicorn PID: {proc.pid}")

try:
    for i in range(15):
        line = proc.stdout.readline()
        if line:
            print(f"[{i}s] {line.rstrip()}")
        if proc.poll() is not None:
            print(f"Process exited: {proc.returncode}")
            break
        import time
        time.sleep(1)
except KeyboardInterrupt:
    print("Interrupted")
finally:
    if proc.poll() is None:
        print("Terminating...")
        proc.terminate()
        proc.wait(timeout=5)