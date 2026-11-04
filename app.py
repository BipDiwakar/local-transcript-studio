from __future__ import annotations

import re
import base64
import json
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Literal

import streamlit as st

from transcribe_local.config import (
    DEFAULT_MAX_FILE_MB,
    LANGUAGES,
    SUPPORTED_EXTENSIONS,
)
from transcribe_local.exporters import docx_bytes, pdf_bytes, txt_bytes
from transcribe_local.media import (
    MediaError,
    analyze_audio,
    extract_audio,
    format_duration,
    human_size,
    inspect_media,
    validate_extension,
)
from transcribe_local.transcription import get_model, transcribe_audio


QUALITY_PRESETS = {
    "Fast Draft": {"model": "base", "beam": 2, "normalize": False, "size": "~145 MB"},
    "Balanced": {"model": "small", "beam": 3, "normalize": True, "size": "~460 MB"},
    "High Accuracy": {"model": "medium", "beam": 5, "normalize": True, "size": "~1.5 GB"},
    "Best Accuracy": {"model": "large-v3", "beam": 5, "normalize": True, "size": "~3 GB"},
}

APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "Local Transcript Studio"
SESSION_PATH = APP_SUPPORT_DIR / "session.json"
VOCAB_PATH = APP_SUPPORT_DIR / "vocabulary_profiles.json"
PROJECTS_DIR = APP_SUPPORT_DIR / "projects"
RUNTIME_DIR = APP_SUPPORT_DIR / "runtime"
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
APP_LOGO_PATH = ASSETS_DIR / "app_logo.png"


st.set_page_config(
    page_title="Local Transcript Studio",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_styles() -> None:
    sidebar_css = ""
    if st.session_state.get("sidebar_open") is False:
        sidebar_css = """
        section[data-testid="stSidebar"] {
            display: none;
        }
        .block-container {
            max-width: min(1240px, calc(100vw - 28px));
        }
        """

    active_page = str(st.session_state.get("active_page", "Transcribe")).lower()
    active_nav_css = f"""
        div.st-key-nav_{active_page} button {{
            color: var(--ink) !important;
            background: rgba(217, 121, 72, 0.14) !important;
            border-color: rgba(217, 121, 72, 0.22) !important;
        }}
    """

    st.markdown(
        """
        <style>
        __SIDEBAR_CSS__
        __ACTIVE_NAV_CSS__
        :root {
            --ink: #f7f2eb;
            --muted: #aaa29a;
            --quiet: #7d766f;
            --line: rgba(247, 242, 235, 0.11);
            --line-strong: rgba(210, 121, 72, 0.34);
            --accent: #d97948;
            --accent-strong: #f0a16e;
            --accent-deep: #9c5334;
            --surface: rgba(27, 25, 23, 0.86);
            --surface-strong: rgba(34, 31, 28, 0.94);
            --surface-soft: rgba(247, 242, 235, 0.045);
            --danger: #fb7185;
        }

        .stApp {
            background:
                radial-gradient(circle at 18% 0%, rgba(217, 121, 72, 0.12), transparent 24rem),
                linear-gradient(145deg, #151412 0%, #1c1916 46%, #11100f 100%);
            color: var(--ink);
        }

        .block-container {
            max-width: min(1360px, calc(100vw - 28px));
            padding: 0.7rem 1rem 1.6rem;
        }

        [data-testid="stHeader"] {
            display: none;
        }

        section[data-testid="stSidebar"] {
            background:
                linear-gradient(180deg, rgba(29, 27, 25, 0.98), rgba(18, 17, 16, 0.98));
            border-right: 1px solid var(--line);
        }

        section[data-testid="stSidebar"] > div {
            padding-top: 1.1rem;
        }

        button[title="Close sidebar"],
        button[title="Open sidebar"] {
            border: 1px solid rgba(247, 242, 235, 0.14) !important;
            background: rgba(247, 242, 235, 0.08) !important;
            border-radius: 10px !important;
            color: var(--ink) !important;
        }

        [data-testid="stSidebarCollapseButton"] {
            display: none !important;
        }

        .app-title {
            margin: 0;
            color: var(--ink);
            font-size: clamp(1.8rem, 2.7vw, 2.75rem);
            line-height: 1;
            letter-spacing: 0;
            font-weight: 780;
        }

        .app-subtitle {
            color: var(--muted);
            margin: 0.3rem auto 0.65rem;
            max-width: 620px;
            font-size: 0.88rem;
            text-align: center;
        }

        .hero-header {
            padding: 0 0 0.4rem;
            margin-bottom: 0.1rem;
        }

        .hero-title-row {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.8rem;
        }

        .hero-logo {
            display: block;
            width: 44px;
            height: 44px;
            border-radius: 11px;
            box-shadow: 0 14px 34px rgba(0, 0, 0, 0.24);
            flex: 0 0 auto;
        }

        .hero-kicker {
            color: var(--accent-strong);
            font-size: 0.75rem;
            font-weight: 760;
            letter-spacing: 0.08em;
            text-align: center;
            text-transform: uppercase;
            margin-bottom: 0.18rem;
        }

        .menu-toggle-row {
            position: sticky;
            top: 0.35rem;
            z-index: 20;
            width: fit-content;
            margin-bottom: 0.1rem;
        }

        .sidebar-brand {
            display: flex;
            align-items: center;
            gap: 0.58rem;
            color: var(--ink);
            font-size: 1.05rem;
            font-weight: 760;
            margin-bottom: 0.15rem;
        }

        .sidebar-logo {
            width: 34px;
            height: 34px;
            border-radius: 9px;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.24);
            flex: 0 0 auto;
        }

        .sidebar-caption {
            color: var(--muted);
            font-size: 0.78rem;
            margin-bottom: 1rem;
        }

        .sidebar-section {
            color: var(--quiet);
            font-size: 0.68rem;
            font-weight: 780;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin: 1rem 0 0.35rem;
        }

        .sidebar-hint {
            color: var(--quiet);
            font-size: 0.74rem;
            line-height: 1.35;
            margin-top: 0.85rem;
        }

        section[data-testid="stSidebar"] .stButton > button {
            justify-content: flex-start;
            min-height: 2.35rem;
            padding: 0.35rem 0.7rem;
            color: #e8dfd6;
            background: transparent;
            border-color: transparent;
            box-shadow: none;
        }

        section[data-testid="stSidebar"] .stButton > button p {
            width: 100%;
            text-align: left;
        }

        .quiet-panel {
            border: 1px solid var(--line);
            background: rgba(247, 242, 235, 0.035);
            border-radius: 12px;
            padding: 0.8rem 0.85rem;
        }

        div[data-testid="stVerticalBlock"] {
            gap: 0.72rem;
        }

        .product-header {
            position: relative;
            overflow: hidden;
            min-height: 0;
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: clamp(0.85rem, 1.7vw, 1.25rem);
            margin: 0 0 0.6rem;
            color: var(--ink);
            background:
                linear-gradient(135deg, rgba(39, 33, 28, 0.96), rgba(29, 25, 21, 0.92) 52%, rgba(85, 48, 30, 0.78)),
                radial-gradient(circle at 82% 18%, rgba(242, 165, 111, 0.18), transparent 17rem);
            box-shadow: 0 28px 90px rgba(0, 0, 0, 0.30);
        }

        .product-header::before {
            content: "";
            position: absolute;
            inset: auto -8% -38% 42%;
            height: 220px;
            background:
                repeating-linear-gradient(
                    90deg,
                    rgba(242,165,111,0.09) 0 7px,
                    transparent 7px 16px
                );
            transform: rotate(-8deg);
            mask-image: linear-gradient(90deg, transparent, black 20%, black 80%, transparent);
        }

        .top-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            position: relative;
            z-index: 1;
            margin-bottom: clamp(0.55rem, 1vw, 0.85rem);
        }

        .top-pill {
            border: 1px solid rgba(242, 165, 111, 0.26);
            background: rgba(255, 246, 235, 0.07);
            color: #f7d7bd;
            border-radius: 999px;
            padding: 0.48rem 0.72rem;
            font-size: 0.78rem;
            font-weight: 740;
            backdrop-filter: blur(18px);
        }

        .hero-content {
            display: grid;
            grid-template-columns: minmax(0, 1fr) minmax(280px, 420px);
            align-items: center;
            gap: 1.35rem;
            position: relative;
            z-index: 1;
        }

        .brand-mark {
            color: var(--accent-strong);
            font-size: 0.78rem;
            font-weight: 760;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin-bottom: 0.35rem;
        }

        .product-header h1 {
            color: var(--ink);
            font-size: clamp(1.95rem, 3.2vw, 3.15rem);
            line-height: 0.98;
            letter-spacing: 0;
            margin: 0;
            max-width: 880px;
        }

        .product-header p {
            color: #d8cfc6;
            max-width: 400px;
            margin: 0 0 0.2rem;
            line-height: 1.55;
            font-size: 0.94rem;
        }

        .hero-metrics {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 0.65rem;
        }

        .metric {
            min-height: 60px;
            border-radius: 8px;
            border: 1px solid rgba(242, 165, 111, 0.18);
            background: rgba(255, 246, 235, 0.07);
            padding: 0.58rem 0.66rem;
            backdrop-filter: blur(18px);
        }

        .metric strong {
            display: block;
            color: #fff7ed;
            font-size: 1.1rem;
            margin-bottom: 0.18rem;
        }

        .metric span {
            color: #c8b8aa;
            font-size: 0.8rem;
        }

        .panel-title {
            color: var(--ink);
            font-weight: 760;
            font-size: 1.05rem;
            margin-bottom: 0.25rem;
        }

        .panel-caption {
            color: var(--muted);
            font-size: 0.88rem;
            margin-bottom: 0.9rem;
        }

        .flow-strip {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.55rem;
            margin: 0 0 0.75rem;
        }

        .flow-step {
            display: flex;
            align-items: center;
            gap: 0.55rem;
            border: 1px solid var(--line);
            background: rgba(33, 29, 25, 0.76);
            border-radius: 8px;
            padding: 0.58rem 0.7rem;
            color: #cfc3b7;
            font-size: 0.85rem;
            box-shadow: 0 12px 34px rgba(0, 0, 0, 0.16);
        }

        .flow-step strong {
            display: grid;
            place-items: center;
            width: 1.55rem;
            height: 1.55rem;
            border-radius: 999px;
            background: rgba(217, 119, 69, 0.16);
            color: var(--accent-strong);
            font-size: 0.78rem;
        }

        div[data-testid="stFileUploader"] {
            border: 1px dashed rgba(242, 165, 111, 0.44);
            border-radius: 8px;
            background:
                linear-gradient(135deg, rgba(255, 246, 235, 0.075), rgba(217, 119, 69, 0.08));
            padding: 0.85rem;
            margin-bottom: 0.75rem;
        }

        div[data-testid="stFileUploader"] section {
            border: 0;
            background: transparent;
            padding: 0.15rem 0;
        }

        div[data-testid="stFileUploader"] button {
            min-height: 2.55rem;
            border-radius: 8px;
            background: rgba(242, 165, 111, 0.10);
            border: 1px solid rgba(242, 165, 111, 0.30);
            color: #ffd7b8;
            font-weight: 760;
        }

        div[data-testid="stFileUploader"] small,
        div[data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] {
            color: var(--muted);
        }

        div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
            border-radius: 8px;
            border-color: rgba(244, 238, 231, 0.14);
            background: rgba(20, 18, 16, 0.84);
            color: var(--ink);
        }

        .stTextInput input {
            border-radius: 8px;
            border-color: rgba(244, 238, 231, 0.14);
            background: rgba(20, 18, 16, 0.84);
            color: var(--ink);
            min-height: 2.55rem;
        }

        button[data-baseweb="tab"] {
            color: #d6c9bc;
            border-radius: 8px;
            font-weight: 720;
            min-height: 2.55rem;
            padding: 0.35rem 0.75rem;
            background: rgba(255, 246, 235, 0.045);
            border: 1px solid rgba(244, 238, 231, 0.10);
        }

        button[data-baseweb="tab"][aria-selected="true"] {
            color: #fff7ed;
            background: linear-gradient(135deg, rgba(217, 119, 69, 0.28), rgba(255, 246, 235, 0.08));
            border-color: rgba(242, 165, 111, 0.34);
            box-shadow: inset 0 0 0 1px rgba(255, 246, 235, 0.04);
        }

        [data-testid="stTabs"] [data-baseweb="tab-list"] {
            gap: 0.45rem;
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 0.35rem;
            margin-bottom: 0.75rem;
            background: rgba(20, 18, 16, 0.64);
        }

        [data-testid="stTabs"] [data-baseweb="tab-highlight"] {
            display: none;
        }

        [data-testid="stExpander"] {
            border-color: var(--line);
            background: rgba(255, 246, 235, 0.035);
            border-radius: 8px;
        }

        .section-rule {
            height: 1px;
            background: linear-gradient(90deg, rgba(242, 165, 111, 0.38), rgba(244, 238, 231, 0.08), transparent);
            margin: 0.35rem 0 0.75rem;
        }

        .section-kicker {
            color: var(--accent-strong);
            font-size: 0.75rem;
            font-weight: 760;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            margin: 0.9rem 0 0.35rem;
        }

        .worktop {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            margin-bottom: 0.45rem;
        }

        .worktop strong {
            color: var(--ink);
            font-size: 1rem;
        }

        .worktop span {
            color: var(--quiet);
            font-size: 0.78rem;
        }

        .setup-note {
            color: var(--quiet);
            font-size: 0.76rem;
            line-height: 1.35;
            margin: -0.2rem 0 0.15rem;
        }

        .keyterms-note {
            color: #d5c6b7;
            font-size: 0.82rem;
            margin: -0.2rem 0 0.2rem;
        }

        label, p, span, div {
            letter-spacing: 0;
        }

        div[data-testid="stWidgetLabel"] p,
        div[data-testid="stMarkdownContainer"] p,
        .stCaptionContainer {
            color: var(--muted);
        }

        div[data-testid="stFileUploaderDropzone"] {
            color: var(--muted);
        }

        div[data-testid="stFileUploaderDropzone"] svg,
        div[data-testid="stFileUploader"] svg {
            color: var(--accent-strong);
            fill: var(--accent-strong);
        }

        div[data-testid="stFileUploaderFile"] {
            background: rgba(20, 18, 16, 0.62);
            border: 1px solid rgba(244, 238, 231, 0.12);
            border-radius: 8px;
        }

        [data-baseweb="popover"] {
            background: #211d19;
            color: var(--ink);
        }

        ul[role="listbox"] {
            background: #211d19;
            border: 1px solid var(--line);
        }

        .meta-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 0.6rem;
            margin: 0.8rem 0 0.5rem;
        }

        .meta-item {
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 0.62rem 0.66rem;
            background: var(--surface-soft);
            min-width: 0;
        }

        .meta-label {
            color: var(--muted);
            display: block;
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            margin-bottom: 0.2rem;
        }

        .meta-value {
            color: #fff7ed;
            display: block;
            font-size: 0.92rem;
            font-weight: 650;
            overflow-wrap: anywhere;
        }

        .status-strip {
            display: flex;
            align-items: center;
            gap: 0.45rem;
            background: linear-gradient(135deg, rgba(217, 119, 69, 0.12), rgba(255, 246, 235, 0.055));
            color: #f8c9a8;
            border: 1px solid rgba(242, 165, 111, 0.18);
            border-radius: 8px;
            padding: 0.65rem 0.75rem;
            font-size: 0.88rem;
            margin-top: 0.75rem;
            margin-bottom: 0.35rem;
        }

        .status-dot {
            width: 0.55rem;
            height: 0.55rem;
            border-radius: 99px;
            background: var(--accent);
            box-shadow: 0 0 0 4px rgba(217, 119, 69, 0.16);
            flex: 0 0 auto;
        }

        .stButton > button,
        .stDownloadButton > button {
            border-radius: 8px;
            min-height: 2.65rem;
            font-weight: 720;
            border: 1px solid rgba(244, 238, 231, 0.14);
            background: rgba(255, 246, 235, 0.065);
            color: #f4eee7;
            transition: transform 150ms ease, box-shadow 150ms ease, border-color 150ms ease;
        }

        .stButton > button p,
        .stDownloadButton > button p {
            color: inherit;
            font-weight: inherit;
        }

        .stButton > button:hover,
        .stDownloadButton > button:hover {
            transform: translateY(-1px);
            border-color: var(--line-strong);
            box-shadow: 0 12px 30px rgba(0, 0, 0, 0.24);
        }

        .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #f2a56f, #d97745 54%, #9a4f2e);
            color: #1b110d !important;
            border: 0;
            font-weight: 820;
            box-shadow: 0 16px 36px rgba(217, 119, 69, 0.22);
        }

        .stButton > button[kind="primary"] p {
            color: #1b110d !important;
            font-weight: 820;
        }

        .stButton > button:focus,
        .stDownloadButton > button:focus,
        div[data-testid="stFileUploader"] button:focus {
            box-shadow: 0 0 0 4px rgba(217, 119, 69, 0.18);
            outline: none;
        }

        .stTextArea textarea {
            min-height: 0;
            border-radius: 8px;
            border-color: rgba(244, 238, 231, 0.14);
            color: #f4eee7;
            font-size: 0.96rem;
            line-height: 1.58;
            background:
                linear-gradient(180deg, rgba(27, 24, 21, 0.98), rgba(20, 18, 16, 0.98));
        }

        .stTextArea textarea::placeholder {
            color: #83766c;
        }

        .small-note {
            color: var(--muted);
            font-size: 0.84rem;
            line-height: 1.45;
            margin-top: 0.7rem;
        }

        .export-caption {
            color: var(--muted);
            font-size: 0.82rem;
            margin: 0.2rem 0 0.45rem;
        }

        @media (max-width: 860px) {
            .product-header {
                min-height: auto;
            }

            .hero-content {
                grid-template-columns: 1fr;
            }

            .hero-metrics,
            .flow-strip {
                grid-template-columns: 1fr 1fr;
            }

            .block-container {
                max-width: 100%;
                padding: 0.75rem 0.75rem 2rem;
            }

            .product-header h1 {
                font-size: clamp(2.25rem, 11vw, 3.4rem);
            }

            .top-row {
                align-items: flex-start;
                flex-direction: column;
                margin-bottom: 1.4rem;
            }
        }

        @media (max-width: 520px) {
            .product-header {
                padding: 0.9rem;
            }

            .top-row {
                flex-direction: row;
                flex-wrap: wrap;
                gap: 0.45rem;
                margin-bottom: 0.85rem;
            }

            .top-pill {
                padding: 0.38rem 0.54rem;
                font-size: 0.72rem;
            }

            .hero-content {
                gap: 0.75rem;
            }

            .product-header h1 {
                font-size: clamp(2rem, 9vw, 2.55rem);
                line-height: 0.98;
            }

            .product-header p {
                font-size: 0.88rem;
                line-height: 1.45;
            }

            .hero-metrics {
                display: none;
            }

            .flow-strip {
                grid-template-columns: 1fr 1fr;
                gap: 0.45rem;
            }

            .flow-step {
                padding: 0.48rem 0.55rem;
                font-size: 0.78rem;
            }

            .meta-grid {
                grid-template-columns: 1fr;
            }
        }
        </style>
        """
        .replace("__SIDEBAR_CSS__", sidebar_css)
        .replace("__ACTIVE_NAV_CSS__", active_nav_css),
        unsafe_allow_html=True,
    )


def initialize_state() -> None:
    saved = load_session()
    saved_transcript = saved.get("transcript_text", "")
    defaults = {
        "transcript_text": saved_transcript,
        "transcript_editor": saved_transcript,
        "source_filename": saved.get("source_filename", ""),
        "selected_language_label": saved.get("selected_language_label", "English"),
        "detected_language": "",
        "detected_probability": None,
        "last_export_time": None,
        "export_message": "",
        "last_saved_path": "",
        "last_saved_folder": "",
        "segments": saved.get("segments", []),
        "key_terms": saved.get("key_terms", ""),
        "project_name": saved.get("project_name", ""),
        "current_project_file": saved.get("current_project_file", ""),
        "notes_text": saved.get("notes_text", ""),
        "uploader_version": 0,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def load_session() -> dict:
    try:
        return json.loads(SESSION_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


@st.cache_data(show_spinner=False)
def logo_data_uri() -> str:
    if not APP_LOGO_PATH.exists():
        return ""
    encoded = base64.b64encode(APP_LOGO_PATH.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def autosave_session() -> None:
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "transcript_text": st.session_state.get("transcript_text", ""),
        "source_filename": st.session_state.get("source_filename", ""),
        "selected_language_label": st.session_state.get("selected_language_label", "English"),
        "segments": st.session_state.get("segments", []),
        "key_terms": st.session_state.get("key_terms", ""),
        "project_name": st.session_state.get("project_name", ""),
        "current_project_file": st.session_state.get("current_project_file", ""),
        "notes_text": st.session_state.get("notes_text", ""),
    }
    SESSION_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def set_transcript_text(text: str, *, save: bool = True) -> None:
    st.session_state.transcript_text = text
    st.session_state.transcript_editor = text
    if save:
        autosave_session()


def load_vocab_profiles() -> dict[str, str]:
    try:
        return json.loads(VOCAB_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_vocab_profile(name: str, terms: str) -> None:
    if not name.strip() or not terms.strip():
        return
    VOCAB_PATH.parent.mkdir(parents=True, exist_ok=True)
    profiles = load_vocab_profiles()
    profiles[name.strip()] = terms.strip()
    VOCAB_PATH.write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")


def project_path(name: str) -> Path:
    return PROJECTS_DIR / f"{safe_download_stem(name)}.json"


def list_projects() -> list[dict[str, str]]:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    projects: list[dict[str, str]] = []
    for path in PROJECTS_DIR.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        projects.append(
            {
                "file": path.name,
                "name": payload.get("name") or path.stem,
                "saved_at": payload.get("saved_at") or "",
                "source_filename": payload.get("source_filename") or "",
            }
        )
    return sorted(projects, key=lambda item: item["saved_at"], reverse=True)


def save_project(name: str) -> Path:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    source_name = Path(st.session_state.get("source_filename") or "").stem
    project_name = name.strip() or source_name or "Untitled Transcript"
    payload = {
        "name": project_name,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "transcript_text": st.session_state.get("transcript_text", ""),
        "source_filename": st.session_state.get("source_filename", ""),
        "selected_language_label": st.session_state.get("selected_language_label", "English"),
        "segments": st.session_state.get("segments", []),
        "key_terms": st.session_state.get("key_terms", ""),
        "notes_text": st.session_state.get("notes_text", ""),
    }
    path = project_path(project_name)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    st.session_state.current_project_file = path.name
    autosave_session()
    return path


def load_project(project_file: str) -> None:
    path = PROJECTS_DIR / project_file
    if not path.exists():
        path = project_path(project_file)
    payload = json.loads(path.read_text(encoding="utf-8"))
    for key in ("source_filename", "selected_language_label", "segments", "key_terms", "notes_text"):
        st.session_state[key] = payload.get(key, "" if key != "segments" else [])
    set_transcript_text(payload.get("transcript_text", ""), save=False)
    st.session_state.project_name = payload.get("name") or path.stem
    st.session_state.current_project_file = path.name
    st.session_state.export_message = ""
    autosave_session()


def open_in_finder(path: Path) -> None:
    target = path if path.is_dir() else path.parent
    subprocess.run(["open", str(target)], check=False)


def huggingface_cache_dir() -> Path:
    return Path.home() / ".cache" / "huggingface" / "hub"


def directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    seen: set[tuple[int, int]] = set()
    for item in path.rglob("*"):
        try:
            if item.is_symlink() or not item.is_file():
                continue
            stat = item.stat()
            identity = (stat.st_dev, stat.st_ino)
            if identity not in seen:
                seen.add(identity)
                total += stat.st_size
        except OSError:
            continue
    return total


def model_cache_entries() -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    labels_by_model: dict[str, str] = {}
    for label, preset in QUALITY_PRESETS.items():
        labels_by_model[str(preset["model"])] = label

    prefix = "models--Systran--faster-whisper-"
    for path in huggingface_cache_dir().glob(f"{prefix}*"):
        model = path.name.removeprefix(prefix)
        entries.append(
            {
                "label": labels_by_model.get(model, "Other model"),
                "model": model,
                "path": path,
                "size": directory_size(path),
            }
        )
    return sorted(entries, key=lambda entry: int(entry["size"]), reverse=True)


def uploaded_media_preview(uploaded_file) -> tuple[object, dict[str, str]]:
    signature = (uploaded_file.name, uploaded_file.size)
    if st.session_state.get("media_signature") == signature:
        return st.session_state.media_details, st.session_state.audio_quality

    with tempfile.TemporaryDirectory(prefix="local-transcript-preview-") as temp_dir_name:
        input_path = Path(temp_dir_name) / uploaded_file.name
        input_path.write_bytes(uploaded_file.getbuffer())
        details = inspect_media(input_path, uploaded_file.name)
        quality = analyze_audio(input_path)

    st.session_state.media_signature = signature
    st.session_state.media_details = details
    st.session_state.audio_quality = quality
    return details, quality


def safe_download_stem(filename: str) -> str:
    stem = Path(filename).stem or "transcription"
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._")
    return cleaned or "transcription"


def export_folder() -> Path:
    folder = Path.home() / "Downloads" / "Local Transcript Studio Exports"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def export_path(filename: str, extension: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return export_folder() / f"{safe_download_stem(filename)}-{timestamp}.{extension}"


def save_export(
    export_type: Literal["txt", "docx", "pdf"],
    filename: str,
    language: str,
    text: str,
    created_at: datetime,
) -> Path:
    path = export_path(filename, export_type)
    if export_type == "txt":
        data = txt_bytes(filename, language, text, created_at)
    elif export_type == "docx":
        data = docx_bytes(filename, language, text, created_at)
    else:
        data = pdf_bytes(filename, language, text, created_at)
    path.write_bytes(data)
    return path


def format_timestamp(seconds: float) -> str:
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def timestamped_text(segments: list[dict]) -> str:
    lines = []
    for segment in segments:
        lines.append(f"[{format_timestamp(segment['start'])}] {segment['text']}")
    return "\n\n".join(lines)


def export_text_for_template(template: str, transcript: str, segments: list[dict]) -> str:
    if template == "Timestamped":
        return timestamped_text(segments) if segments else transcript
    if template == "Meeting Notes":
        return f"{meeting_notes(transcript)}\n\nTranscript\n\n{transcript}"
    return transcript


def cleanup_transcript(text: str) -> str:
    cleaned = re.sub(r"\b(um+|uh+|erm+|hmm+|you know|like)\b[,\s]*", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(\w+)(\s+\1\b){2,}", r"\1", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+([,.!?;:])", r"\1", cleaned)
    cleaned = re.sub(r"([.!?])([A-Za-z])", r"\1 \2", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def refine_transcript_format(text: str) -> str:
    cleaned = cleanup_transcript(text)
    if not cleaned:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    polished: list[str] = []
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        sentence = sentence[0].upper() + sentence[1:] if sentence else sentence
        polished.append(sentence)

    paragraphs = []
    for index in range(0, len(polished), 4):
        paragraphs.append(" ".join(polished[index : index + 4]))
    return "\n\n".join(paragraphs) if paragraphs else cleaned


def meeting_notes(text: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
    summary = sentences[:5] or [text[:220].strip()]
    action_keywords = ("need to", "should", "todo", "action", "follow up", "next", "must", "please")
    actions = [s for s in sentences if any(k in s.lower() for k in action_keywords)][:8]
    return (
        "Summary\n"
        + "\n".join(f"- {s}" for s in summary)
        + "\n\nAction Items\n"
        + ("\n".join(f"- {s}" for s in actions) if actions else "- Review transcript and add action owners.")
    )


def speaker_format(text: str, speakers: str) -> str:
    names = [name.strip() for name in speakers.split(",") if name.strip()]
    if not names:
        return text
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    return "\n\n".join(f"{names[i % len(names)]}: {p}" for i, p in enumerate(paragraphs))


def reliability_warnings(text: str) -> list[str]:
    warnings: list[str] = []
    words = [w.lower().strip(".,!?;:") for w in text.split() if w.strip()]
    if len(words) < 12 and text:
        warnings.append("Transcript is very short; check whether the audio is quiet or mostly silence.")
    if len(words) > 80 and len(set(words)) / len(words) < 0.22:
        warnings.append("Transcript looks repetitive; try Retry English or High Accuracy.")
    return warnings


def copy_button(text: str) -> None:
    if st.button("Copy Text", use_container_width=True, disabled=not bool(text.strip())):
        try:
            subprocess.run(["pbcopy"], input=text, text=True, check=True)
            st.toast("Transcript copied")
        except (OSError, subprocess.CalledProcessError) as exc:
            st.error(f"Could not copy the transcript: {exc}")


def render_header() -> None:
    st.markdown(
        """
        <div class="product-header">
            <div class="top-row">
                <div class="top-pill">Private local transcription</div>
                <div class="top-pill">Audio and video</div>
            </div>
            <div class="hero-content">
                <div>
                    <div class="brand-mark">Local Transcript Studio</div>
                    <h1>Turn recordings into clean text.</h1>
                </div>
                <div>
                    <p>Upload a file, choose a language, transcribe locally, then export the edited transcript.</p>
                    <div class="hero-metrics">
                        <div class="metric"><strong>20+ languages</strong><span>Auto or manual</span></div>
                        <div class="metric"><strong>TXT, DOCX, PDF</strong><span>Export ready</span></div>
                    </div>
                </div>
            </div>
        </div>
        <div class="flow-strip">
            <div class="flow-step"><strong>1</strong><span>Upload file</span></div>
            <div class="flow-step"><strong>2</strong><span>Choose language</span></div>
            <div class="flow-step"><strong>3</strong><span>Transcribe locally</span></div>
            <div class="flow-step"><strong>4</strong><span>Edit and export</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_file_meta(uploaded_file) -> object | None:
    if uploaded_file is None:
        return None

    try:
        validate_extension(uploaded_file.name)
    except MediaError as exc:
        st.error(str(exc))
        return None

    size_mb = uploaded_file.size / (1024 * 1024)
    if size_mb > DEFAULT_MAX_FILE_MB:
        st.error(f"File is too large: {size_mb:.1f} MB. Current local limit is {DEFAULT_MAX_FILE_MB} MB.")
        return None

    try:
        details, quality = uploaded_media_preview(uploaded_file)
        st.session_state.audio_quality = quality
    except MediaError as exc:
        st.error(str(exc))
        return None

    st.markdown(
        f"""
        <div class="meta-grid">
            <div class="meta-item"><span class="meta-label">File</span><span class="meta-value">{details.name}</span></div>
            <div class="meta-item"><span class="meta-label">Type</span><span class="meta-value">{details.extension.upper()}</span></div>
            <div class="meta-item"><span class="meta-label">Size</span><span class="meta-value">{human_size(details.size_bytes)}</span></div>
            <div class="meta-item"><span class="meta-label">Duration</span><span class="meta-value">{format_duration(details.duration_seconds)}</span></div>
        </div>
        <div class="status-strip"><span class="status-dot"></span><span>Ready to transcribe locally.</span></div>
        """,
        unsafe_allow_html=True,
    )
    quality = st.session_state.get("audio_quality")
    if quality:
        st.caption(
            f"Audio quality: {quality['quality']} | Mean: {quality['mean_volume']} | "
            f"Peak: {quality['max_volume']} | {quality['suggestion']}"
        )
    return details


def run_transcription(uploaded_file, language_label: str, quality_label: str) -> None:
    if uploaded_file is None:
        st.warning("Upload a supported audio or video file first.")
        return

    with tempfile.TemporaryDirectory(prefix="local-transcript-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        input_path = temp_dir / uploaded_file.name
        audio_path = temp_dir / "audio.wav"
        input_path.write_bytes(uploaded_file.getbuffer())

        progress = st.progress(0, text="Preparing media")

        def update_progress(value: float, label: str) -> None:
            progress.progress(value, text=label)

        try:
            details = inspect_media(input_path, uploaded_file.name)
            update_progress(0.04, "Extracting audio with ffmpeg")
            preset = QUALITY_PRESETS[quality_label]
            extract_audio(input_path, audio_path, normalize=bool(preset["normalize"]))
            selected_model = str(preset["model"])
            accepted_auto_languages = {code for code in LANGUAGES.values() if code}
            result = transcribe_audio(
                audio_path,
                model_name=selected_model,
                language_code=LANGUAGES[language_label],
                initial_prompt=build_initial_prompt(st.session_state.get("key_terms", "")),
                hotwords=build_hotwords(st.session_state.get("key_terms", "")),
                beam_size=int(preset["beam"]),
                accepted_auto_languages=accepted_auto_languages,
                progress_callback=update_progress,
            )
        except Exception as exc:
            progress.empty()
            st.error(f"Transcription failed: {exc}")
            return

    set_transcript_text(result.text, save=False)
    st.session_state.source_filename = details.name
    if not st.session_state.get("project_name", "").strip():
        st.session_state.project_name = Path(details.name).stem
    st.session_state.selected_language_label = language_label
    st.session_state.detected_language = result.detected_language or ""
    st.session_state.detected_probability = result.detected_probability
    st.session_state.last_export_time = datetime.now()
    st.session_state.export_message = ""
    st.session_state.segments = [
        {"start": segment.start, "end": segment.end, "text": segment.text}
        for segment in result.segments
    ]
    autosave_session()
    if result.retry_reason:
        st.warning(f"Auto-detect looked unreliable ({result.retry_reason}), so the app retried as English.")
    st.success(f"Transcription finished. Segments processed: {result.segment_count}.")


def build_initial_prompt(key_terms: str) -> str | None:
    cleaned_terms = ", ".join(term.strip() for term in key_terms.split(",") if term.strip())
    if not cleaned_terms:
        return None
    return (
        "Transcribe the audio exactly. Preserve punctuation, names, acronyms, product names, "
        f"and these key terms exactly when spoken: {cleaned_terms}."
    )


def build_hotwords(key_terms: str) -> str | None:
    cleaned_terms = ", ".join(term.strip() for term in key_terms.split(",") if term.strip())
    return cleaned_terms or None


def render_exports() -> None:
    text = st.session_state.get("transcript_text", "")
    filename = st.session_state.get("project_name") or st.session_state.get("source_filename") or "transcription"
    selected_language = st.session_state.get("selected_language_label") or "Auto-detect"
    created_at = st.session_state.get("last_export_time") or datetime.now()
    segments = st.session_state.get("segments", [])
    template = st.selectbox(
        "Export template",
        ["Clean Transcript", "Timestamped", "Meeting Notes"],
        label_visibility="collapsed",
    )
    export_text = export_text_for_template(template, text, segments)

    col_copy, col_txt, col_docx, col_pdf = st.columns(4)
    with col_copy:
        copy_button(export_text)
    with col_txt:
        if st.button("Save TXT", use_container_width=True, disabled=not bool(text.strip())):
            path = save_export("txt", filename, selected_language, export_text, created_at)
            st.session_state.export_message = f"Saved TXT: {path.name}"
            st.session_state.last_saved_path = str(path)
            st.session_state.last_saved_folder = str(path.parent)
    with col_docx:
        if st.button("Save Word", use_container_width=True, disabled=not bool(text.strip())):
            path = save_export("docx", filename, selected_language, export_text, created_at)
            st.session_state.export_message = f"Saved Word: {path.name}"
            st.session_state.last_saved_path = str(path)
            st.session_state.last_saved_folder = str(path.parent)
    with col_pdf:
        if st.button("Save PDF", use_container_width=True, disabled=not bool(text.strip())):
            path = save_export("pdf", filename, selected_language, export_text, created_at)
            st.session_state.export_message = f"Saved PDF: {path.name}"
            st.session_state.last_saved_path = str(path)
            st.session_state.last_saved_folder = str(path.parent)

    if st.session_state.get("export_message"):
        st.success(st.session_state.export_message)
        folder = st.session_state.get("last_saved_folder")
        if folder and st.button("Open saved folder", use_container_width=True):
            open_in_finder(Path(folder))


def render_app_header(title: str, subtitle: str) -> None:
    logo = logo_data_uri()
    logo_html = f'<img class="hero-logo" src="{logo}" alt="Local Transcript Studio logo" />' if logo else ""
    st.markdown(
        f"""
        <div class="hero-header">
            <div class="hero-kicker">{title}</div>
            <div class="hero-title-row">
                {logo_html}
                <h1 class="app-title">Local Transcript Studio</h1>
            </div>
            <p class="app-subtitle">{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def clear_workspace() -> None:
    for key in (
        "transcript_text",
        "transcript_editor",
        "source_filename",
        "selected_language_label",
        "detected_language",
        "detected_probability",
        "last_export_time",
        "export_message",
        "last_saved_path",
        "last_saved_folder",
        "segments",
        "notes_text",
        "compare_text",
        "project_name",
        "current_project_file",
        "media_signature",
        "media_details",
        "audio_quality",
    ):
        st.session_state.pop(key, None)
    st.session_state.uploader_version = st.session_state.get("uploader_version", 0) + 1
    if SESSION_PATH.exists():
        SESSION_PATH.unlink()
    st.rerun()


def render_transcribe_page() -> None:
    render_app_header("Private transcription", "Your recording stays on this Mac.")
    setup_col, transcript_col = st.columns([0.34, 0.66], gap="large")

    with setup_col:
        st.markdown('<div class="worktop"><strong>Source</strong></div>', unsafe_allow_html=True)
        project_col, save_col = st.columns([0.7, 0.3], gap="small", vertical_alignment="bottom")
        with project_col:
            st.text_input(
                "Project name",
                key="project_name",
                placeholder="Meeting or project name",
                on_change=autosave_session,
            )
        with save_col:
            if st.button(
                "Save",
                key="save_project_inline",
                use_container_width=True,
                disabled=not bool(st.session_state.get("transcript_text", "").strip()),
                help="Save or update this project",
            ):
                save_project(st.session_state.get("project_name", ""))
                st.toast("Project saved")

        uploaded_file = st.file_uploader(
            "Audio or video file",
            type=sorted(SUPPORTED_EXTENSIONS),
            accept_multiple_files=False,
            key=f"upload_file_{st.session_state.get('uploader_version', 0)}",
        )
        render_file_meta(uploaded_file)

        language_col, quality_col = st.columns(2, gap="small")
        with language_col:
            language_label = st.selectbox(
                "Language",
                options=list(LANGUAGES.keys()),
                index=1,
                help="Choose the language when you know it; this is more reliable than auto-detect.",
            )
        with quality_col:
            quality_label = st.selectbox(
                "Quality",
                options=list(QUALITY_PRESETS.keys()),
                index=1,
                help="Balanced is the recommended speed, accuracy, and storage setting.",
            )

        preset = QUALITY_PRESETS[quality_label]
        st.markdown(
            f'<div class="setup-note">{preset["model"]} model · {preset["size"]} download</div>',
            unsafe_allow_html=True,
        )

        with st.expander("Vocabulary and audio options", expanded=False):
            st.text_area(
                "Key terms",
                key="key_terms",
                height=110,
                placeholder="Names, acronyms, project terms, technical vocabulary",
            )
            if uploaded_file is not None:
                st.audio(uploaded_file.getvalue())

            retry_a, retry_b = st.columns(2)
            with retry_a:
                if st.button("Retry English", use_container_width=True, disabled=uploaded_file is None):
                    run_transcription(uploaded_file, "English", quality_label)
            with retry_b:
                if st.button("Retry High", use_container_width=True, disabled=uploaded_file is None):
                    run_transcription(uploaded_file, language_label, "High Accuracy")

        action_col, clear_col = st.columns([0.68, 0.32])
        with action_col:
            if st.button("Transcribe", type="primary", use_container_width=True, disabled=uploaded_file is None):
                run_transcription(uploaded_file, language_label, quality_label)
        with clear_col:
            if st.button("Clear", use_container_width=True):
                clear_workspace()

    with transcript_col:
        detected = st.session_state.get("detected_language")
        probability = st.session_state.get("detected_probability")
        status = f"Detected: {detected} ({probability:.0%})" if detected and probability is not None else "Ready for transcript"
        st.markdown(f'<div class="worktop"><strong>Transcript</strong><span>{status}</span></div>', unsafe_allow_html=True)

        if st.session_state.get("transcript_editor") != st.session_state.get("transcript_text", ""):
            st.session_state.transcript_text = st.session_state.get("transcript_editor", "")
            autosave_session()

        edited_text = st.text_area(
            "Transcript",
            key="transcript_editor",
            height=250,
            placeholder="Your transcript will appear here.",
            label_visibility="collapsed",
        )
        if edited_text != st.session_state.get("transcript_text", ""):
            st.session_state.transcript_text = edited_text
            autosave_session()

        for warning in reliability_warnings(st.session_state.get("transcript_text", "")):
            st.warning(warning)

        st.markdown('<div class="section-kicker">Export</div>', unsafe_allow_html=True)
        render_exports()

        with st.expander("Polish transcript", expanded=False):
            edit_a, edit_b, edit_c = st.columns(3)
            with edit_a:
                if st.button("Clean", use_container_width=True, disabled=not bool(st.session_state.get("transcript_text", ""))):
                    set_transcript_text(cleanup_transcript(st.session_state.transcript_text))
            with edit_b:
                if st.button("Format", use_container_width=True, disabled=not bool(st.session_state.get("transcript_text", ""))):
                    set_transcript_text(refine_transcript_format(st.session_state.transcript_text))
            with edit_c:
                speaker_names = st.text_input("Speakers", placeholder="Speaker 1, Speaker 2", label_visibility="collapsed")
                if st.button("Apply speakers", use_container_width=True, disabled=not bool(st.session_state.get("transcript_text", ""))):
                    set_transcript_text(speaker_format(st.session_state.transcript_text, speaker_names))

        with st.expander("Search, timestamps, notes", expanded=False):
            search_query = st.text_input("Search transcript", placeholder="Find a term")
            if search_query and st.session_state.get("transcript_text"):
                count = st.session_state.transcript_text.lower().count(search_query.lower())
                st.caption(f"{count} match{'es' if count != 1 else ''}")
            if st.session_state.get("segments") and st.toggle("Show timestamped transcript"):
                st.code(timestamped_text(st.session_state.segments), language="text")
            if st.button("Create notes", use_container_width=True, disabled=not bool(st.session_state.get("transcript_text", ""))):
                st.session_state.notes_text = meeting_notes(st.session_state.transcript_text)
                autosave_session()
            if st.session_state.get("notes_text"):
                st.text_area("Notes", key="notes_text", height=180)


def render_projects_page() -> None:
    render_app_header("Projects", "Save the current transcript as a named workspace.")
    save_disabled = not bool(st.session_state.get("transcript_text", "").strip())
    save_col, folder_col = st.columns(2)
    with save_col:
        if st.button("Save current project", type="primary", use_container_width=True, disabled=save_disabled):
            path = save_project(st.session_state.get("project_name", ""))
            st.success(f"Saved: {path.stem}")
    with folder_col:
        if st.button("Open projects folder", use_container_width=True):
            PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
            open_in_finder(PROJECTS_DIR)

    st.caption("Open saved transcripts from History.")


def render_history_page() -> None:
    render_app_header("History", "Reopen previous transcripts without hunting through folders.")
    projects = list_projects()
    if not projects:
        st.info("No saved projects yet.")
        return

    labels = {f"{p['name']}  {p['saved_at'][:16].replace('T', ' ')}": p["file"] for p in projects}
    selected_label = st.selectbox("Saved transcripts", [""] + list(labels.keys()))
    open_col, folder_col = st.columns(2)
    with open_col:
        if selected_label and st.button("Open selected", type="primary", use_container_width=True):
            load_project(labels[selected_label])
            st.session_state.active_page = "Transcribe"
            st.rerun()
    with folder_col:
        if st.button("Open history folder", use_container_width=True):
            PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
            open_in_finder(PROJECTS_DIR)


def render_vocabulary_page() -> None:
    render_app_header("Vocabulary", "Keep names and technical terms ready for better local transcription.")
    st.text_area("Current key terms", key="key_terms", height=160)
    name_col, action_col = st.columns([0.55, 0.45])
    with name_col:
        profile_name = st.text_input("Profile name", placeholder="DataGEMS, thesis, client call")
    with action_col:
        st.write("")
        if st.button("Save vocabulary", use_container_width=True):
            save_vocab_profile(profile_name, st.session_state.get("key_terms", ""))
            st.success("Saved.")

    profiles = load_vocab_profiles()
    if profiles:
        selected_profile = st.selectbox("Load profile", [""] + list(profiles.keys()))
        if selected_profile and st.button("Use this profile", use_container_width=True):
            st.session_state.key_terms = profiles[selected_profile]
            st.rerun()


def render_storage_page() -> None:
    render_app_header("Settings", "Manage local storage and downloaded speech models.")
    hf_dir = huggingface_cache_dir()
    runtime_size = directory_size(RUNTIME_DIR)
    model_size = directory_size(hf_dir)
    user_data_size = max(directory_size(APP_SUPPORT_DIR) - runtime_size, 0)

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Projects and settings", human_size(user_data_size))
    col_b.metric("Shared app runtime", human_size(runtime_size))
    col_c.metric("Speech models", human_size(model_size))

    open_a, open_b, clear_c = st.columns(3)
    with open_a:
        if st.button("Open app data", use_container_width=True):
            APP_SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
            open_in_finder(APP_SUPPORT_DIR)
    with open_b:
        if st.button("Open model cache", use_container_width=True):
            hf_dir.mkdir(parents=True, exist_ok=True)
            open_in_finder(hf_dir)
    with clear_c:
        if st.button("Clear temporary cache", use_container_width=True):
            st.cache_data.clear()
            for key in ("media_signature", "media_details", "audio_quality"):
                st.session_state.pop(key, None)
            st.success("Temporary cache cleared.")

    st.markdown('<div class="section-kicker">Downloaded models</div>', unsafe_allow_html=True)
    entries = model_cache_entries()
    if not entries:
        st.info("No complete speech model is currently cached.")
    else:
        labels = {
            f"{entry['label']} · {entry['model']} · {human_size(int(entry['size']))}": entry
            for entry in entries
        }
        selected_label = st.selectbox("Model to manage", list(labels.keys()))
        selected = labels[selected_label]
        st.caption("Keep Balanced for everyday work. Removed models download again only when you select them.")
        confirm_remove = st.checkbox(f"Confirm removal of {selected['model']}")
        if st.button(
            "Remove selected model",
            disabled=not confirm_remove,
            help="Frees local disk space; the model can be downloaded again later.",
        ):
            try:
                get_model.cache_clear()
                shutil.rmtree(Path(selected["path"]))
                st.success(f"Removed {selected['model']} from the model cache.")
                st.rerun()
            except OSError as exc:
                st.error(f"Could not remove the model: {exc}")

    st.caption("Partly deleted models are repaired automatically the next time that quality is selected.")


def set_active_page(page: str) -> None:
    st.session_state.active_page = page


def main() -> None:
    initialize_state()
    st.session_state.setdefault("active_page", "Transcribe")
    st.session_state.setdefault("sidebar_open", True)
    inject_styles()

    st.markdown('<div class="menu-toggle-row">', unsafe_allow_html=True)
    if st.button("☰", key="sidebar_toggle_button", help="Toggle menu"):
        st.session_state.sidebar_open = not st.session_state.sidebar_open
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state.sidebar_open:
        logo = logo_data_uri()
        logo_html = f'<img class="sidebar-logo" src="{logo}" alt="" />' if logo else ""
        st.sidebar.markdown(
            f'<div class="sidebar-brand">{logo_html}<span>Local Transcript Studio</span></div>',
            unsafe_allow_html=True,
        )
        st.sidebar.markdown('<div class="sidebar-caption">Private, local, free transcription</div>', unsafe_allow_html=True)
        st.sidebar.markdown('<div class="sidebar-section">Workspace</div>', unsafe_allow_html=True)
        st.sidebar.button(
            "Transcribe",
            key="nav_transcribe",
            use_container_width=True,
            on_click=set_active_page,
            args=("Transcribe",),
        )
        st.sidebar.button(
            "Projects",
            key="nav_projects",
            use_container_width=True,
            on_click=set_active_page,
            args=("Projects",),
        )
        st.sidebar.markdown('<div class="sidebar-section">Library</div>', unsafe_allow_html=True)
        st.sidebar.button(
            "History",
            key="nav_history",
            use_container_width=True,
            on_click=set_active_page,
            args=("History",),
        )
        st.sidebar.button(
            "Vocabulary",
            key="nav_vocabulary",
            use_container_width=True,
            on_click=set_active_page,
            args=("Vocabulary",),
        )
        st.sidebar.markdown('<div class="sidebar-section">System</div>', unsafe_allow_html=True)
        st.sidebar.button(
            "Settings",
            key="nav_settings",
            use_container_width=True,
            on_click=set_active_page,
            args=("Settings",),
        )
        st.sidebar.divider()
        st.sidebar.caption(f"Language: {st.session_state.get('selected_language_label', 'English')}")
        if st.sidebar.button("Open exports folder", use_container_width=True):
            open_in_finder(export_folder())

    page = st.session_state.active_page
    if page == "Transcribe":
        render_transcribe_page()
    elif page == "Projects":
        render_projects_page()
    elif page == "History":
        render_history_page()
    elif page == "Vocabulary":
        render_vocabulary_page()
    else:
        render_storage_page()


if __name__ == "__main__":
    main()
