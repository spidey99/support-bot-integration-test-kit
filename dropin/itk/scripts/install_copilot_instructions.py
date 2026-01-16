"""Helper script: prints merge instructions.

In the work repo, you may already have `.github/copilot-instructions.md`.
This script does NOT modify files automatically (safer). It tells you what to copy/append.
"""

from pathlib import Path


def main() -> None:
    here = Path(__file__).resolve().parent
    merge_root = here.parent / "_merge_to_repo_root" / ".github"

    print("Copy these into <WORK_REPO>/.github/ :")
    for p in merge_root.rglob("*"):
        if p.is_file():
            rel = p.relative_to(merge_root)
            print(f"- {rel}")

    print("\nIf <WORK_REPO>/.github/copilot-instructions.md exists:")
    print("- Append copilot-instructions.append.md between the ITK_BEGIN/ITK_END markers.")


if __name__ == "__main__":
    main()
