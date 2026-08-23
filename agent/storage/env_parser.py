"""Environment variable parser and updater."""
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


@dataclass
class EnvVariable:
    key: str
    default_value: str
    description: str
    inferred_type: str  # 'bool', 'int', 'str'


@dataclass
class EnvSection:
    title: str
    variables: List[EnvVariable]


def _infer_type(value: str) -> str:
    val = value.strip()
    if val in ("0", "1"):
        return "bool"
    if val.isdigit():
        return "int"
    return "str"


def parse_env_example(path: Path) -> List[EnvSection]:
    """Parse .env.example into sections of variables with descriptions and default values."""
    if not path.is_file():
        return []

    lines = path.read_text(encoding="utf-8").splitlines()
    sections: List[EnvSection] = []
    
    current_title = "General"
    current_desc_lines: List[str] = []
    current_vars: List[EnvVariable] = []
    
    seen_keys = set()

    for line in lines:
        line = line.strip()
        if not line:
            if current_vars and current_title:
                sections.append(EnvSection(current_title, current_vars))
                current_vars = []
                current_title = "Advanced"
            continue

        if line.startswith("#"):
            comment = line.lstrip("#").strip()
            if "=" not in line:
                if not current_vars and not current_desc_lines and len(comment) > 0:
                    current_title = comment
                else:
                    current_desc_lines.append(comment)
            else:
                key_val = line.lstrip("#").strip()
                if "=" in key_val:
                    key, val = key_val.split("=", 1)
                    key = key.strip()
                    val = val.strip()
                    
                    import re
                    if not re.match(r'^[A-Za-z0-9_]+$', key):
                        current_desc_lines.append(comment)
                        continue
                    
                    if key in seen_keys:
                        current_desc_lines = []
                        continue
                    
                    inline_desc = ""
                    if " #" in val:
                        val, inline_desc = val.split(" #", 1)
                        val = val.strip()
                        inline_desc = inline_desc.strip()
                    
                    desc = " ".join(current_desc_lines)
                    if inline_desc:
                        desc = desc + (" " if desc else "") + inline_desc
                        
                    current_vars.append(
                        EnvVariable(
                            key=key,
                            default_value=val,
                            description=desc.strip(),
                            inferred_type=_infer_type(val)
                        )
                    )
                    seen_keys.add(key)
                    current_desc_lines = []
        else:
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                
                if key in seen_keys:
                    current_desc_lines = []
                    continue
                
                inline_desc = ""
                if " #" in val:
                    val, inline_desc = val.split(" #", 1)
                    val = val.strip()
                    inline_desc = inline_desc.strip()
                
                desc = " ".join(current_desc_lines)
                if inline_desc:
                    desc = desc + (" " if desc else "") + inline_desc
                    
                current_vars.append(
                    EnvVariable(
                        key=key,
                        default_value=val,
                        description=desc.strip(),
                        inferred_type=_infer_type(val)
                    )
                )
                seen_keys.add(key)
                current_desc_lines = []

    if current_vars:
        sections.append(EnvSection(current_title, current_vars))
        
    final_sections = []
    for s in sections:
        if not s.variables:
            continue
        title = s.title
        if " — " in title:
            title = title.split(" — ")[0]
        if " - " in title:
            title = title.split(" - ")[0]
        final_sections.append(EnvSection(title.strip(), s.variables))

    return final_sections


def read_env(path: Path) -> Dict[str, str]:
    """Read the current .env overrides."""
    if not path.is_file():
        return {}
    
    overrides = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            if " #" in val:
                val = val.split(" #", 1)[0]
            overrides[key.strip()] = val.strip()
            
    return overrides


def update_env(path: Path, updates: Dict[str, str]) -> None:
    """Update or add keys to .env while preserving structure."""
    if not path.is_file():
        lines = []
    else:
        lines = path.read_text(encoding="utf-8").splitlines()

    updated_keys = set()
    new_lines = []
    
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, val = stripped.split("=", 1)
            key = key.strip()
            if key in updates:
                new_val = updates[key]
                new_lines.append(f"{key}={new_val}")
                updated_keys.add(key)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    for key, val in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={val}")

    text = "\n".join(new_lines).rstrip() + "\n"
    path.write_text(text, encoding="utf-8")
