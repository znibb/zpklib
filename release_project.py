#!/usr/bin/env python3
"""
Create a git tag and GitHub release for a KiCad project and upload its
production files.

The version is read from the VERSION text variable in the project's
.kicad_pro file; the tag and release are called v<VERSION>. Every file matched
by FILE_PATTERNS must carry the same _v<VERSION>_ in its name, otherwise the
script aborts. The release notes are the matching section of CHANGELOG.md.

If the tag and/or the release already exists you are asked whether to
overwrite it. An existing release is updated in place (notes replaced, assets
with the same name replaced, stale assets removed); an existing tag is moved to
HEAD.

Requires git and an authenticated GitHub CLI (gh). The project's working tree
must be clean and HEAD must be pushed to its upstream.

Usage:
  release_project.py PROJECT_DIR
"""

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Glob patterns, relative to the project directory, of the files to upload.
FILE_PATTERNS = [
    "output/*_3D-model.step",
    "output/*_PCB.zip",
    "output/*_PCBA.zip",
    "output/*_PCB-Layers.pdf",
    "output/*_Schematic.pdf",
    "output/PCBA/*",
]

CHANGELOG = "CHANGELOG.md"


def die(message):
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def run(cmd, cwd, check=True):
    """Run a command in cwd and return the CompletedProcess (text output captured)."""
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        die(f"'{' '.join(cmd)}' failed:\n{(result.stderr or result.stdout).strip()}")
    return result


def confirm(prompt):
    return input(f"{prompt} [y/N]: ").strip().lower() in ("y", "yes")


def read_version(project_dir):
    kicad_pro_files = list(project_dir.glob("*.kicad_pro"))
    if not kicad_pro_files:
        die(f"No .kicad_pro file found in {project_dir}.")
    if len(kicad_pro_files) > 1:
        die("Multiple .kicad_pro files found in "
            f"{project_dir}: {', '.join(f.name for f in kicad_pro_files)}")
    try:
        with open(kicad_pro_files[0]) as f:
            project = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        die(f"Could not read {kicad_pro_files[0].name}: {e}")

    version = ((project.get("text_variables") or {}).get("VERSION") or "").strip()
    if not version:
        die(f"No VERSION text variable set in {kicad_pro_files[0].name}.")
    if not re.match(r"^\d+\.\d+\.\d+$", version):
        die(f"VERSION '{version}' is not valid (expected MAJOR.MINOR.PATCH).")
    return version


def collect_files(project_dir):
    """Expand FILE_PATTERNS into a sorted list of unique files."""
    files = {}
    for pattern in FILE_PATTERNS:
        matches = sorted(p for p in project_dir.glob(pattern) if p.is_file())
        if not matches:
            die(f"No files match '{pattern}' in {project_dir}.\n"
                "Has the production jobset been run?")
        for path in matches:
            files[path] = None
    files = sorted(files)

    names = {}
    for path in files:
        if path.name in names:
            die(f"Two files would be uploaded as '{path.name}':\n"
                f"  {names[path.name]}\n  {path}")
        names[path.name] = path
    return files


def check_file_versions(files, version, project_dir):
    """Abort if any file name carries a different _vX.Y.Z_ than version."""
    mismatched = []
    for path in files:
        m = re.search(r"_v(\d+\.\d+\.\d+)_", path.name)
        if m is None:
            print(f"  Warning: no version in file name: {path.relative_to(project_dir)}")
        elif m.group(1) != version:
            mismatched.append((path, m.group(1)))
    if mismatched:
        lines = [f"  {p.relative_to(project_dir)}  (v{v})" for p, v in mismatched]
        die(f"File versions do not match VERSION {version}:\n" + "\n".join(lines))


def changelog_section(project_dir, tag):
    """Return the CHANGELOG.md section for tag (heading included), or None."""
    path = project_dir / CHANGELOG
    if not path.exists():
        return None
    section = []
    in_section = False
    for line in path.read_text().splitlines():
        if line.startswith("## "):
            if in_section:
                break
            in_section = line[3:].strip().split()[0] == tag
        if in_section:
            section.append(line)
    return "\n".join(section).strip() + "\n" if section else None


def human_size(num_bytes):
    for unit in ("B", "kB", "MB"):
        if num_bytes < 1024 or unit == "MB":
            return f"{num_bytes:.0f} {unit}" if unit == "B" else f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} PROJECT_DIR", file=sys.stderr)
        sys.exit(1)

    project_dir = Path(sys.argv[1]).resolve()
    if not project_dir.is_dir():
        die(f"{project_dir} is not a directory.")

    # ------------------------------------------------------------------
    # Version, tools and files
    # ------------------------------------------------------------------
    version = read_version(project_dir)
    tag = f"v{version}"
    print(f"Project: {project_dir}")
    print(f"VERSION: {version}  (tag/release: {tag})")

    if run(["git", "rev-parse", "--is-inside-work-tree"], project_dir, check=False).returncode != 0:
        die(f"{project_dir} is not a git repository.")
    if run(["git", "remote", "get-url", "origin"], project_dir, check=False).returncode != 0:
        die("The repository has no 'origin' remote.")
    if run(["gh", "auth", "status"], project_dir, check=False).returncode != 0:
        die("The GitHub CLI is not authenticated. Run 'gh auth login'.")

    print("\nCollecting files...")
    files = collect_files(project_dir)
    check_file_versions(files, version, project_dir)
    print(f"  {len(files)} files, all matching v{version}")

    # ------------------------------------------------------------------
    # Git state
    # ------------------------------------------------------------------
    print("\nChecking git state...")
    if run(["git", "status", "--porcelain"], project_dir).stdout.strip():
        die("The working tree has uncommitted changes. Commit or stash them first.")
    run(["git", "fetch", "origin"], project_dir)
    if run(["git", "rev-parse", "--abbrev-ref", "@{upstream}"], project_dir, check=False).returncode != 0:
        die("The current branch has no upstream. Push it first.")
    if run(["git", "merge-base", "--is-ancestor", "HEAD", "@{upstream}"], project_dir, check=False).returncode != 0:
        die("HEAD has not been pushed to its upstream. Push it first.")
    head = run(["git", "rev-parse", "HEAD"], project_dir).stdout.strip()
    head_subject = run(["git", "log", "-1", "--format=%s"], project_dir).stdout.strip()
    print(f"  Clean and pushed. HEAD: {head[:8]} {head_subject}")

    # ------------------------------------------------------------------
    # Existing tag and release
    # ------------------------------------------------------------------
    print(f"\nChecking for existing {tag}...")
    local_tag = run(["git", "rev-parse", "-q", "--verify", f"refs/tags/{tag}^{{commit}}"],
                    project_dir, check=False).stdout.strip()
    remote_out = run(["git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}"], project_dir).stdout.strip()
    remote_tag = remote_out.split()[0] if remote_out else ""
    tag_exists = bool(local_tag or remote_tag)
    tag_sha = remote_tag or local_tag

    view = run(["gh", "release", "view", tag, "--json", "assets,url"], project_dir, check=False)
    release_exists = view.returncode == 0
    if not release_exists and "not found" not in view.stderr.lower():
        die(f"Could not query release {tag}:\n{view.stderr.strip()}")
    existing_assets = []
    if release_exists:
        existing_assets = [a["name"] for a in json.loads(view.stdout)["assets"]]

    new_names = {p.name for p in files}
    stale_assets = sorted(set(existing_assets) - new_names)

    print(f"  Tag:     {'exists, points at ' + tag_sha[:8] if tag_exists else 'does not exist'}")
    if tag_exists and local_tag and remote_tag and local_tag != remote_tag:
        print(f"           (local {local_tag[:8]} differs from origin {remote_tag[:8]})")
    print(f"  Release: {'exists (' + str(len(existing_assets)) + ' assets)' if release_exists else 'does not exist'}")

    notes = changelog_section(project_dir, tag)
    if notes is None:
        print(f"  Warning: no '## {tag}' section in {CHANGELOG} — release notes will be empty.")
        notes = ""

    # ------------------------------------------------------------------
    # Summary and confirmation
    # ------------------------------------------------------------------
    print("\n--- Summary ---")
    print(f"  Tag:      {tag} -> {head[:8]}")
    print(f"  Release:  {tag}")
    print("  Files:")
    for path in files:
        print(f"    {path.relative_to(project_dir)}  ({human_size(path.stat().st_size)})")
    if notes:
        print("  Notes:")
        for line in notes.rstrip().splitlines():
            print(f"    {line}")
    print()

    if tag_exists:
        at_head = " (already at HEAD)" if tag_sha == head else f" (HEAD is {head[:8]})"
        if not confirm(f"Tag {tag} exists and points at {tag_sha[:8]}{at_head}. Overwrite it?"):
            print("Aborted.")
            sys.exit(0)
    if release_exists:
        print(f"Release {tag} exists. Updating it in place replaces the notes, replaces assets")
        print("with the same name" + (f" and removes {len(stale_assets)} stale asset(s): "
                                      + ", ".join(stale_assets) if stale_assets else "") + ".")
        if not confirm("Update the existing release?"):
            print("Aborted.")
            sys.exit(0)
    if not confirm("Proceed?"):
        print("Aborted.")
        sys.exit(0)

    # ------------------------------------------------------------------
    # Tag
    # ------------------------------------------------------------------
    print(f"\nTagging {head[:8]} as {tag}...")
    if tag_exists:
        run(["git", "tag", "-f", tag, head], project_dir)
        run(["git", "push", "--force", "origin", f"refs/tags/{tag}"], project_dir)
    else:
        run(["git", "tag", tag, head], project_dir)
        run(["git", "push", "origin", f"refs/tags/{tag}"], project_dir)
    print("  Done")

    # ------------------------------------------------------------------
    # Release
    # ------------------------------------------------------------------
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as notes_file:
        notes_file.write(notes)
    try:
        file_args = [str(p) for p in files]
        if release_exists:
            print(f"\nUpdating release {tag}...")
            run(["gh", "release", "edit", tag, "--notes-file", notes_file.name], project_dir)
            run(["gh", "release", "upload", tag, *file_args, "--clobber"], project_dir)
            for name in stale_assets:
                run(["gh", "release", "delete-asset", tag, name, "--yes"], project_dir)
                print(f"  Removed stale asset {name}")
        else:
            print(f"\nCreating release {tag}...")
            run(["gh", "release", "create", tag, *file_args,
                 "--title", tag, "--notes-file", notes_file.name], project_dir)
    finally:
        Path(notes_file.name).unlink(missing_ok=True)

    url = run(["gh", "release", "view", tag, "--json", "url", "-q", ".url"], project_dir).stdout.strip()
    print(f"\nDone. Release {tag} ({len(files)} files uploaded).")
    print(f"  URL: {url}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(0)
