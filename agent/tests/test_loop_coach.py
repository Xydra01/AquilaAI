import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import LoopCoach
from agent.core import is_degenerate_description


def test_scratchpad_quality_blocks_repetition():
    coach = LoopCoach(mode="character_build", step_kind="search")
    block = coach.scratchpad_quality_block("Complex antagonist, " * 30)
    assert block is not None
    assert "OS BLOCK" in block


def test_scratchpad_quality_allows_good_note():
    coach = LoopCoach()
    body = (
        "- Name: Emet-Selch\n- Role: Ascian emissary\n"
        "- Traits: theatrical, manipulative, mournful\n"
        "- Speech: formal, archaic flourishes\n"
    )
    assert coach.scratchpad_quality_block(body) is None
    assert not is_degenerate_description(body)


def test_scratchpad_quality_allows_long_good_note():
    coach = LoopCoach()
    # Create a non-degenerate markdown note that is > 1200 characters with diverse words
    facts = [
        "Memory-mapped files are extremely useful for databases because they eliminate kernel-to-user copy overhead.",
        "On the Windows operating system, SQLite faces a critical constraint: it cannot truncate a memory-mapped file.",
        "This means operations like VACUUM or auto_vacuum that try to shrink the database will fail silently.",
        "No data is actually lost during this failure, and the unused space is reused next time the database grows.",
        "Older versions of SQLite prior to 3.7.0 might incorrectly report database corruption during integrity checks.",
        "Memory-mapped I/O is disabled by default (mmap_size is zero) to avoid platform bugs or signal crashes.",
        "To enable it, set PRAGMA mmap_size to a value larger than 256MB based on process memory availability.",
        "Total potential address space used is mmap_size multiplied by the number of open database files.",
        "Processes built on 32-bit architectures have a tight 2GB address space limit and must map conservatively.",
        "For 64-bit applications, virtual address space is abundant, making larger mapping sizes safe to use.",
        "The SQLITE_MAX_MMAP_SIZE compile-time option sets a hard upper bound on the maximum allowed map size.",
        "At start-time, SQLITE_CONFIG_MMAP_SIZE can be used to configure default and maximum sizes programmatically.",
        "If a process accesses memory-mapped regions beyond the defined limit, SQLite falls back to standard file reads.",
        "Since SQLite uses a read-only memory map for queries, it prevents stray pointer errors from corrupting data.",
        "Database writes still make a copy of page content in private heap memory before modifying the database file.",
        "Therefore, memory-mapping primarily benefits read-heavy workloads rather than write performance.",
        "Using shared-memory in WAL mode allows multiple concurrent reader connections to access the database efficiently.",
        "SQLite file locks are handled by the OS and can lead to contention under highly concurrent write workloads.",
        "Performance benchmarks show that memory-mapped databases are faster than disk but slower than in-memory databases.",
        "A memory database open via colon-memory-colon runs completely in heap memory without any VFS or VFS lock overhead.",
        "It is possible to use ramdisk files as a backing store, but they still pay the cost of filesystem API layers."
    ]
    body = "\n".join(f"- {fact}" for fact in facts)
    assert len(body) > 1200
    assert coach.scratchpad_quality_block(body) is None


