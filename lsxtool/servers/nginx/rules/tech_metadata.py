"""
Validación de metadata de tecnologías runtime
Valida tech_provider y tech_manager cuando tech está presente
"""

from pathlib import Path
from typing import List, Optional
from .base import ValidationRule, ValidationResult, NginxConfig, FixCapability

# Importar catálogos con fallback
try:
    from ...sites.catalogs import get_tech_providers, get_tech_managers
except ImportError:
    import sys
    from pathlib import Path
    BASE_DIR = Path(__file__).parent.parent.parent.parent.parent
    sys.path.insert(0, str(BASE_DIR))
    from servers.sites.catalogs import get_tech_providers, get_tech_managers


class TechMetadataValidationRule(ValidationRule):
    """
    Valida que cuando tech está presente, tech_provider y tech_manager estén definidos
    y sean valores válidos del catálogo.
    
    Principio: DEFINICIÓN > DETECCIÓN
    - La metadata es la fuente de verdad
    - La detección solo se usa como sugerencia UX
    """
    
    @property
    def name(self) -> str:
        return "Tech Metadata"
    
    @property
    def description(self) -> str:
        return "Valida que tech_provider y tech_manager estén definidos cuando tech está presente"
    
    def validate(self, config: NginxConfig) -> List[ValidationResult]:
        results = []
        
        tech = config.meta.get("tech", "").lower() if config.meta.get("tech") else None
        
        # Si no hay tech, no hay nada que validar
        if not tech:
            return results
        
        # Cuando tech está presente, tech_provider y tech_manager son OBLIGATORIOS
        tech_provider = config.meta.get("tech_provider")
        tech_manager = config.meta.get("tech_manager")
        
        # Validar tech_provider
        if not tech_provider:
            # ERROR: metadata faltante (no error técnico)
            detected_providers = self._detect_tech_providers(tech)
            suggestion_text = ""
            if detected_providers:
                suggestion_text = f"\n\nSe detectaron en el sistema: {', '.join(detected_providers)}\n"
                suggestion_text += "Selecciona cuál usar para ESTE servicio (no se autoasignará)."
            
            results.append(self.error_with_fix(
                f"tech_provider es OBLIGATORIO cuando tech={tech}",
                f"Debe declararse explícitamente en META.{suggestion_text}",
                fix_capability=FixCapability.INTERACTIVE,
                fix_description=f"Configurar tech_provider para {tech} mediante wizard interactivo"
            ))
        else:
            # Validar que tech_provider esté en el catálogo
            valid_providers = get_tech_providers(tech)
            if tech_provider.lower() not in [p.lower() for p in valid_providers]:
                results.append(self.error_with_fix(
                    f"tech_provider '{tech_provider}' no es válido para {tech}",
                    f"Valores válidos: {', '.join(valid_providers)}",
                    fix_capability=FixCapability.INTERACTIVE,
                    fix_description=f"Corregir tech_provider a un valor válido del catálogo"
                ))
            else:
                results.append(self.info(
                    f"tech_provider '{tech_provider}' es válido para {tech}"
                ))
        
        # Validar tech_manager
        if not tech_manager:
            # ERROR: metadata faltante (no error técnico)
            detected_managers = self._detect_tech_managers(tech)
            suggestion_text = ""
            if detected_managers:
                suggestion_text = f"\n\nSe detectaron en el sistema: {', '.join(detected_managers)}\n"
                suggestion_text += "Selecciona cuál usar para ESTE servicio (no se autoasignará)."
            
            results.append(self.error_with_fix(
                f"tech_manager es OBLIGATORIO cuando tech={tech}",
                f"Debe declararse explícitamente en META.{suggestion_text}",
                fix_capability=FixCapability.INTERACTIVE,
                fix_description=f"Configurar tech_manager para {tech} mediante wizard interactivo"
            ))
        else:
            # Validar que tech_manager esté en el catálogo
            valid_managers = get_tech_managers(tech)
            if tech_manager.lower() not in [m.lower() for m in valid_managers]:
                results.append(self.error_with_fix(
                    f"tech_manager '{tech_manager}' no es válido para {tech}",
                    f"Valores válidos: {', '.join(valid_managers)}",
                    fix_capability=FixCapability.INTERACTIVE,
                    fix_description=f"Corregir tech_manager a un valor válido del catálogo"
                ))
            else:
                results.append(self.info(
                    f"tech_manager '{tech_manager}' es válido para {tech}"
                ))
        
        return results
    
    def _detect_tech_providers(self, tech: str) -> List[str]:
        """
        Detecta tech_providers instalados en el sistema
        SOLO para sugerencia UX, NUNCA para autoasignar
        
        Returns:
            Lista de tech_providers detectados
        """
        import shutil
        import os
        
        detected = []
        tech_lower = tech.lower()
        
        if tech_lower == "node":
            # Detectar volta
            if shutil.which("volta"):
                detected.append("volta")
            
            # Detectar nvm (verificar variable de entorno o ~/.nvm)
            if os.environ.get("NVM_DIR") or (Path.home() / ".nvm").exists():
                detected.append("nvm")
            
            # Detectar asdf
            if shutil.which("asdf") and os.environ.get("ASDF_DATA_DIR"):
                detected.append("asdf")
            
            # system siempre está disponible
            detected.append("system")
        
        elif tech_lower == "php":
            # Detectar phpbrew
            if shutil.which("phpbrew"):
                detected.append("phpbrew")
            
            # system siempre está disponible
            detected.append("system")
        
        elif tech_lower == "python":
            # Detectar pyenv
            if shutil.which("pyenv"):
                detected.append("pyenv")
            
            # Detectar asdf
            if shutil.which("asdf") and os.environ.get("ASDF_DATA_DIR"):
                detected.append("asdf")
            
            # system siempre está disponible
            detected.append("system")
        
        return detected
    
    def _detect_tech_managers(self, tech: str) -> List[str]:
        """
        Detecta tech_managers instalados en el sistema
        SOLO para sugerencia UX, NUNCA para autoasignar
        
        Returns:
            Lista de tech_managers detectados
        """
        detected = []
        tech_lower = tech.lower()
        import shutil
        
        if tech_lower == "node":
            if shutil.which("npm"):
                detected.append("npm")
            if shutil.which("yarn"):
                detected.append("yarn")
            if shutil.which("pnpm"):
                detected.append("pnpm")
            if shutil.which("bun"):
                detected.append("bun")
        
        elif tech_lower == "php":
            if shutil.which("composer"):
                detected.append("composer")
        
        elif tech_lower == "python":
            if shutil.which("pip"):
                detected.append("pip")
            if shutil.which("poetry"):
                detected.append("poetry")
        
        return detected
