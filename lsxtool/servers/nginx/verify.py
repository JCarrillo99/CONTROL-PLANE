"""
Sistema de verificación avanzado para Nginx
Valida reglas de negocio, estructura, naming y coherencia semántica
"""

from pathlib import Path
from typing import List, Dict, Tuple
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from .parser import parse_nginx_config, find_nginx_configs
from .rules import ALL_RULES, ValidationResult, Severity


def verify_nginx_configs(base_dir: Path, console: Console) -> Tuple[bool, Dict[str, List[ValidationResult]]]:
    """
    Verifica todos los archivos de configuración Nginx
    
    Args:
        base_dir: Directorio base del proyecto
        console: Console de Rich para output
    
    Returns:
        Tuple (éxito, resultados_por_archivo)
    """
    # Encontrar todos los archivos .conf
    config_files = find_nginx_configs(base_dir)
    
    if not config_files:
        console.print("[yellow]⚠️ No se encontraron archivos de configuración Nginx[/yellow]")
        return True, {}
    
    console.print(f"[dim]Encontrados {len(config_files)} archivo(s) de configuración[/dim]\n")
    
    results_by_file: Dict[str, List[ValidationResult]] = {}
    all_errors = []
    all_warnings = []
    
    # Procesar cada archivo
    for config_file in config_files:
        config = parse_nginx_config(config_file)
        
        if not config:
            console.print(f"[red]❌ Error al parsear: {config_file}[/red]")
            continue
        
        # Ejecutar todas las reglas
        file_results = []
        for rule_class in ALL_RULES:
            rule = rule_class()
            rule_results = rule.validate(config)
            file_results.extend(rule_results)
        
        results_by_file[str(config_file)] = file_results
        
        # Contar errores y warnings
        for result in file_results:
            if result.is_error:
                all_errors.append((config_file, result))
            elif result.is_warning:
                all_warnings.append((config_file, result))
    
    # Mostrar resultados
    _display_results(results_by_file, console)
    
    # Resumen
    total_files = len(results_by_file)
    total_errors = len(all_errors)
    total_warnings = len(all_warnings)
    
    _display_summary(total_files, total_errors, total_warnings, console)
    
    # Retornar éxito (True si no hay errores)
    success = total_errors == 0
    return success, results_by_file


def _display_results(results_by_file: Dict[str, List[ValidationResult]], console: Console):
    """Muestra los resultados de validación por archivo"""
    
    for file_path, results in results_by_file.items():
        # Crear panel para cada archivo
        file_name = Path(file_path).name
        
        # Contar por severidad
        errors = [r for r in results if r.is_error]
        warnings = [r for r in results if r.is_warning]
        infos = [r for r in results if r.severity == Severity.INFO]
        
        # Determinar color del borde según errores
        if errors:
            border_style = "red"
            status_icon = "❌"
        elif warnings:
            border_style = "yellow"
            status_icon = "⚠️"
        else:
            border_style = "green"
            status_icon = "✅"
        
        # Crear tabla de resultados
        table = Table(show_header=True, header_style="bold", box=box.SIMPLE)
        table.add_column("Check", style="cyan", width=20)
        table.add_column("Estado", width=10)
        table.add_column("Mensaje", style="white", width=50)
        
        for result in results:
            if result.is_error:
                status = "[red]✖ ERROR[/red]"
                message = result.message
            elif result.is_warning:
                status = "[yellow]⚠ WARNING[/yellow]"
                message = result.message
            else:
                status = "[green]✔ OK[/green]"
                message = result.message
            
            table.add_row(result.rule_name, status, message)
        
        # Panel con resumen
        summary = f"{status_icon} {file_name}\n"
        summary += f"[dim]Errores: {len(errors)} | Warnings: {len(warnings)} | OK: {len(infos)}[/dim]"
        
        console.print(Panel(table, title=summary, border_style=border_style))
        console.print()  # Espacio entre archivos


def _display_summary(total_files: int, total_errors: int, total_warnings: int, console: Console):
    """Muestra el resumen final"""
    
    # Determinar color según errores
    if total_errors > 0:
        border_style = "red"
        status_icon = "❌"
        status_text = "[red]FALLÓ[/red]"
    elif total_warnings > 0:
        border_style = "yellow"
        status_icon = "⚠️"
        status_text = "[yellow]CON ADVERTENCIAS[/yellow]"
    else:
        border_style = "green"
        status_icon = "✅"
        status_text = "[green]ÉXITO[/green]"
    
    summary_table = Table(show_header=False, box=None)
    summary_table.add_column("Métrica", style="cyan", width=20)
    summary_table.add_column("Valor", style="white")
    
    summary_table.add_row("Total de archivos", str(total_files))
    summary_table.add_row("Errores", f"[red]{total_errors}[/red]")
    summary_table.add_row("Warnings", f"[yellow]{total_warnings}[/yellow]")
    summary_table.add_row("Estado", status_text)
    
    console.print(Panel(
        summary_table,
        title=f"{status_icon} Resumen de Verificación",
        border_style=border_style
    ))
    
    if total_errors > 0:
        console.print("\n[red]❌ Se encontraron errores. Corrige los problemas antes de recargar Nginx.[/red]")
    elif total_warnings > 0:
        console.print("\n[yellow]⚠️ Se encontraron advertencias. Revisa los problemas antes de recargar Nginx.[/yellow]")
    else:
        console.print("\n[green]✅ Todas las validaciones pasaron correctamente.[/green]")
