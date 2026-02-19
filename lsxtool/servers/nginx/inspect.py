"""
Inspección interactiva de configuración Nginx por dominio
Muestra checklist numerado y permite ver detalles
"""

from pathlib import Path
from typing import List, Dict, Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, IntPrompt
from rich import box

from .parser import parse_nginx_config, find_nginx_configs
from .rules import ALL_RULES, ValidationResult, Severity, FixCapability


def inspect_nginx_domain(domain: str, base_dir: Path, console: Console) -> bool:
    """
    Inspecciona un dominio específico de forma interactiva
    
    Args:
        domain: Dominio a inspeccionar
        base_dir: Directorio base del proyecto
        console: Console de Rich para output
    
    Returns:
        True si se encontró el dominio, False si no
    """
    # Buscar archivo de configuración del dominio
    config_files = find_nginx_configs(base_dir)
    
    config_file = None
    # Primero intentar coincidencia exacta
    for cf in config_files:
        if domain == cf.stem:
            config_file = cf
            break
    
    # Si no hay coincidencia exacta, buscar por prefijo (solo para prefijos simples)
    # Esto permite buscar "dev-identity" y encontrar "dev-identity.lunarsystemx.com"
    # Pero evita que "dev-identity.lunarsystemx.co" coincida con "dev-identity.lunarsystemx.com"
    if not config_file:
        for cf in config_files:
            file_stem = cf.stem
            # Solo permitir búsqueda por prefijo si el dominio NO contiene puntos
            # (es un prefijo simple como "dev-identity")
            # Y el archivo comienza con el dominio seguido de un punto
            if "." not in domain and file_stem.startswith(domain + "."):
                config_file = cf
                break
    
    if not config_file:
        console.print(f"[red]❌ No se encontró configuración para el dominio: {domain}[/red]")
        console.print("[yellow]💡 Usa 'lsxtool servers verify nginx' para ver todos los archivos[/yellow]")
        return False
    
    # Parsear configuración
    config = parse_nginx_config(config_file)
    if not config:
        console.print(f"[red]❌ Error al parsear: {config_file}[/red]")
        return False
    
    console.print(Panel.fit(
        f"[bold cyan]Inspección de Configuración Nginx[/bold cyan]\n"
        f"[dim]Dominio:[/dim] {domain}\n"
        f"[dim]Archivo:[/dim] {config_file.name}",
        border_style="cyan"
    ))

    # Estado declarativo: upstream_ref y catálogo
    try:
        from ..declarative.loader import DeclarativeLoader
        from ..declarative.upstream_loader import UpstreamCatalogLoader
        loader = DeclarativeLoader(base_dir, console)
        loader.load_all()
        domain_config = loader.get_domain(domain)
        if domain_config and getattr(domain_config.server_web, "upstream_ref", None):
            ref = domain_config.server_web.upstream_ref
            catalog = UpstreamCatalogLoader(base_dir, console)
            exists = catalog.exists(ref)
            if exists:
                console.print(f"\n[cyan]upstream_ref:[/cyan] {ref} [green]✓ en catálogo[/green]")
                defn = catalog.load(ref)
                if defn and defn.servers:
                    console.print(f"  [dim]Servers:[/dim] {', '.join(f'{s.host}:{s.port}' for s in defn.servers[:5])}")
                    if len(defn.servers) > 5:
                        console.print(f"  [dim]... +{len(defn.servers) - 5} más[/dim]")
            else:
                console.print(f"\n[cyan]upstream_ref:[/cyan] {ref} [red]✗ no encontrado en catálogo[/red]")
                console.print("[yellow]  Ejecuta 'lsxtool servers fix nginx <dominio>' para asociar o corregir[/yellow]")
    except Exception:
        pass

    # Ejecutar todas las reglas
    all_results: List[ValidationResult] = []
    results_by_rule: Dict[str, List[ValidationResult]] = {}
    
    for rule_class in ALL_RULES:
        rule = rule_class()
        rule_results = rule.validate(config)
        all_results.extend(rule_results)
        results_by_rule[rule.name] = rule_results
    
    # Mostrar checklist numerado
    _display_checklist(results_by_rule, console)
    
    # Interacción: seleccionar check para ver detalle
    while True:
        console.print()
        try:
            choice = Prompt.ask(
                "[bold cyan]Selecciona un número para ver detalles (o 'q' para salir)[/bold cyan]",
                default="q"
            )
            
            if choice.lower() == 'q':
                break
            
            check_num = int(choice)
            if 1 <= check_num <= len(ALL_RULES):
                rule_name = list(results_by_rule.keys())[check_num - 1]
                _show_rule_details(rule_name, results_by_rule[rule_name], console)
            else:
                console.print(f"[red]❌ Número inválido. Debe estar entre 1 y {len(ALL_RULES)}[/red]")
        except (ValueError, KeyboardInterrupt):
            break
    
    return True


def _display_checklist(results_by_rule: Dict[str, List[ValidationResult]], console: Console):
    """Muestra checklist numerado de validaciones"""
    table = Table(title="Checklist de Validación", show_header=True, header_style="bold cyan", box=box.SIMPLE)
    table.add_column("#", style="cyan", width=4, justify="right")
    table.add_column("Check", style="cyan", width=20)
    table.add_column("Estado", width=25)
    table.add_column("Mensaje", style="white")
    
    rule_names = list(results_by_rule.keys())
    
    for idx, rule_name in enumerate(rule_names, 1):
        results = results_by_rule[rule_name]
        
        # Determinar estado general y capacidad de fix
        has_errors = any(r.is_error for r in results)
        has_warnings = any(r.is_warning for r in results)
        
        # Obtener capacidad de fix del primer problema (si hay)
        problem_result = next((r for r in results if r.is_error or r.is_warning), None)
        fix_capability = problem_result.fix_capability if problem_result else FixCapability.NONE
        
        if has_errors:
            if fix_capability == FixCapability.AUTO:
                status = "[red]✖ ERROR (AUTO)[/red]"
            elif fix_capability == FixCapability.INTERACTIVE:
                status = "[red]✖ ERROR (requiere confirmación)[/red]"
            else:
                status = "[red]✖ ERROR[/red]"
            message = next((r.message for r in results if r.is_error), "Error")
        elif has_warnings:
            if fix_capability == FixCapability.AUTO:
                status = "[yellow]⚠ WARNING (AUTO)[/yellow]"
            elif fix_capability == FixCapability.INTERACTIVE:
                status = "[yellow]⚠ WARNING (requiere confirmación)[/yellow]"
            else:
                status = "[yellow]⚠ WARNING[/yellow]"
            message = next((r.message for r in results if r.is_warning), "Advertencia")
        else:
            status = "[green]✔ OK[/green]"
            message = next((r.message for r in results if r.severity == Severity.INFO), "OK")
        
        table.add_row(str(idx), rule_name, status, message)
    
    console.print(table)


def _show_rule_details(rule_name: str, results: List[ValidationResult], console: Console):
    """Muestra detalles de una regla específica"""
    console.print()
    
    # Agrupar por severidad
    errors = [r for r in results if r.is_error]
    warnings = [r for r in results if r.is_warning]
    infos = [r for r in results if r.severity == Severity.INFO]
    
    # Determinar color del panel
    if errors:
        border_style = "red"
        title = f"[red]❌ {rule_name} - Errores[/red]"
    elif warnings:
        border_style = "yellow"
        title = f"[yellow]⚠️ {rule_name} - Advertencias[/yellow]"
    else:
        border_style = "green"
        title = f"[green]✅ {rule_name} - OK[/green]"
    
    # Crear tabla de detalles
    details_table = Table(show_header=True, header_style="bold", box=box.SIMPLE)
    details_table.add_column("Severidad", width=12)
    details_table.add_column("Mensaje", style="white")
    details_table.add_column("Detalles", style="dim")
    
    for result in results:
        if result.is_error:
            severity = "[red]ERROR[/red]"
        elif result.is_warning:
            severity = "[yellow]WARNING[/yellow]"
        else:
            severity = "[green]INFO[/green]"
        
        details_table.add_row(
            severity,
            result.message,
            result.details or ""
        )
    
    console.print(Panel(details_table, title=title, border_style=border_style))
    
    # Mostrar capacidad de fix
    auto_fixable = [r for r in results if r.is_auto_fixable]
    interactive_fixable = [r for r in results if r.is_interactive_fixable]
    none_fixable = [r for r in results if r.fix_capability == FixCapability.NONE and (r.is_error or r.is_warning)]
    
    if auto_fixable:
        console.print("\n[green]💡 Algunos problemas pueden corregirse automáticamente[/green]")
    if interactive_fixable:
        console.print("\n[yellow]💡 Algunos problemas requieren confirmación interactiva[/yellow]")
    if none_fixable:
        console.print("\n[dim]ℹ️ Algunos problemas no pueden corregirse automáticamente[/dim]")
        for r in none_fixable:
            if r.fix_description:
                console.print(f"[dim]   • {r.rule_name}: {r.fix_description}[/dim]")
    
    if auto_fixable or interactive_fixable:
        console.print("[dim]   Usa 'lsxtool servers fix nginx <dominio>' para corregirlos[/dim]")
