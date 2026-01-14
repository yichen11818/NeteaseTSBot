from __future__ import annotations

from pathlib import Path


def ensure_voice_stubs() -> None:
    package_dir = Path(__file__).resolve().parent
    repo_root = package_dir.parent
    proto_file = repo_root / "proto" / "voice.proto"

    out_dir = package_dir / "_generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    init_file = out_dir / "__init__.py"
    if not init_file.exists():
        init_file.touch()

    pb2 = out_dir / "voice_pb2.py"
    pb2_grpc = out_dir / "voice_pb2_grpc.py"

    if pb2.exists() and pb2_grpc.exists() and pb2.stat().st_mtime >= proto_file.stat().st_mtime:
        return

    from grpc_tools import protoc  # type: ignore
    import grpc_tools

    grpc_tools_proto = str(Path(grpc_tools.__file__).resolve().parent / "_proto")

    args = [
        "protoc",
        f"-I{repo_root / 'proto'}",
        f"-I{grpc_tools_proto}",
        f"--python_out={out_dir}",
        f"--grpc_python_out={out_dir}",
        str(proto_file),
    ]

    rc = protoc.main(args)
    if rc != 0:
        raise RuntimeError(f"grpc stub generation failed with code {rc}")
