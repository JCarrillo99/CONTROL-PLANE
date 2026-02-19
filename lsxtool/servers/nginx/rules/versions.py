"""
Validación de versiones
"""

import subprocess
from typing import List
from pathlib import Path
import sys
from .base import ValidationRule, ValidationResult, NginxConfig, FixCapability


class VersionsValidationRule(ValidationRule):
    """Valida que las versiones en META coincidan con las instaladas"""
    
    @property
    def name(self) -> str:
        return "Versiones"
    
    @property
    def description(self) -> str:
        return "Valida que backend_version y tech_version sean válidas"
    
    def validate(self, config: NginxConfig) -> List[ValidationResult]:
        results = []
        
        # Validar server_web_version (compat: backend_version)
        declared_version = config.meta.get("server_web_version") or config.meta.get("backend_version")
        if declared_version:
            sw = (config.meta.get("server_web") or config.meta.get("backend") or "").lower()
            
            if sw == "nginx":
                installed_version = self._get_nginx_version()
                if installed_version:
                    # Comparar versiones (solo mayor.minor)
                    if self._version_match(declared_version, installed_version):
                        results.append(self.info(
                            f"server_web_version '{declared_version}' coincide con Nginx instalado ({installed_version})"
                        ))
                    else:
                        results.append(self.warning(
                            f"server_web_version '{declared_version}' no coincide con Nginx instalado ({installed_version})",
                            "Actualiza el campo server_web_version en META"
                        ))
                else:
                    results.append(self.warning(
                        "No se pudo detectar la versión de Nginx instalada",
                        "Verifica que Nginx esté instalado y accesible"
                    ))
        
        # Validar tech_version
        # PRINCIPIO: DEFINICIÓN > DETECCIÓN
        # La metadata declarada es la fuente de verdad
        # La detección solo se usa como sugerencia informativa
        if "tech" in config.meta and "tech_version" in config.meta:
            tech = config.meta["tech"].lower()
            tech_version = config.meta["tech_version"]
            
            # Verificar que tech_provider y tech_manager estén definidos primero
            # (validado por TechMetadataValidationRule, pero verificamos aquí para contexto)
            tech_provider = config.meta.get("tech_provider")
            tech_manager = config.meta.get("tech_manager")
            
            if not tech_provider or not tech_manager:
                # Si falta metadata obligatoria, no intentar validar versiones
                # (será manejado por TechMetadataValidationRule)
                results.append(self.warning_none(
                    f"tech_version declarada pero falta tech_provider o tech_manager",
                    "Completa la metadata obligatoria antes de validar versiones",
                    reason="Requiere tech_provider y tech_manager para validar tech_version correctamente"
                ))
                return results
            
            # Si la metadata está completa, validar tech_version
            # La detección es solo informativa, no bloqueante
            try:
                # Intentar importar desde el path correcto
                base_dir = Path(__file__).parent.parent.parent.parent.parent
                sys.path.insert(0, str(base_dir))
                from servers.sites.tech_versions import (
                    get_php_versions,
                    get_node_versions,
                    get_python_versions
                )
                
                valid_versions = []
                if tech == "php":
                    valid_versions = get_php_versions()
                elif tech == "node":
                    valid_versions = get_node_versions()
                elif tech == "python":
                    valid_versions = get_python_versions()
                
                if valid_versions:
                    # Normalizar versión (puede ser "20.x" o "20.11.0")
                    tech_version_normalized = tech_version.split(".")[0] + "." + tech_version.split(".")[1] if "." in tech_version else tech_version
                    
                    version_found = False
                    for valid_version in valid_versions:
                        valid_normalized = valid_version.split(".")[0] + "." + valid_version.split(".")[1] if "." in valid_version else valid_version
                        if tech_version_normalized == valid_normalized or tech_version in valid_version:
                            version_found = True
                            results.append(self.info(
                                f"tech_version '{tech_version}' declarada y coincide con versiones detectadas"
                            ))
                            break
                    
                    if not version_found:
                        # INFORMATIVO: la versión declarada no coincide con detectada
                        # Pero la metadata declarada tiene prioridad
                        results.append(self.warning_none(
                            f"tech_version '{tech_version}' declarada no coincide con versiones detectadas",
                            f"Versiones detectadas: {', '.join(valid_versions)}. "
                            f"La versión declarada en META tiene prioridad.",
                            reason="La metadata declarada es la fuente de verdad. La detección es solo informativa."
                        ))
                else:
                    # No se pudieron detectar versiones, pero la metadata declarada es válida
                    results.append(self.info(
                        f"tech_version '{tech_version}' declarada en META (no se detectaron versiones instaladas para comparar)"
                    ))
            except Exception as e:
                # Error en detección, pero la metadata declarada es válida
                results.append(self.info(
                    f"tech_version '{tech_version}' declarada en META (error al detectar versiones: {str(e)})"
                ))
        
        return results
    
    def _get_nginx_version(self) -> str:
        """Obtiene la versión de Nginx instalada"""
        try:
            result = subprocess.run(
                ["nginx", "-v"],
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                timeout=5
            )
            output = result.stderr if result.stderr else result.stdout
            if output and "nginx version:" in output:
                parts = output.split("nginx/")
                if len(parts) > 1:
                    return parts[1].strip()
        except:
            pass
        return None
    
    def _version_match(self, declared: str, installed: str) -> bool:
        """Compara versiones (solo mayor.minor)"""
        try:
            declared_parts = declared.split(".")[:2]
            installed_parts = installed.split(".")[:2]
            return declared_parts == installed_parts
        except:
            return False
