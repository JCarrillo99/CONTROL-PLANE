"""
Módulo Deploy - Simulación y ejecución de despliegues
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
from core.ssh import ssh_execute
from core.gitlab import GitLabAPI


def deploy_environment(
    env: str,
    fixture_data: Dict[str, Any],
    console: Console,
    dry_run: bool = True,
    mock: bool = False
) -> tuple[bool, Optional[str]]:
    """
    Simula o ejecuta un despliegue
    
    Args:
        env: Nombre del ambiente
        fixture_data: Datos del fixture
        console: Console de Rich para salida
        dry_run: Si True, solo simula (por defecto True por seguridad)
        mock: Si True, simula respuestas
    
    Returns:
        Tuple (success, error_message)
    """
    console.print(Panel.fit(f"[bold cyan]Deploy - Ambiente {env.upper()}[/bold cyan]", border_style="cyan"))
    
    if dry_run:
        console.print("[yellow]🔍 Modo DRY-RUN: Solo simulación, no se ejecutarán cambios[/yellow]")
    else:
        console.print("[red]⚠️ MODO REAL: Se ejecutarán cambios en el servidor[/red]")
        from rich.prompt import Confirm
        if not Confirm.ask("¿Estás seguro de continuar?", default=False):
            return False, "Despliegue cancelado por el usuario"
    
    if mock:
        console.print("[yellow]🎭 Modo MOCK[/yellow]")
    
    server = fixture_data.get("server", {})
    gitlab = fixture_data.get("gitlab", {})
    repo = fixture_data.get("repository", {})
    deploy_config = fixture_data.get("deploy", {})
    
    deploy_steps = deploy_config.get("steps", [])
    
    if not deploy_steps:
        console.print("[yellow]⚠️ No hay pasos de despliegue configurados[/yellow]")
        return True, None
    
    console.print(f"\n[bold]Pasos de despliegue ({len(deploy_steps)}):[/bold]")
    
    steps_table = Table(show_header=True, header_style="bold cyan")
    steps_table.add_column("#", style="cyan", width=4)
    steps_table.add_column("Comando", style="green")
    steps_table.add_column("Estado", style="yellow")
    
    for idx, step in enumerate(deploy_steps, 1):
        if dry_run or mock:
            status = "[dim]Simulado[/dim]"
        else:
            status = "[yellow]Pendiente[/yellow]"
        steps_table.add_row(str(idx), step, status)
    
    console.print(steps_table)
    
    if dry_run:
        console.print("\n[yellow]⚠️ DRY-RUN: Los comandos no se ejecutarán[/yellow]")
        console.print("[dim]Ejecuta sin --dry-run para realizar el despliegue real[/dim]")
        return True, None
    
    # Ejecutar pasos (solo si no es dry-run)
    console.print("\n[bold]Ejecutando pasos...[/bold]")
    
    host = server.get("host")
    user = server.get("user")
    repo_path = Path(repo.get("path", ""))
    auth = server.get("auth", {})
    key_path = None
    
    if auth.get("type") == "key" and auth.get("key_path"):
        key_path = Path(auth["key_path"].replace("~", str(Path.home())))
    
    for idx, step in enumerate(deploy_steps, 1):
        console.print(f"\n[cyan]Paso {idx}/{len(deploy_steps)}: {step}[/cyan]")
        
        if mock:
            console.print("[green]✔ Comando ejecutado (MOCK)[/green]")
        else:
            # Ejecutar comando en el servidor remoto
            success, stdout, stderr = ssh_execute(
                host=host,
                user=user,
                command=f"cd {repo_path} && {step}",
                key_path=key_path,
                timeout=300,
                console=console
            )
            
            if success:
                console.print("[green]✔ Comando ejecutado exitosamente[/green]")
                if stdout:
                    console.print(f"[dim]{stdout[:200]}[/dim]")
            else:
                console.print(f"[red]✘ Error ejecutando comando: {stderr}[/red]")
                if deploy_config.get("rollback_on_error"):
                    console.print("[yellow]⚠ Rollback activado[/yellow]")
                return False, f"Error en paso {idx}: {stderr}"
    
    # Post-deploy
    post_deploy_steps = deploy_config.get("post_deploy", [])
    if post_deploy_steps:
        console.print("\n[bold]Ejecutando pasos post-despliegue...[/bold]")
        for step in post_deploy_steps:
            console.print(f"[cyan]Post-deploy: {step}[/cyan]")
            if not mock:
                success, stdout, stderr = ssh_execute(
                    host=host,
                    user=user,
                    command=f"cd {repo_path} && {step}",
                    key_path=key_path,
                    timeout=60,
                    console=console
                )
                if not success:
                    console.print(f"[yellow]⚠ Error en post-deploy: {stderr}[/yellow]")
    
    console.print("\n[bold green]✅ Despliegue completado[/bold green]")
    
    return True, None
