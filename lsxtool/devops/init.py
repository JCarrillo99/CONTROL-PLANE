"""
Módulo Init - Inicialización de ambiente DevOps
"""

from typing import Dict, Any, Optional
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import sys
from pathlib import Path

# Agregar directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from .fixture_loader import FixtureLoader
from lsxtool.core.doctor import run_doctor
from lsxtool.core.ssh import ssh_test_connection
from lsxtool.core.gitlab import GitLabAPI
from lsxtool.core.tools import mask_sensitive_data


def init_environment(
    env: str,
    fixture_data: Dict[str, Any],
    console: Console,
    dry_run: bool = False,
    mock: bool = False
) -> tuple[bool, Optional[str]]:
    """
    Inicializa un ambiente DevOps
    
    Args:
        env: Nombre del ambiente
        fixture_data: Datos del fixture
        console: Console de Rich para salida
        dry_run: Si True, no ejecuta acciones reales
        mock: Si True, simula respuestas
    
    Returns:
        Tuple (success, error_message)
    """
    console.print(Panel.fit(f"[bold cyan]Init - Ambiente {env.upper()}[/bold cyan]", border_style="cyan"))
    
    if dry_run:
        console.print("[yellow]🔍 Modo DRY-RUN: No se ejecutarán acciones reales[/yellow]")
    
    if mock:
        console.print("[yellow]🎭 Modo MOCK: Simulando respuestas[/yellow]")
    
    # Validar fixture
    loader = FixtureLoader()
    is_valid, errors = loader.validate_fixture(fixture_data)
    
    if not is_valid:
        error_msg = "Errores en fixture:\n" + "\n".join(f"  - {e}" for e in errors)
        console.print(f"[red]✘ {error_msg}[/red]")
        return False, error_msg
    
    # Mostrar configuración
    console.print("\n[bold]Configuración del ambiente:[/bold]")
    config_table = Table(show_header=False, box=None)
    config_table.add_column("Campo", style="cyan", width=20)
    config_table.add_column("Valor", style="green")
    
    server = fixture_data.get("server", {})
    gitlab = fixture_data.get("gitlab", {})
    repo = fixture_data.get("repository", {})
    
    config_table.add_row("Servidor", f"{server.get('user', 'N/A')}@{server.get('host', 'N/A')}")
    config_table.add_row("GitLab", gitlab.get("url", "N/A"))
    config_table.add_row("Proyecto", gitlab.get("project", "N/A"))
    config_table.add_row("Repositorio", repo.get("branch", "N/A"))
    config_table.add_row("Tipo", fixture_data.get("project_type", "N/A"))
    
    console.print(config_table)
    
    # Verificar herramientas
    console.print("\n[bold]Verificando herramientas...[/bold]")
    required_tools = ["git", "ssh"]
    doctor_results = run_doctor(console, required_tools=required_tools)
    
    all_tools_ok = all(doctor_results.get(f"tool_{tool}", False) for tool in required_tools)
    
    if not all_tools_ok and not dry_run and not mock:
        return False, "Faltan herramientas requeridas"
    
    # Verificar conexión SSH
    if not dry_run:
        console.print("\n[bold]Verificando conexión SSH...[/bold]")
        host = server.get("host")
        user = server.get("user")
        auth = server.get("auth", {})
        
        if mock:
            console.print("[green]✔ Conexión SSH (MOCK)[/green]")
        else:
            key_path = None
            if auth.get("type") == "key" and auth.get("key_path"):
                key_path = Path(auth["key_path"].replace("~", str(Path.home())))
            
            if ssh_test_connection(host, user, key_path=key_path, console=console):
                console.print("[green]✔ Conexión SSH exitosa[/green]")
            else:
                console.print("[yellow]⚠ Conexión SSH falló (puede continuar)[/yellow]")
    
    # Verificar conexión GitLab
    if not dry_run:
        console.print("\n[bold]Verificando conexión GitLab...[/bold]")
        gitlab_url = gitlab.get("url")
        gitlab_token = gitlab.get("token", "")
        
        # Enmascarar token en salida
        masked_token = mask_sensitive_data(gitlab_token)
        console.print(f"[dim]Token: {masked_token}[/dim]")
        
        gitlab_api = GitLabAPI(gitlab_url, gitlab_token, console=console, mock=mock)
        
        if gitlab_api.test_connection():
            console.print("[green]✔ Conexión GitLab exitosa[/green]")
        else:
            console.print("[yellow]⚠ Conexión GitLab falló (puede continuar)[/yellow]")
    
    console.print("\n[bold green]✅ Ambiente inicializado[/bold green]")
    
    return True, None
