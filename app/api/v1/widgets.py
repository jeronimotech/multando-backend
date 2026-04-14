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
    },
}


@router.get(
    "/reports-map",
    response_class=HTMLResponse,
    summary="Embeddable Leaflet map of verified reports",
    description=(
        "Returns a self-contained HTML page that renders an interactive map "
        "of Multando reports. Designed to be used inside an ``<iframe>``."
    ),
)
async def reports_map_widget(
    request: Request,
    city_id: int | None = Query(default=None, description="Filter by city ID"),
    status_filter: str = Query(
        default="approved,community_verified",
        alias="status",
        description="Comma-separated statuses to include.",
    ),
    primary_color: str = Query(
        default="e63946",
        description="Primary accent color (hex, no '#').",
        pattern=r"^[0-9a-fA-F]{6}$",
    ),
    lat: float = Query(default=4.7110, description="Initial map latitude"),
    lon: float = Query(default=-74.0721, description="Initial map longitude"),
    zoom: int = Query(default=12, ge=1, le=20, description="Initial zoom level"),
    height: int = Query(default=500, ge=100, le=4000, description="Map height in pixels"),
    show_legend: bool = Query(default=True, description="Show the status legend"),
    locale: str = Query(default="es", pattern=r"^(es|en)$", description="UI locale"),
    limit: int = Query(default=500, ge=1, le=5000, description="Max markers to load"),
    cluster: bool = Query(default=True, description="Cluster markers at low zoom"),
) -> HTMLResponse:
    """Render a standalone Leaflet map page for iframe embedding.

    The page is a single HTML document that loads Leaflet + optional
    MarkerCluster from CDN and fetches data from the public
    ``/api/v1/reports/geojson`` endpoint.

    Args:
        request: Incoming request, used to resolve the API base URL.
        city_id: Optional city filter.
        status_filter: Comma-separated report statuses to include.
        primary_color: Hex accent color (no leading ``#``).
        lat: Initial map center latitude.
        lon: Initial map center longitude.
        zoom: Initial zoom level.
        height: Map height in pixels.
        show_legend: Whether to render the status legend.
        locale: UI locale — ``es`` or ``en``.
        limit: Maximum number of markers to fetch.
        cluster: Whether to cluster markers at low zoom levels.

    Returns:
        An ``HTMLResponse`` with permissive framing headers so the page can
        be embedded from any origin.
    """
    strings = _LOCALE_STRINGS.get(locale, _LOCALE_STRINGS["es"])

    # Compute the API base URL from the inbound request so the widget works
    # on sandbox, staging, and production without hard-coding a host.
    base_url = str(request.base_url).rstrip("/")
    geojson_params: list[str] = [f"status={status_filter}", f"limit={limit}"]
    if city_id is not None:
        geojson_params.append(f"city_id={city_id}")
    geojson_url = f"{base_url}/api/v1/reports/geojson?{'&'.join(geojson_params)}"

    legend_display = "block" if show_legend else "none"
    cluster_js = "true" if cluster else "false"

    # NOTE: keep this template literal-friendly — avoid stray { } characters
    # unless escaped as {{ }} for the f-string.
    html = f"""<!doctype html>
<html lang="{locale}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Multando Reports Map</title>
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
    }}
    #wrap {{
      position: relative;
      width: 100%;
      height: {height}px;
    }}
    #map {{
      position: absolute;
      inset: 0;
      border: 1px solid rgba(0, 0, 0, 0.08);
      border-radius: 8px;
      overflow: hidden;
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
      bottom: 4px;
      left: 8px;
      z-index: 1000;
      font-size: 11px;
      color: #666;
      background: rgba(255, 255, 255, 0.85);
      padding: 2px 8px;
      border-radius: 4px;
    }}
    #footer a {{
      color: var(--primary);
      text-decoration: none;
      font-weight: 600;
    }}
    #footer a:hover {{ text-decoration: underline; }}
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
  </style>
</head>
<body>
  <div id="wrap">
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
    <div id="footer">
      {strings["powered_by"]}
      <a href="https://multando.com" target="_blank" rel="noopener">Multando</a>
    </div>
  </div>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
  <script>
    (function () {{
      var STRINGS = {{
        confidence: {strings["confidence"]!r},
        reported: {strings["reported"]!r},
        total: {strings["total"]!r},
        error: {strings["error"]!r}
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

      var map = L.map('map').setView([{lat}, {lon}], {zoom});
      L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>'
      }}).addTo(map);

      var useCluster = {cluster_js};
      var layer = useCluster && L.markerClusterGroup
        ? L.markerClusterGroup({{ showCoverageOnHover: false }})
        : L.layerGroup();
      layer.addTo(map);

      function makeIcon(color) {{
        return L.divIcon({{
          className: 'multando-pin',
          html: '<div style="width:14px;height:14px;border-radius:50%;background:' + color +
                ';box-shadow:0 0 0 3px rgba(255,255,255,0.95),0 2px 6px rgba(0,0,0,0.25);"></div>',
          iconSize: [14, 14],
          iconAnchor: [7, 7]
        }});
      }}

      function formatDate(iso) {{
        if (!iso) return '';
        try {{ return new Date(iso).toLocaleString(); }} catch (e) {{ return iso; }}
      }}

      function popupFor(props) {{
        var name = props.infraction || props.short_id || 'Report';
        return '<div class="popup-title">' + name + '</div>' +
               '<div class="popup-row popup-meta">' + (props.short_id || '') + '</div>' +
               '<div class="popup-row popup-meta">' + STRINGS.reported + ': ' + formatDate(props.created_at) + '</div>' +
               '<div class="popup-row popup-meta">' + STRINGS.confidence + ': ' + (props.confidence_score || 0) + '%</div>';
      }}

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
