"""
Health Check para sitios web
Realiza verificaciones de disponibilidad mediante curl
"""

import subprocess
from typing import Optional, Dict
from rich.console import Console


def check_site_health(domain: str, timeout: int = 5, console: Optional[Console] = None) -> Dict[str, any]:
    """
    Verifica el estado de salud de un sitio mediante curl
    
    Args:
        domain: Dominio a verificar
        timeout: Timeout en segundos para la petición
        console: Console de Rich para salida (opcional)
    
    Returns:
        Dict con:
            - status: "up", "down", "timeout", "error"
            - http_code: Código HTTP (si disponible)
            - response_time: Tiempo de respuesta en segundos (si disponible)
            - response_ip: IP a la que está respondiendo (si disponible)
            - error: Mensaje de error (si hay error)
    """
    import time
    
    result = {
        "status": "unknown",
        "http_code": None,
        "response_time": None,
        "response_ip": None,
        "error": None
    }
    
    # Estrategia: Intentar primero HTTPS (más común en producción)
    # Si falla la resolución DNS, intentar con Host header a localhost
    # Priorizar códigos exitosos (2xx, 3xx) y códigos de autenticación (401, 403) sobre 404
    urls_to_try = [
        (f"https://127.0.0.1", True),    # HTTPS localhost con Host header (prioridad)
        (f"https://{domain}", False),    # HTTPS directo
        (f"http://127.0.0.1", True),     # HTTP localhost con Host header
        (f"http://{domain}", False),     # HTTP directo
        (f"http://localhost", True),     # HTTP localhost alternativo
    ]
    
    best_result = None
    best_priority = -1
    
    # Prioridad de códigos: 2xx > 401/403 > otros 4xx > 3xx > 5xx
    # Nota: 3xx tiene menor prioridad porque puede ser redirección HTTP->HTTPS
    def get_code_priority(code, is_https=False):
        if 200 <= code < 300:
            return 5  # Éxito directo
        elif code in [401, 403]:
            return 4  # Autenticación requerida (servicio vivo)
        elif 400 <= code < 500:
            # 4xx en HTTPS tiene más prioridad que 3xx en HTTP
            return 3 if is_https else 2  # Error del cliente pero servicio vivo
        elif 300 <= code < 400:
            # 3xx tiene menor prioridad, especialmente en HTTP
            return 1 if is_https else 0  # Redirección (menos confiable)
        elif code >= 500:
            return -1  # Error del servidor
        return -2
    
    for url, use_host_header in urls_to_try:
        start_time = time.time()
        try:
            curl_cmd = [
                "curl",
                "-s",
                "-o", "/dev/null",
                "-w", "%{http_code}\n%{remote_ip}",
                "--max-time", str(timeout),
                "--connect-timeout", "3",
                "-k",  # Ignorar certificados SSL (útil para dev)
            ]
            
            # Si es localhost, agregar Host header
            if use_host_header and ("127.0.0.1" in url or "localhost" in url):
                curl_cmd.extend(["-H", f"Host: {domain}"])
            
            curl_cmd.append(url)
            
            curl_result = subprocess.run(
                curl_cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 2
            )
            
            response_time = time.time() - start_time
            
            if curl_result.returncode == 0:
                output_lines = curl_result.stdout.strip().split("\n")
                http_code = output_lines[0] if output_lines else ""
                response_ip = output_lines[1] if len(output_lines) > 1 else None
                
                if http_code.isdigit():
                    http_code_int = int(http_code)
                    is_https = "https" in url
                    priority = get_code_priority(http_code_int, is_https)
                    
                    # Si encontramos un código exitoso (2xx) o de autenticación (401/403), retornar inmediatamente
                    if priority >= 4:  # 2xx o 401/403: Éxito o autenticación requerida
                        result["status"] = "up"
                        result["http_code"] = http_code_int
                        result["response_time"] = round(response_time, 2)
                        result["response_ip"] = response_ip or "127.0.0.1"
                        return result
                    
                    # Guardar el mejor resultado encontrado hasta ahora
                    # Priorizar resultados HTTPS sobre HTTP para el mismo código
                    if priority > best_priority or (priority == best_priority and is_https and best_result and "http://" in str(best_result.get("response_ip", ""))):
                        best_priority = priority
                        best_result = {
                            "status": "up" if http_code_int >= 200 else "down",
                            "http_code": http_code_int,
                            "response_time": round(response_time, 2),
                            "response_ip": response_ip or "127.0.0.1"
                        }
            
        except subprocess.TimeoutExpired:
            continue  # Intentar siguiente URL
        except Exception:
            continue  # Intentar siguiente URL
    
    # Si encontramos algún resultado válido, retornarlo
    if best_result:
        result.update(best_result)
        return result
    
    # Si todas las URLs fallaron
    result["status"] = "down"
    result["error"] = "No response"
    
    return result


def format_health_status(health_result: Dict[str, any]) -> str:
    """
    Formatea el resultado del health check para mostrar en tabla
    
    Args:
        health_result: Resultado de check_site_health
    
    Returns:
        String formateado con Rich markup (una sola línea)
    """
    status = health_result.get("status", "unknown")
    http_code = health_result.get("http_code")
    response_time = health_result.get("response_time")
    response_ip = health_result.get("response_ip")
    
    # Formatear IP si existe y no es localhost
    ip_suffix = ""
    if response_ip:
        if response_ip not in ["127.0.0.1", "localhost", "::1"]:
            ip_suffix = f" ({response_ip})"
        else:
            ip_suffix = " (localhost)"
    
    if status == "up":
        if http_code:
            # Distinguir entre códigos exitosos (2xx, 3xx) y errores que indican servicio vivo (4xx, 5xx)
            if 200 <= http_code < 300:
                # 2xx: Éxito
                return f"[green]✅ {http_code}[/green]{ip_suffix}"
            elif 300 <= http_code < 400:
                # 3xx: Redirección (servicio funciona)
                return f"[green]✅ {http_code}[/green]{ip_suffix}"
            elif 400 <= http_code < 500:
                # 4xx: Error del cliente pero servicio está vivo (401=autenticación, 403=prohibido, 404=no encontrado)
                if http_code in [401, 403]:
                    return f"[yellow]🔐 {http_code}[/yellow]{ip_suffix}"  # Requiere autenticación
                else:
                    return f"[yellow]⚠ {http_code}[/yellow]{ip_suffix}"  # Otro error 4xx
            elif http_code >= 500:
                # 5xx: Error del servidor pero está vivo
                return f"[red]⚠ {http_code}[/red]{ip_suffix}"
            else:
                return f"[green]✅ {http_code}[/green]{ip_suffix}"
        else:
            return f"[green]✅ UP[/green]{ip_suffix}"
    elif status == "down":
        if http_code:
            return f"[red]❌ {http_code}[/red]{ip_suffix}"
        else:
            return f"[red]❌ DOWN[/red]{ip_suffix}"
    elif status == "timeout":
        return "[yellow]⏱ TIMEOUT[/yellow]"
    elif status == "error":
        error = health_result.get("error", "Error")
        # Truncar error para que quepa en una línea
        error_short = error[:8] if len(error) > 8 else error
        return f"[red]⚠ {error_short}[/red]"
    else:
        return "[dim]—[/dim]"
