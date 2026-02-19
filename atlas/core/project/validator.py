"""
Validación de configuración y modelos (lógica pura).

Sin I/O; solo reglas de negocio sobre estructuras de datos.
"""

from typing import Any, Dict, List, Optional

from atlas.core.errors import ValidationError


def validate_domain_slug(slug: str) -> None:
    """Valida que el slug sea seguro para paths y nombres."""
    if not slug or not slug.strip():
        raise ValidationError("El slug no puede estar vacío")
    if any(c in slug for c in "/\\:*?\"<>|"):
        raise ValidationError("El slug no puede contener caracteres prohibidos en paths")


def validate_environment(env: str) -> None:
    """Valida que el ambiente sea uno de los permitidos."""
    allowed = {"dev", "qa", "prod"}
    if env.lower() not in allowed:
        raise ValidationError(f"Ambiente debe ser uno de: {allowed}")


def validate_desired_config(desired: Dict[str, Any]) -> List[str]:
    """
    Valida un diccionario de configuración deseada.
    Devuelve lista de mensajes de error; si vacía, es válido.
    """
    errors: List[str] = []
    if not isinstance(desired, dict):
        errors.append("La configuración deseada debe ser un diccionario")
        return errors
    # Reglas mínimas; extensible por dominio
    if "domain" in desired and not isinstance(desired.get("domain"), str):
        errors.append("'domain' debe ser una cadena")
    return errors
