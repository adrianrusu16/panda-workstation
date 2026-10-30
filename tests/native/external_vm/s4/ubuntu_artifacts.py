"""Bounded data-only Debian member and ELF readers. Never loads candidate code."""
import io
import lzma
from pathlib import PurePosixPath
import re
import struct
import tarfile
import zlib

from common import MIB, require, sha256

MAX_PACKAGE = 32 * MIB
MAX_EXPANSION = 64 * MIB
MAX_MEMBERS = 20000
MAX_ELF = 32 * MIB
MAX_TOTAL_EXPANSION = 256 * MIB
LIB_DIRS = ("/lib/x86_64-linux-gnu", "/usr/lib/x86_64-linux-gnu", "/lib64", "/usr/lib64")


def normalize(path):
    require(type(path) is str and path.startswith("/") and len(path) <= 4096 and
            not re.search(r"[\x00-\x20\x7f]", path), "archive path identity")
    stack = []
    for part in path.split("/"):
        if part in ("", "."): continue
        if part == "..":
            require(stack, "archive path escape")
            stack.pop()
        else: stack.append(part)
    return "/" + "/".join(stack)


def resolve_path(nodes, path):
    require(type(path) is str and path.startswith("/") and len(path) <= 4096 and
            not re.search(r"[\x00-\x20\x7f]", path), "archive path identity")
    pending, stack, seen, links = path.split("/")[1:], [], set(), []
    # Parent components are interpreted after preceding symlinks, as by the loader.
    for _ in range(8192):
        state = (tuple(stack), tuple(pending))
        require(state not in seen, "archive link cycle")
        seen.add(state)
        if not pending: break
        part, pending = pending[0], pending[1:]
        if part in ("", "."): continue
        if part == "..":
            require(stack, "archive path escape")
            stack.pop(); continue
        prefix = "/" + "/".join(stack + [part])
        node = nodes.get(prefix)
        if node is None or node["kind"] == "directory":
            stack.append(part); continue
        if node["kind"] == "file":
            require(not pending, "archive non-directory ancestor")
            return prefix, links
        require(node["kind"] in ("symlink", "hardlink"), "archive link type")
        target = node["target"]
        require(type(target) is str and 0 < len(target) <= 4096 and
                not re.search(r"[\x00-\x20\x7f]", target), "archive link target")
        require(len(links) < 64, "archive link depth budget")
        links.append(prefix)
        if target.startswith("/") or node["kind"] == "hardlink": stack = []
        pending = target.split("/") + pending
        require(sum(map(len, pending)) + len(pending) <= 8192, "archive link path budget")
    else: raise ValueError("archive path traversal budget")
    raise ValueError("archive dependency missing: /" + "/".join(stack))


def expand(name, raw, inflate):
    if name.endswith(".xz"):
        decoder = lzma.LZMADecompressor(memlimit=64 * MIB)
        data = decoder.decompress(raw, max_length=MAX_EXPANSION + 1)
        require(decoder.eof and not decoder.unused_data, "archive xz framing/budget")
    elif name.endswith(".gz"):
        decoder = zlib.decompressobj(31)
        data = decoder.decompress(raw, MAX_EXPANSION + 1)
        require(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail, "archive gzip framing/budget")
    elif name.endswith(".zst"):
        require(callable(inflate), "preinstalled bounded zstd adapter required")
        data = inflate(raw, MAX_EXPANSION)
    else:
        require(name.endswith(".tar"), "archive compression identity")
        data = raw
    require(type(data) is bytes and len(data) <= MAX_EXPANSION, "archive expansion budget")
    return data


def package_members(raw, package, wanted, inflate, *, budget=None):
    require(type(raw) is bytes and 8 <= len(raw) <= MAX_PACKAGE and raw[:8] == b"!<arch>\n", "Debian ar identity/budget")
    ar, pos = {}, 8
    while pos < len(raw):
        header = raw[pos:pos+60]
        require(len(header) == 60 and header[58:] == b"`\n", "Debian ar header")
        name = header[:16].decode("ascii").strip().removesuffix("/")
        count = header[48:58].strip()
        require(count.isdigit() and name not in ar and len(ar) < 3, "Debian ar member identity")
        size = int(count); pos += 60
        require(pos+size <= len(raw), "Debian ar truncated member")
        ar[name] = raw[pos:pos+size]; pos += size
        if size % 2:
            require(raw[pos:pos+1] == b"\n", "Debian ar padding")
            pos += 1
    require(pos == len(raw) and ar.get("debian-binary") == b"2.0\n" and len(ar) == 3, "Debian member set")
    nodes, contents, control = {}, {}, None
    if budget is None: budget = [0]
    total_members = 0
    for kind in ("control", "data"):
        names = [name for name in ar if re.fullmatch(kind + r"\.tar(?:\.xz|\.gz|\.zst)?", name)]
        require(len(names) == 1, "Debian archive identity")
        data = expand(names[0], ar[names[0]], inflate)
        budget[0] += len(data)
        require(budget[0] <= MAX_TOTAL_EXPANSION, "aggregate Debian expansion budget")
        archive = tarfile.open(fileobj=io.BytesIO(data), mode="r:", errorlevel=2)
        seen = set()
        for member in archive:
            total_members += 1
            require(total_members <= MAX_MEMBERS, "archive member count budget")
            name = member.name.removeprefix("./")
            require(not name.startswith("/") and ".." not in PurePosixPath(name).parts, "archive member path")
            path = normalize("/"+name)
            require(path not in seen, "duplicate archive member")
            seen.add(path)
            require(not member.issparse() and not member.pax_headers and
                    (member.isdir() or not member.mode & 0o7000), "archive sparse/pax/privileged metadata")
            require(member.isdir() or member.isfile() or member.issym() or member.islnk(), "archive special member")
            if kind == "control":
                if path == "/control":
                    require(member.isfile() and member.size <= MIB, "Debian control type/budget")
                    control = archive.extractfile(member).read()
                continue  # Never retain or execute scriptlets.
            node = dict(kind="directory" if member.isdir() else "file" if member.isfile() else
                        "symlink" if member.issym() else "hardlink", package=package)
            if member.isfile():
                require(0 <= member.size <= MAX_ELF, "archive member byte budget")
                content = archive.extractfile(member).read(MAX_ELF + 1)
                require(len(content) == member.size, "archive member truncation")
                node.update(sha256=sha256(content), bytes=len(content))
                if path in wanted: contents[path] = content
            elif not member.isdir():
                node["target"] = member.linkname
                normalize(("/" if member.islnk() else str(PurePosixPath(path).parent)+"/") +
                          member.linkname if not member.linkname.startswith("/") else member.linkname)
            nodes[path] = node
        archive.close()
    require(control is not None, "Debian control missing")
    text = control.decode("utf-8")
    require(not re.search(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u2028\u2029]", text), "Debian control character")
    values, current = {}, None
    for line in text.rstrip("\n").split("\n"):
        if line.startswith((" ", "\t")):
            require(current is not None and current not in ("package", "version", "architecture"), "Debian control continuation")
            values[current].append(line)
            continue
        key, sep, value = line.partition(":")
        require(sep and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*", key), "Debian control field")
        current = key.lower()
        require(current not in values, "duplicate Debian control field")
        values[current] = [value.lstrip(" \t")]
    values = {key: "\n".join(parts) for key, parts in values.items()}
    require(values.get("package") == package and all(values.get(k) for k in ("version", "architecture")), "Debian control identity")
    return values, nodes, contents


def elf_info(raw):
    require(type(raw) is bytes and 64 <= len(raw) <= MAX_ELF and raw[:7] == b"\x7fELF\x02\x01\x01", "ELF class/encoding/budget")
    def unpack(fmt, offset):
        size = struct.calcsize(fmt)
        require(type(offset) is int and 0 <= offset <= len(raw)-size, "ELF offset bounds")
        return struct.unpack_from(fmt, raw, offset)
    header = unpack("<HHIQQQIHHHHHH", 16)
    kind, machine, version, _, phoff, _, _, ehsize, entsize, count, *_ = header
    require(kind in (2, 3) and machine == 62 and version == 1 and ehsize == 64 and
            entsize == 56 and 0 < count <= 64, "ELF architecture/program budget")
    segments = [unpack("<IIQQQQQQ", phoff+i*56) for i in range(count)]
    for typ, flags, offset, va, _, size, mem, align in segments:
        require(offset+size <= len(raw) and size <= mem, "ELF segment bounds")
        require(typ not in (0x6ffffefa, 0x6ffffefb), "ELF unsupported segment")
    def at(va):
        offsets = [off+va-start for typ, _, off, start, _, size, _, _ in segments
                   if typ == 1 and start <= va < start+size]
        require(len(offsets) == 1, "ELF virtual address ambiguity")
        return offsets[0]
    interpreters, dynamics, build_ids = [], [], []
    for typ, _, offset, va, _, size, _, _ in segments:
        if typ == 3:
            require(2 <= size <= 4096 and raw[offset+size-1] == 0, "ELF interpreter string")
            interpreter = raw[offset:offset+size-1].decode("ascii")
            require(normalize(interpreter) == interpreter, "ELF interpreter path")
            interpreters.append(interpreter)
        elif typ == 2:
            require(size % 16 == 0 and size <= 16384, "ELF dynamic budget")
            table = []; terminated = False
            for pos in range(offset, offset+size, 16):
                tag, value = unpack("<qQ", pos)
                if tag == 0: terminated = True; break
                table.append((tag, value))
            require(terminated, "ELF dynamic termination")
            dynamics.append(table)
        elif typ == 4:
            pos = offset
            while pos < offset+size:
                names, descs, tag = unpack("<III", pos); pos += 12
                require(pos+((names+3)&~3)+((descs+3)&~3) <= offset+size, "ELF note bounds")
                name = raw[pos:pos+names]; pos += (names+3)&~3
                desc = raw[pos:pos+descs]; pos += (descs+3)&~3
                if name == b"GNU\0" and tag == 3: build_ids.append(desc.hex())
    require(len(interpreters) <= 1 and len(dynamics) == 1, "ELF interpreter/dynamic ambiguity")
    tags = {}
    for tag, value in dynamics[0]: tags.setdefault(tag, []).append(value)
    for tag in (5, 10, 14, 0x6ffffffe, 0x6fffffff, 0x6ffffffc, 0x6ffffffd, 0x6ffffffb):
        require(len(tags.get(tag, [])) <= 1, "ELF duplicate singleton tag")
    require(5 in tags and 10 in tags and all(t not in tags for t in (15, 29, 0x6ffffefb, 0x6ffffefc, 0x7fffffff, 0x7ffffffd)), "ELF loader configuration")
    require(not any(value & 0x800 for value in tags.get(0x6ffffffb, [])), "ELF NODEFLIB search override")
    start, size = at(tags[5][0]), tags[10][0]
    require(0 < size <= MIB and start+size <= len(raw), "ELF string table bounds")
    def string(offset):
        require(0 <= offset < size, "ELF string offset")
        end = raw.find(b"\0", start+offset, start+size)
        require(end >= start+offset and end-(start+offset) <= 4096, "ELF string termination/budget")
        value = raw[start+offset:end].decode("ascii")
        require(value and not re.search(r"[\x00-\x20\x7f]", value), "ELF string identity")
        return value
    needed = [string(value) for value in tags.get(1, [])]
    require(len(needed) <= 64 and len(set(needed)) == len(needed) and all("/" not in value for value in needed), "ELF dependency identity/budget")
    required, provided = {}, []
    for address_tag, count_tag, required_table in ((0x6ffffffe, 0x6fffffff, True), (0x6ffffffc, 0x6ffffffd, False)):
        require((address_tag in tags) == (count_tag in tags), "ELF version table incomplete")
        if address_tag not in tags: continue
        count = tags[count_tag][0]
        require(0 < count <= 128, "ELF version count budget")
        pos, seen = at(tags[address_tag][0]), set()
        for index in range(count):
            require(pos not in seen, "ELF version chain cycle")
            seen.add(pos)
            if required_table:
                version, aux_count, provider, aux, nxt = unpack("<HHIII", pos)
                provider = string(provider)
                require(version == 1 and provider in needed and provider not in required and 0 < aux_count <= 128, "ELF required version identity")
                values, cursor, aux_seen = [], pos+aux, set()
                for i in range(aux_count):
                    require(cursor not in aux_seen, "ELF auxiliary version cycle")
                    aux_seen.add(cursor)
                    _, _, _, name, following = unpack("<IHHII", cursor)
                    values.append(string(name))
                    require((following == 0) == (i == aux_count-1), "ELF auxiliary version termination")
                    cursor += following
                required[provider] = sorted(set(values))
            else:
                version, _, _, aux_count, _, aux, nxt = unpack("<HHHHIII", pos)
                require(version == 1 and 0 < aux_count <= 128, "ELF provided version identity")
                name, _ = unpack("<II", pos+aux)
                provided.append(string(name))
            require((nxt == 0) == (index == count-1), "ELF version termination")
            pos += nxt
    return dict(machine=62, bits=64, interpreter=interpreters[0] if interpreters else None,
                needed=needed, soname=string(tags[14][0]) if 14 in tags else None,
                build_ids=sorted(build_ids), required_versions=required, provided_versions=sorted(set(provided)))


def runtime_closure(nodes, contents, references, links, tools):
    require(len(references) == 13 and set(contents) == set(references) and len(tools) == 3, "runtime complete 13-ELF set")
    for path, expected in links.items():
        require(path in nodes and all(nodes[path].get(k) == expected[k] for k in ("kind", "target", "package")), "runtime link membership")
    files = {}
    for path, expected in sorted(references.items()):
        require(path in nodes and nodes[path]["kind"] == "file" and
                nodes[path]["package"] == expected["package"] and
                sha256(contents[path]) == expected["sha256"] and len(contents[path]) == expected["bytes"], "runtime package/file membership")
        info = elf_info(contents[path])
        require(info["needed"] == expected["needed"] and info["interpreter"] == expected["interpreter"], "runtime ELF reference mismatch")
        files[path] = dict(package=expected["package"], sha256=sha256(contents[path]), bytes=len(contents[path]), elf=info)
    return runtime_graph(files, links, tools, nodes=nodes)


def runtime_graph(files, links, tools, *, nodes=None):
    """Reconcile declared ELF metadata; does not authenticate bytes or their producer."""
    require(not set(files) & set(links), "runtime file/link collision")
    if nodes is None:
        nodes = {path: dict(kind="file", package=row["package"]) for path, row in files.items()}
        nodes.update(links)
    pending, visited, edges, used_links = list(tools.values()), set(), [], set()
    while pending:
        requested = pending.pop(0)
        path, chain = resolve_path(nodes, requested); used_links.update(chain)
        require(path in files, "runtime missing ELF dependency")
        if path in visited: continue
        visited.add(path); info = files[path]["elf"]
        if info["interpreter"]:
            target, chain = resolve_path(nodes, info["interpreter"]); used_links.update(chain)
            require(target in files, "runtime missing interpreter")
            edges.append(dict(source=path, kind="PT_INTERP", name=info["interpreter"], target=target))
            pending.append(target)
        for needed in info["needed"]:
            targets = {}
            for directory in LIB_DIRS:
                try: target, chain = resolve_path(nodes, directory+"/"+needed)
                except ValueError as error:
                    if str(error).startswith("archive dependency missing: "): continue
                    raise
                targets.setdefault(target, set()).update(chain)
            require(len(targets) == 1, "runtime missing/ambiguous library: " + needed)
            target = next(iter(targets)); used_links.update(targets[target])
            require(target in files and files[target]["elf"]["soname"] == needed, "runtime library SONAME/membership")
            require(set(info["required_versions"].get(needed, [])) <= set(files[target]["elf"]["provided_versions"]), "runtime symbol version missing")
            edges.append(dict(source=path, kind="DT_NEEDED", name=needed, target=target))
            pending.append(target)
    require(visited == set(files) and used_links == set(links), "runtime incomplete/unreachable closure")
    return dict(files=files, links={path: nodes[path] for path in sorted(used_links)},
                edges=sorted(edges, key=lambda row: (row["source"], row["kind"], row["name"])),
                closure_complete=True, actual_candidate_mappings_verified=False)
