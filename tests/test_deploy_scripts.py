from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
SECRET_SCRIPT = ROOT / "deploy" / "gcp" / "set-paper-secrets.ps1"


class DeploymentScriptTests(unittest.TestCase):
    def test_secret_ingestion_avoids_unsupported_argument_list(self) -> None:
        source = SECRET_SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("$StartInfo.ArgumentList", source)
        self.assertIn("$StartInfo.Arguments", source)
        self.assertIn("RedirectStandardInput = $true", source)
        self.assertIn("ZeroFreeBSTR", source)

    @unittest.skipUnless(
        shutil.which("powershell.exe") and shutil.which("gcloud"),
        "Windows PowerShell and gcloud are required for the compatibility probe",
    )
    def test_secret_ingestion_validates_under_windows_powershell(self) -> None:
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(SECRET_SCRIPT),
                "-ValidateOnly",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("No secret was read or written", completed.stdout)


if __name__ == "__main__":
    unittest.main()
