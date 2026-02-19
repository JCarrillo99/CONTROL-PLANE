"""
Validación de metadatos META
"""

import re
from typing import List
from .base import ValidationRule, ValidationResult, NginxConfig, FixAction, FixCapability


class MetaValidationRule(ValidationRule):
    """Valida que existan todos los campos META requeridos"""
    
    @property
    def name(self) -> str:
        return "META"
    
    @property
    def description(self) -> str:
        return "Valida que todos los campos META requeridos existan y tengan valores válidos"
    
    def validate(self, config: NginxConfig) -> List[ValidationResult]:
        results = []
        
        # Campos requeridos
        required_fields = [
            "server_web",
            "server_web_version",
            "environment",
            "owner",
            "provider",
            "service_type"
        ]
        
        # Verificar campos requeridos (compat: backend → server_web, backend_version → server_web_version)
        missing_fields = []
        for field in required_fields:
            if field == "server_web":
                if not (config.meta.get("server_web") or config.meta.get("backend")):
                    missing_fields.append(field)
            elif field == "server_web_version":
                if not (config.meta.get("server_web_version") or config.meta.get("backend_version")):
                    missing_fields.append(field)
            elif field not in config.meta or not config.meta[field]:
                missing_fields.append(field)
        
        if missing_fields:
            # META requiere wizard interactivo
            results.append(self.error_with_fix(
                f"Campos META requeridos faltantes: {', '.join(missing_fields)}",
                f"El archivo debe contener todos los campos META requeridos",
                fix_capability=FixCapability.INTERACTIVE,
                fix_description=f"Crear bloque META completo mediante wizard interactivo"
            ))
        
        # Validar valores específicos
        if "environment" in config.meta:
            valid_envs = ["dev", "qa", "prod"]
            if config.meta["environment"] not in valid_envs:
                results.append(self.error_with_fix(
                    f"Ambiente inválido: {config.meta['environment']}",
                    f"Debe ser uno de: {', '.join(valid_envs)}",
                    fix_capability=FixCapability.INTERACTIVE,
                    fix_description="Corregir valor de environment en META mediante wizard"
                ))
        
        sw = config.meta.get("server_web") or config.meta.get("backend")
        if sw:
            valid_servers = ["nginx", "apache", "caddy", "traefik"]
            if sw.lower() not in valid_servers:
                results.append(self.error_with_fix(
                    f"Server web inválido: {sw}",
                    f"Debe ser uno de: {', '.join(valid_servers)}",
                    fix_capability=FixCapability.INTERACTIVE,
                    fix_description="Corregir valor de server_web en META mediante wizard"
                ))
        
        if not results:
            results.append(self.info("Todos los campos META requeridos están presentes"))
        
        return results
