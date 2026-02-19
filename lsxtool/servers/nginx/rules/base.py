"""
Clase base para reglas de validación
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Callable


class Severity(Enum):
    """Severidad de un resultado de validación"""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class FixCapability(Enum):
    """Capacidad de corrección de un problema"""
    AUTO = "auto"  # Corrección automática segura y determinística
    INTERACTIVE = "interactive"  # Requiere confirmación o elección del usuario
    NONE = "none"  # No puede corregirse automáticamente


@dataclass
class ValidationResult:
    """Resultado de una validación"""
    rule_name: str
    severity: Severity
    message: str
    details: Optional[str] = None
    fix_capability: 'FixCapability' = FixCapability.NONE  # Capacidad de corrección
    fix_description: Optional[str] = None  # Descripción humana de la corrección
    fix_action: Optional['FixAction'] = None  # Acción de corrección disponible (solo para AUTO)
    
    @property
    def is_error(self) -> bool:
        """Retorna True si es un error"""
        return self.severity == Severity.ERROR
    
    @property
    def is_warning(self) -> bool:
        """Retorna True si es una advertencia"""
        return self.severity == Severity.WARNING
    
    @property
    def is_fixable(self) -> bool:
        """Retorna True si puede corregirse (AUTO o INTERACTIVE)"""
        return self.fix_capability in [FixCapability.AUTO, FixCapability.INTERACTIVE]
    
    @property
    def is_auto_fixable(self) -> bool:
        """Retorna True si puede corregirse automáticamente"""
        return self.fix_capability == FixCapability.AUTO
    
    @property
    def is_interactive_fixable(self) -> bool:
        """Retorna True si requiere corrección interactiva"""
        return self.fix_capability == FixCapability.INTERACTIVE


@dataclass
class NginxConfig:
    """Representación parseada de un archivo de configuración Nginx"""
    file_path: Path
    content: str
    meta: Dict[str, str]
    server_name: Optional[str] = None
    upstreams: Dict[str, Dict] = None  # {name: {servers: [...], ...}}
    proxy_pass: Optional[str] = None
    access_log: Optional[str] = None
    error_log: Optional[str] = None
    
    def __post_init__(self):
        if self.upstreams is None:
            self.upstreams = {}
    
    @property
    def domain_type(self) -> str:
        """root si dominio tiene 1 punto (ej: dev-lunarsystemx.com), subdomain si 2+ (ej: dev-identity.lunarsystemx.com)"""
        if not self.server_name:
            return "root"
        return "subdomain" if self.server_name.count(".") >= 2 else "root"


@dataclass
class FixAction:
    """Describe una acción de corrección"""
    description: str
    apply: callable  # Función que aplica el fix: (config: NginxConfig) -> str (nuevo contenido)
    affected_lines: Optional[List[int]] = None  # Líneas afectadas para diff
    
    def __call__(self, config: NginxConfig) -> str:
        """Aplica el fix y retorna el nuevo contenido"""
        return self.apply(config)


class ValidationRule(ABC):
    """Clase base abstracta para reglas de validación"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Nombre de la regla"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Descripción de lo que valida esta regla"""
        pass
    
    @abstractmethod
    def validate(self, config: NginxConfig) -> List[ValidationResult]:
        """
        Valida la configuración
        
        Args:
            config: Configuración Nginx parseada
        
        Returns:
            Lista de resultados de validación
        """
        pass
    
    def error(self, message: str, details: Optional[str] = None) -> ValidationResult:
        """Crea un resultado de error"""
        return ValidationResult(
            rule_name=self.name,
            severity=Severity.ERROR,
            message=message,
            details=details
        )
    
    def warning(self, message: str, details: Optional[str] = None) -> ValidationResult:
        """Crea un resultado de advertencia"""
        return ValidationResult(
            rule_name=self.name,
            severity=Severity.WARNING,
            message=message,
            details=details
        )
    
    def info(self, message: str, details: Optional[str] = None) -> ValidationResult:
        """Crea un resultado informativo"""
        return ValidationResult(
            rule_name=self.name,
            severity=Severity.INFO,
            message=message,
            details=details
        )
    
    def error_with_fix(
        self, 
        message: str, 
        details: Optional[str] = None,
        fix_capability: FixCapability = FixCapability.AUTO,
        fix_description: Optional[str] = None,
        fix_action: Optional[FixAction] = None
    ) -> ValidationResult:
        """Crea un resultado de error con capacidad de corrección"""
        return ValidationResult(
            rule_name=self.name,
            severity=Severity.ERROR,
            message=message,
            details=details,
            fix_capability=fix_capability,
            fix_description=fix_description,
            fix_action=fix_action
        )
    
    def warning_with_fix(
        self, 
        message: str, 
        details: Optional[str] = None,
        fix_capability: FixCapability = FixCapability.AUTO,
        fix_description: Optional[str] = None,
        fix_action: Optional[FixAction] = None
    ) -> ValidationResult:
        """Crea un resultado de advertencia con capacidad de corrección"""
        return ValidationResult(
            rule_name=self.name,
            severity=Severity.WARNING,
            message=message,
            details=details,
            fix_capability=fix_capability,
            fix_description=fix_description,
            fix_action=fix_action
        )
    
    def warning_interactive(
        self,
        message: str,
        details: Optional[str] = None,
        fix_description: Optional[str] = None
    ) -> ValidationResult:
        """Crea un resultado de advertencia que requiere corrección interactiva"""
        return ValidationResult(
            rule_name=self.name,
            severity=Severity.WARNING,
            message=message,
            details=details,
            fix_capability=FixCapability.INTERACTIVE,
            fix_description=fix_description
        )
    
    def warning_none(
        self,
        message: str,
        details: Optional[str] = None,
        reason: Optional[str] = None
    ) -> ValidationResult:
        """Crea un resultado de advertencia que no puede corregirse automáticamente"""
        return ValidationResult(
            rule_name=self.name,
            severity=Severity.WARNING,
            message=message,
            details=details,
            fix_capability=FixCapability.NONE,
            fix_description=reason or "Requiere acción manual"
        )
