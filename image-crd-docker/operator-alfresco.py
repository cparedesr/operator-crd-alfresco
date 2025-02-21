import kopf
import kubernetes.client
from kubernetes.client import (
    V1Service,
    V1Deployment,
    V1Container,
    V1EnvVar,
    V1PodSpec,
    V1ObjectMeta,
    V1ServicePort,
    V1ServiceSpec,
    V1DeploymentSpec,
    V1PodTemplateSpec,
    V1ResourceRequirements,
    V1ContainerPort,
    V1LabelSelector,
    V1SecurityContext,
    V1PodSecurityContext
)

def create_resource(service_name, service_spec, namespace, logger):
    # Configurar securityContext para PostgreSQL (opcional)
    container_security_context = None
    if "postgres" in service_spec.get('image', '').lower():
        container_security_context = V1SecurityContext(
            run_as_user=999,
            run_as_group=999,
            allow_privilege_escalation=False
        
        )
    
    # Usar 'args' en lugar de 'command' para conservar el entrypoint predeterminado
    container_args = service_spec.get('command', [])
    
    container = V1Container(
        name=service_name,
        image=service_spec.get('image'),
        env=[V1EnvVar(name=k, value=v) for k, v in service_spec.get('environment', {}).items()],
        args=container_args,
        resources=V1ResourceRequirements(
            limits=service_spec.get('resources', {}).get('limits', {}),
            requests=service_spec.get('resources', {}).get('requests', {})
        ),
        ports=[V1ContainerPort(
            container_port=int(p.split(":")[1]),
            host_port=int(p.split(":")[0])
        ) for p in service_spec.get('ports', [])],
        security_context=container_security_context
    )
    
    # Configurar securityContext a nivel del Pod para forzar el UID
    pod_security_context = None
    if "postgres" in service_spec.get('image', '').lower():
        pod_security_context = V1PodSecurityContext(
            run_as_user=999,
            run_as_group=999,
            fs_group=999,
            run_as_non_root=True
        )
    
    pod_spec = V1PodSpec(
        containers=[container],
        security_context=pod_security_context
    )
    
    deployment = V1Deployment(
        api_version="apps/v1",
        kind="Deployment",
        metadata=V1ObjectMeta(name=service_spec.get('name', service_name), namespace=namespace),
        spec=V1DeploymentSpec(
            replicas=service_spec.get('replicas', 1),
            selector=V1LabelSelector(match_labels={"app": service_name}),
            template=V1PodTemplateSpec(
                metadata=V1ObjectMeta(labels={"app": service_name}),
                spec=pod_spec
            )
        )
    )
    
    service = V1Service(
        api_version="v1",
        kind="Service",
        metadata=V1ObjectMeta(name=service_spec.get('name', service_name), namespace=namespace),
        spec=V1ServiceSpec(
            selector={"app": service_name},
            ports=[V1ServicePort(
                name=f"port-{p.split(':')[1]}",
                port=int(p.split(":")[1]),
                target_port=int(p.split(":")[1])
            ) for p in service_spec.get('ports', [])]
        )
    )
    
    return deployment, service

@kopf.on.create('alfresco.community.com', 'v1', 'alfrescos')
def create_alfresco(name, namespace, spec, logger, **kwargs):
    api_instance = kubernetes.client.CoreV1Api()
    apps_api_instance = kubernetes.client.AppsV1Api()
    for service_name, service_spec in spec.items():
        deployment, service = create_resource(service_name, service_spec, namespace, logger)
        
        try:
            apps_api_instance.create_namespaced_deployment(namespace, deployment)
            logger.info(f"Deployment {service_spec.get('name', service_name)} created in namespace {namespace}")
        except kubernetes.client.rest.ApiException as e:
            if e.status == 409:
                logger.info(f"Deployment {service_spec.get('name', service_name)} already exists in namespace {namespace}")
            else:
                raise
        
        try:
            api_instance.create_namespaced_service(namespace, service)
            logger.info(f"Service {service_spec.get('name', service_name)} created in namespace {namespace}")
        except kubernetes.client.rest.ApiException as e:
            if e.status == 409:
                logger.info(f"Service {service_spec.get('name', service_name)} already exists in namespace {namespace}")
            else:
                raise

@kopf.on.update('alfresco.community.com', 'v1', 'alfrescos')
def update_alfresco(name, namespace, spec, logger, **kwargs):
    api_instance = kubernetes.client.CoreV1Api()
    apps_api_instance = kubernetes.client.AppsV1Api()
    # Para cada servicio, se realiza un patch del deployment y del service
    for service_name, service_spec in spec.items():
        deployment, service = create_resource(service_name, service_spec, namespace, logger)
        try:
            apps_api_instance.patch_namespaced_deployment(
                name=service_spec.get('name', service_name),
                namespace=namespace,
                body=deployment
            )
            logger.info(f"Deployment {service_spec.get('name', service_name)} updated in namespace {namespace}")
        except kubernetes.client.rest.ApiException as e:
            logger.error(f"Error updating deployment {service_spec.get('name', service_name)}: {e}")
        try:
            api_instance.patch_namespaced_service(
                name=service_spec.get('name', service_name),
                namespace=namespace,
                body=service
            )
            logger.info(f"Service {service_spec.get('name', service_name)} updated in namespace {namespace}")
        except kubernetes.client.rest.ApiException as e:
            logger.error(f"Error updating service {service_spec.get('name', service_name)}: {e}")

@kopf.on.delete('alfresco.community.com', 'v1', 'alfrescos')
def delete_alfresco(name, namespace, spec, logger, **kwargs):
    api_instance = kubernetes.client.CoreV1Api()
    apps_api_instance = kubernetes.client.AppsV1Api()
    # Se eliminan los deployments y services asociados
    for service_name, service_spec in spec.items():
        resource_name = service_spec.get('name', service_name)
        try:
            apps_api_instance.delete_namespaced_deployment(
                name=resource_name,
                namespace=namespace
            )
            logger.info(f"Deployment {resource_name} deleted from namespace {namespace}")
        except kubernetes.client.rest.ApiException as e:
            if e.status == 404:
                logger.info(f"Deployment {resource_name} not found in namespace {namespace}")
            else:
                logger.error(f"Error deleting deployment {resource_name}: {e}")
        try:
            api_instance.delete_namespaced_service(
                name=resource_name,
                namespace=namespace
            )
            logger.info(f"Service {resource_name} deleted from namespace {namespace}")
        except kubernetes.client.rest.ApiException as e:
            if e.status == 404:
                logger.info(f"Service {resource_name} not found in namespace {namespace}")
            else:
                logger.error(f"Error deleting service {resource_name}: {e}")

if __name__ == '__main__':
    kopf.run(namespaces=['default'])