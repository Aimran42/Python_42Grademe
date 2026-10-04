# /* ************************************************************************** */ #  # noqa: E501
# /*                                                                            */ #  # noqa: E501
# /*                                                        :::      ::::::::   */ #  # noqa: E501
# /*   grademe.py                                         :+:      :+:    :+:   */ #  # noqa: E501
# /*                                                    +:+ +:+         +:+     */ #  # noqa: E501
# /*   By: momahdam <momahdam@student.42.fr>          +#+  +:+       +#+        */ #  # noqa: E501
# /*                                                +#+#+#+#+#+   +#+           */ #  # noqa: E501
# /*   Created: 2026/10/04 17:45:46 by momahdam          #+#    #+#             */ #  # noqa: E501
# /*   Updated: 2026/10/04 13:09:03 by momahdam         ###   ########.fr       */ #  # noqa: E501
# /*                                                                            */ #  # noqa: E501
# /* ************************************************************************** */ #  # noqa: E501

"""Small examshell-style grader for the ExamRank3 Python exercises.

A real-mode session selects
six exercises (two easy, two medium, two hard) and advances only after every
check for the current exercise succeeds.
"""

from __future__ import annotations

import ast
import importlib.util
import random
import signal
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent
RENDU = ROOT / "rendu"
STATE_FILE = ROOT / ".grademe_session"
EXAM_SECONDS = 3 * 60 * 60
TASKS: dict[str, list[tuple[str, str, str, Callable[[], list[tuple[tuple[Any, ...], Any]]]]]] = {  # noqa: E501
    "easy": [
        ("echo_validator", "ez/py_echo_validator/py_echo_validator.py", "echo_validator", lambda: [(("racecar",), True), (("A man a plan a canal Panama",), True), (("race a car",), False), (("",), False), (("!!!",), False)]),  # noqa: E501
        ("mirror_matrix", "ez/py_mirror_matrix/py_mirror_matrix.py", "mirror_matrix", lambda: [(([[1, 2, 3], [4, 5, 6]],), [[3, 2, 1], [6, 5, 4]]), (([],), []), (([[]],), [[]])]),  # noqa: E501
        ("shadow_merge", "ez/py_shadow_merge/py_shadow_merge.py", "shadow_merge", lambda: [(([1, 3, 5], [2, 4, 6]), [1, 2, 3, 4, 5, 6]), (([], [1, 2]), [1, 2]), (([1, 1], [1, 2]), [1, 1, 1, 2])]),  # noqa: E501
        ("whisper_cipher", "ez/py_whisper_cipher/py_whisper_cipher.py", "whisper_cipher", lambda: [(("Hello World!", 1), "Ifmmp Xpsme!"), (("xyz", 3), "abc"), (("abc", -1), "zab"), (("", 5), "")]),  # noqa: E501
    ],
    "medium": [
        ("bracket_validator", "medium/py_bracket_validator/py_bracket_validator.py", "bracket_validator", lambda: [(("()[]{}",), True), (("([)]",), False), (("hello(world)[test]{code}",), True), (("((())",), False), (("",), True)]),  # noqa: E501
        ("number_base_converter", "medium/py_number_base_converter/py_number_base_converter.py", "number_base_converter", lambda: [(("1010", 2, 10), "10"), (("FF", 16, 10), "255"), (("255", 10, 16), "FF"), (("Z", 36, 10), "35"), (("G", 16, 10), "ERROR"), (("10", 1, 2), "ERROR")]),  # noqa: E501
        ("pattern_tracker", "medium/py_pattern_tracker/py_pattern_tracker.py", "pattern_tracker", lambda: [(("123",), 2), (("12a34",), 2), (("987654321",), 0), (("1a2b",), 0), (("12x",), 0)]),  # noqa: E501
        ("string_sculptor", "medium/py_string_sculptor/py_string_sculptor.py", "string_sculptor", lambda: [(("hello",), "hElLo"), (("Hello World",), "hElLo wOrLd"), (("Python3.9!",), "pYtHoN3.9!"), (("",), "")]),  # noqa: E501
        ("twist_sequence", "medium/py_twist_sequence/py_twist_sequence.py", "twist_sequence", lambda: [(([1, 2, 3, 4, 5], 2), [4, 5, 1, 2, 3]), (([1, 2, 3], 5), [2, 3, 1]), (([], 3), []), (([1, 2], 0), [1, 2])]),  # noqa: E501
    ],
    "hard": [
        ("cryptic_sorter", "hard/py_cryptic_sorter/py_cryptic_sorter.py", "cryptic_sorter", lambda: [((["apple", "cat", "banana", "dog", "elephant"],), ["cat", "dog", "apple", "banana", "elephant"]), ((["aaa", "bbb", "AAA", "BBB"],), ["aaa", "AAA", "bbb", "BBB"]), (([],), []), (([""],), [""])]),  # noqa: E501
        ("string_permutation_checker", "hard/py_string_permutation_checker/py_string_permutation_checker.py", "string_permutation_checker", lambda: [(("abc", "bca"), True), (("abc", "def"), False), (("", ""), True), (("Abc", "abc"), False), (("a gentleman", "elegant man"), True)]),  # noqa: E501
    ],
}


def _forbidden_sorted(path: Path) -> bool:
    """Reject use of sorted() anywhere in a submitted exercise module."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeError):
        return True
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "sorted"
        for node in ast.walk(tree)
    )


def _load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(f"grademe_{name}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _submission_location(task: tuple[str, str, str, Callable[[], list[tuple[tuple[Any, ...], Any]]]]) -> tuple[str, Path]:  # noqa: E501
    name, relative_path, _function_name, _cases_factory = task
    filename = Path(relative_path).name
    expected_dir = Path(relative_path).parent.name
    directory = RENDU / expected_dir
    # The starter echo exercise uses its short directory name.
    if not directory.exists() and (RENDU / name).exists():
        directory = RENDU / name
    return filename, directory


def grade(task: tuple[str, str, str, Callable[[], list[tuple[tuple[Any, ...], Any]]]]) -> bool:  # noqa: E501
    name, relative_path, function_name, cases_factory = task
    filename, directory = _submission_location(task)
    submission_dir = directory.name
    path = directory / filename
    print(f"\n\033[92mGrading {name}\033[0m")
    if not directory.is_dir():
        print(f"  FAIL: create the required directory: rendu/{submission_dir}/")  # noqa: E501
        return False
    if not path.is_file():
        print(f"  FAIL: required file is missing: rendu/{submission_dir}/{filename}")  # noqa: E501
        return False
    if _forbidden_sorted(path):
        print("  FAIL: sorted() is forbidden")
        return False
    try:
        function = getattr(_load(path, name), function_name)
    except Exception as exc:
        print(f"  FAIL: could not load {function_name}: {exc}")
        return False

    passed = 0
    cases = cases_factory()
    for index, (args, expected) in enumerate(cases, 1):
        try:
            actual = _call_with_timeout(function, args)
            ok = actual == expected
        except Exception:
            ok = False
            actual = traceback.format_exc(limit=1).strip().splitlines()[-1]
        print(f"  {'PASS' if ok else 'FAIL'} test {index}/{len(cases)}")
        if not ok:
            print(f"    expected: {expected!r}\n    got:      {actual!r}")
        passed += int(ok)
    print(f"  Result: {passed}/{len(cases)}")
    return passed == len(cases)


def _call_with_timeout(function: Callable[..., Any], args: tuple[Any, ...]) -> Any:  # noqa: E501
    """Keep one hanging solution from blocking the whole exam session."""
    if not hasattr(signal, "SIGALRM"):
        return function(*args)

    def timeout_handler(_signum: int, _frame: Any) -> None:
        raise TimeoutError("execution exceeded 3 seconds")

    previous = signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(3)
    try:
        return function(*args)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def _save_session(tasks: list[tuple[str, str, str, Callable[[], list[tuple[tuple[Any, ...], Any]]]]], level: int, score: int, deadline: float) -> None:  # noqa: E501
    # Persist only simple values; task order is recovered by its exercise name.
    names = [task[0] for task in tasks]
    STATE_FILE.write_text(f"2\n{level}\n{score}\n{deadline}\n" + "\n".join(names) + "\n", encoding="utf-8")  # noqa: E501


def _restore_session() -> tuple[list[tuple[str, str, str, Callable[[], list[tuple[tuple[Any, ...], Any]]]]], int, int, float] | None:  # noqa: E501
    if not STATE_FILE.exists():
        return None
    try:
        lines = STATE_FILE.read_text(encoding="utf-8").splitlines()
        if lines[0] != "2":
            return None
        level, score = int(lines[1]), int(lines[2])
        deadline = float(lines[3])
        by_name = {task[0]: task for group in TASKS.values() for task in group}
        tasks = [by_name[name] for name in lines[4:]]
        if len(tasks) != 6 or len({task[0] for task in tasks}) != 6 or not 0 <= level <= 6:  # noqa: E501
            return None
        return tasks, level, score, deadline
    except (OSError, ValueError, KeyError, IndexError):
        return None


def _new_session() -> list[tuple[str, str, str, Callable[[], list[tuple[tuple[Any, ...], Any]]]]]:  # noqa: E501
    all_tasks = [task for tier in TASKS.values() for task in tier]
    selected = random.sample(all_tasks, 6)
    random.shuffle(selected)
    return selected


def _green_typing(text: str, delay: float = 0.035) -> None:
    for char in text:
        print(f"\033[92m{char}\033[0m", end="", flush=True)
        if sys.stdout.isatty():
            time.sleep(delay)
    print()


def _confirm(message: str = "Continue? [Y/n] ") -> bool:
    answer = input(message).strip().lower()
    return answer in {"", "y", "yes"}


def _countdown(deadline: float) -> int:
    remaining = max(0, int(deadline - time.time()))
    hours, remainder = divmod(remaining, 3600)
    minutes, seconds = divmod(remainder, 60)
    print(f"\033[92mTime remaining: {hours:02d}:{minutes:02d}:{seconds:02d}\033[0m")  # noqa: E501
    return remaining


class GradeMe:
    """Fire CLI entry points for the ExamRank3 grader."""

    @staticmethod
    def grade_changed() -> int:
        """Grade exercises changed by the commit being pushed (pre-push hook)."""  # noqa: E501
        tasks_by_path: dict[str, tuple[str, str, str, Callable[[], list[tuple[tuple[Any, ...], Any]]]]] = {}  # noqa: E501
        for group in TASKS.values():
            for task in group:
                filename, directory = _submission_location(task)
                tasks_by_path[f"rendu/{directory.name}/{filename}"] = task
        changed: set[str] = set()
        try:
            for line in sys.stdin:
                fields = line.split()
                if len(fields) != 4:
                    continue
                local_sha, remote_sha = fields[1], fields[3]
                if set(remote_sha) == {"0"}:
                    result = subprocess.run(
                        ["git", "ls-tree", "-r", "--name-only", local_sha, "--", "rendu"],  # noqa: E501
                        check=True, capture_output=True, text=True,
                    )
                else:
                    result = subprocess.run(
                        ["git", "diff", "--name-only", f"{remote_sha}..{local_sha}", "--", "rendu"],  # noqa: E501
                        check=True, capture_output=True, text=True,
                    )
                changed.update(result.stdout.splitlines())
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f"FAIL: could not inspect pushed commits: {exc}", file=sys.stderr)  # noqa: E501
            return 1

        selected = [task for path, task in tasks_by_path.items() if path in changed]  # noqa: E501
        if not selected:
            print("No grader exercise files changed in this push; grading skipped.")  # noqa: E501
            return 0
        print(f"Grading {len(selected)} changed exercise(s) before push.")
        results = [grade(task) for task in selected]
        if all(results):
            print("SUCCESS: all changed exercises passed.")
            return 0
        print("FAIL: one or more changed exercises did not pass.")
        return 1

    @staticmethod
    def login() -> int:
        print("\033[92m╔══════════════════════════════════════╗\033[0m")
        print("\033[92m║          42  EXAM RANK 03           ║\033[0m")
        print("\033[92m╚══════════════════════════════════════╝\033[0m")
        username = input("\033[92mlogin:\033[0m ").strip()
        if not username:
            print("A login is required.", file=sys.stderr)
            return 2
        _green_typing(f"Welcome, {username}. Good luck!")
        mode = input("Choose mode (realmode / finish): ").strip().lower()
        if mode in {"realmode", "real", "1"}:
            if not _confirm():
                print("Exam cancelled before starting.")
                return 0
            return GradeMe._real_mode()
        return 0

    @staticmethod
    def _real_mode() -> int:
        print("\033[92mREAL MODE\033[0m — six unique exercises; score 100 points to pass.")  # noqa: E501
        print("Create each requested submission at rendu/<full_exercise_directory>/<file>.py.")  # noqa: E501
        print("Levels are numbered 0–5. Levels 0–4 are worth 16 points; level 5 is worth 20.")  # noqa: E501
        print("You have three hours. The timer continues while the session is paused.")  # noqa: E501
        RENDU.mkdir(exist_ok=True)
        (RENDU / ".gitkeep").touch(exist_ok=True)
        restored = _restore_session()
        if restored:
            tasks, level, score, deadline = restored
            if level == 6:
                print("Exam already passed — 100/100.")
                STATE_FILE.unlink(missing_ok=True)
                return 0
            print(f"Resuming level {level}/5 with {score} points.")
        else:
            tasks, level, score = _new_session(), 0, 0
            deadline = time.time() + EXAM_SECONDS
            _save_session(tasks, level, score, deadline)
        if not _confirm():
            print("Session saved. You can continue later with the remaining time.")  # noqa: E501
            return 0

        while level < 6:
            if _countdown(deadline) <= 0:
                print("\033[91mTime is up. Exam failed.\033[0m")
                STATE_FILE.unlink(missing_ok=True)
                return 1
            task = tasks[level]
            print(f"\n\033[92mLevel {level}/5\033[0m — {task[0]} — current score {score}/100")  # noqa: E501
            submission_dir = Path(task[1]).parent.name
            print(f"Submission: rendu/{submission_dir}/{Path(task[1]).name}")
            if not _confirm():
                print("Session saved. You can continue later with the remaining time.")  # noqa: E501
                return 0
            while True:
                command = input("\033[92mexamshell>\033[0m ").strip().lower()
                if command == "finish":
                    print("Session saved. You will resume at this level next time.")  # noqa: E501
                    return 0
                if command == "status":
                    print(f"Level {level}/5 | {task[0]} | score {score}/100")
                    _countdown(deadline)
                    continue
                if command == "help":
                    print("Commands: status, help, grademe, finish")
                    _countdown(deadline)
                    continue
                if command == "grademe":
                    break
                print("command not found. Use status, help, grademe, or finish.")  # noqa: E501
            if grade(task):
                print("SUCCESS: exercise passed.")
                score += 20 if level == 5 else 16
                level += 1
                _save_session(tasks, level, score, deadline)
                if level < 6:
                    _green_typing(f"Level passed! Next: level {level} ({tasks[level][0]}).")  # noqa: E501
            else:
                print("FAIL: exercise did not pass. Fix it and run grademe again.")  # noqa: E501
            if _countdown(deadline) <= 0:
                print("\033[91mTime is up. Exam failed.\033[0m")
                STATE_FILE.unlink(missing_ok=True)
                return 1
        print("\n\033[92m🎉 Exam passed — 100/100. All six levels passed. 🎉\033[0m")  # noqa: E501
        STATE_FILE.unlink(missing_ok=True)
        return 0


if __name__ == "__main__":
    try:
        command = sys.argv[1] if len(sys.argv) > 1 else "login"
        if command == "grade_changed":
            sys.exit(GradeMe.grade_changed())
        if command == "login":
            sys.exit(GradeMe.login())
        print(f"command not found: {command}", file=sys.stderr)
        print("Commands: login, grade_changed", file=sys.stderr)
        sys.exit(2)
    except (KeyboardInterrupt):
        print("\nExiting ...")
        sys.exit(130)
    except (Exception) as e:
        print(f"Error: {e}")
        sys.exit(1)
