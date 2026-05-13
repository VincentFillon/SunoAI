"""
build.py — Build + sign SunoAI.exe with a self-signed certificate.

Usage:
    python build.py              # build + sign
    python build.py --cert-only  # only (re)generate the certificate
    python build.py --build-only # build without signing

Requirements:
    - PyInstaller  (pip install pyinstaller)
    - PowerShell 5+ (built-in on Windows 10/11) for cert generation
    - signtool.exe from Windows SDK  (auto-detected)

The .pfx certificate is generated once and reused on subsequent builds.
It is stored as 'certs/SunoAI.pfx' (excluded from git via .gitignore).
"""

import argparse
import glob
import os
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parent
CERT_DIR = ROOT / "certs"
PFX_PATH = CERT_DIR / "SunoAI.pfx"
CERT_PASSWORD = "sunoai-dev"          # Change for production use
CERT_SUBJECT = "CN=SunoAI Dev, O=SunoAI, C=FR"
EXE_PATH = ROOT / "dist" / "SunoAI.exe"

# signtool search roots (Windows SDK locations)
SIGNTOOL_SEARCH_ROOTS = [
    r"C:\Program Files (x86)\Windows Kits\10\bin",
    r"C:\Program Files\Windows Kits\10\bin",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(cmd: list[str], *, check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    print(f"\n>>> {' '.join(str(c) for c in cmd)}")
    return subprocess.run(cmd, check=check, **kwargs)


def find_signtool() -> Path | None:
    """Locate signtool.exe in Windows SDK installation."""
    for root in SIGNTOOL_SEARCH_ROOTS:
        root_path = Path(root)
        if not root_path.exists():
            continue
        # Walk sub-directories (SDK version folders) looking for x64/signtool.exe
        matches = sorted(root_path.glob("*/x64/signtool.exe"), reverse=True)
        if matches:
            return matches[0]
        # Fallback: any signtool.exe
        matches = sorted(root_path.glob("**/signtool.exe"), reverse=True)
        if matches:
            return matches[0]
    return None


# ---------------------------------------------------------------------------
# Step 1 — Certificate
# ---------------------------------------------------------------------------

def generate_certificate():
    """Generate a self-signed code-signing certificate via PowerShell."""
    CERT_DIR.mkdir(exist_ok=True)

    if PFX_PATH.exists():
        print(f"[cert] Certificate already exists: {PFX_PATH}")
        return

    print("[cert] Generating self-signed certificate …")

    # Create cert in CurrentUser\My store, then export to .pfx
    ps_script = f"""
$cert = New-SelfSignedCertificate `
    -Subject "{CERT_SUBJECT}" `
    -CertStoreLocation "Cert:\\CurrentUser\\My" `
    -KeyUsage DigitalSignature `
    -KeyAlgorithm RSA `
    -KeyLength 2048 `
    -Type CodeSigningCert `
    -NotAfter (Get-Date).AddYears(10)

$pwd = ConvertTo-SecureString -String "{CERT_PASSWORD}" -Force -AsPlainText
Export-PfxCertificate -Cert $cert -FilePath "{PFX_PATH}" -Password $pwd | Out-Null
Write-Host "Certificate exported to {PFX_PATH}"
"""

    run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script])
    print(f"[cert] PFX saved → {PFX_PATH}")

    # Also install cert into Trusted Root and Trusted Publishers so Windows
    # recognises the signature without a SmartScreen warning locally.
    install_script = f"""
$pwd = ConvertTo-SecureString -String "{CERT_PASSWORD}" -Force -AsPlainText
$cert = Get-PfxCertificate -FilePath "{PFX_PATH}"
$stores = @("Root", "TrustedPublisher")
foreach ($store in $stores) {{
    $s = [System.Security.Cryptography.X509Certificates.X509Store]::new($store, "CurrentUser")
    $s.Open("ReadWrite")
    $s.Add($cert)
    $s.Close()
    Write-Host "Installed in $store"
}}
"""
    run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", install_script])
    print("[cert] Certificate installed in CurrentUser\\Root and CurrentUser\\TrustedPublisher")


# ---------------------------------------------------------------------------
# Step 2 — Build
# ---------------------------------------------------------------------------

def build_exe():
    print("[build] Running PyInstaller …")
    run([sys.executable, "-m", "PyInstaller", "SunoAI.spec", "--clean"], cwd=ROOT)
    if not EXE_PATH.exists():
        print(f"[build] ERROR: expected output not found: {EXE_PATH}", file=sys.stderr)
        sys.exit(1)
    print(f"[build] Built → {EXE_PATH}")


# ---------------------------------------------------------------------------
# Step 3 — Sign
# ---------------------------------------------------------------------------

def sign_exe():
    if not EXE_PATH.exists():
        print(f"[sign] ERROR: {EXE_PATH} not found — build first.", file=sys.stderr)
        sys.exit(1)

    signtool = find_signtool()
    if signtool is None:
        print(
            "[sign] WARNING: signtool.exe not found.\n"
            "       Install Windows SDK: https://developer.microsoft.com/windows/downloads/windows-sdk/\n"
            "       Skipping signature.",
            file=sys.stderr,
        )
        return

    print(f"[sign] Using signtool: {signtool}")
    run([
        str(signtool), "sign",
        "/fd", "SHA256",
        "/f", str(PFX_PATH),
        "/p", CERT_PASSWORD,
        "/tr", "http://timestamp.digicert.com",
        "/td", "SHA256",
        "/d", "SunoAI",
        str(EXE_PATH),
    ])

    # Verify
    run([str(signtool), "verify", "/pa", str(EXE_PATH)], check=False)
    print(f"[sign] Signed → {EXE_PATH}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Build and sign SunoAI.exe")
    parser.add_argument("--cert-only",  action="store_true", help="Only generate certificate")
    parser.add_argument("--build-only", action="store_true", help="Build without signing")
    args = parser.parse_args()

    if args.cert_only:
        generate_certificate()
        return

    generate_certificate()
    build_exe()

    if not args.build_only:
        sign_exe()


if __name__ == "__main__":
    main()
