"""
Corrección guiada de problemas en configuración Nginx
Solo habilitado si hay WARNINGS o ERRORS
Crea backups y muestra diffs antes de aplicar
"""

import re
import difflib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Set
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich import box

from .parser import parse_nginx_config, find_nginx_configs
from .rules import ALL_RULES, ValidationResult, Severity, FixCapability


def fix_nginx_domain(domain: str, base_dir: Path, console: Console) -> bool:
    """
    Corrige problemas en la configuración de un dominio
    
    Args:
        domain: Dominio a corregir
        base_dir: Directorio base del proyecto
        console: Console de Rich para output
    
    Returns:
        True si se encontró y procesó el dominio, False si no
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
        return False
    
    # Parsear configuración
    config = parse_nginx_config(config_file)
    if not config:
        console.print(f"[red]❌ Error al parsear: {config_file}[/red]")
        return False
    
    console.print(Panel.fit(
        f"[bold cyan]Corrección de Configuración Nginx[/bold cyan]\n"
        f"[dim]Dominio:[/dim] {domain}\n"
        f"[dim]Archivo:[/dim] {config_file.name}",
        border_style="cyan"
    ))

    # Si el dominio usa upstream_ref, no modificar bloques upstream; ofrecer asociar/corregir ref
    domain_uses_upstream_ref = False
    upstream_ref_invalid = False
    try:
        from ..declarative.loader import DeclarativeLoader
        from ..declarative.upstream_loader import UpstreamCatalogLoader
        loader = DeclarativeLoader(base_dir, console)
        loader.load_all()
        domain_config = loader.get_domain(domain)
        if domain_config and getattr(domain_config.server_web, "upstream_ref", None):
            domain_uses_upstream_ref = True
            ref = domain_config.server_web.upstream_ref
            catalog = UpstreamCatalogLoader(base_dir, console)
            if not catalog.exists(ref):
                upstream_ref_invalid = True
                console.print(f"\n[red]❌ Referencia inválida: upstream_ref '{ref}' no existe en catálogo[/red]")
                console.print("[dim]Opciones: lsxtool servers upstream list | Editar .lsxtool/domains/<dominio>.yaml[/dim]")
    except Exception:
        pass

    # Ejecutar todas las reglas y obtener solo problemas
    all_results: List[ValidationResult] = []
    results_by_rule: Dict[str, List[ValidationResult]] = {}

    # No modificar upstream cuando el dominio usa upstream_ref (catálogo)
    skip_upstream_rules = ("Upstream", "Puertos") if domain_uses_upstream_ref else ()

    for rule_class in ALL_RULES:
        rule = rule_class()
        rule_results = rule.validate(config)
        # Solo incluir errores y warnings; excluir reglas de upstream si usa catálogo
        problems = [r for r in rule_results if r.is_error or r.is_warning]
        if rule.name in skip_upstream_rules:
            if problems:
                console.print(f"[dim]  (Se omite fix '{rule.name}' porque el dominio usa upstream_ref)[/dim]")
            continue
        if problems:
            all_results.extend(problems)
            results_by_rule[rule.name] = problems
    
    # Verificar si hay problemas
    if not all_results:
        console.print("\n[green]✅ No se encontraron problemas que corregir[/green]")
        console.print("[dim]La configuración está correcta[/dim]")
        return True
    
    # Clasificar problemas por capacidad de fix
    auto_results = {}
    interactive_results = {}
    none_results = {}
    
    for rule_name, results in results_by_rule.items():
        auto_problems = [r for r in results if r.is_auto_fixable]
        interactive_problems = [r for r in results if r.is_interactive_fixable]
        none_problems = [r for r in results if r.fix_capability == FixCapability.NONE]
        
        if auto_problems:
            auto_results[rule_name] = auto_problems
        if interactive_problems:
            interactive_results[rule_name] = interactive_problems
        if none_problems:
            none_results[rule_name] = none_problems
    
    # Mostrar todos los problemas con su capacidad de fix
    _display_all_problems(auto_results, interactive_results, none_results, console)
    
    # Si no hay problemas corregibles, salir
    if not auto_results and not interactive_results:
        console.print("\n[yellow]⚠️ No hay problemas que puedan corregirse automáticamente[/yellow]")
        console.print("[dim]Corrige los problemas manualmente[/dim]")
        return True
    
    # Combinar auto e interactive para selección
    fixable_results = {**auto_results, **interactive_results}
    
    # Crear lista ordenada: primero AUTO, luego INTERACTIVE
    all_fixable = list(auto_results.keys()) + list(interactive_results.keys())
    
    # Seleccionar checks a corregir
    selected_rules = _select_checks_to_fix(all_fixable, console)
    
    if not selected_rules:
        console.print("\n[yellow]Operación cancelada[/yellow]")
        return True
    
    # Aplicar fixes (maneja AUTO e INTERACTIVE automáticamente)
    return _apply_fixes(config, config_file, selected_rules, fixable_results, auto_results, interactive_results, console)


def _display_all_problems(
    auto_results: Dict[str, List[ValidationResult]],
    interactive_results: Dict[str, List[ValidationResult]],
    none_results: Dict[str, List[ValidationResult]],
    console: Console
):
    """Muestra todos los problemas clasificados por capacidad de fix"""
    
    # Tabla de problemas corregibles
    if auto_results or interactive_results:
        table = Table(title="Problemas Detectados", show_header=True, header_style="bold cyan", box=box.SIMPLE)
        table.add_column("#", style="cyan", width=4, justify="right")
        table.add_column("Check", style="cyan", width=20)
        table.add_column("Tipo", width=20)
        table.add_column("Problema", style="white")
        table.add_column("Corrección", style="dim")
        
        rule_counter = 1
        
        # Primero AUTO (más prioritarios)
        for rule_name, results in auto_results.items():
            problem = results[0].message
            # Obtener descripción de fix (priorizar fix_description, luego fix_action.description)
            fix_desc = results[0].fix_description
            if not fix_desc and results[0].fix_action:
                fix_desc = results[0].fix_action.description
            if not fix_desc:
                fix_desc = "Corrección automática"
            table.add_row(str(rule_counter), rule_name, "[green]✔ AUTO[/green]", problem, fix_desc)
            rule_counter += 1
        
        # Luego INTERACTIVE
        for rule_name, results in interactive_results.items():
            problem = results[0].message
            fix_desc = results[0].fix_description or "Requiere confirmación"
            table.add_row(str(rule_counter), rule_name, "[yellow]⚠ INTERACTIVE[/yellow]", problem, fix_desc)
            rule_counter += 1
        
        console.print(table)
        
        # Mostrar problemas no corregibles (informativo)
        if none_results:
            console.print("\n[bold]Problemas informativos (no corregibles automáticamente):[/bold]")
            for rule_name, results in none_results.items():
                problem = results[0].message
                reason = results[0].fix_description or "Requiere acción manual"
                console.print(f"  [dim]• {rule_name}:[/dim] {problem}")
                console.print(f"    [dim]  Razón: {reason}[/dim]")
        
        max_num = rule_counter - 1
        if max_num > 0:
            console.print(f"\n[dim]Selecciona números para corregir (1-{max_num}) o 'all' para corregir todos los corregibles[/dim]")
    else:
        # Solo problemas no corregibles
        console.print("\n[bold]Problemas detectados (no corregibles automáticamente):[/bold]")
        for rule_name, results in none_results.items():
            problem = results[0].message
            reason = results[0].fix_description or "Requiere acción manual"
            console.print(f"  [yellow]• {rule_name}:[/yellow] {problem}")
            console.print(f"    [dim]Razón: {reason}[/dim]")


def _select_checks_to_fix(rule_names: List[str], console: Console) -> Set[str]:
    """Permite al usuario seleccionar checks a corregir"""
    console.print()
    choice = Prompt.ask(
        "[bold cyan]Selecciona checks a corregir (números separados por coma o 'all')[/bold cyan]",
        default=""
    )
    
    if not choice:
        return set()
    
    if choice.lower() == "all":
        return set(rule_names)
    
    selected = set()
    try:
        for num_str in choice.split(","):
            num = int(num_str.strip())
            if 1 <= num <= len(rule_names):
                selected.add(rule_names[num - 1])
            else:
                console.print(f"[red]❌ Número inválido: {num}. Debe estar entre 1 y {len(rule_names)}[/red]")
    except ValueError:
        console.print("[red]❌ Entrada inválida. Usa números separados por coma o 'all'[/red]")
        return set()
    
    return selected


def _apply_fixes(
    config, 
    config_file: Path, 
    selected_rules: Set[str],
    fixable_results: Dict[str, List[ValidationResult]],
    auto_results: Dict[str, List[ValidationResult]],
    interactive_results: Dict[str, List[ValidationResult]],
    console: Console
) -> bool:
    """Aplica los fixes seleccionados con backup y confirmación"""
    
    # Separar AUTO e INTERACTIVE de los seleccionados
    auto_selected = [r for r in selected_rules if r in auto_results]
    interactive_selected = [r for r in selected_rules if r in interactive_results]
    
    # Si solo hay INTERACTIVE, manejar de forma especial
    if not auto_selected and interactive_selected:
        console.print("\n[yellow]⚠️ Los checks seleccionados requieren confirmación interactiva[/yellow]")
        for rule_name in interactive_selected:
            results = fixable_results[rule_name]
            fix_desc = results[0].fix_description or "Requiere configuración interactiva"
            console.print(f"  [yellow]•[/yellow] {rule_name}: {fix_desc}")
            
            # META se maneja con bootstrap
            if rule_name == "META":
                domain_from_file = config.file_path.stem
                console.print(f"\n[cyan]💡 Para corregir META, ejecuta:[/cyan]")
                console.print(f"[cyan]   lsxtool servers bootstrap nginx {domain_from_file}[/cyan]")
            
            # Tech Metadata se maneja con bootstrap (requiere wizard interactivo)
            if rule_name == "Tech Metadata":
                domain_from_file = config.file_path.stem
                console.print(f"\n[cyan]💡 Para corregir Tech Metadata (tech_provider/tech_manager), ejecuta:[/cyan]")
                console.print(f"[cyan]   lsxtool servers bootstrap nginx {domain_from_file}[/cyan]")
                console.print("[dim]   Nota: bootstrap actualizará solo los campos faltantes si META ya existe[/dim]")
            
            # Upstream se puede manejar con wizard (por ahora solo informamos)
            if rule_name == "Upstream":
                console.print(f"\n[yellow]⚠️ La corrección de Upstream requiere confirmación[/yellow]")
                console.print("[dim]Esta funcionalidad se implementará próximamente[/dim]")
        
        return True
    
    # Si hay AUTO, aplicar con backup
    if not auto_selected:
        console.print("\n[dim]No hay cambios automáticos para aplicar[/dim]")
        return True
    
    # Crear backup
    backup_path = _create_backup(config_file, console)
    if not backup_path:
        console.print("[red]❌ Error al crear backup. Abortando.[/red]")
        return False
    
    # Aplicar fixes AUTO en orden
    new_content = config.content
    original_content = config.content
    
    console.print("\n[bold]Aplicando correcciones automáticas:[/bold]")
    
    for rule_name in auto_selected:
        results = fixable_results[rule_name]
        for result in results:
            if result.fix_action:
                fix_desc = result.fix_description or (result.fix_action.description if result.fix_action else "Corrección automática")
                console.print(f"  [green]✔[/green] {rule_name}: {fix_desc}")
                try:
                    # Aplicar fix al contenido actual
                    new_content = result.fix_action(config)
                    # Actualizar config.content para que los siguientes fixes trabajen con el contenido actualizado
                    config.content = new_content
                except Exception as e:
                    console.print(f"  [red]❌ Error al aplicar fix: {e}[/red]")
                    import traceback
                    console.print(f"[dim]{traceback.format_exc()}[/dim]")
                    return False
    
    # Mostrar diff solo si hay cambios
    if new_content != original_content:
        _show_diff(original_content, new_content, console)
        
        # Mostrar archivos afectados
        console.print(f"\n[bold]Archivos afectados:[/bold]")
        console.print(f"  [cyan]•[/cyan] {config_file}")
        console.print(f"  [cyan]•[/cyan] Backup: {backup_path.name}")
        
        # Confirmación final
        console.print()
        if not Confirm.ask("[bold yellow]¿Aplicar estos cambios?[/bold yellow]", default=False):
            console.print("[yellow]Operación cancelada[/yellow]")
            return True
        
        # Aplicar cambios
        try:
            config_file.write_text(new_content)
            console.print(f"\n[green]✅ Cambios aplicados correctamente[/green]")
            console.print(f"[dim]Backup guardado en: {backup_path}[/dim]")
            return True
        except Exception as e:
            console.print(f"\n[red]❌ Error al escribir archivo: {e}[/red]")
            return False
    else:
        console.print("\n[dim]No hay cambios para aplicar[/dim]")
        return True


def _create_backup(config_file: Path, console: Console) -> Optional[Path]:
    """Crea un backup del archivo con timestamp"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = config_file.parent / f"{config_file.name}.bak-{timestamp}"
        backup_path.write_text(config_file.read_text())
        return backup_path
    except Exception as e:
        console.print(f"[red]❌ Error al crear backup: {e}[/red]")
        return None


def _show_diff(old_content: str, new_content: str, console: Console):
    """Muestra diff entre contenido antiguo y nuevo"""
    console.print("\n[bold]Cambios propuestos:[/bold]")
    
    # Mostrar diff simple línea por línea
    old_lines = old_content.split('\n')
    new_lines = new_content.split('\n')
    
    # Usar difflib para generar diff unificado
    diff_lines = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile='original',
        tofile='modificado',
        lineterm='',
        n=3
    )
    
    diff_text = '\n'.join(diff_lines)
    if diff_text:
        # Colorear diff manualmente
        colored_diff = []
        for line in diff_text.split('\n'):
            if line.startswith('+') and not line.startswith('+++'):
                colored_diff.append(f"[green]{line}[/green]")
            elif line.startswith('-') and not line.startswith('---'):
                colored_diff.append(f"[red]{line}[/red]")
            elif line.startswith('@'):
                colored_diff.append(f"[cyan]{line}[/cyan]")
            else:
                colored_diff.append(line)
        
        console.print(Panel('\n'.join(colored_diff), title="Diff", border_style="cyan"))
    else:
        console.print("[dim]No hay cambios[/dim]")
