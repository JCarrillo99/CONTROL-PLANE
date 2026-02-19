"""
Validación de puertos
"""

import re
from typing import List
from .base import ValidationRule, ValidationResult, NginxConfig, FixCapability


class PortsValidationRule(ValidationRule):
    """Valida que los puertos en META coincidan con los del upstream"""
    
    @property
    def name(self) -> str:
        return "Puertos"
    
    @property
    def description(self) -> str:
        return "Valida que tech_port (META) aparezca en el upstream y no esté hardcodeado en proxy_pass"
    
    def validate(self, config: NginxConfig) -> List[ValidationResult]:
        results = []
        
        # Buscar puerto en META (tech_port genérico, o node_port/php_port/python_port compat)
        port_meta_key = None
        port_meta_value = None
        for key in ["tech_port", "node_port", "php_port", "python_port"]:
            if key in config.meta:
                port_meta_key = key
                port_meta_value = config.meta[key]
                break
        
        if not port_meta_value:
            # No hay puerto en META, no es obligatorio para todos los tipos
            return results
        
        # Validar que el puerto aparezca en el upstream
        port_found_in_upstream = False
        for upstream_name, upstream_data in config.upstreams.items():
            for server in upstream_data.get("servers", []):
                # Buscar puerto en server (ej: 127.0.0.1:3001)
                port_match = re.search(r':(\d+)', server)
                if port_match:
                    port = port_match.group(1)
                    if port == port_meta_value:
                        port_found_in_upstream = True
                        results.append(self.info(
                            f"Puerto {port_meta_value} ({port_meta_key}) encontrado en upstream '{upstream_name}'"
                        ))
                        break
        
        if port_meta_value and not port_found_in_upstream:
            results.append(self.warning_none(
                f"Puerto {port_meta_value} ({port_meta_key}) no encontrado en ningún upstream",
                f"El puerto declarado en META debe aparecer en el upstream",
                reason="Requiere actualización manual del upstream o del campo META"
            ))
        
        # Validar que el puerto NO esté hardcodeado en proxy_pass
        if config.proxy_pass:
            # Buscar puerto en proxy_pass (ej: http://127.0.0.1:3001)
            port_match = re.search(r':(\d+)', config.proxy_pass)
            if port_match:
                port_in_proxy = port_match.group(1)
                if port_in_proxy == port_meta_value:
                    results.append(self.error_with_fix(
                        f"Puerto hardcodeado en proxy_pass: {config.proxy_pass}",
                        "El puerto no debe estar en proxy_pass, debe estar en el upstream",
                        fix_capability=FixCapability.INTERACTIVE,
                        fix_description="Mover puerto de proxy_pass a upstream (requiere confirmación)"
                    ))
        
        return results
