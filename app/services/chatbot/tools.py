"""Claude tool definitions for the Multando chatbot.

These tools are used by both the REST API chatbot and the WhatsApp chatbot.
"""

TOOLS = [
    {
        "name": "send_reply",
        "description": (
            "Send the final reply to the user. This is the ONLY way to communicate with "
            "the user — never produce free-form assistant text; always call send_reply. "
            "Include quick_replies whenever the user's next input is a choice, a yes/no, "
            "or a confirmation, so the client can render them as tappable buttons. "
            "/ Enviar la respuesta final al usuario. Esta es la UNICA forma de responder "
            "al usuario; nunca escribas texto libre, siempre llama send_reply. Incluye "
            "quick_replies siempre que la siguiente entrada sea una eleccion, un si/no, "
            "o una confirmacion, para que el cliente los muestre como botones."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": (
                        "The visible message text (markdown allowed). Must NOT contain "
                        "[[button]] markers — use the quick_replies array instead."
                    ),
                },
                "quick_replies": {
                    "type": "array",
                    "description": (
                        "Optional list of quick-reply buttons shown below the message. "
                        "Required for yes/no and confirmation prompts. Max 4 items."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {
                                "type": "string",
                                "description": "Text shown on the button.",
                            },
                            "value": {
                                "type": "string",
                                "description": (
                                    "Value sent as the user's next message when tapped. "
                                    "Omit to reuse the label. Ignored when `action` is "
                                    "not `send_text`."
                                ),
                            },
                            "action": {
                                "type": "string",
                                "enum": [
                                    "send_text",
                                    "share_location",
                                    "take_photo",
                                    "pick_image",
                                    "open_url",
                                ],
                                "description": (
                                    "What happens when the user taps the button. "
                                    "`send_text` (default) sends `value` as a plain "
                                    "message. `share_location` opens the GPS picker. "
                                    "`take_photo` opens the camera. `pick_image` opens "
                                    "the gallery. `open_url` opens the URL in `value`. "
                                    "Use native actions when the next step really needs "
                                    "that input (e.g. ubicacion real, foto real)."
                                ),
                            },
                        },
                        "required": ["label"],
                    },
                    "maxItems": 4,
                },
            },
            "required": ["message"],
        },
    },
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
                        "Numero de placa del vehiculo reportado (tal como aparece en la evidencia). "
                        "/ License plate number of the reported vehicle (as shown in the evidence)."
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
        "name": "get_vehicle_types",
        "description": (
            "Obtener la lista de tipos de vehiculo disponibles. "
            "/ Get the list of available vehicle types."
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
