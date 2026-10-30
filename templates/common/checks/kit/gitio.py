from __future__ import annotations

import hashlib
import io
import os
import re
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

# The check kit's only door to git.
#
# Every command runs through _run. It prints paths as they are (core.quotePath=false), and the
# commands that list paths use -z, so names with spaces, quotes or Korean letters come back
# exactly as git stores them. Functions that take `repo` expect the root of a work tree; find it
# with toplevel(). Nothing here changes what the repository or the work tree holds.

# Patch text must be what is in the file. Colour codes, an external diff tool or a textconv
# filter from the user's git config would each change it.
_PLAIN_PATCH = ("--no-color", "--no-ext-diff", "--no-textconv")

# The patch that numbered_added_lines reads. -U0 leaves out the lines around a change, and
# --inter-hunk-context=0 keeps the user's diff.interHunkContext from joining close hunks and
# printing the lines between them (a blank one without its space under diff.suppressBlankEmpty,
# which is then no longer counted). A change of whitespace at the end of a line is no change:
# --ignore-space-at-eol keeps a last line that gains its newline, and a file converted to CRLF,
# from being removed and added again. --text keeps a -diff or binary attribute, which anyone can
# set in .git/info/attributes, from turning the lines into "Binary files differ".
_NUMBERED_PATCH = ("-U0", "--inter-hunk-context=0", "--ignore-space-at-eol", "-M", "--text")

_IGNORE_PROBE = "__ignore_probe__"

# git archive output is extracted with the "tar" filter where this Python has one (3.12, and
# the security releases of older versions). Python 3.9.6 has none.
_EXTRACT_ARGS = {"filter": "tar"} if hasattr(tarfile, "tar_filter") else {}


class GitError(subprocess.CalledProcessError):
    """A git command exited with an unexpected code.

    It is a CalledProcessError (cmd, returncode and stderr are set), so a handler for that
    catches it too. Unlike CalledProcessError, its message includes git's own error text.
    """

    def __init__(self, args: Sequence[str], returncode: int, stderr: str) -> None:
        super().__init__(returncode, ["git", *args], stderr=stderr)

    def __str__(self) -> str:
        return f"{' '.join(self.cmd)} failed (exit {self.returncode}): {self.stderr.strip()}"


def _run(
    repo: Path, args: Sequence[str], ok: Optional[Tuple[int, ...]] = (0,)
) -> subprocess.CompletedProcess[bytes]:
    """Run git in repo. Raise GitError unless the exit code is in `ok` (None accepts any)."""
    # GIT_OPTIONAL_LOCKS=0 keeps `git status` from refreshing and rewriting the index, which
    # could collide with a git command the user runs at the same moment. `git diff` still
    # refreshes it. That is how it drops files that were only touched, so it cannot be turned off.
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    result = subprocess.run(
        ["git", "-c", "core.quotePath=false", "-C", str(repo), *args],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        env=env,
    )
    if ok is not None and result.returncode not in ok:
        stderr = result.stderr.decode("utf-8", errors="replace")
        raise GitError(list(args), result.returncode, stderr)
    return result


def run_git(repo: Path, *args: str, check: bool = True) -> bytes:
    """Run git in repo and return stdout. With check=False a failing command returns its stdout."""
    return _run(repo, args, ok=(0,) if check else None).stdout


def _one_line(raw: bytes) -> str:
    text = os.fsdecode(raw)
    return text[:-1] if text.endswith("\n") else text


def _nul_separated(raw: bytes) -> List[str]:
    """Split `-z` output. Names are decoded the way the OS decodes file names."""
    return [os.fsdecode(part) for part in raw.split(b"\0") if part]


def _literal(path: str) -> str:
    """A pathspec that means exactly this path. "[id].py" is otherwise a glob that matches i.py."""
    return ":(literal)" + path


# --- where we are and what we compare with ---------------------------------------------------


def _git_path(cwd: Path, *flags: str) -> Path:
    # git prints some of these relative to where it ran (".git", "../.git"). Resolve them from
    # `cwd`, not from this process's working directory.
    return (Path(cwd) / _one_line(run_git(cwd, "rev-parse", *flags))).resolve()


def toplevel(cwd: Path) -> Path:
    """Root of the work tree that contains cwd. This is the tree to check."""
    return _git_path(cwd, "--show-toplevel")


def common_dir(cwd: Path) -> Path:
    """Absolute path of the .git directory that the main checkout and all worktrees share."""
    return _git_path(cwd, "--git-common-dir")


def main_checkout(cwd: Path) -> Path:
    return common_dir(cwd).parent


def is_linked_worktree(cwd: Path) -> bool:
    """True in a worktree made by `git worktree add`, false in the main checkout."""
    return _git_path(cwd, "--git-dir") != common_dir(cwd)


def hooks_dir(repo: Path) -> Path:
    """The folder git runs hooks from: the hooks folder every worktree shares, or core.hooksPath
    when that is set. Resolved, so that it can be compared with common_dir(repo) / "hooks"."""
    return _git_path(repo, "--git-path", "hooks")


def config_value(repo: Path, key: str) -> Optional[str]:
    """What git config says for key, or None when it is not set."""
    result = _run(repo, ("config", "--get", key), ok=(0, 1))
    return _one_line(result.stdout) if result.returncode == 0 else None


def rev(repo: Path, ref: str) -> Optional[str]:
    """The full sha of the commit `ref` names, or None if there is no such commit."""
    # --quiet turns "no such ref" into a silent exit 1. Anything else (not a repository, say)
    # is a real error.
    result = _run(repo, ("rev-parse", "--verify", "--quiet", ref + "^{commit}"), ok=(0, 1))
    if result.returncode == 1:
        return None
    return _one_line(result.stdout)


def merge_base(repo: Path, base_ref: str) -> Optional[str]:
    """The common ancestor of HEAD and base_ref, or None when there is none to find.

    While a merge is in progress (MERGE_HEAD resolves) it is the common ancestor of base_ref and
    the merge being made, as it will be once the merge is committed. Merging base_ref itself thus
    gives base_ref: what the merge brings from it is not the branch's own change.

    None covers a base_ref that is not a commit and histories that share nothing.
    """
    heads = ["HEAD", "MERGE_HEAD"] if rev(repo, "MERGE_HEAD") is not None else ["HEAD"]
    # With three or more commits, git merge-base takes the first against a merge of the rest.
    result = _run(repo, ("merge-base", base_ref, *heads), ok=None)
    if result.returncode != 0:
        return None
    return _one_line(result.stdout) or None


def head(repo: Path) -> str:
    return _one_line(run_git(repo, "rev-parse", "HEAD"))


# --- work tree state ---------------------------------------------------------------------------


def working_tree_dirty(repo: Path) -> bool:
    """True if anything differs from HEAD: staged or unstaged edits, or untracked files that are
    not ignored."""
    # --untracked-files=normal overrides a user's status.showUntrackedFiles=no.
    return bool(run_git(repo, "status", "--porcelain", "-z", "--untracked-files=normal"))


def diff_sha256(repo: Path) -> str:
    """sha256 of `git diff HEAD --binary`: staged and unstaged edits to tracked files.

    Untracked files are not part of it.
    """
    # The trailing "--" keeps a file named HEAD from being read as the revision.
    patch = run_git(repo, "diff", "HEAD", "--binary", *_PLAIN_PATCH, "--")
    return hashlib.sha256(patch).hexdigest()


# --- changed paths -----------------------------------------------------------------------------


@dataclass(frozen=True)
class ChangedPath:
    """status is A added, M modified, D deleted, R renamed (old_path is set) or ? untracked."""

    status: str
    path: str
    old_path: Optional[str] = None


# What `git diff --name-status` letters become. M, T (type change) and U (unmerged) all count
# as modified: the file still has to be looked at.
_STATUS = {"A": "A", "C": "A", "D": "D", "R": "R"}


def _parse_name_status(raw: bytes) -> List[ChangedPath]:
    """Parse `git diff -z --name-status`: <letter> NUL <path> NUL, and for a rename or copy
    <letter><score> NUL <old> NUL <new> NUL."""
    changes: List[ChangedPath] = []
    fields = _nul_separated(raw)
    i = 0
    while i < len(fields):
        code = fields[i]
        if code[0] in "RC":
            old: Optional[str] = fields[i + 1]
            path = fields[i + 2]
            i += 3
        else:
            old = None
            path = fields[i + 1]
            i += 2
        status = _STATUS.get(code[0], "M")
        changes.append(ChangedPath(status, path, old if status == "R" else None))
    return changes


def changed_paths(repo: Path, base: str) -> List[ChangedPath]:
    """Paths whose work tree content differs from `base`, then untracked files not ignored."""
    # -M because a user's diff.renames=false would otherwise turn every rename into a delete and
    # an add. The trailing "--" keeps a ref from being read as a file of the same name.
    tracked = run_git(repo, "diff", "-z", "--name-status", "-M", base, "--")
    untracked = run_git(repo, "ls-files", "-z", "--others", "--exclude-standard")
    changes = _parse_name_status(tracked)
    changes.extend(ChangedPath("?", path) for path in _nul_separated(untracked))
    return changes


def staged_paths(repo: Path) -> List[str]:
    """Paths added, copied, modified or renamed in the index (a rename gives the new name)."""
    return _nul_separated(
        run_git(repo, "diff", "--cached", "-z", "--name-only", "--diff-filter=ACMR")
    )


def _text_line(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace")
    return text[:-1] if text.endswith("\r") else text


# "@@ -a,b +c,d @@": the hunk's lines start at line c of the new file. ",d" is left out for 1.
_HUNK = re.compile(rb"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


@dataclass
class Hunk:
    """A run of changed lines in a file: what the base had there (`removed`) and what the work
    tree has instead (`added`, each line with its number in the work tree's file, from 1). Either
    may be empty. Nothing of the file lies between two changed lines of one hunk."""

    removed: List[str]
    added: List[Tuple[int, str]]


def _hunks(patch: bytes) -> List[Hunk]:
    """The hunks of a patch for one file."""
    hunks: List[Hunk] = []
    current: Optional[Hunk] = None
    number = 0  # of the next line of the new file
    for raw in patch.split(b"\n"):
        if raw.startswith(b"@@"):
            match = _HUNK.match(raw)
            number = int(match.group(1)) if match else 0
            current = Hunk([], [])
            hunks.append(current)
        elif current is None:
            continue  # the header: "+++ b/path" is no added line
        elif raw.startswith(b"+"):
            # Inside a hunk a line that starts with "+++" is an added line whose text starts with
            # "++", and one that starts with "---" a removed line whose text starts with "--".
            current.added.append((number, _text_line(raw[1:])))
            number += 1
        elif raw.startswith(b"-"):
            current.removed.append(_text_line(raw[1:]))
        elif raw.startswith(b" "):  # context, which -U0 leaves out
            number += 1
    return hunks


def lines_of_file(path: Path) -> List[str]:
    """Every line of a file in the work tree, as git counts them. A symlink, a directory (a
    nested repository) or a binary file has none, as in a git patch."""
    if path.is_symlink() or not path.is_file():
        return []
    data = path.read_bytes()
    if b"\0" in data[:8000]:  # git's own test for a binary file
        return []
    parts = data.split(b"\n")
    if parts[-1] == b"":  # the newline that ends the last line
        parts.pop()
    return [_text_line(part) for part in parts]


def changed_hunks(
    repo: Path, base: str, changes: Optional[List[ChangedPath]] = None
) -> Dict[str, List[Hunk]]:
    """For each changed file that still exists, its hunks since base: the lines the work tree
    removed and added there, the added ones with their line numbers in the work tree's file.

    Lines come without their "+" or "-" and without their line ending. A file with nothing
    changed that counts (the whitespace at the end of its lines is not a change) has no hunks.
    An untracked file is one hunk of added lines. A deleted file is left out. `changes` is what
    changed_paths(repo, base) gave, or part of it; without it that is asked for here.
    """
    hunks: Dict[str, List[Hunk]] = {}
    for change in changed_paths(repo, base) if changes is None else changes:
        if change.status == "D":
            continue
        if change.status == "?":
            every = lines_of_file(Path(repo) / change.path)
            hunks[change.path] = [Hunk([], list(enumerate(every, 1)))] if every else []
            continue
        # A rename needs both names in the pathspec. Alone, the new name has no old file for git
        # to pair it with, and every line of it would look added.
        names = [name for name in (change.old_path, change.path) if name]
        patch = run_git(
            repo, "diff", *_NUMBERED_PATCH, *_PLAIN_PATCH, base, "--", *(_literal(n) for n in names)
        )
        hunks[change.path] = _hunks(patch)
    return hunks


def numbered_added_lines(
    repo: Path, base: str, changes: Optional[List[ChangedPath]] = None
) -> Dict[str, List[Tuple[int, str]]]:
    """For each changed file that still exists, the lines the work tree added to it since base,
    each with its line number in the work tree's file (from 1): the added lines of changed_hunks.

    Lines come without their "+" and without their line ending. A file with nothing added has an
    empty list. An untracked file counts as all added. A deleted file is left out.
    """
    return {
        path: [line for hunk in hunks for line in hunk.added]
        for path, hunks in changed_hunks(repo, base, changes).items()
    }


def added_lines(
    repo: Path, base: str, changes: Optional[List[ChangedPath]] = None
) -> Dict[str, List[str]]:
    """numbered_added_lines without the numbers."""
    numbered = numbered_added_lines(repo, base, changes)
    return {path: [text for _, text in lines] for path, lines in numbered.items()}


# --- export ------------------------------------------------------------------------------------


def _extract_tar(data: bytes, dest: Path) -> None:
    """Extract a tar stream into dest. Refuse any entry that would land outside it, by name or by
    way of a symlink an earlier entry made."""
    root = os.path.realpath(dest)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:", encoding="utf-8") as tar:
        for member in tar:
            target = os.path.realpath(os.path.join(root, member.name))
            if os.path.commonpath([root, target]) != root:
                raise ValueError(f"archive entry would be written outside {dest}: {member.name!r}")
            tar.extract(member, root, **_EXTRACT_ARGS)


def export_tree(repo: Path, rev: str, dest: Path, subdir: str = ".") -> Path:
    """Write the files of `subdir` as they are in commit `rev` under dest, and return dest.

    Files land at their repo-relative paths, so subdir "server" gives dest/server/... and nothing
    from outside it. The work tree and the index are not used. dest is created if needed.
    Raises GitError if `rev` or `subdir` does not exist. Like any `git archive`, it leaves out
    files marked export-ignore in .gitattributes.
    """
    # `rev` is part of the public signature and hides the rev() function in here.
    data = run_git(repo, "archive", "--format=tar", rev, "--", _literal(subdir))
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    _extract_tar(data, dest)
    return dest


# --- tracked and ignored -----------------------------------------------------------------------


def is_tracked(repo: Path, path: str) -> bool:
    """True if path is tracked. A directory counts when it holds tracked files."""
    return bool(run_git(repo, "ls-files", "-z", "--", _literal(path)))


def is_ignored(repo: Path, path: str) -> bool:
    """True if git ignores path. A path that ends in "/" is a directory and may not exist yet: it
    is asked about through a file name below it, so a rule like "cache/[!.]*", which needs a
    name below the directory to match, counts as ignoring "cache/".

    A tracked file is never ignored. git sees a symlink as a file, so a symlinked directory is
    judged by the file rules alone, and asking about anything below a symlink raises GitError.
    """
    probe = path
    if path.endswith("/"):
        is_symlink = (Path(repo) / path).is_symlink()
        probe = path.rstrip("/") if is_symlink else path + _IGNORE_PROBE
    return _run(repo, ("check-ignore", "-q", "--", probe), ok=(0, 1)).returncode == 0
