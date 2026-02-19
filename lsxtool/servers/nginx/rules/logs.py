"""
Validación de logs
"""

import re
from typing import List, Optional
from .base import ValidationRule, ValidationResult, NginxConfig, FixAction, FixCapability


class LogsValidationRule(ValidationRule):
    """Valida que los logs sigan la estructura correcta"""
    
    @property
    def name(self) -> str:
        return "Logs"
    
    @property
    def description(self) -> str:
        return "Valida que los logs sigan la estructura: /var/log/{provider}/{environment}/{domain}/access.log"
    
    def validate(self, config: NginxConfig) -> List[ValidationResult]:
        results = []
        
        provider = config.meta.get("provider", "").lower()
        environment = config.meta.get("environment", "").lower()
        
        if not provider or not environment:
            results.append(self.warning(
                "No se puede validar estructura de logs sin provider y environment en META"
            ))
            return results
        
        # Estructura esperada: /var/log/{provider}/{environment}/{domain}/access.log
        if config.server_name:
            domain_slug = self._domain_to_slug(config.server_name)
            expected_access_log = f"/var/log/{provider}/{environment}/{domain_slug}/access.log"
            expected_error_log = f"/var/log/{provider}/{environment}/{domain_slug}/error.log"
        else:
            results.append(self.warning(
                "No se puede validar estructura de logs sin server_name"
            ))
            return results
        
        # Validar access_log
        if config.access_log:
            if config.access_log == expected_access_log:
                results.append(self.info(f"access_log sigue la estructura correcta: {config.access_log}"))
            else:
                # Verificar si usa ruta genérica
                if "/var/log/nginx/" in config.access_log and "*.log" not in config.access_log:
                    # Ruta genérica pero no wildcard
                    if config.access_log.endswith(".log"):
                        fix_action = self._create_log_fix_action("access_log", config.access_log, expected_access_log)
                        results.append(self.warning_with_fix(
                            f"access_log no sigue la estructura esperada",
                            f"Esperado: {expected_access_log}, Actual: {config.access_log}",
                            fix_capability=FixCapability.AUTO,
                            fix_description=f"Actualizar access_log a: {expected_access_log}",
                            fix_action=fix_action
                        ))
                    else:
                        fix_action = self._create_log_fix_action("access_log", config.access_log, expected_access_log)
                        results.append(self.error_with_fix(
                            f"access_log no sigue la estructura esperada",
                            f"Esperado: {expected_access_log}, Actual: {config.access_log}",
                            fix_capability=FixCapability.AUTO,
                            fix_description=f"Actualizar access_log a: {expected_access_log}",
                            fix_action=fix_action
                        ))
                else:
                    fix_action = self._create_log_fix_action("access_log", config.access_log, expected_access_log)
                    results.append(self.error_with_fix(
                        f"access_log no sigue la estructura esperada",
                        f"Esperado: {expected_access_log}, Actual: {config.access_log}",
                        fix_capability=FixCapability.AUTO,
                        fix_description=f"Actualizar access_log a: {expected_access_log}",
                        fix_action=fix_action
                    ))
        else:
            fix_action = self._create_log_fix_action("access_log", None, expected_access_log)
            results.append(self.error_with_fix(
                "No se encontró access_log en la configuración",
                f"Debe contener: access_log {expected_access_log};",
                fix_capability=FixCapability.AUTO,
                fix_description=f"Agregar access_log: {expected_access_log}",
                fix_action=fix_action
            ))
        
        # Validar error_log
        if config.error_log:
            if config.error_log == expected_error_log:
                results.append(self.info(f"error_log sigue la estructura correcta: {config.error_log}"))
            else:
                # Verificar si usa ruta genérica
                if "/var/log/nginx/" in config.error_log and "*.log" not in config.error_log:
                    if config.error_log.endswith(".log"):
                        fix_action = self._create_log_fix_action("error_log", config.error_log, expected_error_log)
                        results.append(self.warning_with_fix(
                            f"error_log no sigue la estructura esperada",
                            f"Esperado: {expected_error_log}, Actual: {config.error_log}",
                            fix_capability=FixCapability.AUTO,
                            fix_description=f"Actualizar error_log a: {expected_error_log}",
                            fix_action=fix_action
                        ))
                    else:
                        fix_action = self._create_log_fix_action("error_log", config.error_log, expected_error_log)
                        results.append(self.error_with_fix(
                            f"error_log no sigue la estructura esperada",
                            f"Esperado: {expected_error_log}, Actual: {config.error_log}",
                            fix_capability=FixCapability.AUTO,
                            fix_description=f"Actualizar error_log a: {expected_error_log}",
                            fix_action=fix_action
                        ))
                else:
                    fix_action = self._create_log_fix_action("error_log", config.error_log, expected_error_log)
                    results.append(self.error_with_fix(
                        f"error_log no sigue la estructura esperada",
                        f"Esperado: {expected_error_log}, Actual: {config.error_log}",
                        fix_capability=FixCapability.AUTO,
                        fix_description=f"Actualizar error_log a: {expected_error_log}",
                        fix_action=fix_action
                    ))
        else:
            fix_action = self._create_log_fix_action("error_log", None, expected_error_log)
            results.append(self.error_with_fix(
                "No se encontró error_log en la configuración",
                f"Debe contener: error_log {expected_error_log};",
                fix_capability=FixCapability.AUTO,
                fix_description=f"Agregar error_log: {expected_error_log}",
                fix_action=fix_action
            ))
        
        return results
    
    def _domain_to_slug(self, domain: str) -> str:
        """Convierte un dominio a slug para paths"""
        # Ejemplo: dev-identity.lunarsystemx.com -> identity
        domain = domain.replace("dev-", "").replace("qa-", "").replace("prod-", "")
        parts = domain.split(".")
        if parts:
            return parts[0]
        return domain.replace(".", "_").replace("-", "_")
    
    def _create_log_fix_action(self, log_type: str, current_path: Optional[str], expected_path: str) -> FixAction:
        """Crea una acción de fix para corregir paths de logs"""
        def apply_fix(config: NginxConfig) -> str:
            content = config.content
            
            if current_path:
                # Reemplazar path existente (puede tener parámetros como "combined")
                # Buscar línea completa: access_log /path combined;
                pattern = rf'{log_type}\s+{re.escape(current_path)}([^;]*);'
                replacement = f'{log_type} {expected_path}\\1;'
                content = re.sub(pattern, replacement, content)
            else:
                # Agregar nueva directiva
                # Buscar bloque server
                server_match = re.search(r'server\s*\{', content)
                if server_match:
                    insert_pos = server_match.end()
                    
                    # Buscar si hay sección de logs
                    log_section_match = re.search(r'#\s*==========\s*LOGS\s*==========', content)
                    if log_section_match:
                        # Insertar después de la sección de logs existente
                        # Buscar el último log en la sección
                        after_logs = log_section_match.end()
                        # Buscar siguiente línea no vacía o siguiente sección
                        next_section = re.search(r'#\s*==========', content[after_logs:])
                        if next_section:
                            insert_pos = after_logs + next_section.start()
                        else:
                            # Buscar siguiente línea después de logs
                            next_line = content.find('\n', after_logs)
                            if next_line != -1:
                                insert_pos = next_line + 1
                    else:
                        # Agregar sección de logs completa
                        log_block = f"\n    # ========== LOGS ==========\n    {log_type} {expected_path};\n"
                        # Insertar después de server_name si existe
                        server_name_match = re.search(r'server_name\s+[^;]+;', content)
                        if server_name_match:
                            insert_pos = server_name_match.end()
                            next_line = content.find('\n', insert_pos)
                            if next_line != -1:
                                insert_pos = next_line + 1
                        
                        content = content[:insert_pos] + log_block + content[insert_pos:]
                        return content
                    
                    # Agregar solo la directiva
                    content = content[:insert_pos] + f"    {log_type} {expected_path};\n" + content[insert_pos:]
            
            return content
        
        return FixAction(
            description=f"Actualizar {log_type} a: {expected_path}",
            apply=apply_fix
        )
