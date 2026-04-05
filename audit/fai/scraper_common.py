"""Shared helpers for scraping competition result pages.

Both CIVLCOMPS and Airtribune embed scoring data in their HTML result pages
using the same FS-derived field names (day_quality, available_points_distance,
etc.). This module provides common parsing routines.
"""
from __future__ import annotations

import json
import logging
import re
import time

import requests

log = logging.getLogger(__name__)

# Shared HTTP session with retries
_session: requests.Session | None = None


def get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers["User-Agent"] = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AervyxAudit/1.0"
        )
    return _session


def fetch_page(url: str, retries: int = 3, delay: float = 2.0) -> str:
    """Fetch a URL with retries, returning the response text."""
    session = get_session()
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=30)
            if resp.status_code == 200:
                return resp.text
            log.warning("HTTP %d for %s (attempt %d)", resp.status_code, url, attempt + 1)
        except requests.RequestException as exc:
            log.warning("Request failed for %s: %s (attempt %d)", url, exc, attempt + 1)
        if attempt < retries - 1:
            time.sleep(delay * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {url} after {retries} attempts")


def fetch_json(url: str, retries: int = 3, delay: float = 2.0) -> dict | list:
    """Fetch a URL expecting JSON response."""
    session = get_session()
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            log.warning("HTTP %d for %s (attempt %d)", resp.status_code, url, attempt + 1)
        except requests.RequestException as exc:
            log.warning("Request failed for %s: %s (attempt %d)", url, exc, attempt + 1)
        if attempt < retries - 1:
            time.sleep(delay * (attempt + 1))
    raise RuntimeError(f"Failed to fetch JSON from {url} after {retries} attempts")


def extract_json_from_html(html: str) -> list[dict]:
    """Try to extract JSON objects from script tags in HTML."""
    results = []
    # Pattern 1: <script type="application/json">...</script>
    for m in re.finditer(r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>', html, re.DOTALL):
        try:
            results.append(json.loads(m.group(1)))
        except json.JSONDecodeError:
            pass
    # Pattern 2: var xxx = {...}; or var xxx = [...];
    for m in re.finditer(r'var\s+\w+\s*=\s*(\{[^;]{100,}\}|\[[^;]{100,}\])\s*;', html, re.DOTALL):
        try:
            results.append(json.loads(m.group(1)))
        except json.JSONDecodeError:
            pass
    return results


def parse_scoring_params_from_text(html: str) -> dict:
    """Extract scoring parameters from a result page HTML.

    Both CIVLCOMPS and Airtribune use FS-derived result pages with
    <td class="fs_res">key</td><td class="fs_res">value</td> format.
    """
    params = {}

    # Primary pattern: FS result table cells
    # <td class="fs_res">key</td>\n<td class="fs_res" ...>value</td>
    fs_pattern = re.compile(
        r'<td[^>]*class="fs_res"[^>]*>\s*([a-z_]+)\s*</td>\s*'
        r'<td[^>]*class="fs_res"[^>]*>\s*([^<]+?)\s*</td>',
        re.IGNORECASE,
    )
    for m in fs_pattern.finditer(html):
        key = m.group(1).strip().lower()
        value = m.group(2).strip()
        if key and value:
            params[key] = value

    # Also extract "id" which might be the GAP version
    # (appears as value, not key — look for GAP pattern)
    for m in fs_pattern.finditer(html):
        value = m.group(2).strip()
        if value.startswith("GAP"):
            params["id"] = value
            break

    # Fallback: key: value or key = value patterns in plain text
    if not params:
        kv_keys = [
            "id", "nom_dist", "nom_time", "nom_launch", "nom_goal", "min_dist",
            "score_back_time", "bonus_gr", "day_quality", "launch_validity",
            "distance_validity", "time_validity", "stop_validity",
            "task_distance", "ss_distance",
            "available_points_distance", "available_points_time",
            "available_points_leading", "available_points_arrival",
            "no_of_pilots_present", "no_of_pilots_flying",
            "no_of_pilots_reaching_es", "no_of_pilots_reaching_goal",
            "no_of_pilots_in_competition",
            "best_dist", "best_time", "goalratio",
            "distance_weight", "time_weight", "leading_weight",
            "use_distance_points", "use_time_points", "use_leading_points",
            "use_arrival_position_points", "use_arrival_time_points",
            "use_departure_points", "use_difficulty_for_distance_points",
            "use_semi_circle_control_zone_for_goal_line",
            "use_proportional_leading_weight_if_nobody_in_goal",
            "use_constant_leading_weight", "use_flat_decline_of_timepoints",
            "redistribute_removed_time_points_as_distance_points",
            "time_points_if_not_in_goal",
        ]
        for key in kv_keys:
            pattern = rf'{re.escape(key)}\s*[:=]\s*["\']?([^\s"\'<,;]+)'
            m = re.search(pattern, html, re.IGNORECASE)
            if m:
                params[key] = m.group(1)

    return params
