import kopf
import kubernetes
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
    V1PodSecurityContext,
    V1Probe,
    V1HTTPGetAction,
    V1ExecAction,
    V1TCPSocketAction,
    V1Volume,
    V1VolumeMount,
    V1PersistentVolumeClaimVolumeSource,
    V1OwnerReference,
)


def create_probe(probe_spec: dict | None) -> V1Probe | None:
    """Crea un V1Probe (readiness o liveness) a partir del dict del CR."""
    if not probe_spec:
        return None

    common_kwargs = dict(
        initial_delay_seconds=probe_spec.get("initialDelaySeconds", 10),
        period_seconds=probe_spec.get("periodSeconds", 10),
        failure_threshold=probe_spec.get("failureThreshold", 3),
        timeout_seconds=probe_spec.get("timeoutSeconds", 1),
        success_threshold=probe_spec.get("successThreshold", 1),
    )

    if "httpGet" in probe_spec:
        return V1Probe(
            http_get=V1HTTPGetAction(
                path=probe_spec["httpGet"]["path"],
                port=probe_spec["httpGet"]["port"],
            ),
            **common_kwargs,
        )
    if "exec" in probe_spec:
        return V1Probe(
            _exec=V1ExecAction(
                command=probe_spec["exec"]["command"],
            ),
            **common_kwargs,
        )
    if "tcpSocket" in probe_spec:
        return V1Probe(
            tcp_socket=V1TCPSocketAction(
                port=probe_spec["tcpSocket"]["port"],
            ),
            **common_kwargs,
        )

    return None


def create_resource(
    service_name: str,
    service_spec: dict,
    namespace: str,
    logger,
    owner_references: list[V1OwnerReference] | None = None,
) -> tuple[V1Deployment, V1Service]:
    """
    Construye los objetos Deployment y Service para un 'service_spec' de la CR Alfresco.
    No los crea en el clúster, sólo devuelve las definiciones.
    """

    image = service_spec.get("image")
    replicas = service_spec.get("replicas", 1)
    env_spec: dict = service_spec.get("environment", {})
    ports_spec: list[str] = service_spec.get("ports", [])
    service_type: str = service_spec.get("service_type", "ClusterIP")
    volumes_spec: list[dict] = service_spec.get("volumes", [])
    service_account_name: str | None = service_spec.get("serviceAccountName")

    container_security_context = None
    pod_security_context = None
    if image and "postgres" in image.lower():
        container_security_context = V1SecurityContext(
            run_as_user=999,
            run_as_group=999,
            allow_privilege_escalation=False,
        )
        pod_security_context = V1PodSecurityContext(
            run_as_user=999,
            run_as_group=999,
            fs_group=999,
            run_as_non_root=True,
        )

    container_ports = [
        V1ContainerPort(container_port=int(p)) for p in ports_spec
    ]

    readiness_probe = create_probe(service_spec.get("readinessProbe"))
    liveness_probe = create_probe(service_spec.get("livenessProbe"))

    volumes: list[V1Volume] = []
    volume_mounts: list[V1VolumeMount] = []
    for volume_spec in volumes_spec:
        volume_name = volume_spec.get("name")
        mount_path = volume_spec.get("mountPath")
        existing_claim = volume_spec.get("existingClaim")

        if volume_name and mount_path and existing_claim:
            volumes.append(
                V1Volume(
                    name=volume_name,
                    persistent_volume_claim=V1PersistentVolumeClaimVolumeSource(
                        claim_name=existing_claim
                    ),
                )
            )
            volume_mounts.append(
                V1VolumeMount(
                    name=volume_name,
                    mount_path=mount_path,
                )
            )

    env_vars = [
        V1EnvVar(name=k, value=v) for k, v in env_spec.items()
    ]

    container = V1Container(
        name=service_name,
        image=image,
        env=env_vars,
        args=service_spec.get("command", []),
        resources=V1ResourceRequirements(
            limits=service_spec.get("resources", {}).get("limits", {}),
            requests=service_spec.get("resources", {}).get("requests", {}),
        ),
        ports=container_ports,
        security_context=container_security_context,
        readiness_probe=readiness_probe,
        liveness_probe=liveness_probe,
        volume_mounts=volume_mounts,
    )

    pod_spec = V1PodSpec(
        containers=[container],
        security_context=pod_security_context,
        volumes=volumes,
        service_account_name=service_account_name,
    )

    labels = {
        "app": service_name,
        "alfresco-component": service_name,
    }

    deployment = V1Deployment(
        api_version="apps/v1",
        kind="Deployment",
        metadata=V1ObjectMeta(
            name=service_spec.get("name", service_name),
            namespace=namespace,
            labels=labels,
            owner_references=owner_references,
        ),
        spec=V1DeploymentSpec(
            replicas=replicas,
            selector=V1LabelSelector(match_labels={"app": service_name}),
            template=V1PodTemplateSpec(
                metadata=V1ObjectMeta(labels=labels),
                spec=pod_spec,
            ),
        ),
    )

    service_ports = [
        V1ServicePort(
            name=f"port-{p}",
            port=int(p),
            target_port=int(p),
        )
        for p in ports_spec
    ]

    service = V1Service(
        api_version="v1",
        kind="Service",
        metadata=V1ObjectMeta(
            name=service_spec.get("name", service_name),
            namespace=namespace,
            labels=labels,
            owner_references=owner_references,
        ),
        spec=V1ServiceSpec(
            selector={"app": service_name},
            ports=service_ports,
            type=service_type,
        ),
    )

    return deployment, service


def build_owner_references(body: dict) -> list[V1OwnerReference]:
    meta = body.get("metadata", {})
    return [
        V1OwnerReference(
            api_version=body.get("apiVersion"),
            kind=body.get("kind"),
            name=meta.get("name"),
            uid=meta.get("uid"),
            controller=True,
            block_owner_deletion=True,
        )
    ]


@kopf.on.create("alfresco.community.com", "v1", "alfrescos")
def create_alfresco(spec, name, namespace, logger, body, **kwargs):
    """
    Handler de creación de recursos Alfresco.
    Crea un Deployment y un Service por cada entrada en spec (alfresco, share, postgres, etc.).
    """
    api_instance = kubernetes.client.CoreV1Api()
    apps_api_instance = kubernetes.client.AppsV1Api()

    owner_references = build_owner_references(body)

    for service_name, service_spec in spec.items():
        deployment, service = create_resource(
            service_name, service_spec, namespace, logger, owner_references
        )

        try:
            apps_api_instance.create_namespaced_deployment(
                namespace=namespace,
                body=deployment,
            )
            logger.info(
                f"Deployment {deployment.metadata.name} created in namespace {namespace}"
            )
        except kubernetes.client.rest.ApiException as e:
            if e.status == 409:
                logger.info(
                    f"Deployment {deployment.metadata.name} already exists in namespace {namespace}"
                )
            else:
                logger.error(
                    f"Error creating deployment {deployment.metadata.name}: {e}"
                )
                raise

        try:
            api_instance.create_namespaced_service(
                namespace=namespace,
                body=service,
            )
            logger.info(
                f"Service {service.metadata.name} created in namespace {namespace}"
            )
        except kubernetes.client.rest.ApiException as e:
            if e.status == 409:
                logger.info(
                    f"Service {service.metadata.name} already exists in namespace {namespace}"
                )
            else:
                logger.error(
                    f"Error creating service {service.metadata.name}: {e}"
                )
                raise


@kopf.on.update("alfresco.community.com", "v1", "alfrescos")
def update_alfresco(spec, name, namespace, logger, body, **kwargs):
    """
    Handler de actualización. Reemplaza el spec del Deployment y actualiza/recambia el Service si cambian los puertos.
    """
    api_instance = kubernetes.client.CoreV1Api()
    apps_api_instance = kubernetes.client.AppsV1Api()

    owner_references = build_owner_references(body)

    for service_name, service_spec in spec.items():
        deployment, service = create_resource(
            service_name, service_spec, namespace, logger, owner_references
        )

        try:
            existing_deployment = apps_api_instance.read_namespaced_deployment(
                name=deployment.metadata.name,
                namespace=namespace,
            )
            existing_deployment.spec = deployment.spec
            existing_deployment.metadata.labels = deployment.metadata.labels
            apps_api_instance.replace_namespaced_deployment(
                name=deployment.metadata.name,
                namespace=namespace,
                body=existing_deployment,
            )
            logger.info(
                f"Deployment {deployment.metadata.name} updated in namespace {namespace}"
            )
        except kubernetes.client.rest.ApiException as e:
            logger.error(
                f"Error updating deployment {deployment.metadata.name}: {e}"
            )

        try:
            existing_service = api_instance.read_namespaced_service(
                name=service.metadata.name,
                namespace=namespace,
            )

            ports_changed = False
            existing_ports = existing_service.spec.ports or []
            new_ports = service.spec.ports or []

            if len(existing_ports) != len(new_ports):
                ports_changed = True
            else:
                for existing_port, new_port in zip(existing_ports, new_ports):
                    if (
                        existing_port.port != new_port.port
                        or int(existing_port.target_port) != int(new_port.target_port)
                    ):
                        ports_changed = True
                        break

            if ports_changed:
                api_instance.delete_namespaced_service(
                    name=service.metadata.name,
                    namespace=namespace,
                )
                logger.info(
                    f"Service {service.metadata.name} deleted from namespace {namespace}"
                )

                api_instance.create_namespaced_service(
                    namespace=namespace,
                    body=service,
                )
                logger.info(
                    f"Service {service.metadata.name} created in namespace {namespace}"
                )
            else:
                existing_service.spec = service.spec
                existing_service.metadata.labels = service.metadata.labels
                api_instance.replace_namespaced_service(
                    name=service.metadata.name,
                    namespace=namespace,
                    body=existing_service,
                )
                logger.info(
                    f"Service {service.metadata.name} updated in namespace {namespace}"
                )
        except kubernetes.client.rest.ApiException as e:
            logger.error(
                f"Error updating service {service.metadata.name}: {e}"
            )


@kopf.on.delete("alfresco.community.com", "v1", "alfrescos")
def delete_alfresco(spec, name, namespace, logger, **kwargs):
    """
    Handler de borrado. Elimina los Deployments y Services creados para la instancia Alfresco.
    """
    api_instance = kubernetes.client.CoreV1Api()
    apps_api_instance = kubernetes.client.AppsV1Api()

    for service_name, service_spec in spec.items():
        resource_name = service_spec.get("name", service_name)

        try:
            apps_api_instance.delete_namespaced_deployment(
                name=resource_name,
                namespace=namespace,
            )
            logger.info(
                f"Deployment {resource_name} deleted from namespace {namespace}"
            )
        except kubernetes.client.rest.ApiException as e:
            if e.status == 404:
                logger.info(
                    f"Deployment {resource_name} not found in namespace {namespace}"
                )
            else:
                logger.error(
                    f"Error deleting deployment {resource_name}: {e}"
                )

        try:
            api_instance.delete_namespaced_service(
                name=resource_name,
                namespace=namespace,
            )
            logger.info(
                f"Service {resource_name} deleted from namespace {namespace}"
            )
        except kubernetes.client.rest.ApiException as e:
            if e.status == 404:
                logger.info(
                    f"Service {resource_name} not found in namespace {namespace}"
                )
            else:
                logger.error(
                    f"Error deleting service {resource_name}: {e}"
                )


if __name__ == "__main__":
    kopf.run(namespaces=["default"])