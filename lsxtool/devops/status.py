"""
Módulo Status - Estado de ambiente DevOps
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


def show_status(
    env: str,
    fixture_data: Dict[str, Any],
    console: Console,
    mock: bool = False
) -> None:
    """
    Muestra el estado de un ambiente DevOps
    
    Args:
        env: Nombre del ambiente
        fixture_data: Datos del fixture
        console: Console de Rich para salida
        mock: Si True, simula respuestas
    """
    console.print(Panel.fit(f"[bold cyan]Status - Ambiente {env.upper()}[/bold cyan]", border_style="cyan"))
    
    if mock:
        console.print("[yellow]🎭 Modo MOCK[/yellow]")
    
    server = fixture_data.get("server", {})
    gitlab = fixture_data.get("gitlab", {})
    repo = fixture_data.get("repository", {})
    
    # Tabla de estado general
    status_table = Table(title="Estado del Ambiente", show_header=True, header_style="bold cyan")
    status_table.add_column("Componente", style="cyan")
    status_table.add_column("Estado", style="green")
    status_table.add_column("Detalles", style="yellow")
    
    # Estado del servidor
    host = server.get("host")
    port = server.get("port", 22)
    
    if mock:
        server_status = "[green]✔ Conectado (MOCK)[/green]"
        server_details = f"{server.get('user', 'N/A')}@{host}"
    else:
        is_connected = check_connectivity(host, port)
        server_status = "[green]✔ Conectado[/green]" if is_connected else "[red]✘ Desconectado[/red]"
        server_details = f"{server.get('user', 'N/A')}@{host}:{port}"
    
    status_table.add_row("Servidor", server_status, server_details)
    
    # Estado de GitLab
    gitlab_url = gitlab.get("url")
    gitlab_token = gitlab.get("token", "")
    project_path = gitlab.get("project")
    
    if mock:
        gitlab_status = "[green]✔ Conectado (MOCK)[/green]"
        gitlab_details = project_path or "N/A"
    else:
        gitlab_api = GitLabAPI(gitlab_url, gitlab_token, console=console, mock=mock)
        gitlab_ok = gitlab_api.test_connection()
        gitlab_status = "[green]✔ Conectado[/green]" if gitlab_ok else "[red]✘ Error de conexión[/red]"
        gitlab_details = project_path or "N/A"
    
    status_table.add_row("GitLab", gitlab_status, gitlab_details)
    
    # Estado del repositorio
    repo_path = repo.get("path")
    repo_branch = repo.get("branch")
    
    if repo_path:
        if mock:
            repo_status = "[green]✔ Accesible (MOCK)[/green]"
            repo_details = f"{repo_path} ({repo_branch})"
        else:
            user = server.get("user")
            auth = server.get("auth", {})
            key_path = None
            if auth.get("type") == "key" and auth.get("key_path"):
                key_path = Path(auth["key_path"].replace("~", str(Path.home())))
            
            success, stdout, stderr = ssh_execute(
                host=host,
                user=user,
                command=f"test -d {repo_path} && cd {repo_path} && git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'not_git'",
                key_path=key_path,
                console=console
            )
            
            if success and "not_git" not in stdout:
                current_branch = stdout.strip()
                repo_status = "[green]✔ Repositorio Git[/green]"
                repo_details = f"{repo_path} (branch: {current_branch})"
            elif success:
                repo_status = "[yellow]⚠ Directorio existe[/yellow]"
                repo_details = f"{repo_path} (no es repositorio Git)"
            else:
                repo_status = "[red]✘ No accesible[/red]"
                repo_details = repo_path
    else:
        repo_status = "[dim]N/A[/dim]"
        repo_details = "No configurado"
    
    status_table.add_row("Repositorio", repo_status, repo_details)
    
    console.print(status_table)
    
    # Información adicional
    console.print(f"\n[bold]Información adicional:[/bold]")
    info_table = Table(show_header=False, box=None)
    info_table.add_column("Campo", style="cyan", width=20)
    info_table.add_column("Valor", style="green")
    
    info_table.add_row("Ambiente", env.upper())
    info_table.add_row("Tipo de proyecto", fixture_data.get("project_type", "N/A"))
    info_table.add_row("Rama por defecto", gitlab.get("default_branch", "N/A"))
    
    runner = fixture_data.get("runner", {})
    if runner.get("enabled"):
        runner_tags = ", ".join(runner.get("tags", []))
        info_table.add_row("Runner", f"Activo ({runner_tags})")
    else:
        info_table.add_row("Runner", "Inactivo")
    
    console.print(info_table)
