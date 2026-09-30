"""Offline synthetic inference + entrypoint checks; never real DB/Gmail/Gemini."""

import argparse
import json
import math
import os
import resource
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from unittest.mock import patch


def synthetic_environment() -> dict[str, str]:
    from cryptography.fernet import Fernet
    return os.environ | {
        "APP_ENV": "production",
        "DATABASE_URL": "postgresql://demo:unused@127.0.0.1:1/postgres?sslmode=require",
        "SUPABASE_URL": "https://project.example",
        "GEMINI_API_KEY": "synthetic-not-a-real-key",
        "GOOGLE_CLIENT_ID": "synthetic.apps.googleusercontent.com",
        "GOOGLE_CLIENT_SECRET": "synthetic-not-a-real-secret",
        "TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "GOOGLE_REDIRECT_URI": "https://api.example/gmail/callback",
        "FRONTEND_URL": "https://frontend.example",
        "GMAIL_SYNC_DISPATCH": "cloud_run",
        "CLOUD_RUN_PROJECT": "synthetic-project",
        "CLOUD_RUN_REGION": "us-west1",
        "GMAIL_SYNC_JOB_NAME": "synthetic-worker",
        "PORT": "18080",
    }


def check_api_startup() -> None:
    process = subprocess.Popen(
        [sys.executable, "-m", "scripts.start_api"],
        env=synthetic_environment(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("API entrypoint stopped before health was ready")
            try:
                with urllib.request.urlopen("http://127.0.0.1:18080/health", timeout=1) as response:
                    if response.status != 200 or json.load(response) != {"status": "ok"}:
                        raise RuntimeError("API health response mismatch")
                break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.2)
        else:
            raise RuntimeError("API startup exceeded smoke-test deadline")
        for path, body in (("/gmail/sync", b"{}"), ("/ask", b'{"question":"Synthetic question"}')):
            request = urllib.request.Request(
                "http://127.0.0.1:18080" + path, data=body,
                headers={"Content-Type": "application/json"}, method="POST",
            )
            try:
                urllib.request.urlopen(request, timeout=5).close()
            except urllib.error.HTTPError as exc:
                if exc.code != 401:
                    raise RuntimeError("Protected API did not return 401") from None
                exc.close()
            else:
                raise RuntimeError("Protected API unexpectedly accepted missing authentication")
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def check_worker_noop() -> None:
    from app.worker import main
    target = uuid.UUID("00000000-0000-4000-8000-000000000001")
    with patch.dict(os.environ, synthetic_environment()), patch("app.worker.load_dotenv"), patch(
        "app.worker.claim_gmail_sync_job", return_value=None,
    ) as claim:
        if main(["--job-id", str(target)]) != 0:
            raise RuntimeError("Targeted worker no-op did not exit successfully")
        claim.assert_called_once_with(target)


def run_smoke(role: str, require_linux: bool = False) -> dict:
    if require_linux and sys.platform != "linux":
        raise RuntimeError("Linux container verification must run on Linux")
    if os.environ.get("HF_HUB_OFFLINE") != "1" or os.environ.get("TRANSFORMERS_OFFLINE") != "1":
        raise RuntimeError("Model smoke checks require offline mode")
    import torch
    from app.embeddings import EMBEDDING_DIMENSION, embed_texts
    from app.model_artifacts import validate_packaged_models
    if torch.version.cuda is not None:
        raise RuntimeError("Unexpected CUDA-enabled runtime")
    if require_linux and torch.__version__ != "2.13.0+cpu":
        raise RuntimeError("Unexpected Linux PyTorch build")
    print("Checking packaged model inventory and checksums", flush=True)
    validate_packaged_models(role)
    started = time.monotonic()
    # Representative chunk length and the existing worker's embedding batch size.
    text = ("Synthetic email about a college orientation schedule. " * 25)[:1000]
    count = 64 if role == "worker" else 1
    print("Checking offline synthetic embeddings", flush=True)
    vectors = embed_texts([text] * count)
    if len(vectors) != count or any(
        len(vector) != EMBEDDING_DIMENSION or not all(math.isfinite(v) for v in vector)
        for vector in vectors
    ):
        raise RuntimeError("Embedding output is invalid")
    if role == "api":
        print("Checking offline reranking and API startup/401 responses", flush=True)
        from app.rerank import rerank_candidates
        candidates = [{"text": text, "chunk_id": str(index)} for index in range(20)]
        ranked = rerank_candidates("When is orientation?", candidates)
        if len(ranked) != 5 or not all(math.isfinite(row["score"]) for row in ranked):
            raise RuntimeError("Reranking output is invalid")
        check_api_startup()
    else:
        print("Checking targeted worker no-op exit (mocked database claim)", flush=True)
        check_worker_noop()
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {
        "role": role, "platform": sys.platform, "torch": torch.__version__,
        "passed": True, "network_required": False, "live_database_used": False,
        "synthetic_embedding_count": count, "seconds": round(time.monotonic() - started, 2),
        "synthetic_process_peak_mib": round(rss / (1024 if sys.platform == "linux" else 1024 * 1024), 1),
        "measurement_scope": "synthetic CPU inference, not production concurrency or full-mailbox peak",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=("api", "worker"), required=True)
    parser.add_argument("--require-linux", action="store_true")
    args = parser.parse_args()
    try:
        result = run_smoke(args.role, args.require_linux)
    except Exception as exc:
        print(f"Container smoke check failed: {type(exc).__name__}")
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
