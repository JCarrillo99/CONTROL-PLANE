"""
Validación de dominio y nombre de archivo
"""

from typing import List
from .base import ValidationRule, ValidationResult, NginxConfig, FixCapability


class DomainValidationRule(ValidationRule):
    """Valida que el nombre del archivo coincida con server_name"""
    
    @property
    def name(self) -> str:
        return "Dominio"
    
    @property
    def description(self) -> str:
        return "Valida que el nombre del archivo .conf coincida EXACTAMENTE con server_name"
    
    def validate(self, config: NginxConfig) -> List[ValidationResult]:
        results = []
        
        # Obtener nombre del archivo sin extensión
        file_name = config.file_path.stem
        
        # Obtener server_name
        if not config.server_name:
            results.append(self.error(
                "No se encontró server_name en la configuración",
                "El archivo debe contener: server_name dominio.com;"
            ))
            return results
        
        # Comparar (sin considerar mayúsculas/minúsculas)
        if file_name.lower() != config.server_name.lower():
            results.append(self.error_with_fix(
                f"El nombre del archivo no coincide con server_name",
                f"Archivo: {file_name}, server_name: {config.server_name}",
                fix_capability=FixCapability.INTERACTIVE,
                fix_description="Renombrar archivo para que coincida con server_name (requiere confirmación)"
            ))
        else:
            results.append(self.info(f"Nombre de archivo coincide con server_name: {config.server_name}"))
        
        return results
