"""Claude tool definitions for the Multando chatbot.

These tools are used by both the REST API chatbot and the WhatsApp chatbot.
"""

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
            "Crear un nuevo reporte de infraccion de transito. Solo llamar DESPUES de que "
            "el usuario haya confirmado todos los detalles. "
            "/ Create a new traffic infraction report. Only call AFTER the user "
            "has confirmed all details."
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
            "/ List the current user's traffic infraction reports."
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
    {
        "name": "analyze_evidence",
        "description": (
            "Analizar una imagen enviada por el usuario para detectar infracciones de transito. "
            "Extrae placa, tipo de vehiculo, color y detalles de la infraccion. "
            "/ Analyze a user-uploaded image for traffic infraction evidence. "
            "Extracts plate number, vehicle type, color, and infraction details."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "image_description": {
                    "type": "string",
                    "description": (
                        "Descripcion de lo que se observa en la imagen. "
                        "/ Description of what is observed in the image."
                    ),
                },
            },
            "required": [],
        },
    },
]
