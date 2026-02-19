"""
Validación de upstream
"""

import re
from typing import List
from .base import ValidationRule, ValidationResult, NginxConfig, FixAction, FixCapability


class UpstreamValidationRule(ValidationRule):
    """Valida que los servicios API usen upstream y que el naming sea correcto"""
    
    @property
    def name(self) -> str:
        return "Upstream"
    
    @property
    def description(self) -> str:
        return "Valida que service_type=api use upstream y que el naming sea correcto"
    
    def validate(self, config: NginxConfig) -> List[ValidationResult]:
        results = []
        
        service_type = config.meta.get("service_type", "").lower()
        environment = config.meta.get("environment", "").lower()
        
        # Si es API, DEBE tener upstream
        if service_type == "api":
            if not config.upstreams:
                results.append(self.error(
                    "service_type=api requiere un upstream",
                    "Los servicios API deben usar upstream, no IPs directas en proxy_pass"
                ))
                return results
            
            # Validar que proxy_pass use upstream
            if not config.proxy_pass:
                results.append(self.error(
                    "No se encontró proxy_pass en la configuración",
                    "Los servicios API deben tener proxy_pass apuntando a un upstream"
                ))
                return results
            
            # Verificar que proxy_pass apunte a un upstream (no IP directa)
            if re.match(r'http://\d+\.\d+\.\d+\.\d+', config.proxy_pass):
                results.append(self.error(
                    "proxy_pass apunta directamente a una IP",
                    f"proxy_pass: {config.proxy_pass}. Debe usar un upstream."
                ))
                return results
            
            # Validar naming del upstream
            # Formato: {service_type}_{environment}_{domain_slug} (snake_case, sin puntos ni guiones)
            # Ejemplo: api_dev_identity_lunarsystemx para dev-identity.lunarsystemx.com
            if config.server_name:
                domain_slug = self._domain_to_slug(config.server_name)
                expected_upstream = f"{service_type}_{environment}_{domain_slug}"
                
                # Buscar upstream que se use en proxy_pass
                upstream_used = None
                for upstream_name in config.upstreams.keys():
                    # Verificar si este upstream está en proxy_pass
                    if upstream_name in config.proxy_pass or f"http://{upstream_name}" in config.proxy_pass:
                        upstream_used = upstream_name
                        break
                
                if not upstream_used:
                    results.append(self.error(
                        "Ningún upstream está siendo usado en proxy_pass",
                        f"proxy_pass: {config.proxy_pass}, Upstreams disponibles: {', '.join(config.upstreams.keys())}"
                    ))
                else:
                    # Verificar naming
                    if upstream_used == expected_upstream:
                        results.append(self.info(
                            f"Upstream '{upstream_used}' sigue el naming correcto: {expected_upstream}"
                        ))
                    else:
                        # Verificar si al menos contiene los componentes esperados
                        has_service_type = service_type in upstream_used
                        has_environment = environment in upstream_used
                        has_domain = domain_slug in upstream_used
                        
                        # Usar metadata para determinar si puede corregirse automáticamente
                        # Si tenemos service_type, environment y dominio, podemos corregir automáticamente
                        metadata_complete = (
                            service_type and 
                            environment and 
                            domain_slug and
                            config.server_name
                        )
                        
                        # También verificar variantes comunes (ej: identity_backend en lugar de api_dev_identity)
                        # Si contiene el dominio slug, es aceptable aunque no tenga service_type y environment
                        if domain_slug in upstream_used:
                            if metadata_complete:
                                # Con metadata completa, podemos corregir automáticamente
                                fix_action = self._create_rename_upstream_fix(
                                    upstream_used,
                                    expected_upstream,
                                    config
                                )
                                results.append(self.warning_with_fix(
                                    f"Upstream '{upstream_used}' contiene el dominio pero no sigue el formato completo",
                                    f"Formato esperado: {expected_upstream}, Actual: {upstream_used}",
                                    fix_capability=FixCapability.AUTO,
                                    fix_description=f"Renombrar upstream a formato estándar: {expected_upstream}",
                                    fix_action=fix_action
                                ))
                            else:
                                # Sin metadata completa, solo informar
                                results.append(self.warning_none(
                                    f"Upstream '{upstream_used}' contiene el dominio pero no sigue el formato completo",
                                    f"Formato esperado: {expected_upstream}, Actual: {upstream_used}",
                                    reason="Requiere metadata completa (service_type, environment, dominio) para corrección automática"
                                ))
                        elif has_service_type and has_environment and has_domain:
                            if metadata_complete:
                                # Con metadata completa, podemos corregir automáticamente
                                fix_action = self._create_rename_upstream_fix(
                                    upstream_used,
                                    expected_upstream,
                                    config
                                )
                                results.append(self.warning_with_fix(
                                    f"Upstream '{upstream_used}' contiene los componentes correctos pero no sigue el formato exacto",
                                    f"Formato esperado: {expected_upstream}, Actual: {upstream_used}",
                                    fix_capability=FixCapability.AUTO,
                                    fix_description=f"Renombrar upstream a formato estándar: {expected_upstream}",
                                    fix_action=fix_action
                                ))
                            else:
                                results.append(self.warning(
                                    f"Upstream '{upstream_used}' contiene los componentes correctos pero no sigue el formato exacto",
                                    f"Formato esperado: {expected_upstream}, Actual: {upstream_used}"
                                ))
                        else:
                            # Sin metadata suficiente, requiere acción manual
                            results.append(self.warning_none(
                                f"Upstream '{upstream_used}' no sigue el naming esperado",
                                f"Formato esperado: {expected_upstream}, Actual: {upstream_used}",
                                reason="Requiere metadata completa (service_type, environment, dominio) para determinar corrección automática"
                            ))
        
        return results
    
    def _domain_type(self, domain: str) -> str:
        """Determina si el dominio es root o subdomain"""
        # 2+ puntos → subdomain (ej: dev-identity.lunarsystemx.com)
        # 1 punto → root (ej: dev-lunarsystemx.com)
        if not domain:
            return "root"
        return "subdomain" if domain.count(".") >= 2 else "root"

    def _domain_to_slug(self, domain: str) -> str:
        """Convierte un dominio a slug snake_case para naming de upstream (sin puntos ni guiones)"""
        # Remover prefijos de ambiente
        domain_clean = domain.replace("dev-", "").replace("qa-", "").replace("prod-", "")
        parts = domain_clean.split(".")
        # Usar primeras dos partes: identity_lunarsystemx o lunarsystemx_com
        if len(parts) >= 2:
            return (parts[0] + "_" + parts[1]).replace("-", "_")
        if parts:
            return parts[0].replace("-", "_")
        return domain_clean.replace(".", "_").replace("-", "_")
    
    def _create_rename_upstream_fix(self, old_name: str, new_name: str, config: NginxConfig) -> FixAction:
        """Crea una acción de fix para renombrar upstream"""
        def apply_fix(cfg: NginxConfig) -> str:
            content = cfg.content
            
            # Renombrar definición de upstream
            content = re.sub(
                rf'upstream\s+{re.escape(old_name)}\s*{{',
                f'upstream {new_name} {{',
                content
            )
            
            # Renombrar uso en proxy_pass
            content = re.sub(
                rf'proxy_pass\s+http://{re.escape(old_name)}([^;]*)',
                f'proxy_pass http://{new_name}\\1',
                content
            )
            content = re.sub(
                rf'proxy_pass\s+{re.escape(old_name)}([^;]*)',
                f'proxy_pass http://{new_name}\\1',
                content
            )
            
            return content
        
        return FixAction(
            description=f"Renombrar upstream '{old_name}' a '{new_name}' y actualizar proxy_pass",
            apply=apply_fix
        )
