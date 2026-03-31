"""Maps Multando city names to Colombian department and municipality names.

The RECORD form uses department + municipality dropdowns that correspond to
Colombia's official DANE division codes. This module provides the mapping from
the city names used in Multando to the exact strings expected by the form.
"""

import logging
from typing import NamedTuple

logger = logging.getLogger(__name__)


class DepartmentCity(NamedTuple):
    """A (department, municipality) pair matching the RECORD form values."""

    department: str
    municipality: str


# Mapping of Multando city names to (department, municipality) tuples.
# The department and municipality strings must exactly match the <option> values
# in the RECORD form dropdowns (fieldFrm715 and fieldFrm715Ciudad).
CITY_TO_DEPARTMENT: dict[str, DepartmentCity] = {
    # Major cities
    "Bogotá": DepartmentCity("Bogotá D.C", "Bogotá D.C"),
    "Medellín": DepartmentCity("Antioquia", "Medellín"),
    "Cali": DepartmentCity("Valle del Cauca", "Cali"),
    "Barranquilla": DepartmentCity("Atlántico", "Barranquilla"),
    "Cartagena": DepartmentCity("Bolívar", "Cartagena de Indias"),
    "Bucaramanga": DepartmentCity("Santander", "Bucaramanga"),
    "Cúcuta": DepartmentCity("Norte de Santander", "Cúcuta"),
    "Pereira": DepartmentCity("Risaralda", "Pereira"),
    "Santa Marta": DepartmentCity("Magdalena", "Santa Marta"),
    "Manizales": DepartmentCity("Caldas", "Manizales"),
    # Secondary cities
    "Ibagué": DepartmentCity("Tolima", "Ibagué"),
    "Villavicencio": DepartmentCity("Meta", "Villavicencio"),
    "Pasto": DepartmentCity("Nariño", "Pasto"),
    "Montería": DepartmentCity("Córdoba", "Montería"),
    "Neiva": DepartmentCity("Huila", "Neiva"),
    "Valledupar": DepartmentCity("Cesar", "Valledupar"),
    "Armenia": DepartmentCity("Quindío", "Armenia"),
    "Sincelejo": DepartmentCity("Sucre", "Sincelejo"),
    "Popayán": DepartmentCity("Cauca", "Popayán"),
    "Tunja": DepartmentCity("Boyacá", "Tunja"),
    "Florencia": DepartmentCity("Caquetá", "Florencia"),
    "Riohacha": DepartmentCity("La Guajira", "Riohacha"),
    "Quibdó": DepartmentCity("Chocó", "Quibdó"),
    "Yopal": DepartmentCity("Casanare", "Yopal"),
    "Leticia": DepartmentCity("Amazonas", "Leticia"),
    "Mocoa": DepartmentCity("Putumayo", "Mocoa"),
    "Arauca": DepartmentCity("Arauca", "Arauca"),
    "San José del Guaviare": DepartmentCity("Guaviare", "San José del Guaviare"),
    "Inírida": DepartmentCity("Guainía", "Inírida"),
    "Mitú": DepartmentCity("Vaupés", "Mitú"),
    "Puerto Carreño": DepartmentCity("Vichada", "Puerto Carreño"),
    "San Andrés": DepartmentCity("San Andrés y Providencia", "San Andrés"),
    # Metro area / satellite cities
    "Envigado": DepartmentCity("Antioquia", "Envigado"),
    "Bello": DepartmentCity("Antioquia", "Bello"),
    "Itagüí": DepartmentCity("Antioquia", "Itagüí"),
    "Sabaneta": DepartmentCity("Antioquia", "Sabaneta"),
    "Soacha": DepartmentCity("Cundinamarca", "Soacha"),
    "Chía": DepartmentCity("Cundinamarca", "Chía"),
    "Zipaquirá": DepartmentCity("Cundinamarca", "Zipaquirá"),
    "Soledad": DepartmentCity("Atlántico", "Soledad"),
    "Palmira": DepartmentCity("Valle del Cauca", "Palmira"),
    "Buenaventura": DepartmentCity("Valle del Cauca", "Buenaventura"),
    "Tuluá": DepartmentCity("Valle del Cauca", "Tuluá"),
    "Dosquebradas": DepartmentCity("Risaralda", "Dosquebradas"),
    "Floridablanca": DepartmentCity("Santander", "Floridablanca"),
    "Girón": DepartmentCity("Santander", "Girón"),
    "Piedecuesta": DepartmentCity("Santander", "Piedecuesta"),
    "Sogamoso": DepartmentCity("Boyacá", "Sogamoso"),
    "Duitama": DepartmentCity("Boyacá", "Duitama"),
}

# Normalised lookup (lowercase, stripped) for fuzzy matching
_NORMALISED_MAP: dict[str, DepartmentCity] = {
    key.lower().strip(): value for key, value in CITY_TO_DEPARTMENT.items()
}


class CityNotMappedError(Exception):
    """Raised when a city name cannot be mapped to a department."""

    pass


def get_department_and_city(city_name: str) -> tuple[str, str]:
    """Map a Multando city name to RECORD department and municipality.

    Args:
        city_name: The city name as stored in Multando (e.g. "Bogotá").

    Returns:
        A (department, municipality) tuple matching the RECORD form options.

    Raises:
        CityNotMappedError: If the city is not in the mapping.
    """
    # Try exact match first
    result = CITY_TO_DEPARTMENT.get(city_name)
    if result is not None:
        return result.department, result.municipality

    # Try normalised match
    normalised = city_name.lower().strip()
    result = _NORMALISED_MAP.get(normalised)
    if result is not None:
        return result.department, result.municipality

    logger.warning("City '%s' not found in RECORD department mapping", city_name)
    raise CityNotMappedError(
        f"City '{city_name}' is not mapped to a Colombian department. "
        "Add it to CITY_TO_DEPARTMENT in department_mapper.py."
    )
