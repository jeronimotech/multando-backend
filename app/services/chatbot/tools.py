"""Claude tool definitions for the Multando chatbot."""

TOOLS = [
    {
        "name": "get_infractions",
        "description": (
            "Obtener la lista de tipos de infraccion de transito disponibles para reportar. "
            "/ Get the list of available traffic infraction types for reporting."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "create_report",
        "description": (
            "Crear un nuevo reporte de infraccion de transito. Requiere tipo de infraccion, "
            "placa del vehiculo, ubicacion y descripcion. "
            "/ Create a new traffic violation report. Requires infraction type, "
            "vehicle plate, location, and description."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "infraction_id": {
                    "type": "integer",
                    "description": (
                        "ID del tipo de infraccion (obtenido de get_infractions). "
                        "/ ID of the infraction type (from get_infractions)."
                    ),
                },
                "plate_number": {
                    "type": "string",
                    "description": (
                        "Numero de placa del vehiculo infractor. "
                        "/ License plate number of the offending vehicle."
                    ),
                },
                "latitude": {
                    "type": "number",
                    "description": (
                        "Latitud de la ubicacion del incidente. "
                        "/ Latitude of the incident location."
                    ),
                },
                "longitude": {
                    "type": "number",
                    "description": (
                        "Longitud de la ubicacion del incidente. "
                        "/ Longitude of the incident location."
                    ),
                },
                "description": {
                    "type": "string",
                    "description": (
                        "Descripcion breve del incidente. "
                        "/ Brief description of the incident."
                    ),
                },
                "vehicle_type_id": {
                    "type": "integer",
                    "description": (
                        "ID del tipo de vehiculo (opcional). "
                        "/ Vehicle type ID (optional)."
                    ),
                },
            },
            "required": ["infraction_id", "plate_number", "latitude", "longitude", "description"],
        },
    },
    {
        "name": "list_my_reports",
        "description": (
            "Listar los reportes de infracciones del usuario actual. "
            "/ List the current user's traffic violation reports."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "page": {
                    "type": "integer",
                    "description": "Numero de pagina (por defecto 1). / Page number (default 1).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_report_status",
        "description": (
            "Obtener el estado de un reporte especifico por su ID o codigo corto (ej: RPT-A1B2C3). "
            "/ Get the status of a specific report by its ID or short code (e.g., RPT-A1B2C3)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "report_id": {
                    "type": "string",
                    "description": (
                        "ID del reporte (UUID o codigo corto como RPT-A1B2C3). "
                        "/ Report ID (UUID or short code like RPT-A1B2C3)."
                    ),
                },
            },
            "required": ["report_id"],
        },
    },
    {
        "name": "get_wallet_balance",
        "description": (
            "Consultar el saldo de puntos y tokens MULTA del usuario. "
            "/ Check the user's points and MULTA token balance."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]
