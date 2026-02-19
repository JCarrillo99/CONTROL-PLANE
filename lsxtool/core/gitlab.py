"""
Módulo GitLab - Interacción con GitLab API
"""

import json
from typing import Optional, Dict, Any, List
from pathlib import Path
from rich.console import Console

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class GitLabAPI:
    """Cliente para GitLab API"""
    
    def __init__(self, url: str, token: str, console: Optional[Console] = None, mock: bool = False):
        """
        Inicializa cliente GitLab API
        
        Args:
            url: URL base de GitLab (ej: https://gitlab.com)
            token: Token de acceso GitLab
            console: Console de Rich para salida
            mock: Si True, simula respuestas sin hacer llamadas reales
        """
        self.url = url.rstrip("/")
        self.token = token
        self.console = console
        self.mock = mock
        self.api_url = f"{self.url}/api/v4"
    
    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None
    ) -> tuple[bool, Optional[Dict], Optional[str]]:
        """
        Realiza una petición a la API de GitLab
        
        Args:
            method: Método HTTP (GET, POST, etc.)
            endpoint: Endpoint de la API (sin /api/v4)
            params: Parámetros de query
            data: Datos del body
        
        Returns:
            Tuple (success, response_data, error_message)
        """
        if self.mock:
            return self._mock_request(method, endpoint, params, data)
        
        if not HAS_REQUESTS:
            return False, None, "Librería 'requests' no instalada. Instala con: pip install requests"
        
        url = f"{self.api_url}/{endpoint.lstrip('/')}"
        headers = {
            "PRIVATE-TOKEN": self.token,
            "Content-Type": "application/json"
        }
        
        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, params=params, timeout=10)
            elif method.upper() == "POST":
                response = requests.post(url, headers=headers, params=params, json=data, timeout=10)
            elif method.upper() == "PUT":
                response = requests.put(url, headers=headers, params=params, json=data, timeout=10)
            elif method.upper() == "DELETE":
                response = requests.delete(url, headers=headers, params=params, timeout=10)
            else:
                return False, None, f"Método HTTP no soportado: {method}"
            
            if response.status_code == 200 or response.status_code == 201:
                return True, response.json(), None
            else:
                error_msg = f"Error {response.status_code}: {response.text[:200]}"
                return False, None, error_msg
        except requests.exceptions.Timeout:
            return False, None, "Timeout al conectar con GitLab"
        except requests.exceptions.ConnectionError:
            return False, None, "Error de conexión con GitLab"
        except Exception as e:
            return False, None, f"Error GitLab API: {str(e)}"
    
    def _mock_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None
    ) -> tuple[bool, Optional[Dict], Optional[str]]:
        """Simula respuestas de GitLab API"""
        if self.console:
            self.console.print(f"[dim][MOCK] {method} {endpoint}[/dim]")
        
        # Simular respuestas comunes
        if "projects" in endpoint and method.upper() == "GET":
            return True, {
                "id": 1,
                "name": "test-project",
                "path": "test-project",
                "web_url": f"{self.url}/test-project"
            }, None
        
        if "pipelines" in endpoint:
            return True, {
                "id": 1,
                "status": "success",
                "ref": "main",
                "sha": "abc123"
            }, None
        
        return True, {"mock": True}, None
    
    def get_project(self, project_path: str) -> tuple[bool, Optional[Dict], Optional[str]]:
        """
        Obtiene información de un proyecto
        
        Args:
            project_path: Ruta del proyecto (ej: grupo/proyecto)
        
        Returns:
            Tuple (success, project_data, error_message)
        """
        endpoint = f"projects/{project_path.replace('/', '%2F')}"
        return self._request("GET", endpoint)
    
    def get_pipelines(self, project_path: str, limit: int = 5) -> tuple[bool, Optional[List[Dict]], Optional[str]]:
        """
        Obtiene pipelines de un proyecto
        
        Args:
            project_path: Ruta del proyecto
            limit: Número máximo de pipelines a obtener
        
        Returns:
            Tuple (success, pipelines_list, error_message)
        """
        project_id = project_path.replace("/", "%2F")
        endpoint = f"projects/{project_id}/pipelines"
        params = {"per_page": limit}
        success, data, error = self._request("GET", endpoint, params=params)
        
        if success and isinstance(data, list):
            return True, data, None
        elif success:
            return True, [data], None
        else:
            return False, None, error
    
    def trigger_pipeline(self, project_path: str, ref: str = "main") -> tuple[bool, Optional[Dict], Optional[str]]:
        """
        Dispara un pipeline
        
        Args:
            project_path: Ruta del proyecto
            ref: Rama o tag a usar
        
        Returns:
            Tuple (success, pipeline_data, error_message)
        """
        project_id = project_path.replace("/", "%2F")
        endpoint = f"projects/{project_id}/pipeline"
        data = {"ref": ref}
        return self._request("POST", endpoint, data=data)
    
    def test_connection(self) -> bool:
        """
        Prueba la conexión con GitLab
        
        Returns:
            True si la conexión es exitosa
        """
        success, data, error = self._request("GET", "user")
        
        if success:
            if self.console:
                if self.mock:
                    self.console.print("[green]✔ Conexión GitLab (MOCK)[/green]")
                else:
                    username = data.get("username", "unknown") if isinstance(data, dict) else "unknown"
                    self.console.print(f"[green]✔ Conexión GitLab exitosa: {username}[/green]")
            return True
        else:
            if self.console:
                self.console.print(f"[red]✘ Error de conexión GitLab: {error}[/red]")
            return False
