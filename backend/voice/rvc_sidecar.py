"""Local-only RVC inference service for the optional RVC runtime."""

import argparse
import base64
import binascii
import hashlib
import logging
import os
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit

logger = logging.getLogger("rvc_sidecar")
MAX_AUDIO_BYTES = 20 * 1024 * 1024
HUBERT_MODEL_URL = (
    "https://huggingface.co/Daswer123/RVC_Base/resolve/main/hubert_base.pt"
)
HUBERT_MODEL_SIZE = 189_507_909
HUBERT_MODEL_SHA256 = (
    "f54b40fd2802423a5643779c4861af1e9ee9c1564dc9d32f54f20b5ffba7db96"
)
HUBERT_CHUNK_SIZE = 8 * 1024 * 1024


def _ensure_hubert_model(lib_dir: str) -> None:
    import requests

    model_dir = Path(lib_dir) / "base_model"
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / "hubert_base.pt"
    if model_path.is_file() and model_path.stat().st_size == HUBERT_MODEL_SIZE:
        return

    parsed_url = urlsplit(HUBERT_MODEL_URL)
    if parsed_url.scheme != "https" or parsed_url.hostname != "huggingface.co":
        raise RuntimeError("HuBERT model URL must use the trusted Hugging Face host.")

    chunks_dir = model_dir / ".hubert_download_chunks"
    chunks_dir.mkdir(exist_ok=True)
    partial_path = model_dir / "hubert_base.pt.part"
    chunk_starts = list(range(0, HUBERT_MODEL_SIZE, HUBERT_CHUNK_SIZE))

    if partial_path.is_file():
        legacy_size = min(partial_path.stat().st_size, HUBERT_MODEL_SIZE)
        with partial_path.open("rb") as partial_file:
            for start in chunk_starts:
                expected_chunk_size = min(
                    HUBERT_CHUNK_SIZE, HUBERT_MODEL_SIZE - start
                )
                if start + expected_chunk_size > legacy_size:
                    break
                chunk_path = chunks_dir / f"{start:012d}.chunk"
                if not chunk_path.exists():
                    partial_file.seek(start)
                    chunk_path.write_bytes(partial_file.read(expected_chunk_size))
        partial_path.unlink()

    missing_chunks = []
    for start in chunk_starts:
        chunk_size = min(HUBERT_CHUNK_SIZE, HUBERT_MODEL_SIZE - start)
        chunk_path = chunks_dir / f"{start:012d}.chunk"
        if chunk_path.is_file() and chunk_path.stat().st_size == chunk_size:
            continue
        chunk_path.unlink(missing_ok=True)
        missing_chunks.append(start)

    if missing_chunks:
        logger.info(
            "Downloading required HuBERT model (%d MiB); this may take several minutes.",
            HUBERT_MODEL_SIZE // (1024 * 1024),
        )

    def download_chunk(start: int) -> None:
        end = min(start + HUBERT_CHUNK_SIZE, HUBERT_MODEL_SIZE) - 1
        chunk_path = chunks_dir / f"{start:012d}.chunk"
        headers = {"Range": f"bytes={start}-{end}"}
        with requests.get(
            HUBERT_MODEL_URL,
            headers=headers,
            stream=True,
            timeout=(15, 180),
        ) as response:
            if response.status_code != 206:
                raise RuntimeError(
                    f"HuBERT server did not honor byte range {start}-{end} "
                    f"(HTTP {response.status_code})."
                )
            content_range = response.headers.get("Content-Range", "")
            if not re.fullmatch(
                rf"bytes {start}-{end}/{HUBERT_MODEL_SIZE}", content_range
            ):
                raise RuntimeError(
                    f"Unexpected HuBERT range response: {content_range!r}."
                )

            chunk = bytearray()
            for part in response.iter_content(chunk_size=1024 * 1024):
                if part:
                    chunk.extend(part)
            if len(chunk) != end - start + 1:
                raise RuntimeError(
                    f"Incomplete HuBERT range {start}-{end}: "
                    f"received {len(chunk)} bytes."
                )
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{start:012d}_",
                suffix=".part",
                dir=chunks_dir,
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)
                temp_file.write(chunk)
            os.replace(temp_path, chunk_path)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [
                executor.submit(download_chunk, start) for start in missing_chunks
            ]
            completed = 0
            for future in as_completed(futures):
                future.result()
                completed += 1
                if completed % 4 == 0 or completed == len(futures):
                    logger.info(
                        "HuBERT download: %d/%d chunks complete.",
                        completed,
                        len(missing_chunks),
                    )

        with partial_path.open("wb") as assembled_file:
            for start in chunk_starts:
                chunk_path = chunks_dir / f"{start:012d}.chunk"
                with chunk_path.open("rb") as chunk_file:
                    while chunk := chunk_file.read(1024 * 1024):
                        assembled_file.write(chunk)
        if partial_path.stat().st_size != HUBERT_MODEL_SIZE:
            raise RuntimeError("HuBERT download did not produce the expected file size.")
        digest = hashlib.sha256()
        with partial_path.open("rb") as model_file:
            for chunk in iter(lambda: model_file.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != HUBERT_MODEL_SHA256:
            partial_path.unlink()
            raise RuntimeError("HuBERT model SHA-256 verification failed.")
        os.replace(partial_path, model_path)
        for chunk_path in chunks_dir.glob("*.chunk"):
            chunk_path.unlink()
        chunks_dir.rmdir()
        logger.info("Downloaded HuBERT model to %s", model_path)
    except (requests.RequestException, OSError) as exc:
        raise RuntimeError(
            "Could not download the required HuBERT model. A partial download, "
            "if present, will be resumed the next time the RVC service starts."
        ) from exc


def _download_required_rvc_assets(lib_dir: str) -> None:
    _ensure_hubert_model(lib_dir)


def _infer_audio_file(converter, input_path: str, output_path: str) -> None:
    model_info = converter.models[converter.current_model]
    result = converter.vc.vc_single(
        sid=0,
        input_audio_path=input_path,
        f0_up_key=converter.f0up_key,
        f0_method=converter.f0method,
        file_index=model_info.get("index", ""),
        index_rate=converter.index_rate,
        filter_radius=converter.filter_radius,
        resample_sr=converter.resample_sr,
        rms_mix_rate=converter.rms_mix_rate,
        protect=converter.protect,
        f0_file="",
        file_index2="",
    )
    if isinstance(result, tuple):
        details = result[0] if result and isinstance(result[0], str) else repr(result)
        raise RuntimeError(f"RVC inference failed: {details[-1000:]}")
    if not hasattr(result, "dtype"):
        raise RuntimeError(
            f"RVC inference returned unexpected output type: {type(result).__name__}"
        )

    from scipy.io import wavfile

    wavfile.write(output_path, converter.vc.tgt_sr, result)


def create_app(model_path: str, index_path: str, device: str = "cpu"):
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import Response
    from pydantic import BaseModel
    from .python311_compat import (
        enable_fairseq_py311_compatibility,
        enable_trusted_checkpoint_loading,
    )

    enable_fairseq_py311_compatibility()
    hubert_model_path = (
        Path(__import__("rvc_python").__file__).resolve().parent
        / "base_model"
        / "hubert_base.pt"
    )
    enable_trusted_checkpoint_loading(str(hubert_model_path))
    import rvc_python.infer as rvc_infer

    rvc_infer.download_rvc_models = _download_required_rvc_assets
    from rvc_python.infer import RVCInference

    model_file = Path(model_path).resolve()
    index_file = Path(index_path).resolve()
    if not model_file.is_file():
        raise FileNotFoundError(f"RVC model not found: {model_file}")
    if not index_file.is_file():
        raise FileNotFoundError(f"RVC index not found: {index_file}")

    converter = RVCInference(
        device=device,
        model_path=str(model_file),
        index_path=str(index_file),
        version="v2",
    )
    converter.set_params(
        f0method="harvest",
        f0up_key=0,
        index_rate=0.65,
        filter_radius=3,
        resample_sr=0,
        rms_mix_rate=0.25,
        protect=0.33,
    )

    class ConvertRequest(BaseModel):
        audio_data: str

    app = FastAPI()

    @app.post("/convert")
    def convert_audio(payload: ConvertRequest):
        try:
            input_bytes = base64.b64decode(payload.audio_data, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Invalid audio_data") from exc
        if not input_bytes or len(input_bytes) > MAX_AUDIO_BYTES:
            raise HTTPException(
                status_code=413,
                detail="Audio must be non-empty and no larger than 20 MB",
            )

        input_fd, input_path = tempfile.mkstemp(prefix="rvc_input_", suffix=".mp3")
        output_fd, output_path = tempfile.mkstemp(prefix="rvc_output_", suffix=".wav")
        os.close(input_fd)
        os.close(output_fd)
        try:
            with open(input_path, "wb") as input_file:
                input_file.write(input_bytes)
            _infer_audio_file(converter, input_path, output_path)
            with open(output_path, "rb") as output_file:
                audio = output_file.read()
        except Exception as exc:
            logger.exception("RVC conversion failed")
            raise HTTPException(
                status_code=500,
                detail=f"RVC conversion failed: {str(exc)[:300]}",
            ) from exc
        finally:
            Path(input_path).unlink(missing_ok=True)
            Path(output_path).unlink(missing_ok=True)

        if not audio:
            raise HTTPException(status_code=500, detail="RVC returned empty audio")
        return Response(content=audio, media_type="audio/wav")

    return app


def main():
    parser = argparse.ArgumentParser(description="Run a local RVC conversion API.")
    parser.add_argument("--model", required=True, help="Path to an RVC inference .pth model")
    parser.add_argument("--index", required=True, help="Path to the RVC .index file")
    parser.add_argument("--device", default="cpu", help="Inference device, e.g. cpu or cuda:0")
    parser.add_argument("--port", type=int, default=5050)
    args = parser.parse_args()

    import uvicorn

    app = create_app(args.model, args.index, args.device)
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
