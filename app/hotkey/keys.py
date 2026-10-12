from __future__ import annotations


KEY_LABELS = {
    "space": "Space",
    "enter": "Enter",
    "tab": "Tab",
    "esc": "Esc",
    "escape": "Esc",
    "backspace": "Backspace",
    "delete": "Delete",
    "insert": "Insert",
    "home": "Home",
    "end": "End",
    "page up": "PageUp",
    "page down": "PageDown",
    "up": "↑",
    "down": "↓",
    "left": "←",
    "right": "→",
    "caps lock": "CapsLock",
    "ctrl": "Ctrl",
    "left ctrl": "LeftCtrl",
    "right ctrl": "RightCtrl",
    "alt": "Alt",
    "left alt": "LeftAlt",
    "right alt": "RightAlt",
    "shift": "Shift",
    "left shift": "LeftShift",
    "right shift": "RightShift",
    "windows": "Win",
    "left windows": "LeftWin",
    "right windows": "RightWin",
    "mouse3": "Middle",
    "mouse4": "鼠标侧键 1 (Mouse4)",
    "mouse5": "鼠标侧键 2 (Mouse5)",
    "wheel_left": "鼠标左滚 (WheelLeft)",
    "wheel_right": "鼠标右滚 (WheelRight)",
}
KEY_LABELS.update({f"f{index}": f"F{index}" for index in range(1, 13)})
KEY_LABELS.update({chr(code): chr(code).upper() for code in range(ord("a"), ord("z") + 1)})
KEY_LABELS.update({str(index): str(index) for index in range(10)})

ALIASES = {
    "spacebar": "space",
    "escape": "esc",
    "return": "enter",
    "control": "ctrl",
    "left control": "left ctrl",
    "right control": "right ctrl",
    "lctrl": "left ctrl",
    "rctrl": "right ctrl",
    "lalt": "left alt",
    "ralt": "right alt",
    "alt gr": "right alt",
    "altgr": "right alt",
    "lshift": "left shift",
    "rshift": "right shift",
    "win": "windows",
    "lwin": "left windows",
    "rwin": "right windows",
    "super": "windows",
    "meta": "windows",
    "cmd": "windows",
    "left cmd": "left windows",
    "right cmd": "right windows",
    "middle": "mouse3",
    "middle button": "mouse3",
    "mouse middle": "mouse3",
    "mouse button 3": "mouse3",
    "mbutton": "mouse3",
    "wheel click": "mouse3",
    "wheel button": "mouse3",
    "mouse side 1": "mouse4",
    "side button 1": "mouse4",
    "mouse button 4": "mouse4",
    "xbutton1": "mouse4",
    "x1": "mouse4",
    "mouse x1": "mouse4",
    "back": "mouse4",
    "mouse side 2": "mouse5",
    "side button 2": "mouse5",
    "mouse button 5": "mouse5",
    "xbutton2": "mouse5",
    "x2": "mouse5",
    "mouse x2": "mouse5",
    "forward": "mouse5",
    "wheel left": "wheel_left",
    "horizontal wheel left": "wheel_left",
    "tilt left": "wheel_left",
    "hscroll left": "wheel_left",
    "wheel right": "wheel_right",
    "horizontal wheel right": "wheel_right",
    "tilt right": "wheel_right",
    "hscroll right": "wheel_right",
}
NEVER_BLOCK_KEYS = frozenset(
    {
        "space", "enter", "tab", "esc", "escape", "backspace", "delete",
        "caps lock", "ctrl", "left ctrl", "right ctrl", "alt", "left alt",
        "right alt", "shift", "left shift", "right shift", "windows",
        "left windows", "right windows",
    }
)
PULSE_MOUSE_TOKENS = frozenset({"mouse3", "wheel_left", "wheel_right"})
HOTKEY_CHOICES = tuple(
    [(token, KEY_LABELS[token]) for token in (
        "right alt", "left alt", "alt", "right ctrl", "left ctrl", "ctrl",
        "right shift", "left shift", "shift", "space", "caps lock", "tab",
    )]
    + [(f"f{index}", f"F{index}") for index in range(1, 13)]
    + [(letter, letter.upper()) for letter in "abcdefghijklmnopqrstuvwxyz"]
    + [(str(index), str(index)) for index in range(10)]
    + [
        ("mouse3", "鼠标中键 (Middle)"),
        ("mouse4", "鼠标侧键1 (Mouse4)"),
        ("mouse5", "鼠标侧键2 (Mouse5)"),
        ("wheel_left", "滚轮左倾 (WheelLeft)"),
        ("wheel_right", "滚轮右倾 (WheelRight)"),
    ]
)


def normalize_key(value: str | None) -> str:
    token = " ".join(str(value or "").strip().lower().replace("_", " ").split())
    return ALIASES.get(token, token)


def display_key(token: str) -> str:
    normalized = normalize_key(token)
    return KEY_LABELS.get(normalized, normalized)


def format_chord(primary: str, secondary: str) -> str:
    return f"{display_key(primary)} + {display_key(secondary)}"


def is_mouse_token(token: str) -> bool:
    return normalize_key(token) in {"mouse3", "mouse4", "mouse5", "wheel_left", "wheel_right"}


def is_pulse_token(token: str) -> bool:
    return normalize_key(token) in PULSE_MOUSE_TOKENS


def is_modifier_token(token: str) -> bool:
    return normalize_key(token) in {
        "alt", "right alt", "left alt", "ctrl", "right ctrl", "left ctrl",
        "shift", "right shift", "left shift", "windows", "left windows",
        "right windows",
    }


def choice_labels() -> list[str]:
    return [label for _, label in HOTKEY_CHOICES]


def token_from_label(label: str) -> str:
    for token, candidate in HOTKEY_CHOICES:
        if label == candidate:
            return token
    for token, candidate in KEY_LABELS.items():
        if label == candidate:
            return normalize_key(token)
    return normalize_key(label)


def label_from_token(token: str) -> str:
    normalized = normalize_key(token)
    for candidate, label in HOTKEY_CHOICES:
        if candidate == normalized:
            return label
    return display_key(normalized)


def ensure_known(token: str) -> str:
    normalized = normalize_key(token)
    if normalized not in KEY_LABELS:
        raise ValueError(f"不支持的按键：{token}")
    return normalized


def validate_hotkey_pair(primary: str, secondary: str) -> str | None:
    try:
        primary_n = ensure_known(primary)
        secondary_n = ensure_known(secondary)
    except ValueError as exc:
        return str(exc)
    if not primary_n or not secondary_n:
        return "主键和次键都不能为空"
    if primary_n == secondary_n:
        return "主键和次键不能相同"
    if is_pulse_token(primary_n):
        return "鼠标中键和滚轮倾斜只能设为次键"
    return None
