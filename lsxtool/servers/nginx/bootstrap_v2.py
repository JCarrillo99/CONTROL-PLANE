"""
Bootstrap v2: frontends, routes, upstreams automáticos.
Detecta frontend vs API, solicita solo datos faltantes, crea upstreams en catálogo.
"""

from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from .parser import parse_nginx_config, find_nginx_configs, extract_location_routes
from ..declarative.loader_v2 import (
    load_domain,
    save_domain,
    load_upstream_v2,
    save_upstream_v2,
    list_upstream_refs,
)
from ..declarative.convention_v2 import (
    upstream_path_v2,
    upstreams_dir_v2,
    expected_upstream_ref_v2,
)
from ..declarative.models_v2 import (
    FrontendDomainConfig,
    ServerWebConfigV2,
    RootConfig,
    RouteConfig,
    UriTransformConfig,
    UpstreamDefConfig,
    UpstreamTechConfig,
    UpstreamRuntimeConfig,
    UpstreamExposureConfig,
    UpstreamNodeConfig,
    UpstreamRoutingConfig,
    UpstreamCanaryConfig,
    UpstreamIdentityConfig,
)
from ..declarative.generator_v2 import generate_nginx_config_v2, write_config_v2
from ..declarative.tech_capabilities import (
    get_capabilities,
    is_manager,
    resolve_provider_input,
    resolve_manager_input,
)
from .prompts import (
    prompt_routing_strategy,
    prompt_routing_algorithm,
    prompt_stickiness,
    prompt_sticky_key,
    prompt_route_type,
    prompt_uri_strategy,
    prompt_upstream_source,
    prompt_tech_language,
    needs_algorithm,
)
from ..declarative.routing_domain import get_default_algorithm_for_strategy, STICKINESS_NEEDS_KEY


def _slug(domain: str) -> str:
    d = domain.replace("dev-", "").replace("qa-", "").replace("prod-", "")
    return d.split(".")[0]


def _detect_role_from_conf(content: str) -> str:
    """
    Si location / → proxy y existen múltiples location /api/... → proxy → frontend compuesto.
    Si no, asumir API (un solo upstream).
    """
    routes = extract_location_routes(content)
    root_proxy = routes.get("/")
    api_like = [p for p in routes if p.startswith("/api") and routes.get(p)]
    if root_proxy and len(api_like) >= 1:
        return "frontend"
    return "api"


def _resolve_config_file(base_dir: Path, domain: str) -> Optional[Path]:
    """Resuelve .conf para el dominio."""
    configs = find_nginx_configs(base_dir)
    for p in configs:
        if p.stem == domain:
            return p
    return None


def bootstrap_nginx_v2(
    domain: str,
    base_dir: Path,
    console: Console,
    full_reconfigure: bool = False,
    non_interactive: bool = False,
) -> bool:
    """
    Bootstrap v2: frontends + upstreams.
    Detecta rol, pide solo lo faltante, crea upstreams automáticamente.
    full_reconfigure=True → lsxtool servers reconfigure nginx <domain>.
    non_interactive=True → error si faltan datos; upstreams deben existir previamente.
    """
    config_file = _resolve_config_file(base_dir, domain)
    existing = load_domain(base_dir, domain, console=console)

    # Detectar rol desde .conf si existe y no hay YAML v2
    role = "frontend"
    routes: List[RouteConfig] = []
    if config_file and config_file.exists() and not existing:
        cfg = parse_nginx_config(config_file)
        if cfg and cfg.content:
            role = _detect_role_from_conf(cfg.content)
            locs = extract_location_routes(cfg.content)
            for path, up in locs.items():
                name = _generate_route_name(path)
                strategy = "passthrough" if path == "/" else "strip"
                uri = UriTransformConfig(public=path, upstream="/", strategy=strategy)
                routes.append(RouteConfig(name=name, type="proxy", upstream_ref=up, uri=uri))

    # Modo no interactivo: requiere existing o datos suficientes
    if non_interactive and not existing and not routes:
        console.print(
            "[red]❌ Modo no interactivo requiere YAML del dominio existente o .conf para inferir. "
            "Ejecute primero en modo interactivo: lsxtool servers bootstrap nginx <domain> --v2[/red]"
        )
        return False

    # Construir o completar FrontendDomainConfig (solo preguntando lo faltante)
    provider_id = _ask_provider(base_dir, console, existing, full_reconfigure, non_interactive)
    env = _ask_env(console, existing, full_reconfigure, non_interactive)
    sw_version = _ask_server_web_version(console, existing, full_reconfigure, non_interactive)
    root_cfg = _ask_root(console, domain, existing, full_reconfigure, non_interactive)
    if not existing or full_reconfigure:
        if not routes:
            if non_interactive:
                console.print("[red]❌ Modo no interactivo: faltan routes. Ejecute sin --non-interactive para definirlas.[/red]")
                return False
            # _ask_routes ya crea y guarda upstreams al definir cada ruta
            routes = _ask_routes(console, domain, provider_id, env, base_dir)
        # Si reconfigure y teníamos uno solo "/" -> API, permitir seguir así o agregar rutas
    elif not routes and existing and existing.routes:
        routes = existing.routes

    if not provider_id or not env:
        console.print("[red]❌ provider y environment son obligatorios.[/red]")
        return False

    domain_cfg = FrontendDomainConfig(
        domain=domain,
        role="frontend",
        environment=env,
        provider=provider_id,
        server_web=ServerWebConfigV2(type="nginx", version=sw_version or "1.26.3"),
        root=root_cfg,
        routes=routes,
    )

    # Asegurar upstreams faltantes (ej. YAML editado manualmente con ref nuevo)
    for route in (domain_cfg.routes or []):
        ref = getattr(route, "upstream_ref", None) or (route if isinstance(route, dict) else {}).get("upstream_ref")
        if not ref:
            continue
        up = load_upstream_v2(base_dir, ref, provider_id, env, console)
        if not up:
            if non_interactive:
                console.print(
                    f"[red]❌ Upstream [bold]{ref}[/bold] no existe. "
                    "En modo no interactivo los upstreams deben existir previamente. "
                    "Ejecute sin --non-interactive para crearlos interactivamente.[/red]"
                )
                return False
            console.print()
            console.print(Panel.fit(f"[bold]Upstream [cyan]{ref}[/cyan] no encontrado — Crear[/bold]", border_style="yellow"))
            up = _create_upstream_interactive(base_dir, console, ref, provider_id, env, non_interactive=False)
            if up:
                save_upstream_v2(base_dir, provider_id, env, up, console)

    # Guardar domain
    if not save_domain(base_dir, domain_cfg, provider_id, env, console):
        return False
    console.print("[green]✅ Estado declarativo guardado (domains + upstreams)[/green]")

    # Orquestación (root, owner, technical_user)
    if domain_cfg.root:
        _run_orchestration(base_dir, console, domain_cfg)

    # Generar .conf y escribir
    ng = generate_nginx_config_v2(base_dir, domain_cfg, provider_id, env, console)
    if not ng:
        console.print("[yellow]⚠ No se pudo generar .conf[/yellow]")
        return True

    out_dir = base_dir / "lsxtool" / "servers" / "nginx" / "configuration" / "etc" / "nginx" / "conf.d" / provider_id.lower() / env
    out_dir.mkdir(parents=True, exist_ok=True)
    target = config_file if (config_file and config_file.exists()) else (out_dir / f"{domain}.conf")
    if config_file and config_file.exists():
        import difflib
        old = config_file.read_text().splitlines()
        new = ng.splitlines()
        diff = list(difflib.unified_diff(old, new, fromfile="actual", tofile="regenerado", lineterm="", n=2))
        if diff:
            console.print("\n[bold]Diff (actual → regenerado):[/bold]")
            for line in diff[:80]:
                if line.startswith("+"):
                    console.print(f"[green]{line}[/green]")
                elif line.startswith("-"):
                    console.print(f"[red]{line}[/red]")
                else:
                    console.print(f"[dim]{line}[/dim]")
            if len(diff) > 80:
                console.print("[dim]... (más líneas)[/dim]")
            if non_interactive or Confirm.ask("\n[bold yellow]¿Aplicar configuración regenerada?[/bold yellow]", default=True):
                target.write_text(ng)
                console.print("[green]✅ Configuración Nginx aplicada.[/green]")
        else:
            console.print("[dim]Sin cambios en .conf[/dim]")
    else:
        target.write_text(ng)
        console.print(f"[green]✅ Configuración Nginx generada: {target}[/green]")

    return True


def _ask_provider(base_dir: Path, console: Console, existing: Optional[FrontendDomainConfig], force: bool, non_interactive: bool = False) -> Optional[str]:
    providers = ["lunarsystemx", "STIC", "EXTERNAL"]
    default = (existing.provider if existing else None) or "lunarsystemx"
    if default and default not in providers:
        providers = [default] + [p for p in providers if p != default]
    if not force and default and default in providers:
        console.print(f"[green]✓[/green] provider: [cyan]{default}[/cyan]")
        return default
    if non_interactive:
        console.print(f"[dim]provider (non-interactive): {default}[/dim]")
        return default
    console.print("[bold cyan]Provider:[/bold cyan]")
    for i, p in enumerate(providers, 1):
        console.print(f"  [cyan]{i}.[/cyan] {p}")
    choices = [str(i) for i in range(1, len(providers) + 1)]
    def_idx = str(providers.index(default) + 1) if default in providers else "1"
    idx = Prompt.ask("  Selecciona", choices=choices, default=def_idx)
    return providers[int(idx) - 1]


def _ask_env(console: Console, existing: Optional[FrontendDomainConfig], force: bool, non_interactive: bool = False) -> str:
    envs = ["dev", "qa", "prod"]
    default = (existing.environment if existing else None) or "dev"
    if not force and default in envs:
        console.print(f"[green]✓[/green] environment: [cyan]{default}[/cyan]")
        return default
    if non_interactive:
        console.print(f"[dim]environment (non-interactive): {default}[/dim]")
        return default
    console.print("[bold cyan]Environment:[/bold cyan]")
    for i, e in enumerate(envs, 1):
        console.print(f"  [cyan]{i}.[/cyan] {e}")
    idx = Prompt.ask("  Selecciona", choices=["1", "2", "3"], default=str(envs.index(default) + 1))
    return envs[int(idx) - 1]


def _ask_server_web_version(console: Console, existing: Optional[FrontendDomainConfig], force: bool, non_interactive: bool = False) -> Optional[str]:
    try:
        from ..sites.server_version import get_nginx_version
        v = get_nginx_version()
    except Exception:
        v = None
    cur = None
    if existing and existing.server_web:
        cur = getattr(existing.server_web, "version", None)
    default = cur or v or "1.26.3"
    if not force and default:
        console.print(f"[green]✓[/green] server_web.version: [cyan]{default}[/cyan]")
        return default
    if non_interactive:
        return default
    return default


def _ask_root(console: Console, domain: str, existing: Optional[FrontendDomainConfig], force: bool, non_interactive: bool = False) -> Optional[RootConfig]:
    slug = _slug(domain)
    path_default = f"/var/www/{slug}"
    owner_default = f"equipo-{slug}"
    user_default = ""
    if existing and existing.root:
        path_default = existing.root.path
        owner_default = existing.root.owner
        user_default = existing.root.technical_user or ""

    if not force and existing and existing.root:
        console.print(f"[green]✓[/green] root.path: [cyan]{existing.root.path}[/cyan]")
        console.print(f"[green]✓[/green] owner: [cyan]{existing.root.owner}[/cyan]")
        console.print(f"[green]✓[/green] technical_user: [cyan]{existing.root.technical_user}[/cyan]")
        return existing.root

    if non_interactive:
        return RootConfig(path=path_default, owner=owner_default, technical_user=user_default or owner_default or "michael.carrillo")

    console.print("[bold cyan]Root (ownership):[/bold cyan]")
    path = Prompt.ask("  path", default=path_default)
    owner = Prompt.ask("  owner", default=owner_default)
    technical_user = Prompt.ask("  technical_user", default=user_default)
    return RootConfig(path=path, owner=owner, technical_user=technical_user or owner)


def _generate_route_name(public_path: str) -> str:
    """Genera name desde public path: /api/identity/ → api_identity"""
    name = public_path.strip("/").replace("/", "_").replace("-", "_")
    return name if name else "root"


def _ask_num_routes(console: Console) -> int:
    """Pregunta cuántas rutas/proxys tendrá el dominio."""
    console.print()
    console.print("[bold cyan]¿Cuántas rutas / proxys tendrá este dominio?[/bold cyan]")
    console.print("  (Ejemplos: /, /api/, /api/identity/, /admin, etc.)")
    while True:
        raw = Prompt.ask("  Número de rutas", default="1")
        try:
            n = int(raw)
            if n >= 1 and n <= 50:
                return n
        except ValueError:
            pass
        console.print("[red]Introduce un número entre 1 y 50.[/red]")


def _ask_single_route(
    console: Console,
    route_num: int,
    total_routes: int,
    domain: str,
    provider_id: str,
    env: str,
    base_dir: Path,
) -> Tuple[RouteConfig, Optional[UpstreamDefConfig]]:
    """
    Configura UNA ruta. Retorna (RouteConfig, UpstreamDefConfig o None si usó existente).
    """
    console.print()
    console.print(Panel.fit(f"[bold]Configurando ruta {route_num} de {total_routes}[/bold]", border_style="cyan"))
    console.print()

    # 1. Ruta pública
    path_default = "/" if route_num == 1 and total_routes == 1 else ("/api/identity/" if route_num == 1 else "/")
    path = Prompt.ask("  Ruta pública (path)", default=path_default)
    path = path if path.startswith("/") else f"/{path}"
    if not path.endswith("/") and path != "/":
        path = path + "/"

    # 2. Tipo de ruta (por ahora solo proxy)
    route_type = prompt_route_type(console)
    if route_type not in ("proxy",):
        route_type = "proxy"  # static/redirect futuros

    # 3. Si proxy → upstream existente o nuevo
    refs = list_upstream_refs(base_dir, provider_id, env)
    slug = _slug(domain)
    default_ref = f"api__{slug}" if slug else "api__identity"

    upstream_ref: str
    new_upstream: Optional[UpstreamDefConfig] = None

    if not refs:
        upstream_ref = Prompt.ask("  Nombre del nuevo upstream", default=default_ref)
        new_upstream = _create_upstream_for_route(console, upstream_ref, provider_id, env, base_dir)
    else:
        source = prompt_upstream_source(console)
        if source == "existing":
            for i, r in enumerate(refs, 1):
                console.print(f"    [cyan]{i}.[/cyan] {r}")
            choice = Prompt.ask("  upstream_ref (número o nombre)", default=refs[0])
            if choice.isdigit() and 1 <= int(choice) <= len(refs):
                upstream_ref = refs[int(choice) - 1]
            else:
                upstream_ref = choice.strip()
        else:
            upstream_ref = Prompt.ask("  Nombre del nuevo upstream", default=default_ref)
            new_upstream = _create_upstream_for_route(console, upstream_ref, provider_id, env, base_dir)

    # 4. URI strategy (por ruta)
    uri_strategy = prompt_uri_strategy(console, path)
    upstream_path = "/" if uri_strategy == "strip" else path
    uri_cfg = UriTransformConfig(public=path, upstream=upstream_path, strategy=uri_strategy)

    name = _generate_route_name(path)
    route = RouteConfig(name=name, type="proxy", upstream_ref=upstream_ref, uri=uri_cfg)
    return (route, new_upstream)


def _ask_node_count(console: Console, prompt: str, default: int = 1) -> int:
    """Pide número de nodos (1-20)."""
    while True:
        raw = Prompt.ask(f"  {prompt}", default=str(default))
        try:
            n = int(raw)
            if 1 <= n <= 20:
                return n
        except ValueError:
            pass
        console.print("[red]Introduce un número entre 1 y 20.[/red]")


def _smart_default_weights(node_count: int, group: Optional[str] = None) -> List[int]:
    """
    Defaults inteligentes que suman 100.
    - 2 nodos: 70,30 (favor primer nodo, típico canary)
    - 3 nodos: 40,30,30
    - 4+: reparto equitativo (25/25/25/25, 20/20/...)
    """
    if node_count <= 0:
        return []
    if node_count == 1:
        return [100]
    if node_count == 2:
        return [70, 30]
    if node_count == 3:
        return [40, 30, 30]
    # 4+: equitativo
    base = 100 // node_count
    remainder = 100 - base * node_count
    weights = [base] * node_count
    weights[0] += remainder
    return weights


def _normalize_weights_to_100(weights: List[int]) -> List[int]:
    """
    Normaliza proporciones a suma 100.
    Ej: [85, 35] → [71, 29]; [1, 1, 1] → [33, 33, 34]
    """
    total = sum(weights)
    if total <= 0:
        return [100 // len(weights)] * len(weights) if weights else []
    normalized = [max(1, round(w * 100 / total)) for w in weights]
    # Ajustar redondeo: puede dar 99 o 101
    diff = 100 - sum(normalized)
    if diff != 0 and normalized:
        idx = 0 if diff > 0 else len(normalized) - 1
        normalized[idx] = max(1, normalized[idx] + diff)
    return normalized


def _loop_nodes(
    console: Console,
    ref: str,
    node_count: int,
    group_label: str,
    group: Optional[str],
) -> List[UpstreamNodeConfig]:
    """
    Loop para configurar N nodos.
    - 1 nodo en grupo canary: peso 100 automático.
    - N nodos: defaults inteligentes, Enter=aceptar. Último nodo puede ofrecer "resto".
    """
    nodes = []
    slug = ref.split("__")[-1] if "__" in ref else ref
    defaults = _smart_default_weights(node_count, group)
    auto_weight = group is not None and node_count == 1

    for i in range(node_count):
        console.print()
        console.print(Panel.fit(f"[bold]Configurando nodo {i + 1} de {node_count} ({group_label})[/bold]", border_style="dim"))
        console.print()
        default_name = f"{slug}_{group_label}_{i + 1}".replace(" ", "_") if group else f"{slug}_v{i + 1}"
        default_name = Prompt.ask("  Nombre del nodo", default=default_name)

        if auto_weight:
            weight = 100
            console.print("  [dim]Peso: 100 (único nodo del grupo)[/dim]")
        else:
            # Default inteligente; último nodo: sugerir resto para sumar 100
            sum_prev = sum(n.weight for n in nodes)
            if i == node_count - 1 and sum_prev > 0 and sum_prev < 100:
                resto = 100 - sum_prev
                hint = f"Enter = {resto} (resto para completar 100)"
                default_w = resto
            else:
                default_w = defaults[i] if i < len(defaults) else 100 // node_count
                hint = "Enter = default"
            console.print(f"  [dim]Ej: 2 nodos → 70,30 o 50,50. {hint}[/dim]")
            weight_raw = Prompt.ask(f"  Peso (%)", default=str(default_w))
            weight = int(weight_raw) if weight_raw.isdigit() else default_w

        language = prompt_tech_language(console)
        tech_node = _ask_tech_config(console, language, non_interactive=False)
        host = Prompt.ask("  Runtime host", default="127.0.0.1").strip()
        port_str = Prompt.ask("  Runtime port", default="3001").strip()
        port = int(port_str) if port_str.isdigit() else 3001

        node_kw: Dict[str, Any] = dict(
            name=default_name,
            weight=weight,
            runtime=UpstreamRuntimeConfig(host=host, port=port),
            tech=tech_node,
        )
        if group:
            node_kw["group"] = group
        nodes.append(UpstreamNodeConfig(**node_kw))

    return nodes


def _validate_group_weights(
    console: Console,
    nodes: List[UpstreamNodeConfig],
    group_name: str,
) -> List[UpstreamNodeConfig]:
    """
    Valida suma=100. Si no: ofrece normalización automática o edición manual.
    """
    if len(nodes) <= 1:
        return nodes
    total = sum(n.weight for n in nodes)
    while total != 100:
        current = [n.weight for n in nodes]
        normalized = _normalize_weights_to_100(current)
        norm_str = ", ".join(str(w) for w in normalized)
        curr_str = " + ".join(str(w) for w in current)
        console.print(f"[yellow]Pesos del grupo {group_name} suman {total} (deben sumar 100).[/yellow]")
        console.print(f"  Actual: {curr_str} = {total}")
        console.print(f"  [dim]Normalizar: {norm_str}[/dim]")
        if Confirm.ask("  ¿Normalizar proporciones automáticamente?", default=True):
            for i, w in enumerate(normalized):
                nodes[i] = nodes[i].model_copy(update={"weight": w})
            console.print(f"[green]✔ Grupo {group_name}: {norm_str} = 100%[/green]")
            return nodes
        console.print("[dim]Modificación manual:[/dim]")
        for i, n in enumerate(nodes):
            w = Prompt.ask(f"  Nodo {n.name} peso (%)", default=str(n.weight))
            nodes[i] = n.model_copy(update={"weight": int(w) if w.isdigit() else n.weight})
        total = sum(n.weight for n in nodes)
    console.print(f"[green]✔ Grupo {group_name}: suma = 100%[/green]")
    return nodes


def _create_upstream_for_route(
    console: Console,
    ref: str,
    provider_id: str,
    env: str,
    base_dir: Path,
) -> Optional[UpstreamDefConfig]:
    """
    Crea upstream. Strategy ≠ número de nodos.
    - Simple: ¿Cuántos nodos? (1+). Si >1 → algorithm. Pesos suman 100.
    - Canary: base_weight + canary_weight = 100, ¿nodos BASE?, ¿nodos CANARY?.
    """
    console.print()
    console.print(Panel.fit(f"[bold]Crear upstream [cyan]{ref}[/cyan][/bold]", border_style="dim"))
    console.print()

    # 1. Routing strategy
    routing_type = prompt_routing_strategy(console)

    nodes: Optional[List[UpstreamNodeConfig]] = None
    runtime: Optional[UpstreamRuntimeConfig] = None
    tech: Optional[UpstreamTechConfig] = None
    routing: Optional[UpstreamRoutingConfig] = None
    algorithm: Optional[str] = None

    if routing_type == "simple":
        # SIMPLE: siempre pregunta cuántos nodos
        node_count = _ask_node_count(console, "¿Cuántos nodos?", default=1)

        if node_count == 1:
            language = prompt_tech_language(console)
            tech = _ask_tech_config(console, language, non_interactive=False)
            host = Prompt.ask("  Runtime host", default="127.0.0.1").strip()
            port_str = Prompt.ask("  Runtime port", default="3001").strip()
            port = int(port_str) if port_str.isdigit() else 3001
            runtime = UpstreamRuntimeConfig(host=host, port=port)
            algorithm = get_default_algorithm_for_strategy("simple") or "round_robin"
        else:
            algorithm = prompt_routing_algorithm(console, "simple")
            nodes = _loop_nodes(console, ref, node_count, "node", None)
            nodes = _validate_group_weights(console, nodes, "nodos")

        routing = UpstreamRoutingConfig(strategy="simple", algorithm=algorithm)

    elif routing_type == "canary":
        # CANARY: base_weight + canary_weight = 100, nodos BASE, nodos CANARY
        canary_mode = prompt_canary_mode(console)

        base_weight, canary_weight = 90, 10
        while True:
            bw_raw = Prompt.ask("  base_weight (% tráfico a versión estable)", default="90") or "90"
            cw_raw = Prompt.ask("  canary_weight (% tráfico a versión experimental)", default="10") or "10"
            bw = int(bw_raw) if bw_raw.isdigit() else 90
            cw = int(cw_raw) if cw_raw.isdigit() else 10
            if bw + cw == 100 and bw >= 0 and cw >= 0:
                base_weight, canary_weight = bw, cw
                break
            total = bw + cw
            if total > 0 and Confirm.ask(f"  Suma = {total}. ¿Normalizar a 100%? (→ {round(bw*100/total)}, {round(cw*100/total)})", default=True):
                base_weight = max(1, round(bw * 100 / total))
                canary_weight = 100 - base_weight
                break
            console.print("[yellow]Introduce valores que sumen 100 (ej: 90, 10).[/yellow]")

        console.print("[green]✔ base_weight + canary_weight = 100%[/green]")

        # Stickiness (persistencia de ruteo)
        stickiness = prompt_stickiness(console)
        sticky_key: Optional[str] = None
        if stickiness in STICKINESS_NEEDS_KEY:
            sticky_key = prompt_sticky_key(console, ref, stickiness)

        # Mapear stickiness → mode (para YAML/generator retrocompat)
        mode_map = {"none": "percentage", "request": "percentage", "ip": "percentage", "cookie": "cookie", "header": "header"}
        canary_mode = mode_map.get(stickiness, "percentage")

        num_base = _ask_node_count(console, "¿Cuántos nodos BASE?", default=1)
        num_canary = _ask_node_count(console, "¿Cuántos nodos CANARY?", default=1)

        base_nodes = _loop_nodes(console, ref, num_base, "base", "base")
        base_nodes = _validate_group_weights(console, base_nodes, "base")

        canary_nodes = _loop_nodes(console, ref, num_canary, "canary", "canary")
        canary_nodes = _validate_group_weights(console, canary_nodes, "canary")

        nodes = base_nodes + canary_nodes

        canary_kw: Dict[str, Any] = {
            "mode": canary_mode,
            "base_weight": base_weight,
            "canary_weight": canary_weight,
            "stickiness": stickiness,
            "sticky_key": sticky_key,
        }
        if stickiness == "header" and sticky_key:
            canary_kw["header"] = sticky_key
        elif stickiness == "cookie" and sticky_key:
            canary_kw["cookie"] = sticky_key
        routing = UpstreamRoutingConfig(strategy="canary", algorithm="weighted", canary=UpstreamCanaryConfig(**canary_kw))

    else:
        # failover, mirror, blue_green: también preguntar nodos
        algorithm = prompt_routing_algorithm(console, routing_type) if needs_algorithm(routing_type) else "round_robin"
        node_count = _ask_node_count(console, "¿Cuántos nodos?", default=2)
        nodes = _loop_nodes(console, ref, node_count, "node", None)
        if node_count > 1:
            nodes = _validate_group_weights(console, nodes, "nodos")
        routing = UpstreamRoutingConfig(strategy=routing_type, algorithm=algorithm)

    slug = ref.split("__")[-1] if "__" in ref else ref
    identity = UpstreamIdentityConfig(slug=slug, domain_group=slug)
    exposure = UpstreamExposureConfig(access_type="internal")

    return UpstreamDefConfig(
        name=ref,
        service_type="api",
        identity=identity,
        exposure=exposure,
        routing=routing,
        nodes=nodes,
        runtime=runtime,
        tech=tech,
    )


def _ask_routes(
    console: Console,
    domain: str,
    provider_id: str,
    env: str,
    base_dir: Path,
) -> List[RouteConfig]:
    """
    Flujo UX: 1) ¿Cuántas rutas? 2) Loop "Configurando ruta X de N" por cada una.
    Ruta manda, upstream es consecuencia.
    """
    # 1. Pregunta clave: número de rutas
    console.print()
    console.print(Panel.fit("[bold]Rutas / proxys del dominio[/bold]", border_style="cyan"))
    num_routes = _ask_num_routes(console)

    routes: List[RouteConfig] = []
    new_upstreams: List[UpstreamDefConfig] = []

    for i in range(num_routes):
        route, new_up = _ask_single_route(console, i + 1, num_routes, domain, provider_id, env, base_dir)
        routes.append(route)
        if new_up:
            new_upstreams.append(new_up)
            save_upstream_v2(base_dir, provider_id, env, new_up, console)

    return routes


def _ask_tech_config(console: Console, language: str, non_interactive: bool = False) -> UpstreamTechConfig:
    """Pide configuración tech por lenguaje."""
    cap = get_capabilities(language)
    
    # Versión
    v_default = cap.get("default_version", "20")
    version = (Prompt.ask("  tech.version", default=v_default) or v_default).strip() or v_default

    provider: Optional[str] = None
    manager: Optional[str] = None

    if language == "php":
        provider = "system"
        console.print("  [dim]PHP usa runtime del sistema (provider: system)[/dim]")
        managers = cap.get("managers", ["composer"])
        mgr_default = cap.get("default_manager", "composer")
        if len(managers) == 1:
            manager = managers[0]
            console.print(f"  [dim]tech.manager: {manager}[/dim]")
        else:
            choice = Prompt.ask("  tech.manager", default=mgr_default)
            manager = resolve_manager_input(language, choice)
    else:
        # Node o Python
        if cap.get("provider_required"):
            choices = "|".join(cap.get("providers", []))
            raw_provider = Prompt.ask(
                f"  tech.provider ({choices})",
                default=cap.get("default_provider", "volta"),
            )
            provider = resolve_provider_input(language, raw_provider, console)
            raw_lower = (raw_provider or "").strip().lower()
            valid_managers = [m.lower() for m in cap.get("managers", [])]
            if is_manager(raw_lower):
                console.print(
                    "[yellow]Composer es un tech_manager, no un tech_provider. Ajustando modelo.[/yellow]"
                )
                if raw_lower in valid_managers:
                    manager = raw_lower
        else:
            provider = cap.get("default_provider", "system")
            console.print(f"  [dim]tech.provider: {provider} (default)[/dim]")

        if manager is None:
            managers = "|".join(cap.get("managers", []))
            mgr_default = cap.get("default_manager", "yarn")
            raw_mgr = Prompt.ask(f"  tech.manager ({managers})", default=mgr_default)
            manager = resolve_manager_input(language, raw_mgr)

    provider = provider or cap.get("default_provider", "system")
    manager = manager or resolve_manager_input(language, "")

    return UpstreamTechConfig(
        language=language,
        version=version,
        provider=provider,
        manager=manager,
    )


def _ask_node_config(console: Console, node_name: str, weight: int = 100, non_interactive: bool = False) -> UpstreamNodeConfig:
    """Pide configuración de un nodo upstream."""
    console.print(f"  [bold]Nodo: {node_name}[/bold]")
    
    language = prompt_tech_language(console) if not non_interactive else "node"
    
    tech = _ask_tech_config(console, language, non_interactive)
    
    host = Prompt.ask("    runtime.host", default="127.0.0.1").strip()
    port_str = Prompt.ask("    runtime.port", default="3001").strip()
    port = int(port_str) if port_str.isdigit() else 3001
    
    weight_str = Prompt.ask("    weight (0-100)", default=str(weight)).strip()
    weight = int(weight_str) if weight_str.isdigit() else weight
    
    return UpstreamNodeConfig(
        name=node_name,
        weight=weight,
        runtime=UpstreamRuntimeConfig(host=host, port=port),
        tech=tech,
    )


def _create_upstream_interactive(
    base_dir: Path,
    console: Console,
    ref: str,
    provider_id: str,
    env: str,
    non_interactive: bool = False,
) -> Optional[UpstreamDefConfig]:
    """
    Crea upstream cuando falta (YAML con ref que no existe).
    Delega en _create_upstream_for_route (flujo completo: simple/canary con nodos).
    """
    return _create_upstream_for_route(console, ref, provider_id, env, base_dir)


def _run_orchestration(base_dir: Path, console: Console, domain_cfg: FrontendDomainConfig) -> None:
    if not domain_cfg.root:
        return
    try:
        from ..orchestration import run_bootstrap_orchestration
        run_bootstrap_orchestration(
            domain_cfg.provider.lower(),
            domain_cfg.environment,
            _slug(domain_cfg.domain),
            domain_cfg.root.owner,
            domain_cfg.root.technical_user or None,
            base_dir,
            console,
            dry_run=False,
        )
    except Exception as e:
        console.print(f"[yellow]⚠ Orquestación falló: {e}[/yellow]")
        if not Confirm.ask("¿Continuar?", default=True):
            raise
