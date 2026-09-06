"""ComfyUI-AnyTop — thin wrapper around Anytop2025/Anytop (MIT).

Clones/runs AnyTop in an isolated venv and returns a .bvh path. Does not
import AnyTop into the ComfyUI process (avoids Python/CUDA clashes).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

import folder_paths

PKG_ROOT = Path(__file__).resolve().parent
DEFAULT_REPO = os.environ.get("ANYTOP_REPO", "https://github.com/Anytop2025/Anytop.git")
DEFAULT_BRANCH = os.environ.get("ANYTOP_BRANCH", "main")
ANYTOP_ROOT = Path(os.environ.get("ANYTOP_ROOT", str(PKG_ROOT / "anytop_repo")))
VENV_DIR = PKG_ROOT / "anytop_venv"

# Curated Truebones-style object types grouped by AnyTop model subset.
# Users can type any name present in their local cond.npy after Setup.
OBJECT_TYPES_BY_SUBSET = {
    "quadropeds": ["Dog", "Horse", "Coyote", "Cat", "Lion", "Wolf", "Fox", "Bear"],
    "flying": ["Parrot2", "Bat", "Eagle", "Hawk", "Crow"],
    "millipeds_snakes": ["Snake", "Cobra", "Millipede"],
    "bipeds": ["Monkey", "Gorilla", "Ostrich", "Tyranno"],
    "all": ["Dog", "Horse", "Parrot2", "Bat", "Snake", "Monkey", "Scorpion", "Crab"],
}

MODEL_SUBSETS = list(OBJECT_TYPES_BY_SUBSET.keys())


def _venv_python() -> Path:
    override = os.environ.get("ANYTOP_PYTHON", "").strip()
    if override:
        return Path(override)
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def _run(cmd: list[str], *, cwd: Path | None = None, env: dict | None = None) -> None:
    print("[ComfyUI-AnyTop]", " ".join(cmd))
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=env, check=True)


def _ensure_repo() -> Path:
    if ANYTOP_ROOT.is_dir() and (ANYTOP_ROOT / "sample" / "generate.py").is_file():
        return ANYTOP_ROOT
    ANYTOP_ROOT.parent.mkdir(parents=True, exist_ok=True)
    if ANYTOP_ROOT.exists():
        shutil.rmtree(ANYTOP_ROOT)
    _run(["git", "clone", "--branch", DEFAULT_BRANCH, "--depth", "1", DEFAULT_REPO, str(ANYTOP_ROOT)])
    return ANYTOP_ROOT


def _ensure_venv(repo: Path) -> Path:
    py = _venv_python()
    if not py.is_file():
        print("[ComfyUI-AnyTop] Creating venv at", VENV_DIR)
        venv.EnvBuilder(with_pip=True).create(str(VENV_DIR))
        _run([str(py), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
        # Minimal deps; full CUDA stack is the user's responsibility via torch index.
        req = repo / "environment.yaml"
        _run(
            [
                str(py),
                "-m",
                "pip",
                "install",
                "torch",
                "numpy",
                "scipy",
                "tqdm",
                "blobfile",
                "PyYAML",
                "matplotlib",
                "imageio",
                "imageio-ffmpeg",
                "transformers",
                "sentencepiece",
            ]
        )
        # Motion / BVH helpers used by AnyTop
        _run([str(py), "-m", "pip", "install", "--no-build-isolation", "git+https://github.com/inbar-2344/Motion.git"])
    return py


def _find_model_checkpoint(repo: Path, subset: str) -> Path:
    save = repo / "save"
    if not save.is_dir():
        raise FileNotFoundError(
            f"No AnyTop save/ under {repo}. Run AnyTop Setup (downloads checkpoints)."
        )
    # Prefer directories whose name starts with the subset prefix used in AnyTop README.
    candidates: list[Path] = []
    for d in sorted(save.iterdir()):
        if not d.is_dir():
            continue
        name = d.name.lower()
        if subset == "all" and name.startswith("all_"):
            candidates.extend(d.glob("model*.pt"))
        elif subset != "all" and subset.replace("quadropeds", "quad").split("_")[0] in name:
            candidates.extend(d.glob("model*.pt"))
        elif subset in name:
            candidates.extend(d.glob("model*.pt"))
    if not candidates:
        # Fallback: any model*.pt
        candidates = sorted(save.glob("**/model*.pt"))
    if not candidates:
        raise FileNotFoundError(
            f"No model*.pt under {save}. Run AnyTop Setup / utils.download_dependencies."
        )
    # Prefer highest iteration number
    def _iter_num(p: Path) -> int:
        digits = "".join(ch for ch in p.stem if ch.isdigit())
        return int(digits) if digits else 0

    return max(candidates, key=_iter_num)


class AnyTopSetup:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "download_models": ("BOOLEAN", {"default": True}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("status",)
    FUNCTION = "run"
    CATEGORY = "AnyTop"
    OUTPUT_NODE = True

    def run(self, download_models: bool = True):
        repo = _ensure_repo()
        py = _ensure_venv(repo)
        status = [f"repo={repo}", f"python={py}"]
        if download_models:
            # AnyTop's own downloader (weights + cond.npy deps)
            env = os.environ.copy()
            env["PYTHONPATH"] = str(repo) + os.pathsep + env.get("PYTHONPATH", "")
            try:
                _run([str(py), "-m", "utils.download_dependencies"], cwd=repo, env=env)
                status.append("download_dependencies=ok")
            except subprocess.CalledProcessError as exc:
                status.append(
                    f"download_dependencies failed ({exc}); place model*.pt under {repo/'save'} manually"
                )
        text = "\n".join(status)
        print("[ComfyUI-AnyTop]", text)
        return {"ui": {"text": [text]}, "result": (text,)}


class AnyTopGenerate:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": "a dog trots forward happily"}),
                "model_subset": (MODEL_SUBSETS, {"default": "quadropeds"}),
                "object_type": ("STRING", {"default": "Dog"}),
                "motion_length": ("FLOAT", {"default": 4.0, "min": 1.0, "max": 9.8, "step": 0.1}),
                "seed": ("INT", {"default": 42, "min": 0, "max": 0x7FFFFFFF}),
                "num_repetitions": ("INT", {"default": 1, "min": 1, "max": 8}),
                "device": ("STRING", {"default": "cuda:0"}),
            },
            "optional": {
                "model_path": ("STRING", {"default": ""}),
                "cond_path": ("STRING", {"default": ""}),
                "output_subdir": ("STRING", {"default": "anytop"}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("bvh_path", "output_dir")
    FUNCTION = "run"
    CATEGORY = "AnyTop"

    def run(
        self,
        prompt: str,
        model_subset: str,
        object_type: str,
        motion_length: float = 4.0,
        seed: int = 42,
        num_repetitions: int = 1,
        device: str = "cuda:0",
        model_path: str = "",
        cond_path: str = "",
        output_subdir: str = "anytop",
    ):
        # prompt is accepted for workflow UX / future text conditioning;
        # stock AnyTop generate is object_type-conditioned (T5 on joint names),
        # not free-form HML text. We still write the prompt next to outputs.
        _ = prompt
        repo = _ensure_repo()
        py = _ensure_venv(repo)
        ckpt = Path(model_path) if model_path.strip() else _find_model_checkpoint(repo, model_subset)
        if not ckpt.is_file():
            raise FileNotFoundError(f"AnyTop checkpoint not found: {ckpt}")

        out_base = Path(folder_paths.get_output_directory()) / output_subdir
        out_base.mkdir(parents=True, exist_ok=True)
        (out_base / "prompt.txt").write_text(prompt.strip() + "\n", encoding="utf-8")

        env = os.environ.copy()
        env["PYTHONPATH"] = str(repo) + os.pathsep + env.get("PYTHONPATH", "")

        cmd = [
            str(py),
            "-m",
            "sample.generate",
            "--model_path",
            str(ckpt),
            "--object_type",
            object_type.strip(),
            "--num_repetitions",
            str(num_repetitions),
            "--motion_length",
            str(motion_length),
            "--seed",
            str(seed),
            "--device",
            device,
            "--output_dir",
            str(out_base),
        ]
        if cond_path.strip():
            cmd.extend(["--cond_path", cond_path.strip()])

        _run(cmd, cwd=repo, env=env)

        bvhs = sorted(out_base.glob("*.bvh"), key=lambda p: p.stat().st_mtime)
        if not bvhs:
            raise RuntimeError(
                f"AnyTop finished but no .bvh under {out_base}. "
                "Check the AnyTop log / IK step; npy/mp4 may still be present."
            )
        bvh_path = str(bvhs[-1].resolve())
        meta = {"bvh_path": bvh_path, "model": str(ckpt), "object_type": object_type, "prompt": prompt}
        (out_base / "last_run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return (bvh_path, str(out_base.resolve()))


NODE_CLASS_MAPPINGS = {
    "AnyTopSetup": AnyTopSetup,
    "AnyTopGenerate": AnyTopGenerate,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "AnyTopSetup": "AnyTop Setup",
    "AnyTopGenerate": "AnyTop Generate",
}
