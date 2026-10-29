"""Proposed full-set archive admission and private rootfs writer. CLI sealed.

No tar extraction API, package manager, ownership restore, hook or chroot is used.
Planner tests operate on in-memory TarInfo objects; assembly is never tested/run
as part of S4 source preparation.
"""
import hashlib
import os
from pathlib import Path
import stat
import tarfile

from common import FdPath, LOCK_SHA256, MIB, new_private, require

METADATA = {".PKGINFO", ".BUILDINFO", ".MTREE", ".INSTALL", ".CHANGELOG"}
RESERVED = {"inputs", "runtime", "out", "private"}
EMPTY_MOUNTPOINTS = {"dev", "proc", "sys", "run", "tmp"}
MAX_MEMBERS = 100000
MAX_FILE = 512*MIB
MAX_EXPANDED = 2*1024*MIB


def safe_text(value):
    require(isinstance(value,str) and 0 < len(value) <= 4096 and
            all(32 <= ord(c) < 127 for c in value) and "\\" not in value,
            "unsafe archive text")
    return value


def canonical(name, directory=False):
    safe_text(name)
    require(not name.startswith("/"), "absolute archive path")
    if name.startswith("./"):
        name=name[2:]
    if directory and name.endswith("/"):
        name=name[:-1]
    if directory and name in ("", "."):
        return ""
    parts=name.split("/")
    require(len(parts) <= 128 and all(p not in ("", ".", "..") for p in parts), "archive path alias/traversal")
    require(parts[0] not in RESERVED, "reserved harness path")
    require(parts[0] not in EMPTY_MOUNTPOINTS or (directory and len(parts)==1), "nonempty runtime mountpoint")
    require(not parts[0].startswith(".") or (len(parts)==1 and name in METADATA), "unexpected root metadata")
    return name


def inspect_tar(path):
    members=[]
    with tarfile.open(path,mode="r:") as archive:
        for member in archive:
            members.append(member)
            require(len(members) <= MAX_MEMBERS, "archive member budget")
    plan_members({"package":members})
    return members


def resolved_link(name, target, entries):
    safe_text(target)
    require(not target.startswith("/"), "absolute symlink target")
    pending=name.split("/")[:-1]+target.split("/")
    result,seen=[],set()
    hops=0
    while pending:
        part=pending.pop(0)
        if part in ("", "."):
            continue
        if part=="..":
            require(result, "symlink escapes root")
            result.pop()
            continue
        result.append(part)
        path="/".join(result)
        item=entries.get(path)
        if item and item["kind"]=="symlink":
            require(path not in seen, "symlink cycle")
            seen.add(path)
            hops+=1
            require(hops<=40, "symlink hop budget")
            nested=safe_text(item["link"])
            require(not nested.startswith("/"), "absolute symlink target")
            result.pop()
            pending=nested.split("/")+pending
        elif item and pending:
            require(item["kind"]=="directory", "symlink traverses regular file")
        require(len(result)+len(pending)<=256, "symlink depth budget")
    require(result and result[0] not in RESERVED|EMPTY_MOUNTPOINTS and "/".join(result) not in METADATA,
            "symlink target outside package namespace")
    return "/".join(result)


def plan_members(packages):
    """Validate ALL members across ALL packages before writing any rootfs byte."""
    entries,locals_by_package={},{}
    total_members=0
    for package,members in packages.items():
        local={}
        for member in members:
            total_members+=1
            require(total_members<=MAX_MEMBERS, "set member budget")
            require(not member.sparse and not any("sparse" in k.lower() for k in member.pax_headers), "sparse archive member")
            require(set(member.pax_headers) <= {"path","linkpath","mtime","atime","ctime"}, "unreviewed extended archive metadata")
            require(member.isdir() or member.isfile() or member.issym() or member.islnk(), "special archive member")
            require(type(member.size) is int and 0<=member.size<=MAX_FILE, "member size budget")
            require(member.isfile() or member.size==0, "nonregular member carries data")
            name=canonical(member.name,member.isdir())
            require(name not in local, "duplicate/aliased archive path")
            local[name]=member
            if not name or name in METADATA:
                require(member.isdir() if not name else member.isfile(), "invalid package metadata type")
                require(not name or member.size<=4*MIB, "package metadata budget")
                continue
            kind="directory" if member.isdir() else "symlink" if member.issym() else "copy" if member.islnk() else "regular"
            item=dict(package=package,member=member.name,kind=kind,size=member.size,
                      mode=0o555 if member.mode & 0o111 else 0o444,link=member.linkname)
            if name in entries:
                require(kind==entries[name]["kind"]=="directory", "cross-package file collision: "+name)
            else:
                entries[name]=item
        locals_by_package[package]=local
    for name,item in list(entries.items()):
        parent=name.rpartition("/")[0]
        while parent:
            require(parent not in entries or entries[parent]["kind"]=="directory", "nondirectory write parent")
            entries.setdefault(parent,dict(kind="directory",mode=0o555,size=0,package=None))
            parent=parent.rpartition("/")[0]
        if item["kind"]=="copy":
            target=canonical(item["link"])
            require(target not in METADATA, "hardlink to package metadata")
            linked=locals_by_package[item["package"]].get(target)
            require(linked is not None and linked.isfile() and not linked.sparse, "hardlink must target same-archive direct regular file")
            require(target in entries and entries[target]["kind"]=="regular" and
                    entries[target]["package"]==item["package"], "hardlink target substitution")
            item.update(member=linked.name,size=linked.size,mode=0o555 if linked.mode&0o111 else 0o444)
    for name,item in entries.items():
        if item["kind"]=="symlink":
            item["resolved_target"]=resolved_link(name,item["link"],entries)
    expanded=sum(item["size"] for item in entries.values())
    require(expanded<=MAX_EXPANDED and len(entries)<=MAX_MEMBERS, "rootfs expansion budget")
    return dict(schema_version=1,lock_sha256=LOCK_SHA256,entries=entries,expanded_bytes=expanded,
                file_count=len(entries),hardlinks_materialized_as_copies=True)


def parent_fd(root_fd,name):
    directory=os.dup(root_fd)
    try:
        for part in name.split("/")[:-1]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory)
            os.close(directory)
            directory=child
        return directory
    except BaseException:
        os.close(directory)
        raise


def write_root(root_fd,plan,bundles):
    """Private writer, called only after authentication and complete admission.

    Caller owns a new empty root, no concurrent actors; future VM confinement
    must isolate this process. Every component is still opened without links.
    """
    entries=plan["entries"]
    directories=sorted((n for n,e in entries.items() if e["kind"]=="directory"),key=lambda n:(n.count("/"),n))
    for name in directories:
        parent=parent_fd(root_fd,name)
        try:
            os.mkdir(name.split("/")[-1],0o700,dir_fd=parent)
        finally:
            os.close(parent)
    manifest={}
    for package,bundle in bundles.items():
        with tarfile.open(bundle["path"],mode="r:") as archive:
            by_name={m.name:m for m in bundle["members"]}
            for name,item in sorted(entries.items()):
                if item.get("package")!=package or item["kind"] not in ("regular","copy"):
                    continue
                member=by_name[item["member"]]
                require(member.isfile() and member.size==item["size"], "admitted member drift")
                parent=parent_fd(root_fd,name)
                try:
                    fd=os.open(name.split("/")[-1],os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent)
                finally:
                    os.close(parent)
                digest,count=hashlib.sha256(),0
                with os.fdopen(fd,"wb") as output,archive.extractfile(member) as source:
                    while block:=source.read(min(MIB,item["size"]-count+1)):
                        count+=len(block)
                        require(count<=item["size"], "member grew beyond admitted size")
                        digest.update(block)
                        output.write(block)
                    require(count==item["size"], "truncated member")
                    output.flush()
                    os.fchmod(output.fileno(),item["mode"])
                    require(os.fstat(output.fileno()).st_nlink==1, "unexpected shared inode")
                    os.fsync(output.fileno())
                manifest[name]=dict(kind="regular",bytes=count,sha256=digest.hexdigest(),mode=item["mode"],package=package)
    # No archive write follows link creation. Parents are always real directories.
    for name,item in sorted(entries.items()):
        if item["kind"]=="symlink":
            parent=parent_fd(root_fd,name)
            try:
                os.symlink(item["link"],name.split("/")[-1],dir_fd=parent)
            finally:
                os.close(parent)
            manifest[name]=dict(kind="symlink",target=item["link"],package=item["package"])
    for name in reversed(directories):
        parent=parent_fd(root_fd,name)
        try:
            fd=os.open(name.split("/")[-1],os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
            try:
                os.fchmod(fd,0o555)
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            os.close(parent)
        manifest[name]=dict(kind="directory",mode=0o555)
    os.fchmod(root_fd,0o555)
    os.fsync(root_fd)
    return manifest


def assemble(destination,lock_path,policy_path,keyring_path,cache,tool_paths):
    """PROPOSED future VM API. Not called in source-only tests or any workflow.

    A newly created destination is an incomplete workspace until success receipt
    is written. Failure leaves no success receipt; never resume or reuse it.
    The containing mode-0700 directory must be privately owned, not shared.
    """
    from authenticate import authenticate_set,check_policy
    from common import read_bounded,read_json
    check_policy(read_json(read_bounded(policy_path,MIB)))
    require(all(os.environ.get(k)==v for k,v in {"GITHUB_ACTIONS":"true",
                "RUNNER_ENVIRONMENT":"github-hosted","ImageOS":"ubuntu24"}.items()), "future hosted VM context required")
    with new_private(destination) as workspace:
        disk=os.fstatvfs(workspace.fd)
        require(disk.f_bavail*disk.f_frsize>=6*1024*MIB,"at least 6 GiB free staging space required")
        (workspace/"authentication-spool").mkdir(mode=0o700)
        spool_fd=os.open("authentication-spool",os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=workspace.fd)
        with FdPath(spool_fd) as spool:
            bundles,authentication=authenticate_set(lock_path,policy_path,keyring_path,cache,tool_paths,spool)
            plan=plan_members({name:b["members"] for name,b in bundles.items()})
            require(authentication["spool_bytes"]+plan["expanded_bytes"]+64*MIB<=4*1024*MIB,
                    "combined spool/rootfs staging budget")
            # No rootfs directory exists until every payload and path is admitted.
            os.mkdir("rootfs",0o700,dir_fd=workspace.fd)
            root=os.open("rootfs",os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=workspace.fd)
            try:
                manifest=write_root(root,plan,bundles)
            finally:
                os.close(root)
        receipt=dict(schema_version=1,status="assembled-not-built",authentication=authentication,
                     manifest=manifest,expanded_bytes=plan["expanded_bytes"],native_worker_executed=False)
        import json
        fd=os.open("assembly-receipt.json",os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400,dir_fd=workspace.fd)
        with os.fdopen(fd,"w") as output:
            json.dump(receipt,output,indent=2,sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.fsync(workspace.fd)
        return receipt


if __name__=="__main__":
    raise SystemExit("S4 assembler CLI is sealed; source review and separate VM authorization required")
