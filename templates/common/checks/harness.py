from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List

# python3 harness.py <command>: putting the check kit into a repository and keeping it linked.
#
#   install --target DIR --stack S --arch A --placement personal|shared --project-kind existing|new
#       Run from the template (templates/common/checks/harness.py). Copies the pieces into DIR.
#   link            in a linked worktree: link the private files of the main checkout into it
#   approve         THE USER ONLY: write down the fingerprints of the protected files as they are
#                   (personal placement; in the shared placement git tracks them all)
#   prune --stage NAME
#                   shared placement: delete the baseline entries the stage no longer finds
#   skills add SKILL_DIR [--name N] | skills remove NAME | skills list
#                   project skills the project picks (the template's docs/skill-guide.md)
#   baseline adopt --stage NAME --reason TEXT
#                   THE USER ONLY, shared placement: right after a change of style, put the stage's
#                   violations of old code in the baseline and approve its new content
#   proposal apply NAME
#                   THE USER ONLY: write the protected files a proposal under .ai/proposals/NAME
#                   holds, and approve them in the same step (kit/proposal.py)
#
# Every command but install works on the repository that holds the current directory.

HERE = Path(__file__).resolve().parent
# templates/common/checks/harness.py in the template repository.
DEFAULT_TEMPLATE = HERE.parents[2]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="harness.py", description="검사 키트 설치와 연결")
    commands = parser.add_subparsers(dest="command", metavar="<command>")
    commands.required = True
    install = commands.add_parser("install", help="템플릿의 조각을 대상 저장소에 설치한다")
    install.add_argument("--target", required=True, type=Path)
    install.add_argument("--stack", required=True)
    install.add_argument("--arch", required=True)
    install.add_argument("--placement", required=True, choices=("personal", "shared"))
    install.add_argument("--project-kind", required=True, choices=("existing", "new"))
    install.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    commands.add_parser("link", help="이 워크트리에 메인 체크아웃의 개인 파일을 연결한다")
    commands.add_parser("approve", help="(사용자 전용) 보호 파일의 지문을 다시 기록한다")
    prune = commands.add_parser("prune", help="기준선에서 이제는 없는 위반을 지운다")
    prune.add_argument("--stage", required=True)
    skills = commands.add_parser("skills", help="이 프로젝트가 고른 스킬을 넣고 뺀다")
    actions = skills.add_subparsers(dest="action", metavar="<add|remove|list>")
    actions.required = True
    add = actions.add_parser(
        "add", help="SKILL.md가 든 스킬 폴더를 넣는다. 이미 .agents/skills/<이름>에 있으면 등록만 한다"
    )
    add.add_argument("source", type=Path)
    add.add_argument("--name")
    remove = actions.add_parser("remove", help="넣은 스킬을 뺀다")
    remove.add_argument("name")
    actions.add_parser("list", help="이 저장소의 스킬을 보여 준다")
    baseline = commands.add_parser("baseline", help="공유 배치의 기준선을 다룬다")
    moves = baseline.add_subparsers(dest="move", metavar="<adopt>")
    moves.required = True
    adopt = moves.add_parser(
        "adopt", help="(사용자 전용) 스타일을 바꾼 직후의 기존 위반을 기준선에 올리고 승인한다"
    )
    adopt.add_argument("--stage", required=True)
    adopt.add_argument("--reason", required=True)
    proposal = commands.add_parser("proposal", help="보호 파일 변경 제안을 다룬다")
    steps = proposal.add_subparsers(dest="step", metavar="<apply>")
    steps.required = True
    apply = steps.add_parser(
        "apply", help="(사용자 전용) 제안한 보호 파일 변경을 적용하고 승인을 기록한다"
    )
    apply.add_argument("name")
    return parser


def _install(args: argparse.Namespace) -> int:
    from kit.install import install

    record = install(
        args.template, args.target, args.stack, args.arch, args.placement, args.project_kind
    )
    # approve works on the repository of the current directory.
    print(f"INFO install: 설치했다. 기록: {record}")
    print(f"INFO install: 이어서 {record.parents[2]}에서 차례로 한다")
    print("INFO install: 1. 프로젝트 소유 파일의 <<FILL: ...>>를 채운다")
    print(
        "INFO install: 2. 사용자가 python3 .ai/checks/harness.py approve를 실행한다. "
        "보호 파일을 바꾸면 마지막에 다시 한다"
    )
    return 0


def _link() -> int:
    from kit.gitio import main_checkout, toplevel
    from kit.link import link_worktree

    if toplevel(Path.cwd()) == main_checkout(Path.cwd()):
        print("INFO link: 메인 체크아웃이다. 연결할 것이 없다")
        return 0
    made = link_worktree(Path.cwd())
    for path in made:
        print(f"INFO link: {path} -> {os.readlink(str(path))}")
    if not made:
        print("INFO link: 새로 연결할 것이 없다")
    return 0


def _placement(top: Path) -> str:
    """The placement of the install record, else of stages.json, else personal."""
    from kit.config import ConfigError, load_config

    try:
        record = json.loads((top / ".ai" / "checks" / "install.json").read_text(encoding="utf-8"))
        if isinstance(record, dict) and record.get("placement") in ("personal", "shared"):
            return str(record["placement"])
    except (OSError, ValueError):
        pass
    try:
        return load_config(top / ".ai" / "checks" / "stages.json").placement
    except ConfigError:
        return "personal"


def _approve() -> int:
    from kit.gitio import toplevel
    from kit.proposal import stage_list
    from kit.weakening import write_protected_record

    top = toplevel(Path.cwd())
    checks = top / ".ai" / "checks"
    # Only the placement and the protected globs: a stage list with kinds this kit does not know
    # (another kit's, before a proposal brings it back) can still be approved as it is.
    placement, protected, _ = stage_list(top)
    if placement == "shared":  # git tracks every protected file: no record to write
        print(
            "INFO approve: 공유 배치는 보호 파일을 모두 git이 추적해서 지문을 기록하지 않는다. "
            "보호 파일을 바꿨으면 approvals.json에 그 파일 지금 내용의 sha256으로 승인을 적고 "
            "함께 커밋한다"
        )
        return 0
    record = checks / "protected.json"
    hashes = write_protected_record(top, record, protected)
    print(f"INFO approve: 보호 파일 {len(hashes)}개의 지문을 기록했다: {record}")
    return 0


def _skills(args: argparse.Namespace) -> int:
    from kit import skills
    from kit.gitio import toplevel

    top = toplevel(Path.cwd())
    if args.action == "list":
        for name, description in skills.list_skills(top):
            print(f"{name}: {description}")
        return 0
    placement = _placement(top)
    if args.action == "add":
        made, recorded = skills.add_skill(top, args.source, placement, args.name)
        for rel in made:
            print(f"INFO skills: {rel}")
    else:
        recorded = skills.remove_skill(top, args.name, placement)
        print(f"INFO skills: {args.name}를 뺐다")
    if recorded:
        print(
            "INFO skills: install.json이 바뀌었다. 사용자가 approve를 다시 실행하고, "
            "다른 워크트리에서는 harness.py link를 다시 실행한다"
        )
    elif placement == "shared" and args.action == "add":
        print("INFO skills: 공유 배치다. 넣은 스킬을 함께 커밋한다")
    return 0


def main(argv: List[str]) -> int:
    sys.path.insert(0, str(HERE))
    from kit.config import ConfigError
    from kit.gitio import GitError
    from kit.install import InstallError
    from kit.runner import prune

    for stream in (sys.stdout, sys.stderr):  # Korean output whatever the locale
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    args = _parser().parse_args(argv)
    try:
        if args.command == "install":
            return _install(args)
        if args.command == "link":
            return _link()
        if args.command == "approve":
            return _approve()
        if args.command == "skills":
            return _skills(args)
        if args.command == "baseline":
            from kit.runner import adopt

            return adopt(Path.cwd(), args.stage, args.reason, out=sys.stdout)
        if args.command == "proposal":
            from kit.proposal import apply_proposal

            return apply_proposal(Path.cwd(), args.name, sys.stdout)
        return prune(Path.cwd(), args.stage, out=sys.stdout)
    except (InstallError, ConfigError, GitError, OSError, ValueError) as exc:
        sys.stderr.write(f"ERROR harness: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
