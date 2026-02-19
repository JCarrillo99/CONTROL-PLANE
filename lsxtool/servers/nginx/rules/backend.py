"""
Validación de backend
"""

import re
from typing import List
from .base import ValidationRule, ValidationResult, NginxConfig, FixCapability


class BackendValidationRule(ValidationRule):
    """Valida que el backend declarado coincida con la ubicación y contenido del archivo"""
    
    @property
    def name(self) -> str:
        return "Backend"
    
    @property
    def description(self) -> str:
        return "Valida que el backend declarado en META coincida con la ubicación y contenido"
    
    def validate(self, config: NginxConfig) -> List[ValidationResult]:
        results = []
        
        sw = config.meta.get("server_web") or config.meta.get("backend")
        if not sw:
            results.append(self.error(
                "No se encontró campo 'server_web' (o 'backend') en META",
                "El archivo debe contener: # server_web: nginx"
            ))
            return results
        
        backend = sw.lower()
        
        # Validar que el archivo esté en la ubicación correcta
        file_path_str = str(config.file_path)
        
        if backend == "nginx":
            # Debe estar bajo /etc/nginx/ (en la estructura de configuración)
            if "/nginx/" not in file_path_str:
                results.append(self.warning(
                    "El archivo no está en la estructura esperada para Nginx",
                    f"Ruta actual: {config.file_path}"
                ))
            
            # No debe contener directivas de Apache
            apache_directives = ["<VirtualHost", "<Directory", "DocumentRoot", "SetHandler"]
            for directive in apache_directives:
                if directive in config.content:
                    results.append(self.error_with_fix(
                        f"Directiva de Apache encontrada en archivo Nginx: {directive}",
                        "Los archivos Nginx no deben contener directivas de Apache",
                        fix_capability=FixCapability.INTERACTIVE,
                        fix_description="Eliminar directivas de Apache (requiere revisión manual)"
                    ))
            
            # No debe contener PHP-FPM directo (debe usar upstream)
            if "php-fpm.sock" in config.content and "upstream" not in config.content:
                results.append(self.warning_interactive(
                    "PHP-FPM detectado sin upstream",
                    "Se recomienda usar upstream para PHP-FPM",
                    fix_description="Crear upstream para PHP-FPM (requiere confirmación)"
                ))
        
        elif backend == "apache":
            results.append(self.warning(
                "Backend Apache detectado en archivo de configuración Nginx",
                "Este archivo debería estar en la estructura de Apache"
            ))
        
        if not any(r.is_error for r in results):
            results.append(self.info(f"Backend '{backend}' validado correctamente"))
        
        return results
