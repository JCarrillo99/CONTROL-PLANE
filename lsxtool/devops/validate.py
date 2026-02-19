"""
Módulo Validate - Validación de configuración y estado
"""

from typing import Dict, Any, Optional
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from .fixture_loader import FixtureLoader
from lsxtool.core.ssh import ssh_execute
from lsxtool.core.gitlab import GitLabAPI
from lsxtool.core.doctor import check_connectivity


def validate_environment(
    env: str,
    fixture_data: Dict[str, Any],
    console: Console,
    dry_run: bool = False,
    mock: bool = False
) -> tuple[bool, Optional[str]]:
    """
    Valida un ambiente DevOps
    
    Args:
        env: Nombre del ambiente
        fixture_data: Datos del fixture
        console: Console de Rich para salida
        dry_run: Si True, no ejecuta acciones reales
        mock: Si True, simula respuestas
    
    Returns:
        Tuple (success, error_message)
    """
    console.print(Panel.fit(f"[bold cyan]Validate - Ambiente {env.upper()}[/bold cyan]", border_style="cyan"))
    
    if dry_run:
        console.print("[yellow]🔍 Modo DRY-RUN[/yellow]")
    
    if mock:
        console.print("[yellow]🎭 Modo MOCK[/yellow]")
    
    validation_results = []
    
    # Validar fixture
    loader = FixtureLoader()
    is_valid, errors = loader.validate_fixture(fixture_data)
    validation_results.append(("Fixture", is_valid, None if is_valid else "\n".join(errors)))
    
    # Validar servidor
    server = fixture_data.get("server", {})
    host = server.get("host")
    port = server.get("port", 22)
    
    if not dry_run:
        if mock:
            validation_results.append(("Conectividad Servidor", True, None))
        else:
            is_connected = check_connectivity(host, port)
            validation_results.append(("Conectividad Servidor", is_connected, None if is_connected else "No se puede conectar"))
    
    # Validar GitLab
    gitlab = fixture_data.get("gitlab", {})
    gitlab_url = gitlab.get("url")
    gitlab_token = gitlab.get("token", "")
    
    if not dry_run:
        gitlab_api = GitLabAPI(gitlab_url, gitlab_token, console=console, mock=mock)
        gitlab_ok = gitlab_api.test_connection()
        validation_results.append(("GitLab API", gitlab_ok, None))
        
        # Validar proyecto GitLab
        project_path = gitlab.get("project")
        if project_path:
            project_ok, project_data, project_error = gitlab_api.get_project(project_path)
            validation_results.append(("Proyecto GitLab", project_ok, project_error))
    
    # Validar repositorio
    repo = fixture_data.get("repository", {})
    repo_path = Path(repo.get("path", ""))
    
    if repo_path:
        if mock or dry_run:
            validation_results.append(("Ruta Repositorio", True, None))
        else:
            # Verificar en servidor remoto
            user = server.get("user")
            auth = server.get("auth", {})
            key_path = None
            if auth.get("type") == "key" and auth.get("key_path"):
                key_path = Path(auth["key_path"].replace("~", str(Path.home())))
            
            if not mock:
                success, stdout, stderr = ssh_execute(
                    host=host,
                    user=user,
                    command=f"test -d {repo_path} && echo 'exists' || echo 'not_found'",
                    key_path=key_path,
                    console=console
                )
                
                if success and "exists" in stdout:
                    validation_results.append(("Ruta Repositorio", True, None))
                else:
                    validation_results.append(("Ruta Repositorio", False, f"Ruta no existe: {repo_path}"))
    
    # Mostrar resultados
    console.print("\n[bold]Resultados de validación:[/bold]")
    results_table = Table(show_header=True, header_style="bold cyan")
    results_table.add_column("Validación", style="cyan")
    results_table.add_column("Estado", style="green")
    results_table.add_column("Detalles", style="yellow")
    
    all_valid = True
    for check_name, is_valid, error_msg in validation_results:
        status = "[green]✔[/green]" if is_valid else "[red]✘[/red]"
        details = error_msg or "[dim]OK[/dim]"
        results_table.add_row(check_name, status, details)
        if not is_valid:
            all_valid = False
    
    console.print(results_table)
    
    if all_valid:
        console.print("\n[bold green]✅ Todas las validaciones pasaron[/bold green]")
        return True, None
    else:
        console.print("\n[yellow]⚠️ Algunas validaciones fallaron[/yellow]")
        return False, "Validaciones fallidas"
