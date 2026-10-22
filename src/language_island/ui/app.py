"""Minimal status screen for the local MVP services."""

from __future__ import annotations

from typing import Any

import httpx
import streamlit as st

from language_island.settings import get_settings


def load_health(api_url: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        response = httpx.get(f"{api_url}/health", timeout=3.0)
        response.raise_for_status()
        return response.json(), None
    except (httpx.HTTPError, ValueError) as exc:
        return None, str(exc)


def render() -> None:
    settings = get_settings()
    st.set_page_config(page_title=settings.app_name, page_icon="☕", layout="centered")
    st.title("☕ Language Island")
    st.caption("Local German café tutor — service scaffold")

    health, error = load_health(settings.api_url)
    if error is not None or health is None:
        st.error(f"FastAPI is unavailable at {settings.api_url}: {error}")
        st.info("Start the complete application with scripts/start.ps1.")
        return

    if health.get("status") == "ready":
        st.success("Core local services are ready.")
    else:
        st.error("A required local service failed its readiness check.")

    components = health.get("components", {})
    if isinstance(components, dict):
        for name, details in components.items():
            if not isinstance(details, dict):
                continue
            status = str(details.get("status", "unknown"))
            icon = "✅" if status == "ready" else "⚠️"
            with st.expander(f"{icon} {name.replace('_', ' ').title()}: {status}"):
                st.json(details)

    st.info("The Café island curriculum arrives in Commit 2.")


render()
