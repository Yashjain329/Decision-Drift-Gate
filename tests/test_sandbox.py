import os
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ddg import sandbox
from ddg.demo import build_demo
from ddg.harness import _drive_worker, FakeService, observe

# Evades the static screen on purpose: the container, not the screen, must contain these.
BUILTINS = "(lambda: 0).__globals__['__builtins__']"
CHECK = __import__("json").loads(Path("examples/manual_check.json").read_text(encoding="utf-8"))
HAVE_RUNTIME = sandbox._usable("docker")


def _commit(repo: Path, source: str) -> None:
    (repo / "src" / "job_client.py").write_text(source, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "src/job_client.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=T", "-c", "user.email=t@e.invalid",
                    "commit", "--quiet", "-m", "fixture"], check=True)


class CommandTests(unittest.TestCase):
    def test_container_command_is_locked_down(self):
        argv = sandbox.container_argv("docker", "ddg-x", Path("/s"), Path("/w.py"))
        joined = " ".join(argv)
        for flag in ("--network none", "--read-only", "--cap-drop ALL", "no-new-privileges",
                     "--pids-limit", "--memory", "--user 65534:65534", "noexec"):
            self.assertIn(flag, joined)
        self.assertNotIn("--privileged", joined)
        self.assertTrue(all(m.endswith(":ro") for m in argv if m.startswith(("/s:", "/w.py:"))) or ":ro" in joined)

    def test_unknown_mode_is_rejected(self):
        with patch.dict(os.environ, {"DDG_SANDBOX": "chroot"}):
            with self.assertRaises(sandbox.SandboxUnavailable):
                sandbox.resolve()

    def test_missing_runtime_fails_closed_instead_of_running_on_host(self):
        with TemporaryDirectory() as folder:
            repo = Path(build_demo(Path(folder) / "repo")["repo"])
            with patch.dict(os.environ, {"DDG_SANDBOX": "podman"}), \
                    patch.object(sandbox, "_usable", return_value=False):
                result = observe(repo, "HEAD", CHECK)
        self.assertEqual(result["status"], "ERROR")
        self.assertIn("container runtime", result["error"])

    def test_oversized_worker_message_is_an_error(self):
        class Proc:
            class stdout:
                @staticmethod
                def readline(limit):
                    return "x" * limit
            stdin = None
            def poll(self):
                return None
        outcome = _drive_worker(Proc(), FakeService("none"))
        self.assertEqual(outcome["op"], "error")
        self.assertIn("size limit", outcome["error"])


@unittest.skipUnless(HAVE_RUNTIME, "no usable docker daemon; container escape tests skipped")
class ContainerEscapeTests(unittest.TestCase):
    def run_source(self, source, timeout=30):
        with TemporaryDirectory() as folder, patch.dict(os.environ, {"DDG_SANDBOX": "docker"}):
            repo = Path(build_demo(Path(folder) / "repo")["repo"])
            _commit(repo, source)
            return observe(repo, "HEAD", CHECK, timeout=timeout)

    def assertContained(self, result):
        # The probe must actually have run (job created via the except path), and not escaped.
        self.assertEqual(result["error"], None, result)
        self.assertEqual(result["submit_calls"], 1, result)  # reached the post-probe path
        self.assertNotEqual(result["returned_job_id"], "ESCAPED", result)

    def test_honest_client_still_passes_in_container(self):
        good = ("def submit_job(service, payload, operation_id):\n"
                "    r = service.create(payload, operation_id)\n"
                "    if r.status == 503:\n"
                "        e = service.lookup(operation_id)\n"
                "        if e: return e\n"
                "        r = service.create(payload, operation_id)\n"
                "    return r.job_id\n")
        self.assertEqual(self.run_source(good)["status"], "PASS")

    def test_network_is_unreachable(self):
        src = ("def submit_job(service, payload, operation_id):\n"
               "    s = " + BUILTINS + "['__im' + 'port__']('soc' + 'ket')\n"
               "    try:\n"
               "        s.create_connection(('1.1.1.1', 53), timeout=3)\n"
               "        return 'ESCAPED'\n"
               "    except OSError:\n"
               "        return service.create(payload, operation_id).job_id\n")
        self.assertContained(self.run_source(src))

    def test_filesystem_is_read_only(self):
        src = ("def submit_job(service, payload, operation_id):\n"
               "    try:\n"
               "        " + BUILTINS + "['op' + 'en']('/work/src/pwn', 'w').write('x')\n"
               "        return 'ESCAPED'\n"
               "    except OSError:\n"
               "        return service.create(payload, operation_id).job_id\n")
        self.assertContained(self.run_source(src))

    def test_infinite_loop_times_out_and_container_is_removed(self):
        src = "def submit_job(service, payload, operation_id):\n    while True:\n        pass\n"
        result = self.run_source(src, timeout=8)
        self.assertEqual(result["status"], "ERROR")
        left = subprocess.run(["docker", "ps", "-aq", "--filter", "name=ddg-"],
                              capture_output=True, text=True).stdout.strip()
        self.assertEqual(left, "")

    def test_memory_bomb_is_contained(self):
        src = "def submit_job(service, payload, operation_id):\n    x = bytearray(2 * 1024**3)\n    return None\n"
        self.assertEqual(self.run_source(src)["status"], "ERROR")



PROBE = (
    "def submit_job(service, payload, operation_id):" + chr(10)
    + "    b = " + BUILTINS + chr(10)
    + "    b['op' + 'en'](%r, 'w').write('x')" + chr(10)
    + "    return service.create(payload, operation_id).job_id" + chr(10)
)


class ControlTests(unittest.TestCase):
    def test_same_filesystem_probe_escapes_on_host_so_container_tests_are_meaningful(self):
        with TemporaryDirectory() as folder, patch.dict(os.environ, {"DDG_SANDBOX": "host"}):
            repo = Path(build_demo(Path(folder) / "repo")["repo"])
            target = Path(folder) / "pwn.txt"
            _commit(repo, PROBE % str(target))
            observe(repo, "HEAD", CHECK)
            self.assertTrue(target.exists())


if __name__ == "__main__":
    unittest.main()
