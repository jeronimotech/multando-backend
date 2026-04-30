"""Submit verified Bogota reports to the SDM (Secretaría Distrital de Movilidad) Google Form.

The SDM provides a public Google Form for citizens to report traffic violations
with photographic/video evidence. Since the form requires Google authentication
for file uploads (which cannot be automated reliably in headless browsers),
evidence is uploaded to a shared Google Drive folder and a pre-filled form URL
is generated for manual review and submission by an admin.

Workflow:
1. Upload evidence files to Google Drive (shareable links).
2. Build a pre-fill URL with all text/radio/dropdown fields populated.
3. Include the Drive evidence link(s) in the description field.
4. Store both the pre-fill URL and Drive links in the SDMSubmission record.
5. An admin clicks the pre-fill URL, attaches the file from Drive, and submits.
"""

import io
import json
import logging
from datetime import datetime
from typing import Optional
from urllib.parse import quote, urlencode

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class SDMSubmissionError(Exception):
    """Raised when an SDM form submission fails."""


class SDMBogotaService:
    """Submit verified Bogota reports to the SDM Google Form."""

    # -----------------------------------------------------------------------
    # Google Form entry IDs
    #
    # These must be discovered from the form HTML source by inspecting
    # name="entry.XXXXXXXX" attributes. Use the actual form URL:
    #   https://docs.google.com/forms/d/e/{form_id}/viewform
    # and search the page source for "entry." fields.
    # Google Form entry IDs — extracted from the SDM form HTML source
    # -----------------------------------------------------------------------
    ENTRY_INFRACTION_TYPE = "entry.1628113293"
    ENTRY_ADDRESS = "entry.543300933"
    ENTRY_LOCALIDAD = "entry.1737099860"
    ENTRY_PLATE = "entry.846606664"
    ENTRY_INTERNAL_NUMBER = "entry.754890082"
    ENTRY_EVENT_DATE_YEAR = "entry.742426141_year"
    ENTRY_EVENT_DATE_MONTH = "entry.742426141_month"
    ENTRY_EVENT_DATE_DAY = "entry.742426141_day"
    ENTRY_EVENT_TIME_HOUR = "entry.28021047_hour"
    ENTRY_EVENT_TIME_MINUTE = "entry.28021047_minute"
    ENTRY_DESCRIPTION = "entry.31467045"
    ENTRY_ANONYMOUS = "entry.1252322200"
    ENTRY_TERMS_VERACITY = "entry.576560172"
    ENTRY_TERMS_DATA = "entry.1773740141"

    VIEWFORM_BASE_URL = (
        "https://docs.google.com/forms/d/e/"
        "{form_id}/viewform"
    )

    # Mapping from Multando infraction codes to SDM form radio values.
    # Keys are the Infraction.code values from the infractions table.
    INFRACTION_MAP: dict[str, str] = {
        "illegal_parking": "Estacionar el vehículo en sitios prohibidos",
        "double_parking": "Estacionar el vehículo en sitios prohibidos",
        "red_light": (
            "No detenerse ante una luz roja o amarilla de semáforo, "
            "una señal de \"PARE\" o un semáforo intermitente en rojo"
        ),
        "pedestrian_crossing": (
            "No respetar el carril de peatones que cruzan una vía "
            "en sitio permitido o dar prelación a estos o a los "
            "ciclistas cuando estos cruzan primero"
        ),
        "speeding": "Conducir a velocidad superior a la máxima permitida",
        "wrong_way": "Transitar por sitios restringidos o en horas prohibidas",
        "no_seatbelt": (
            "No usar el cinturón de seguridad por parte de los "
            "ocupantes del vehículo"
        ),
        "cellphone_driving": (
            "Usar sistemas móviles de comunicación o telemáticos "
            "mientras se conduce"
        ),
        "bike_lane_invasion": (
            "Transitar por la ciclorruta, por andenes y demás lugares "
            "destinados al tránsito de peatones"
        ),
        "no_helmet": (
            "Conducir motocicleta sin observar las normas establecidas "
            "en el presente código"
        ),
        "obstruction": (
            "Obstaculizar, perjudicar o poner en riesgo a los demás "
            "usuarios de la vía"
        ),
    }

    # Bogota localidades (administrative divisions).
    LOCALIDADES: list[str] = [
        "Usaquén",
        "Chapinero",
        "Santa Fe",
        "San Cristóbal",
        "Usme",
        "Tunjuelito",
        "Bosa",
        "Kennedy",
        "Fontibón",
        "Engativá",
        "Suba",
        "Barrios Unidos",
        "Teusaquillo",
        "Los Mártires",
        "Antonio Nariño",
        "Puente Aranda",
        "La Candelaria",
        "Rafael Uribe Uribe",
        "Ciudad Bolívar",
        "Sumapaz",
    ]

    # Approximate bounding boxes for each localidad (lat_min, lat_max, lon_min, lon_max).
    # Used for a rough GPS-to-localidad resolution. Values are approximate centroids
    # with ~0.03 degree padding; a production deployment should use proper polygon data.
    _LOCALIDAD_BOUNDS: dict[str, tuple[float, float, float, float]] = {
        "Usaquén": (4.695, 4.795, -74.065, -73.990),
        "Chapinero": (4.625, 4.700, -74.075, -74.030),
        "Santa Fe": (4.575, 4.635, -74.090, -74.050),
        "San Cristóbal": (4.530, 4.585, -74.100, -74.050),
        "Usme": (4.430, 4.540, -74.140, -74.060),
        "Tunjuelito": (4.555, 4.590, -74.150, -74.115),
        "Bosa": (4.590, 4.640, -74.220, -74.160),
        "Kennedy": (4.590, 4.650, -74.190, -74.120),
        "Fontibón": (4.650, 4.710, -74.180, -74.110),
        "Engativá": (4.690, 4.750, -74.140, -74.080),
        "Suba": (4.730, 4.810, -74.110, -74.020),
        "Barrios Unidos": (4.660, 4.690, -74.090, -74.060),
        "Teusaquillo": (4.630, 4.665, -74.100, -74.065),
        "Los Mártires": (4.600, 4.630, -74.095, -74.070),
        "Antonio Nariño": (4.580, 4.605, -74.110, -74.080),
        "Puente Aranda": (4.605, 4.645, -74.130, -74.095),
        "La Candelaria": (4.585, 4.605, -74.080, -74.060),
        "Rafael Uribe Uribe": (4.545, 4.580, -74.125, -74.085),
        "Ciudad Bolívar": (4.460, 4.560, -74.175, -74.115),
        "Sumapaz": (4.200, 4.450, -74.250, -74.050),
    }

    def __init__(self) -> None:
        self._drive_service = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def submit_report(self, report, db) -> dict:
        """Prepare an SDM submission: upload evidence to Drive and build a pre-fill URL.

        The SDM Google Form requires Google authentication for file uploads,
        so fully automated submission is not possible. Instead this method:
        1. Uploads evidence to Google Drive (shareable links).
        2. Generates a pre-fill URL with all fields populated.
        3. Returns both so the SDMSubmission record can store them for
           manual review and one-click submission by an admin.

        Args:
            report: The SQLAlchemy Report model (with evidences loaded).
            db: AsyncSession for updating the SDMSubmission record.

        Returns:
            dict with keys: success (bool), prefill_url (str),
            drive_links (list[str]), error (str|None).
        """
        evidences = report.evidences or []
        error: str | None = None

        # Step 1 — Upload evidence to Google Drive
        drive_links: list[str] = []
        if settings.SDM_GOOGLE_SERVICE_ACCOUNT_JSON and settings.SDM_GOOGLE_DRIVE_FOLDER_ID:
            for evidence in evidences[:5]:  # SDM form allows max 5 files
                try:
                    link = await self.upload_evidence_to_drive(
                        evidence_url=evidence.url,
                        filename=(
                            f"report_{report.short_id}_{evidence.id}"
                            f".{evidence.mime_type.split('/')[-1]}"
                        ),
                    )
                    if link:
                        drive_links.append(link)
                except Exception:
                    logger.warning(
                        "Failed to upload evidence %s to Drive for SDM submission",
                        evidence.id,
                        exc_info=True,
                    )

            if not drive_links and evidences:
                error = "All Drive uploads failed — evidence links unavailable"
                logger.error(
                    "No evidence uploaded to Drive for report %s", report.short_id
                )
        elif evidences:
            error = "Google Drive credentials not configured; evidence not uploaded"
            logger.warning(error)

        # Step 2 — Build pre-fill URL (primary submission method)
        prefill_url = self.build_prefill_url(report, drive_links)

        logger.info(
            "SDM pre-fill URL generated for report %s (%d drive links)",
            report.short_id,
            len(drive_links),
        )

        return {
            "success": True,
            "prefill_url": prefill_url,
            "drive_links": drive_links,
            "error": error,
        }

    async def upload_evidence_to_drive(
        self, evidence_url: str, filename: str
    ) -> str:
        """Upload evidence file to Google Drive and return a shareable link.

        Uses Google Drive API v3 with service account credentials.

        Args:
            evidence_url: The URL of the evidence file to download.
            filename: Desired filename on Google Drive.

        Returns:
            Public shareable link for the uploaded file.

        Raises:
            SDMSubmissionError: If upload fails.
        """
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaIoBaseUpload
        except ImportError:
            raise SDMSubmissionError(
                "google-auth and google-api-python-client are required "
                "for SDM Drive uploads. Install them with: "
                "pip install google-auth google-api-python-client"
            )

        # Load credentials
        creds_data = settings.SDM_GOOGLE_SERVICE_ACCOUNT_JSON
        if not creds_data:
            raise SDMSubmissionError("SDM_GOOGLE_SERVICE_ACCOUNT_JSON is not configured")

        try:
            # Try as JSON string first, then as file path
            try:
                info = json.loads(creds_data)
            except json.JSONDecodeError:
                with open(creds_data) as f:
                    info = json.load(f)

            credentials = service_account.Credentials.from_service_account_info(
                info,
                scopes=["https://www.googleapis.com/auth/drive.file"],
            )
        except Exception as exc:
            raise SDMSubmissionError(f"Failed to load Google credentials: {exc}") from exc

        # Download the evidence file
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(evidence_url)
            resp.raise_for_status()
            file_bytes = resp.content
            content_type = resp.headers.get("content-type", "application/octet-stream")

        # Upload to Google Drive (synchronous API call)
        drive_service = build("drive", "v3", credentials=credentials)

        file_metadata = {
            "name": filename,
            "parents": [settings.SDM_GOOGLE_DRIVE_FOLDER_ID],
        }
        media = MediaIoBaseUpload(
            io.BytesIO(file_bytes),
            mimetype=content_type,
            resumable=True,
        )

        uploaded = (
            drive_service.files()
            .create(body=file_metadata, media_body=media, fields="id,webViewLink")
            .execute()
        )

        file_id = uploaded.get("id")
        if not file_id:
            raise SDMSubmissionError("Google Drive upload returned no file ID")

        # Make the file publicly readable
        drive_service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()

        return uploaded.get("webViewLink", f"https://drive.google.com/file/d/{file_id}/view")

    def build_form_data(
        self, report, evidence_links: list[str]
    ) -> dict[str, str]:
        """Build the form submission data mapping.

        Returns a dict of entry.XXXXXXX -> value pairs ready for URL-encoded POST.

        Args:
            report: The SQLAlchemy Report model (with infraction and evidences loaded).
            evidence_links: List of Google Drive shareable links for evidence.

        Returns:
            Dict mapping Google Form entry IDs to their values.
        """
        infraction_code = report.infraction.code if report.infraction else ""
        sdm_infraction = self.INFRACTION_MAP.get(
            infraction_code,
            # Fallback: use the Spanish name from the infraction record
            report.infraction.name_es if report.infraction else "Otra infracción",
        )

        # Resolve localidad from GPS
        localidad = self.resolve_localidad(report.latitude, report.longitude)

        # Format incident datetime
        incident_dt: datetime = report.incident_datetime

        # Build description with evidence links
        description_parts = []
        if report.location_address:
            description_parts.append(f"Dirección: {report.location_address}")
        description_parts.append(f"Placa: {report.vehicle_plate or 'N/A'}")
        description_parts.append(f"Reporte Multando: {report.short_id}")
        if evidence_links:
            description_parts.append("Evidencia: " + " | ".join(evidence_links))

        description = ". ".join(description_parts)[:200]

        data: dict[str, str] = {
            # Section 1 — Infraction details
            self.ENTRY_INFRACTION_TYPE: sdm_infraction,
            self.ENTRY_ADDRESS: report.location_address or f"{report.latitude}, {report.longitude}",
            self.ENTRY_LOCALIDAD: localidad,
            # Section 2 — Vehicle identification
            self.ENTRY_PLATE: report.vehicle_plate or "",
            self.ENTRY_INTERNAL_NUMBER: "",  # Optional, for public transport
            self.ENTRY_EVENT_DATE_YEAR: str(incident_dt.year),
            self.ENTRY_EVENT_DATE_MONTH: str(incident_dt.month),
            self.ENTRY_EVENT_DATE_DAY: str(incident_dt.day),
            self.ENTRY_EVENT_TIME_HOUR: f"{incident_dt.hour:02d}",
            self.ENTRY_EVENT_TIME_MINUTE: f"{incident_dt.minute:02d}",
            # Section 3 — Evidence description (file upload handled via Drive links)
            self.ENTRY_DESCRIPTION: description,
            # Section 4 — Contact: always anonymous to protect reporter
            self.ENTRY_ANONYMOUS: "Anónimo",
            # Section 5 — Terms acceptance
            self.ENTRY_TERMS_VERACITY: "Sí",
            self.ENTRY_TERMS_DATA: "Sí",
        }

        return data

    def build_prefill_url(
        self, report, evidence_links: Optional[list[str]] = None
    ) -> str:
        """Generate a pre-filled Google Form URL for manual submission.

        An admin clicks this link, reviews the pre-populated fields,
        attaches the evidence file(s) from the Drive link in the description,
        and submits. This is the primary submission method since the SDM
        form requires Google authentication for file uploads.

        Args:
            report: The SQLAlchemy Report model.
            evidence_links: Optional list of Drive shareable links.

        Returns:
            A full URL with pre-filled query parameters.
        """
        form_data = self.build_form_data(report, evidence_links or [])

        base_url = self.VIEWFORM_BASE_URL.format(form_id=settings.SDM_FORM_ID)
        query_string = urlencode(form_data, quote_via=quote)

        return f"{base_url}?usp=pp_url&{query_string}"

    def resolve_localidad(self, lat: float, lon: float) -> str:
        """Resolve GPS coordinates to a Bogota localidad name.

        Uses a simple bounding-box lookup. Falls back to "Bogotá D.C." if
        no localidad matches.

        Args:
            lat: Latitude of the report location.
            lon: Longitude of the report location.

        Returns:
            The name of the matching localidad, or "Bogotá D.C." as fallback.
        """
        best_match: str | None = None
        best_distance = float("inf")

        for name, (lat_min, lat_max, lon_min, lon_max) in self._LOCALIDAD_BOUNDS.items():
            if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
                # Inside bounding box — compute distance to centroid for tie-breaking
                clat = (lat_min + lat_max) / 2
                clon = (lon_min + lon_max) / 2
                dist = (lat - clat) ** 2 + (lon - clon) ** 2
                if dist < best_distance:
                    best_distance = dist
                    best_match = name

        return best_match or "Bogotá D.C."

    @staticmethod
    def is_bogota_report(report) -> bool:
        """Check whether a report is located in Bogota.

        Uses a broad bounding box around Bogota D.C.

        Args:
            report: The SQLAlchemy Report model.

        Returns:
            True if the report coordinates fall within Bogota's bounding box.
        """
        if report.latitude is None or report.longitude is None:
            return False

        # Broad Bogota bounding box
        return (
            4.45 <= report.latitude <= 4.84
            and -74.27 <= report.longitude <= -73.98
        )
