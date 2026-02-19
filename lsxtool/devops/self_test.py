"""
Módulo Self-Test - Pruebas automatizadas del flujo DevOps
"""

import sys
from pathlib import Path
from typing import Dict, Any, Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from .fixture_loader import FixtureLoader
from .init import init_environment
from .validate import validate_environment
from .deploy import deploy_environment
from .status import show_status
from core.doctor import run_doctor


def run_self_test(
    env: str,
    console: Console,
    dry_run: bool = True,
    mock: bool = False,
    verbose: bool = False
) -> tuple[bool, Optional[str]]:
    """
    Ejecuta self-test completo del flujo DevOps
    
    Args:
        env: Nombre del ambiente (dev, qa, prod)
        console: Console de Rich para salida
        dry_run: Si True, no ejecuta acciones reales
        mock: Si True, simula respuestas
        verbose: Si True, muestra información detallada
    
    Returns:
        Tuple (success, error_message)
    """
    console.print(Panel.fit(f"[bold cyan]DEVOPS SELF TEST ({env.upper()})[/bold cyan]", border_style="cyan"))
    
    if dry_run:
        console.print("[yellow]🔍 Modo DRY-RUN activado[/yellow]")
    
    if mock:
        console.print("[yellow]🎭 Modo MOCK activado[/yellow]")
    
    # Cargar fixture
    loader = FixtureLoader()
    fixture_data = loader.load_fixture(env, console)
    
    if not fixture_data:
        return False, f"No se pudo cargar fixture para ambiente: {env}"
    
    # Validar fixture
    is_valid, errors = loader.validate_fixture(fixture_data)
    if not is_valid:
        error_msg = "Errores en fixture:\n" + "\n".join(f"  - {e}" for e in errors)
        console.print(f"[red]✘ {error_msg}[/red]")
        return False, error_msg
    
    # Doctor previo
    console.print("\n[bold]🩺 Doctor - Verificación previa[/bold]")
    required_tools = ["git", "ssh", "curl"]
    doctor_results = run_doctor(console, required_tools=required_tools)
    
    all_tools_ok = all(doctor_results.get(f"tool_{tool}", False) for tool in required_tools)
    
    if not all_tools_ok and not mock:
        missing = [tool for tool in required_tools if not doctor_results.get(f"tool_{tool}", False)]
        console.print(f"[yellow]⚠️ Faltan herramientas: {', '.join(missing)}[/yellow]")
        console.print("[dim]Algunos tests pueden fallar[/dim]")
    
    # Ejecutar flujo completo
    test_results = []
    
    # 1. Init
    console.print("\n[bold]1️⃣ Init[/bold]")
    init_success, init_error = init_environment(env, fixture_data, console, dry_run=dry_run, mock=mock)
    test_results.append(("init", init_success, init_error))
    
    # 2. Validate
    console.print("\n[bold]2️⃣ Validate[/bold]")
    validate_success, validate_error = validate_environment(env, fixture_data, console, dry_run=dry_run, mock=mock)
    test_results.append(("validate", validate_success, validate_error))
    
    # 3. Repository Access
    console.print("\n[bold]3️⃣ Repository Access[/bold]")
    repo = fixture_data.get("repository", {})
    repo_path = repo.get("path")
    
    if repo_path:
        if mock or dry_run:
            repo_success = True
            repo_error = None
        else:
            # Verificar acceso al repositorio
            server = fixture_data.get("server", {})
            host = server.get("host")
            user = server.get("user")
            auth = server.get("auth", {})
            key_path = None
            
            if auth.get("type") == "key" and auth.get("key_path"):
                key_path = Path(auth["key_path"].replace("~", str(Path.home())))
            
            from core.ssh import ssh_execute
            success, stdout, stderr = ssh_execute(
                host=host,
                user=user,
                command=f"test -d {repo_path} && echo 'exists'",
                key_path=key_path,
                console=console
            )
            repo_success = success and "exists" in stdout
            repo_error = None if repo_success else stderr
    else:
        repo_success = True
        repo_error = None
    
    test_results.append(("repository access", repo_success, repo_error))
    
    # 4. Deploy (simulado)
    console.print("\n[bold]4️⃣ Deploy[/bold]")
    deploy_success, deploy_error = deploy_environment(env, fixture_data, console, dry_run=True, mock=mock)
    test_results.append(("deploy", deploy_success, deploy_error))
    
    # Mostrar resumen
    console.print("\n[bold]📊 Resumen del Self-Test[/bold]")
    summary_table = Table(title="Resultados", show_header=True, header_style="bold cyan")
    summary_table.add_column("Test", style="cyan")
    summary_table.add_column("Estado", style="green")
    summary_table.add_column("Notas", style="yellow")
    
    for test_name, success, error in test_results:
        if success:
            status = "[green]✔[/green]"
            notes = "[dim]OK[/dim]"
        else:
            status = "[red]✘[/red]"
            notes = error or "[dim]Error[/dim]"
        
        # Ajustar nombre para deploy en dry-run
        if test_name == "deploy" and dry_run:
            notes = "[dim]dry-run[/dim]"
        
        summary_table.add_row(test_name, status, notes)
    
    console.print(summary_table)
    
    # Resultado final
    all_passed = all(success for success, _ in [(s, e) for _, s, e in test_results])
    
    if all_passed:
        console.print("\n[bold green]✅ Self-Test completado exitosamente[/bold green]")
        return True, None
    else:
        failed_tests = [name for name, success, _ in test_results if not success]
        error_msg = f"Tests fallidos: {', '.join(failed_tests)}"
        console.print(f"\n[yellow]⚠️ Self-Test completado con errores[/yellow]")
        console.print(f"[dim]{error_msg}[/dim]")
        return False, error_msg
