"""Data-only stage design and export validation. Actual export remains sealed."""
import argparse
import json
from pathlib import Path

from common import LOCK_SHA256, MIB, read_bounded, read_json, require, sha256

CANDIDATE_SHA256="75676ac34f92b96a77cc083cc62d478a63fdcf19d8ac67fb5463556aad83a555"
SOURCE_SHA256="4f111953afaea866dd6b0967a8271f79750b4926a71eba94b32ac7d59ed28b64"
EXPORT_LIMITS={"stdout.txt":MIB,"stderr.txt":MIB,"authentication.json":MIB,
               "assembly-receipt.json":4*MIB,"build-receipt.json":MIB,
               "stage-plan.json":4*MIB,"failure.json":MIB}


def stage_plan(root):
    base=root/"tests/native/external_vm"
    raw=read_bounded(base/"candidate.json",MIB)
    require(sha256(raw)==CANDIDATE_SHA256, "single-frame contract changed")
    require(sha256(read_bounded(base/"packages.lock.json",4*MIB))==LOCK_SHA256,"package lock changed")
    require(sha256(read_bounded(base/"single_frame_candidate.cpp",MIB))==SOURCE_SHA256,"candidate seal/source changed")
    candidate=read_json(raw)
    for row in candidate["inputs"]+candidate["preserved_sources"]:
        data=read_bounded(root/row["source"],4*MIB)
        require(len(data)==row["bytes"] and sha256(data)==row["sha256"],"preserved input drift")
    return dict(schema_version=1,status="source-design-only",execution_enabled=False,capture_enabled=False,
        frame_count=1,candidate_id=candidate["candidate_id"],candidate_sha256=CANDIDATE_SHA256,
        lock_sha256=LOCK_SHA256,candidate_source_sha256=SOURCE_SHA256,
        stages=[
            dict(phase="preparation",inputs=["reviewed-trust-policy","public-keyring","158-offline-payloads"],
                 work=["authenticate every locked hash/signature","match signed PKGINFO","recompute dependency closure",
                       "admit complete archive graph","assemble new private rootfs without scriptlets"],
                 outputs=["authentication.json","assembly-receipt.json"],
                 native_execution=False,network=False),
            dict(phase="build",requires=["authenticated closure","rootfs manifest revalidation","read-only rootfs",
                 "no-network namespace","private build/output/home","whole-process limits"],
                 command_design=["run locked /usr/bin/pkgconf --cflags --libs Qt6Gui inside the rootfs",
                   "pass its validated flags as argv to locked /usr/bin/c++",
                   "compile the unchanged sealed single_frame_candidate.cpp with -lKF6Svg",
                   "record ELF/build-id/NEEDED/interpreter via a reviewed nonexecuting ELF reader"],
                 outputs=["sealed ELF","build-receipt.json"],candidate_execution=False),
            dict(phase="capture",status="blocked-source-seal",requires=["separate source review and execution authorization",
                 "pre-main confinement","hashed runtime plugin/font/loader/library inputs","loaded mappings collector",
                 "whole-process kill/reap and bounded failure handling"],
                 logical_size=[288,88],device_pixel_ratio=1,renderer="KSvg::FrameSvg",native_execution=False),
            dict(phase="evidence-export",status="blocked-producer-lifecycle",execution_enabled=False,requires=["stage process tree reaped","no more producer writes"],
                 inputs=list(EXPORT_LIMITS),outputs=["allowlisted regular files","inventory.json"],
                 executes_producers=False,captured_status_supported=False)],
        build_flags=["-std=c++20","-fPIC","-O2","-Wall","-Wextra","-Wpedantic","-Werror",
                     "-I/usr/include/KF6/KSvg","-Wl,--build-id=sha1","-Wl,-z,relro,-z,now,-z,noexecstack"],
        limits=dict(free_disk_before_bytes=6*1024*MIB,archive_bytes=512*MIB,rootfs_bytes=2*1024*MIB,
                    staging_bytes=4*1024*MIB,build_cpu_count=1,build_cpu_seconds=120,build_wall_seconds=180,
                    build_memory_bytes=2*1024*MIB,capture_cpu_count=1,capture_cpu_seconds=30,
                    capture_wall_seconds=60,capture_memory_bytes=1024*MIB,pids=64,nofile=64,
                    export_bytes=16*MIB,log_stream_bytes=MIB),
        runtime_environment=dict(HOME="/private/home",XDG_CONFIG_HOME="/private/config",
            XDG_CACHE_HOME="/private/cache",XDG_DATA_HOME="/inputs/data",XDG_DATA_DIRS="/inputs/data",
            XDG_RUNTIME_DIR="/private/run",FONTCONFIG_FILE="/inputs/fonts.conf",
            QT_QPA_PLATFORM="offscreen",QT_PLUGIN_PATH="/runtime/plugins",QT_SCALE_FACTOR="1",
            QT_AUTO_SCREEN_SCALE_FACTOR="0",LANG="C.UTF-8",LC_ALL="C.UTF-8",TZ="UTC"))


def require_stage(phase,receipts):
    """Design assertions, not a security boundary or a runnable dispatcher."""
    if phase=="capture":
        raise ValueError("capture remains sealed; no policy or receipt enables it")
    if phase=="evidence-export":
        raise ValueError("export remains sealed; producer lifecycle boundary is not implemented")
    required={"preparation":(),"build":("authentication","assembly","rootfs_readonly",
               "network_denied","private_home","toolchain_manifest")}
    require(phase in required,"unknown stage")
    require(all(receipts.get(key) is True for key in required[phase]),"missing stage prerequisite")


def check_export_manifest(files,status):
    require(status in {"prepared","assembled-not-built","built-not-captured","failed-setup",
                       "failed-build"},"capture success export remains sealed")
    require(files and set(files)<=set(EXPORT_LIMITS),"unknown export filename")
    total=0
    for name,row in files.items():
        require(set(row)=={"kind","bytes","sha256"} and row["kind"]=="regular","regular export file required")
        require(type(row["bytes"]) is int and 0<=row["bytes"]<=EXPORT_LIMITS[name],"export file budget")
        import re
        require(isinstance(row["sha256"],str) and re.fullmatch(r"[0-9a-f]{64}",row["sha256"]),"export digest required")
        total+=row["bytes"]
    require(total<=16*MIB,"total export budget")


def export_evidence(source,destination,files,status):
    """Refuse all exports until a reviewed producer lifecycle boundary exists.

    A manifest or caller-supplied reap receipt cannot prove that the producer
    process tree is gone and its files cannot still be written. The future
    supervisor must enforce that boundary before copying or creating output.
    check_export_manifest() validates data only; it grants no export authority.
    """
    raise ValueError("export remains sealed; producer lifecycle boundary is not implemented")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan",action="store_true",required=True)
    parser.parse_args()
    root=Path(__file__).resolve().parents[4]
    print(json.dumps(stage_plan(root),indent=2,sort_keys=True))


if __name__=="__main__":
    main()
