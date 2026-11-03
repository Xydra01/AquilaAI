"""Capture real tool logs for the diagnostics tests (run once, from an MSVC dev shell).

    scripts\\msvc-dev.cmd python tests/fixtures/logs/capture_logs.py

Needs cl, clang++ (llvm-mingw), cmake, ninja and python on PATH. Sources are
written to a scratch directory; machine-specific paths are replaced with
<project> so the committed logs contain no local paths. The pytest logs are
captured by tests/fixtures/python/gen_python_fixtures.py.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

OUT = Path(__file__).resolve().parent

BROKEN_CPP = """#include <string>
int add(int a, int b) { return a + b }
int main() {
    std::string s = 42;
    return undeclared_value;
}
"""

TEMPLATE_SPAM_CPP = """struct A {}; struct B {}; struct C {}; struct D {}; struct E {}; struct F {}; struct G {}; struct H {};
template <class T> int poke(const T& v) { return v.missing(); }
int main() {
    return poke(A{}) + poke(B{}) + poke(C{}) + poke(D{}) + poke(E{}) + poke(F{}) + poke(G{}) + poke(H{});
}
"""

CMAKE_BAD = """cmake_minimum_required(VERSION 3.20)
project(bad CXX)
not_a_real_command(foo)
"""

NINJA_CMAKE = """cmake_minimum_required(VERSION 3.20)
project(proj CXX)
add_executable(app main.cpp util.cpp)
"""
SHARED_HPP = """#pragma once
inline int shared_value() { return missing_symbol; }
"""
MAIN_CPP = '#include "shared.hpp"\nint main() { return shared_value(); }\n'
UTIL_CPP = '#include "shared.hpp"\nint util() { return shared_value() + 1; }\n'

TRACEBACK_PY = """def load(path):
    with open(path) as f:
        return f.read()


def main():
    return load("does-not-exist.txt")


main()
"""


def run(cmd: list[str], cwd: Path) -> str:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, errors="replace")
    return (proc.stdout + proc.stderr).strip() + "\n"


def scrub(text: str, roots: list[Path]) -> str:
    for root in roots:
        for form in {str(root), str(root).replace("\\", "/"), str(root).lower(), str(root).replace("\\", "/").lower()}:
            text = text.replace(form, "<project>")
    user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    if user:
        text = re.sub(re.escape(user), "<user>", text, flags=re.IGNORECASE)
    return text


def save(name: str, text: str) -> None:
    with (OUT / name).open("w", encoding="utf-8", newline="\n") as f:
        f.write(text.replace("\r\n", "\n"))
    print(f"wrote {name} ({len(text)} chars)")


def main() -> None:
    for tool in ("cl", "clang++", "cmake", "ninja"):
        if shutil.which(tool) is None:
            sys.exit(f"{tool} not on PATH; run from an MSVC developer shell with llvm-mingw installed")
    work = Path(tempfile.mkdtemp(prefix="aquila-logs-"))
    (work / "broken.cpp").write_text(BROKEN_CPP)
    (work / "template_spam.cpp").write_text(TEMPLATE_SPAM_CPP)
    roots = [work]

    save("msvc_broken.txt", scrub(run(["cl", "/nologo", "/c", "/EHsc", "/std:c++20", "broken.cpp"], work), roots))
    save("msvc_template_spam.txt", scrub(run(["cl", "/nologo", "/c", "/EHsc", "/std:c++20", "template_spam.cpp"], work), roots))
    save("clang_broken.txt", scrub(run(["clang++", "-fsyntax-only", "-std=c++20", "broken.cpp"], work), roots))
    save("clang_template_spam.txt", scrub(run(["clang++", "-fsyntax-only", "-std=c++20", "template_spam.cpp"], work), roots))

    bad = work / "cmake_bad"
    bad.mkdir()
    (bad / "CMakeLists.txt").write_text(CMAKE_BAD)
    save("cmake_configure_error.txt", scrub(run(["cmake", "-S", ".", "-B", "build", "-G", "Ninja"], bad), roots))

    proj = work / "ninja_proj"
    proj.mkdir()
    (proj / "CMakeLists.txt").write_text(NINJA_CMAKE)
    (proj / "shared.hpp").write_text(SHARED_HPP)
    (proj / "main.cpp").write_text(MAIN_CPP)
    (proj / "util.cpp").write_text(UTIL_CPP)
    run(["cmake", "-S", ".", "-B", "build", "-G", "Ninja", "-DCMAKE_CXX_COMPILER=cl"], proj)
    save("ninja_build_failure.txt", scrub(run(["cmake", "--build", "build", "--", "-k", "0"], proj), roots))

    (work / "tb.py").write_text(TRACEBACK_PY)
    save("python_traceback.txt", scrub(run([sys.executable, "tb.py"], work), roots))


if __name__ == "__main__":
    main()
