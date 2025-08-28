import subprocess, shlex

class CmdError(RuntimeError): pass


def run(cmd: list[str]) -> None:
    print("[INFO]", " ".join(shlex.quote(c) for c in cmd))
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    out, _ = p.communicate()
    print(out or "", end="")
    if p.returncode != 0:
        raise CmdError(f"Command failed (rc={p.returncode})")
