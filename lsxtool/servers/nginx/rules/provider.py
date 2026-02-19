"""
Validación de provider y environment
"""

from typing import List
from .base import ValidationRule, ValidationResult, NginxConfig, FixCapability


class ProviderValidationRule(ValidationRule):
    """Valida que provider y environment se reflejen en paths y estructura"""
    
    @property
    def name(self) -> str:
        return "Provider/Environment"
    
    @property
    def description(self) -> str:
        return "Valida que provider y environment se reflejen en paths, estructura de carpetas y naming"
    
    def validate(self, config: NginxConfig) -> List[ValidationResult]:
        results = []
        
        provider = config.meta.get("provider", "").lower()
        environment = config.meta.get("environment", "").lower()
        
        if not provider or not environment:
            results.append(self.error(
                "provider y environment son requeridos en META",
                "El archivo debe contener: # provider: LSX y # environment: dev"
            ))
            return results
        
        # Validar que el path del archivo refleje provider y environment
        file_path_str = str(config.file_path)
        
        # Buscar si el path contiene el provider (puede estar en diferentes lugares)
        # Ejemplo: .../conf.d/lunarsystemx/dev/... o .../conf.d/stic/dev/...
        provider_in_path = provider in file_path_str.lower()
        environment_in_path = environment in file_path_str.lower()
        
        if not provider_in_path:
            results.append(self.warning_none(
                f"Provider '{provider}' no se refleja claramente en la ruta del archivo",
                f"Ruta: {config.file_path}",
                reason="Requiere mover el archivo manualmente a la estructura correcta"
            ))
        
        if not environment_in_path:
            results.append(self.warning_none(
                f"Environment '{environment}' no se refleja claramente en la ruta del archivo",
                f"Ruta: {config.file_path}",
                reason="Requiere mover el archivo manualmente a la estructura correcta"
            ))
        
        if provider_in_path and environment_in_path:
            results.append(self.info(
                f"Provider '{provider}' y environment '{environment}' se reflejan en la estructura"
            ))
        
        return results
