"""Embeddable widget endpoints for the Multando API.

Self-contained HTML pages designed to be embedded via ``<iframe>`` on city
portals, news sites, or any third-party page. Each widget fetches data from
the public Multando API and renders it with minimal dependencies (Leaflet).

Privacy: widgets always consume public, non-identifying data (plates and
reporter info are never included — see ``/reports/geojson``).
"""

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/widget", tags=["widgets"])


# Strings for the two supported locales, kept tiny on purpose — this is the
# embedded UI, not the full app.
_LOCALE_STRINGS: dict[str, dict[str, str]] = {
    "es": {
        "legend_title": "Estado",
        "status_approved": "Aprobado",
        "status_community_verified": "Verificado por comunidad",
        "status_authority_review": "En revisión",
        "status_pending": "Pendiente",
        "status_rejected": "Rechazado",
        "loading": "Cargando reportes…",
        "error": "No se pudieron cargar los reportes.",
        "total": "reportes",
        "powered_by": "Desarrollado por",
        "confidence": "Confianza",
        "reported": "Reportado",
        "tab_map": "Mapa",
        "tab_leaderboard": "Ranking",
        "leaderboard_reports": "reportes",
        "leaderboard_empty": "Aún no hay reportes verificados",
    },
    "en": {
        "legend_title": "Status",
        "status_approved": "Approved",
        "status_community_verified": "Community verified",
        "status_authority_review": "Under review",
        "status_pending": "Pending",
        "status_rejected": "Rejected",
        "loading": "Loading reports…",
        "error": "Could not load reports.",
        "total": "reports",
        "powered_by": "Powered by",
        "confidence": "Confidence",
        "reported": "Reported",
        "tab_map": "Map",
        "tab_leaderboard": "Leaderboard",
        "leaderboard_reports": "reports",
        "leaderboard_empty": "No verified reports yet",
    },
}


_VALID_TABS = ("map", "leaderboard")


def _parse_tabs(raw: str) -> list[str]:
    """Parse and validate the ``tabs`` query parameter.

    Deduplicates while preserving order, drops unknown values, and falls
    back to ``['map']`` if nothing valid remains so backward compatibility
    is maintained.
    """
    seen: list[str] = []
    for part in raw.split(","):
        token = part.strip().lower()
        if token in _VALID_TABS and token not in seen:
            seen.append(token)
    return seen or ["map"]


@router.get(
    "/reports-map",
    response_class=HTMLResponse,
    summary="Embeddable Leaflet map of verified reports",
    description=(
        "Returns a self-contained HTML page that renders an interactive map "
        "of Multando reports, an optional leaderboard of top plates, or both "
        "as switchable tabs. Designed to be used inside an ``<iframe>``."
    ),
)
async def reports_map_widget(
    request: Request,
    city_id: int | None = Query(default=None, description="Filter by city ID"),
    status_filter: str = Query(
        default="pending,community_verified,authority_review,approved",
        alias="status",
        description="Comma-separated statuses to include (default excludes rejected).",
    ),
    primary_color: str = Query(
        default="e63946",
        description="Primary accent color (hex, no '#').",
        pattern=r"^[0-9a-fA-F]{6}$",
    ),
    lat: float = Query(default=4.7110, description="Initial map latitude"),
    lon: float = Query(default=-74.0721, description="Initial map longitude"),
    zoom: int = Query(default=12, ge=1, le=20, description="Initial zoom level"),
    height: int = Query(default=500, ge=100, le=4000, description="Widget height in pixels"),
    show_legend: bool = Query(default=True, description="Show the status legend"),
    locale: str = Query(default="es", pattern=r"^(es|en)$", description="UI locale"),
    limit: int = Query(default=500, ge=1, le=5000, description="Max markers to load"),
    cluster: bool = Query(default=True, description="Cluster markers at low zoom"),
    tabs: str = Query(
        default="map",
        description=(
            "Which panels to render. Comma-separated list from "
            "``map``/``leaderboard``. When more than one value is given, a "
            "tab bar is rendered at the top."
        ),
    ),
    default_tab: str = Query(
        default="map",
        pattern=r"^(map|leaderboard)$",
        description="Tab selected on load when multiple tabs are shown.",
    ),
) -> HTMLResponse:
    """Render a standalone widget page for iframe embedding.

    The page is a single HTML document that loads Leaflet + optional
    MarkerCluster from CDN and fetches data from the public
    ``/api/v1/reports/geojson`` and ``/api/v1/leaderboard/plates`` endpoints.

    Args:
        request: Incoming request, used to resolve the API base URL.
        city_id: Optional city filter.
        status_filter: Comma-separated report statuses to include.
        primary_color: Hex accent color (no leading ``#``).
        lat: Initial map center latitude.
        lon: Initial map center longitude.
        zoom: Initial zoom level.
        height: Widget height in pixels.
        show_legend: Whether to render the status legend.
        locale: UI locale — ``es`` or ``en``.
        limit: Maximum number of markers to fetch.
        cluster: Whether to cluster markers at low zoom levels.
        tabs: Which panels to render (``map``, ``leaderboard``, or both).
        default_tab: Which tab is active on first load.

    Returns:
        An ``HTMLResponse`` with permissive framing headers so the page can
        be embedded from any origin.
    """
    strings = _LOCALE_STRINGS.get(locale, _LOCALE_STRINGS["es"])
    tab_list = _parse_tabs(tabs)
    if default_tab not in tab_list:
        default_tab = tab_list[0]
    show_tab_bar = len(tab_list) > 1
    show_map_tab = "map" in tab_list
    show_leaderboard_tab = "leaderboard" in tab_list

    # Compute the API base URL from the inbound request so the widget works
    # on sandbox, staging, and production without hard-coding a host.
    # Respect X-Forwarded-Proto from Railway's edge proxy (defaults to HTTPS
    # in production so the widget doesn't hit mixed-content blocks).
    forwarded_proto = request.headers.get("x-forwarded-proto")
    scheme = forwarded_proto or ("https" if request.url.hostname not in ("localhost", "127.0.0.1") else request.url.scheme)
    host = request.url.hostname
    port = request.url.port
    if port and port not in (80, 443):
        base_url = f"{scheme}://{host}:{port}"
    else:
        base_url = f"{scheme}://{host}"
    geojson_params: list[str] = [f"status={status_filter}", f"limit={limit}"]
    if city_id is not None:
        geojson_params.append(f"city_id={city_id}")
    geojson_url = f"{base_url}/api/v1/reports/geojson?{'&'.join(geojson_params)}"

    leaderboard_params: list[str] = ["period=all", "limit=20"]
    if city_id is not None:
        leaderboard_params.append(f"city_id={city_id}")
    leaderboard_url = (
        f"{base_url}/api/v1/leaderboard/plates?{'&'.join(leaderboard_params)}"
    )

    legend_display = "block" if show_legend else "none"
    cluster_js = "true" if cluster else "false"

    # Build the tab bar HTML only when more than one tab is requested.
    if show_tab_bar:
        tab_buttons = []
        for tab_key in tab_list:
            label_key = "tab_map" if tab_key == "map" else "tab_leaderboard"
            active_cls = " active" if tab_key == default_tab else ""
            tab_buttons.append(
                f'<button type="button" class="tab-btn{active_cls}" '
                f'data-tab="{tab_key}">{strings[label_key]}</button>'
            )
        tab_bar_html = (
            f'<div id="tab-bar">{"".join(tab_buttons)}</div>'
        )
    else:
        tab_bar_html = ""

    # Per-panel visibility based on the default tab. Non-default panels are
    # hidden from the start — the JS simply toggles them.
    map_panel_display = "block" if (not show_tab_bar or default_tab == "map") else "none"
    leaderboard_panel_display = (
        "block"
        if show_leaderboard_tab and (not show_tab_bar or default_tab == "leaderboard")
        else "none"
    )

    map_panel_html = (
        f"""
    <div id="map-panel" class="panel" style="display: {map_panel_display};">
      <div id="map"></div>
      <div id="status">{strings["loading"]}</div>
      <div id="legend">
        <h4>{strings["legend_title"]}</h4>
        <ul>
          <li><span class="dot dot-approved"></span>{strings["status_approved"]}</li>
          <li><span class="dot dot-community"></span>{strings["status_community_verified"]}</li>
          <li><span class="dot dot-review"></span>{strings["status_authority_review"]}</li>
          <li><span class="dot dot-pending"></span>{strings["status_pending"]}</li>
          <li><span class="dot dot-rejected"></span>{strings["status_rejected"]}</li>
        </ul>
      </div>
    </div>"""
        if show_map_tab
        else ""
    )

    leaderboard_panel_html = (
        f"""
    <div id="leaderboard-panel" class="panel" style="display: {leaderboard_panel_display};">
      <div id="lb-scroll">
        <div id="lb-status" class="lb-status">{strings["loading"]}</div>
        <ol id="lb-list"></ol>
      </div>
    </div>"""
        if show_leaderboard_tab
        else ""
    )

    # NOTE: keep this template literal-friendly — avoid stray { } characters
    # unless escaped as {{ }} for the f-string.
    html = f"""<!doctype html>
<html lang="{locale}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Multando Widget</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css" />
  <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css" />
  <style>
    :root {{
      --primary: #{primary_color};
    }}
    html, body {{
      margin: 0;
      padding: 0;
      height: 100%;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      background: #fafafa;
      color: #1a1a2e;
    }}
    #wrap {{
      position: relative;
      width: 100%;
      height: {height}px;
      display: flex;
      flex-direction: column;
      border: 1px solid rgba(0, 0, 0, 0.08);
      border-radius: 8px;
      overflow: hidden;
      background: #fff;
    }}
    #tab-bar {{
      display: flex;
      gap: 6px;
      padding: 8px;
      background: #fff;
      border-bottom: 1px solid rgba(0, 0, 0, 0.06);
      flex-shrink: 0;
    }}
    .tab-btn {{
      appearance: none;
      border: 1px solid rgba(0, 0, 0, 0.08);
      background: #f5f5f7;
      color: #444;
      padding: 6px 14px;
      font-size: 13px;
      font-weight: 500;
      border-radius: 999px;
      cursor: pointer;
      transition: background 0.15s, color 0.15s, border-color 0.15s;
      font-family: inherit;
    }}
    .tab-btn:hover {{
      background: #ececef;
    }}
    .tab-btn.active {{
      background: var(--primary);
      color: #fff;
      border-color: var(--primary);
      box-shadow: 0 1px 4px rgba(0, 0, 0, 0.12);
    }}
    .panel {{
      position: relative;
      flex: 1 1 auto;
      min-height: 0;
    }}
    #map {{
      position: absolute;
      inset: 0;
    }}
    #legend {{
      position: absolute;
      bottom: 36px;
      right: 12px;
      z-index: 1000;
      background: rgba(255, 255, 255, 0.96);
      border: 1px solid rgba(0, 0, 0, 0.08);
      border-left: 4px solid var(--primary);
      border-radius: 6px;
      padding: 10px 12px;
      font-size: 12px;
      line-height: 1.5;
      box-shadow: 0 2px 10px rgba(0, 0, 0, 0.08);
      display: {legend_display};
    }}
    #legend h4 {{
      margin: 0 0 6px 0;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: #555;
    }}
    #legend ul {{
      list-style: none;
      margin: 0;
      padding: 0;
    }}
    #legend li {{
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 3px 0;
    }}
    .dot {{
      width: 10px;
      height: 10px;
      border-radius: 50%;
      box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.9);
    }}
    .dot-approved {{ background: #10b981; }}
    .dot-community {{ background: #3b82f6; }}
    .dot-review {{ background: #f59e0b; }}
    .dot-pending {{ background: #94a3b8; }}
    .dot-rejected {{ background: #ef4444; }}
    #status {{
      position: absolute;
      top: 12px;
      left: 12px;
      z-index: 1000;
      background: rgba(255, 255, 255, 0.96);
      border: 1px solid rgba(0, 0, 0, 0.08);
      border-radius: 6px;
      padding: 6px 10px;
      font-size: 12px;
      color: #444;
      box-shadow: 0 2px 10px rgba(0, 0, 0, 0.08);
    }}
    #footer {{
      position: absolute;
      bottom: 8px;
      left: 8px;
      z-index: 1001;
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 12px;
      color: #111827;
      background: rgba(255, 255, 255, 0.95);
      padding: 4px 12px 4px 4px;
      border-radius: 24px;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
      text-decoration: none;
      transition: transform 0.15s ease, box-shadow 0.15s ease;
    }}
    #footer:hover {{
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    }}
    #footer .logo-wrap {{
      width: 28px;
      height: 28px;
      background: #1A1A2E;
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
    }}
    #footer .logo-wrap img {{
      width: 22px;
      height: 22px;
      display: block;
    }}
    #footer .brand {{
      color: #E63946;
      font-weight: 700;
      letter-spacing: -0.01em;
    }}
    #footer .powered {{
      color: #6b7280;
      font-weight: 400;
    }}
    .popup-title {{
      font-weight: 600;
      color: var(--primary);
      margin-bottom: 4px;
    }}
    .popup-meta {{
      font-size: 11px;
      color: #666;
    }}
    .popup-row {{ margin: 2px 0; }}

    /* Leaderboard styles */
    #lb-scroll {{
      position: absolute;
      inset: 0;
      overflow-y: auto;
      padding: 12px 12px 44px 12px;
      background: #fafafa;
    }}
    .lb-status {{
      font-size: 13px;
      color: #666;
      text-align: center;
      padding: 24px 12px;
    }}
    .lb-status.error {{
      color: #b91c1c;
    }}
    #lb-list {{
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}
    .lb-row {{
      display: grid;
      grid-template-columns: 42px 1fr auto;
      gap: 10px;
      align-items: center;
      padding: 10px 12px;
      background: #fff;
      border: 1px solid rgba(0, 0, 0, 0.06);
      border-radius: 10px;
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
    }}
    .lb-pos {{
      font-size: 16px;
      font-weight: 700;
      text-align: center;
      color: #94a3b8;
      font-variant-numeric: tabular-nums;
    }}
    .lb-pos.lb-pos-top {{
      font-size: 20px;
    }}
    .lb-main {{
      min-width: 0;
      display: flex;
      flex-direction: column;
      gap: 2px;
    }}
    .lb-plate {{
      font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
      font-weight: 700;
      font-size: 14px;
      color: #1a1a2e;
      letter-spacing: 0.02em;
    }}
    .lb-infraction {{
      font-size: 11px;
      color: #64748b;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .lb-chips {{
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
      margin-top: 2px;
    }}
    .lb-chip {{
      font-size: 10px;
      padding: 1px 7px;
      border-radius: 999px;
      background: rgba(0, 0, 0, 0.05);
      color: #475569;
    }}
    .lb-count {{
      text-align: right;
      display: flex;
      flex-direction: column;
      align-items: flex-end;
    }}
    .lb-count-num {{
      font-size: 22px;
      font-weight: 800;
      color: var(--primary);
      line-height: 1;
      font-variant-numeric: tabular-nums;
    }}
    .lb-count-label {{
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: #94a3b8;
      margin-top: 2px;
    }}
  </style>
</head>
<body>
  <div id="wrap">
    {tab_bar_html}
    {map_panel_html}
    {leaderboard_panel_html}
    <a id="footer" href="https://multando.com" target="_blank" rel="noopener">
      <span class="logo-wrap"><img src="{base_url}/static/logo.png" alt="Multando" /></span>
      <span class="powered">{strings["powered_by"]}</span>
      <span class="brand">Multando</span>
    </a>
  </div>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
  <script>
    (function () {{
      var STRINGS = {{
        confidence: {strings["confidence"]!r},
        reported: {strings["reported"]!r},
        total: {strings["total"]!r},
        error: {strings["error"]!r},
        loading: {strings["loading"]!r},
        lbReports: {strings["leaderboard_reports"]!r},
        lbEmpty: {strings["leaderboard_empty"]!r}
      }};
      var STATUS_COLORS = {{
        approved: '#10b981',
        community_verified: '#3b82f6',
        authority_review: '#f59e0b',
        pending: '#94a3b8',
        rejected: '#ef4444',
        verified: '#10b981',
        disputed: '#f59e0b'
      }};
      var HAS_MAP = {("true" if show_map_tab else "false")};
      var HAS_LEADERBOARD = {("true" if show_leaderboard_tab else "false")};
      var ACTIVE_TAB = {default_tab!r};

      // ----- Tab switching -----
      var tabButtons = document.querySelectorAll('#tab-bar .tab-btn');
      var panels = {{
        map: document.getElementById('map-panel'),
        leaderboard: document.getElementById('leaderboard-panel')
      }};

      function activateTab(name) {{
        ACTIVE_TAB = name;
        tabButtons.forEach(function (btn) {{
          btn.classList.toggle('active', btn.getAttribute('data-tab') === name);
        }});
        Object.keys(panels).forEach(function (key) {{
          if (!panels[key]) return;
          panels[key].style.display = key === name ? 'block' : 'none';
        }});
        if (name === 'map' && mapInstance) {{
          // Leaflet needs a nudge when its container becomes visible.
          setTimeout(function () {{ mapInstance.invalidateSize(); }}, 50);
        }}
        if (name === 'leaderboard' && !leaderboardLoaded) {{
          loadLeaderboard();
        }}
      }}

      tabButtons.forEach(function (btn) {{
        btn.addEventListener('click', function () {{
          activateTab(btn.getAttribute('data-tab'));
        }});
      }});

      // ----- Map -----
      var mapInstance = null;
      if (HAS_MAP) {{
        mapInstance = L.map('map').setView([{lat}, {lon}], {zoom});
        L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
          maxZoom: 19,
          attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>'
        }}).addTo(mapInstance);

        var useCluster = {cluster_js};
        var layer = useCluster && L.markerClusterGroup
          ? L.markerClusterGroup({{ showCoverageOnHover: false }})
          : L.layerGroup();
        layer.addTo(mapInstance);

        var makeIcon = function (color) {{
          return L.divIcon({{
            className: 'multando-pin',
            html: '<div style="width:14px;height:14px;border-radius:50%;background:' + color +
                  ';box-shadow:0 0 0 3px rgba(255,255,255,0.95),0 2px 6px rgba(0,0,0,0.25);"></div>',
            iconSize: [14, 14],
            iconAnchor: [7, 7]
          }});
        }};

        var formatDate = function (iso) {{
          if (!iso) return '';
          try {{ return new Date(iso).toLocaleString(); }} catch (e) {{ return iso; }}
        }};

        var popupFor = function (props) {{
          var name = props.infraction || props.short_id || 'Report';
          return '<div class="popup-title">' + name + '</div>' +
                 '<div class="popup-row popup-meta">' + (props.short_id || '') + '</div>' +
                 '<div class="popup-row popup-meta">' + STRINGS.reported + ': ' + formatDate(props.created_at) + '</div>' +
                 '<div class="popup-row popup-meta">' + STRINGS.confidence + ': ' + (props.confidence_score || 0) + '%</div>';
        }};

        var statusEl = document.getElementById('status');

        fetch({geojson_url!r})
          .then(function (r) {{ return r.json(); }})
          .then(function (data) {{
            var features = (data && data.features) || [];
            features.forEach(function (f) {{
              if (!f.geometry || !f.geometry.coordinates) return;
              var coords = f.geometry.coordinates;
              var props = f.properties || {{}};
              var color = STATUS_COLORS[props.status] || '#64748b';
              var marker = L.marker([coords[1], coords[0]], {{ icon: makeIcon(color) }});
              marker.bindPopup(popupFor(props));
              layer.addLayer(marker);
            }});
            statusEl.textContent = features.length + ' ' + STRINGS.total;
          }})
          .catch(function () {{
            statusEl.textContent = STRINGS.error;
            statusEl.style.color = '#b91c1c';
          }});
      }}

      // ----- Leaderboard (lazy) -----
      var leaderboardLoaded = false;
      var MEDALS = ['🥇', '🥈', '🥉'];

      function escapeHtml(str) {{
        if (str == null) return '';
        return String(str)
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;')
          .replace(/'/g, '&#39;');
      }}

      function renderLeaderboard(rows) {{
        var list = document.getElementById('lb-list');
        var statusEl = document.getElementById('lb-status');
        if (!list || !statusEl) return;
        list.innerHTML = '';
        if (!rows || rows.length === 0) {{
          statusEl.textContent = STRINGS.lbEmpty;
          statusEl.classList.remove('error');
          return;
        }}
        statusEl.textContent = '';
        rows.forEach(function (row, idx) {{
          var pos = idx + 1;
          var posLabel = idx < 3 ? MEDALS[idx] : String(pos);
          var chips = '';
          if (Array.isArray(row.cities) && row.cities.length) {{
            chips = '<div class="lb-chips">' +
              row.cities.slice(0, 4).map(function (c) {{
                return '<span class="lb-chip">' + escapeHtml(c) + '</span>';
              }}).join('') +
              '</div>';
          }}
          var infraction = row.top_infraction
            ? '<div class="lb-infraction">' + escapeHtml(row.top_infraction) + '</div>'
            : '';
          var li = document.createElement('li');
          li.className = 'lb-row';
          li.innerHTML =
            '<div class="lb-pos' + (idx < 3 ? ' lb-pos-top' : '') + '">' + posLabel + '</div>' +
            '<div class="lb-main">' +
              '<div class="lb-plate">' + escapeHtml(row.plate || '') + '</div>' +
              infraction +
              chips +
            '</div>' +
            '<div class="lb-count">' +
              '<span class="lb-count-num">' + (row.verified_reports || 0) + '</span>' +
              '<span class="lb-count-label">' + STRINGS.lbReports + '</span>' +
            '</div>';
          list.appendChild(li);
        }});
      }}

      function loadLeaderboard() {{
        if (!HAS_LEADERBOARD) return;
        leaderboardLoaded = true;
        var statusEl = document.getElementById('lb-status');
        if (statusEl) {{
          statusEl.textContent = STRINGS.loading;
          statusEl.classList.remove('error');
        }}
        fetch({leaderboard_url!r})
          .then(function (r) {{
            if (!r.ok) throw new Error('http ' + r.status);
            return r.json();
          }})
          .then(function (data) {{
            renderLeaderboard(Array.isArray(data) ? data : []);
          }})
          .catch(function () {{
            if (statusEl) {{
              statusEl.textContent = STRINGS.error;
              statusEl.classList.add('error');
            }}
            leaderboardLoaded = false;
          }});
      }}

      // If the leaderboard is the active panel on load, kick off its fetch.
      if (ACTIVE_TAB === 'leaderboard' && HAS_LEADERBOARD) {{
        loadLeaderboard();
      }}
    }})();
  </script>
</body>
</html>"""

    # Permit embedding from any origin. Content-Security-Policy's
    # ``frame-ancestors *`` is the modern directive; X-Frame-Options is
    # explicitly omitted (absence = allow).
    headers = {
        "Content-Security-Policy": "frame-ancestors *",
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "public, max-age=60",
    }
    return HTMLResponse(content=html, headers=headers)
