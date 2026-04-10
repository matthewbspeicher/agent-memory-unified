# Arena Room Templates Design

## Overview

Three concrete puzzle room types that agents can solve using available tools.

## Room Types

### 1. DatabasePuzzle (`database.py`)
**Concept:** Agent explores a database to find hidden flag in data

**Tools:** `db_schema`, `db_query`, `submit_flag`

**Initial State:**
```python
{
    "tables": {
        "users": [{"id": 1, "name": "Alice", "api_key": "real_key_here"}, ...],
        "transactions": [...],
        "flags": [{"id": 1, "value": "FLAG{hidden_in_plaintext}"}]
    }
}
```

**Difficulty Scaling:**
- Easy: Flag directly in a table
- Medium: Flag requires JOIN to discover
- Hard: Flag requires aggregations, subqueries

### 2. CipherPuzzle (`cipher.py`)
**Concept:** Agent decodes encrypted messages to find the flag

**Tools:** `fs_read`, `exec_python`, `submit_flag`

**Initial State:**
```python
{
    "files": {
        "message.txt": "Uryyb, gur synt vf SYNT{ebgngrq_3_svefg}",
        "hint.txt": "ROT13 - shift each letter by 13"
    }
}
```

**Difficulty Scaling:**
- Easy: Simple ROT13/ROT1
- Medium: Vigenere or Caesar with unknown shift
- Hard: AES/RSA decryption with key discovery

### 3. FileSystemPuzzle (`filesystem.py`)
**Concept:** Agent navigates files to find hidden flag

**Tools:** `fs_read`, `fs_list`, `exec_python`, `submit_flag`

**Initial State:**
```python
{
    "files": {
        "README.txt": "Welcome to the system...",
        "config.yaml": "...",
        ".hidden/secret.txt": "FLAG{found_in_hidden_dir}",
        "notes.txt": "The flag is in a hidden directory..."
    }
}
```

**Difficulty Scaling:**
- Easy: Flag in obvious location
- Medium: Flag requires file analysis (steganography, metadata)
- Hard: Flag requires understanding file relationships

## Base Class Extensions

Extend `EscapeRoomEnvironment` with:
- `validate_tool(tool_name) -> bool` - Check if tool is allowed
- `get_hint() -> str | None` - Progressive hints based on turn count
- `calculate_score() -> float` - Score based on turns, hints used

## Implementation Plan

1. Create `cipher.py` and `filesystem.py` in `/trading/competition/escape_rooms/`
2. Refactor `deterministic.py` to share common state management
3. Add factory function to instantiate rooms from challenge config
4. Add seed challenges to migration for each room type

## Files to Create/Modify

- `trading/competition/escape_rooms/cipher.py` (new)
- `trading/competition/escape_rooms/filesystem.py` (new)
- `trading/competition/escape_rooms/factory.py` (new)
- `scripts/migrations/add-arena-system.sql` (add challenges)
