"""
CLI del catálogo de upstreams: list, create, validate, canary promote/rollback.
"""

import typer
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm, IntPrompt

from .upstream_loader import UpstreamCatalogLoader
from .upstream_catalog import (
    CanaryConfig,
    UpstreamCatalogDef,
    UpstreamServerEntry,
    UpstreamHealthcheck,
)

app = typer.Typer(
    name="upstream",
    help="Catálogo de upstreams declarativos (.lsxtool/upstreams/)",
    add_completion=False,
)
console = Console()

# Base dir: proyecto servers-install-v2
BASE_DIR = Path(__file__).parent.parent.parent.parent.resolve()

# Subgrupo canary
canary_app = typer.Typer(name="canary", help="Canary progresivo: promote / rollback")
app.add_typer(canary_app, name="canary")


def _loader() -> UpstreamCatalogLoader:
    return UpstreamCatalogLoader(BASE_DIR, console)


@app.command("list")
def list_upstreams():
    """Lista los upstreams del catálogo."""
    loader = _loader()
    names = loader.list_names()
    if not names:
        console.print("[yellow]No hay upstreams en .lsxtool/upstreams/[/yellow]")
        console.print("[dim]Crea uno: lsxtool servers upstream create[/dim]")
        return
    table = Table(title="Upstreams en catálogo", show_header=True, header_style="bold cyan")
    table.add_column("Nombre lógico", style="cyan")
    table.add_column("Tipo", style="green")
    table.add_column("Servers", style="yellow")
    for name in names:
        defn = loader.load(name)
        if defn:
            typ = defn.type or "single"
            servers_info = ", ".join(f"{s.host}:{s.port}" for s in defn.servers[:3])
            if len(defn.servers) > 3:
                servers_info += f" (+{len(defn.servers) - 3})"
            table.add_row(name, typ, servers_info)
        else:
            table.add_row(name, "—", "(error al cargar)")
    console.print(table)


@app.command("create")
def create_upstream(
    name: str = typer.Argument(None, help="Nombre lógico (ej: api_identity_dev). Si no se pasa, se pregunta.")
):
    """Crea un upstream en el catálogo (wizard interactivo)."""
    loader = _loader()
    console.print(Panel.fit("[bold cyan]Crear upstream en catálogo[/bold cyan]", border_style="cyan"))

    if not name:
        name = Prompt.ask(
            "[bold]Nombre lógico del upstream[/bold] (ej: api_identity_dev)",
            default="api_identity_dev"
        ).strip().replace("-", "_").replace(" ", "_")
    if loader.exists(name):
        console.print(f"[red]❌ Ya existe un upstream con ese nombre: {name}[/red]")
        raise typer.Exit(1)

    typ = Prompt.ask(
        "[bold]Tipo[/bold] (single | weighted)",
        choices=["single", "weighted"],
        default="single"
    )

    servers = []
    while True:
        console.print(f"\n[cyan]Server #{len(servers) + 1}[/cyan]")
        host = Prompt.ask("  Host (IP o hostname)", default="127.0.0.1")
        port = IntPrompt.ask("  Puerto", default=3001)
        weight = None
        role = None
        if typ == "weighted":
            weight = IntPrompt.ask("  Peso (1-100)", default=100 if len(servers) == 0 else 0)
            role_choice = Prompt.ask(
                "  Rol (stable | canary | primary | backup)",
                choices=["stable", "canary", "primary", "backup", ""],
                default="stable" if len(servers) == 0 else "backup"
            )
            role = role_choice or None
        servers.append(UpstreamServerEntry(host=host.strip(), port=port, weight=weight, role=role))
        if not Confirm.ask("  ¿Añadir otro server?", default=False):
            break

    canary = None
    if typ == "weighted" and len(servers) >= 2 and Confirm.ask("\n¿Habilitar canary progresivo?", default=False):
        current = IntPrompt.ask("  Peso inicial canary (%)", default=10)
        step = IntPrompt.ask("  Paso por promote (%)", default=10)
        max_w = IntPrompt.ask("  Peso máximo canary (%)", default=50)
        canary = CanaryConfig(enabled=True, current_weight=current, step=step, max=max_w)

    defn = UpstreamCatalogDef(
        name=name,
        type=typ,
        protocol="http",
        strategy="canary" if canary else None,
        servers=servers,
        canary=canary,
    )
    if loader.save(defn):
        console.print(f"\n[green]✅ Upstream creado: {name}[/green]")
        console.print(f"[dim]Archivo: .lsxtool/upstreams/{name.replace('_', '-')}.yaml[/dim]")
    else:
        console.print("[red]❌ Error al guardar[/red]")
        raise typer.Exit(1)


@app.command("validate")
def validate_upstreams(
    name: str = typer.Argument(None, help="Nombre del upstream (opcional; si no, valida todos)")
):
    """Valida uno o todos los upstreams del catálogo."""
    loader = _loader()
    if name:
        names = [name] if loader.load(name) else []
        if not names:
            console.print(f"[red]❌ Upstream no encontrado: {name}[/red]")
            raise typer.Exit(1)
    else:
        names = loader.list_names()
    errors = []
    for n in names:
        defn = loader.load(n)
        if not defn:
            errors.append((n, "No se pudo cargar"))
            continue
        if not defn.servers:
            errors.append((n, "Sin servidores"))
        if defn.type == "weighted" and any(s.weight is None for s in defn.servers):
            errors.append((n, "Tipo weighted requiere weight en todos los servers"))
    if errors:
        for n, msg in errors:
            console.print(f"[red]❌ {n}: {msg}[/red]")
        raise typer.Exit(1)
    console.print("[green]✅ Validación correcta[/green]")


def _promote_or_rollback(upstream_name: str, promote: bool) -> bool:
    loader = _loader()
    defn = loader.load(upstream_name)
    if not defn:
        console.print(f"[red]❌ Upstream no encontrado: {upstream_name}[/red]")
        return False
    canary = defn.canary
    if not canary or not canary.enabled:
        console.print("[yellow]⚠️ Canary no está habilitado en este upstream[/yellow]")
        return False
    step = canary.step or 10
    max_w = canary.max or 50
    current = canary.current_weight or 0
    if promote:
        new_weight = min(current + step, max_w)
        if new_weight == current:
            console.print(f"[dim]Canary ya está al máximo ({max_w}%)[/dim]")
            return True
    else:
        new_weight = max(current - step, 0)
        if new_weight == current:
            console.print("[dim]Canary ya está al mínimo (0%)[/dim]")
            return True
    # Actualizar pesos en servers (stable vs canary)
    stable_weight = 100 - new_weight
    canary_weight = new_weight
    new_servers = []
    for s in defn.servers:
        role = (s.role or "").lower()
        if role == "canary":
            new_servers.append(s.model_copy(update={"weight": canary_weight}))
        else:
            new_servers.append(s.model_copy(update={"weight": stable_weight}))
    defn = defn.model_copy(
        update={
            "servers": new_servers,
            "canary": canary.model_copy(update={"current_weight": new_weight}),
        }
    )
    if not loader.save(defn):
        return False
    action = "promote" if promote else "rollback"
    console.print(f"[green]✅ Canary {action}: peso canary = {new_weight}%[/green]")
    # Regenerar .conf de dominios que usan este upstream
    try:
        from .loader import DeclarativeLoader
        from .generator import ConfigGenerator
        base = Path(__file__).parent.parent.parent.parent.resolve()
        decl = DeclarativeLoader(base, console)
        decl.load_all()
        gen = ConfigGenerator(base, console)
        for dname, dconfig in decl._domains.items():
            ref = getattr(dconfig.server_web, "upstream_ref", None)
            if ref == upstream_name:
                if gen.write_config(dconfig):
                    console.print(f"[dim]  Regenerado: {dname}.conf[/dim]")
    except Exception:
        pass
    return True


@canary_app.command("promote")
def canary_promote(
    upstream_name: str = typer.Argument(..., help="Nombre lógico del upstream (ej: api_identity_dev)")
):
    """Aumenta el peso del canary (current_weight += step), guarda estado en YAML."""
    _promote_or_rollback(upstream_name, promote=True)


@canary_app.command("rollback")
def canary_rollback(
    upstream_name: str = typer.Argument(..., help="Nombre lógico del upstream")
):
    """Reduce el peso del canary (current_weight -= step), guarda estado en YAML."""
    _promote_or_rollback(upstream_name, promote=False)
