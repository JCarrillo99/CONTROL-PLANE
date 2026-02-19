"""
Cargador de fixtures para ambientes DevOps
"""

from pathlib import Path
from typing import Dict, Any, Optional
from rich.console import Console
from rich.panel import Panel

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


class FixtureLoader:
    """Carga y valida fixtures de ambientes"""
    
    def __init__(self, fixtures_dir: Optional[Path] = None):
        """
        Inicializa el cargador de fixtures
        
        Args:
            fixtures_dir: Directorio donde están los fixtures (por defecto: devops/fixtures)
        """
        if fixtures_dir is None:
            fixtures_dir = Path(__file__).parent / "fixtures"
        
        self.fixtures_dir = Path(fixtures_dir)
    
    def load_fixture(self, env: str, console: Optional[Console] = None) -> Optional[Dict[str, Any]]:
        """
        Carga un fixture de ambiente
        
        Args:
            env: Nombre del ambiente (dev, qa, prod)
            console: Console de Rich para salida
        
        Returns:
            Dict con datos del fixture o None si hay error
        """
        if not HAS_YAML:
            if console:
                console.print("[red]✘ Librería 'pyyaml' no instalada[/red]")
                console.print("[yellow]Instala con: pip install pyyaml[/yellow]")
            return None
        
        fixture_file = self.fixtures_dir / f"{env}.yaml"
        
        if not fixture_file.exists():
            if console:
                console.print(f"[red]✘ Fixture no encontrado: {fixture_file}[/red]")
            return None
        
        try:
            with open(fixture_file, "r") as f:
                fixture_data = yaml.safe_load(f)
            
            if console:
                console.print(f"[green]✔ Fixture cargado: {env}[/green]")
            
            return fixture_data
        except yaml.YAMLError as e:
            if console:
                console.print(f"[red]✘ Error al parsear YAML: {e}[/red]")
            return None
        except Exception as e:
            if console:
                console.print(f"[red]✘ Error al cargar fixture: {e}[/red]")
            return None
    
    def list_available_fixtures(self) -> list[str]:
        """
        Lista fixtures disponibles
        
        Returns:
            Lista de nombres de ambientes disponibles
        """
        if not self.fixtures_dir.exists():
            return []
        
        fixtures = []
        for yaml_file in self.fixtures_dir.glob("*.yaml"):
            fixtures.append(yaml_file.stem)
        
        return sorted(fixtures)
    
    def validate_fixture(self, fixture_data: Dict[str, Any]) -> tuple[bool, list[str]]:
        """
        Valida que un fixture tenga la estructura correcta
        
        Args:
            fixture_data: Datos del fixture
        
        Returns:
            Tuple (is_valid, list_of_errors)
        """
        errors = []
        required_keys = ["environment", "server", "gitlab", "repository"]
        
        for key in required_keys:
            if key not in fixture_data:
                errors.append(f"Falta clave requerida: {key}")
        
        # Validar estructura de server
        if "server" in fixture_data:
            server = fixture_data["server"]
            if "host" not in server:
                errors.append("server.host es requerido")
            if "user" not in server:
                errors.append("server.user es requerido")
        
        # Validar estructura de gitlab
        if "gitlab" in fixture_data:
            gitlab = fixture_data["gitlab"]
            if "url" not in gitlab:
                errors.append("gitlab.url es requerido")
            if "project" not in gitlab:
                errors.append("gitlab.project es requerido")
        
        return len(errors) == 0, errors
