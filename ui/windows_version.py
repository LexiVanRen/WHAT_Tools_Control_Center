from __future__ import annotations

import ctypes
from ctypes import wintypes


def get_file_product_version(path: str) -> str:
    """
    Returns the Windows "ProductVersion" string from an EXE (like in Properties -> Details).
    If not found, returns "".
    """
    # --- Win32 APIs ---
    version = ctypes.WinDLL("version", use_last_error=True)

    GetFileVersionInfoSizeW = version.GetFileVersionInfoSizeW
    GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    GetFileVersionInfoSizeW.restype = wintypes.DWORD

    GetFileVersionInfoW = version.GetFileVersionInfoW
    GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID]
    GetFileVersionInfoW.restype = wintypes.BOOL

    VerQueryValueW = version.VerQueryValueW
    VerQueryValueW.argtypes = [wintypes.LPCVOID, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT)]
    VerQueryValueW.restype = wintypes.BOOL

    # --- Load version block ---
    dummy = wintypes.DWORD(0)
    size = GetFileVersionInfoSizeW(path, ctypes.byref(dummy))
    if not size:
        return ""

    buf = (ctypes.c_byte * size)()
    ok = GetFileVersionInfoW(path, 0, size, buf)
    if not ok:
        return ""

    # --- Find language/codepage from \VarFileInfo\Translation ---
    trans_ptr = ctypes.c_void_p()
    trans_len = wintypes.UINT(0)

    if not VerQueryValueW(buf, r"\VarFileInfo\Translation", ctypes.byref(trans_ptr), ctypes.byref(trans_len)):
        # No translation block; try common fallback
        return _query_string_value(buf, "040904B0", "ProductVersion")

    # trans_len is bytes; translations are pairs of WORD (lang, codepage)
    # We'll just use the first translation entry.
    class LANGANDCODEPAGE(ctypes.Structure):
        _fields_ = [("wLanguage", wintypes.WORD), ("wCodePage", wintypes.WORD)]

    # trans_len is bytes; number of entries = trans_len / sizeof(struct)
    entry = ctypes.cast(trans_ptr, ctypes.POINTER(LANGANDCODEPAGE))[0]
    lang_cp = f"{entry.wLanguage:04x}{entry.wCodePage:04x}".upper()

    # Query ProductVersion
    return _query_string_value(buf, lang_cp, "ProductVersion")


def _query_string_value(version_buf, lang_cp: str, key: str) -> str:
    version = ctypes.WinDLL("version", use_last_error=True)
    VerQueryValueW = version.VerQueryValueW
    VerQueryValueW.argtypes = [wintypes.LPCVOID, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT)]
    VerQueryValueW.restype = wintypes.BOOL

    ptr = ctypes.c_void_p()
    length = wintypes.UINT(0)
    subblock = fr"\StringFileInfo\{lang_cp}\{key}"

    if not VerQueryValueW(version_buf, subblock, ctypes.byref(ptr), ctypes.byref(length)):
        return ""

    if not ptr.value:
        return ""

    # length is in TCHARs including null; we can read as wchar string
    return ctypes.wstring_at(ptr.value).strip()
